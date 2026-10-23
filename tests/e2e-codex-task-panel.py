#!/usr/bin/env python3
"""Run an isolated, account-free acceptance session in the current WezTerm pane."""

import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import threading
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "watcher/hooks"))
from task_panel_store import binding_key

FEATURES = {"effective_tool_context", "interactive_terminal_context",
            "session_start_on_attach", "committed_plan_callbacks"}
BASE_PLAN = [{"step": "核对真实计划同步", "status": "in_progress"},
             {"step": "验证任务状态更新", "status": "pending"},
             {"step": "验证会话恢复", "status": "pending"}]


def request_action(body):
    """Use the latest user message; historical tool results belong to earlier turns."""
    items = body.get("input", [])
    if not isinstance(items, list):
        raise ValueError("Expected a Responses input array")
    start = next((i for i in range(len(items) - 1, -1, -1)
                  if isinstance(items[i], dict) and items[i].get("role") == "user"), None)
    if start is None:
        raise ValueError("Expected a user message")
    content = items[start].get("content", [])
    text = content if isinstance(content, str) else "\n".join(
        part.get("text", "") for part in content if isinstance(part, dict))
    commands = {"开始验收": "initial", "推进任务": "advance", "清空计划": "clear",
                "长列表": "long", "恢复列表": "initial"}
    action = commands.get(text.strip())
    if action is None:
        return "help", False
    completed = any(isinstance(item, dict) and item.get("type") == "function_call_output"
                    and item.get("call_id", "").startswith("cc-hooks-panel-")
                    for item in items[start + 1:])
    return action, completed


def plan_for(action):
    if action == "clear":
        return []
    if action == "long":
        return [{"step": f"中文滚动任务 {i:02d}",
                 "status": "in_progress" if i == 1 else "pending"} for i in range(1, 26)]
    plan = [dict(item) for item in BASE_PLAN]
    if action == "advance":
        plan[0]["status"], plan[1]["status"] = "completed", "in_progress"
    return plan


def response_events(action, completed):
    identifier = "cc-hooks-panel-" + uuid.uuid4().hex
    events = [{"type": "response.created", "response": {"id": identifier}}]
    if action == "help" or completed:
        text = ("请输入：开始验收、推进任务、清空计划、长列表或恢复列表。"
                if action == "help" else "计划工具已返回。请核对下方任务面板；验收记录会保存在独立配置目录。")
        item = {"type": "message", "role": "assistant", "id": identifier,
                "content": [{"type": "output_text", "text": text}]}
    else:
        item = {"type": "function_call", "call_id": identifier, "name": "update_plan",
                "arguments": json.dumps({"plan": plan_for(action)}, ensure_ascii=False)}
    events.append({"type": "response.output_item.done", "item": item})
    events.append({"type": "response.completed", "response": {"id": identifier,
                   "usage": {"input_tokens": 0, "input_tokens_details": None,
                             "output_tokens": 0, "output_tokens_details": None, "total_tokens": 0}}})
    return "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events).encode()


class StdioServer:
    def __init__(self, executable, environment, error_path):
        self.errors = error_path.open("w")
        self.process = subprocess.Popen([str(executable), "app-server", "--listen", "stdio://"],
                                        env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.errors, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = bytearray()

    def request(self, method, params):
        identifier = uuid.uuid4().hex
        self.process.stdin.write((json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            while b"\n" in self.pending:
                line, _, rest = self.pending.partition(b"\n")
                self.pending[:] = rest
                message = json.loads(line)
                if message.get("id") == identifier:
                    if "error" in message:
                        raise RuntimeError(message["error"])
                    return message["result"]
            if not self.selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("App Server closed stdout")
            self.pending.extend(chunk)
        raise TimeoutError(f"App Server timed out: {method}")

    def close(self):
        self.selector.close()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdout.close()
        self.errors.close()


def list_hooks(executable, environment, project, capabilities, log):
    server = StdioServer(executable, environment, log)
    try:
        result = server.request("initialize", {
            "clientInfo": {"name": "codex_app_server_daemon", "version": capabilities["version"]},
            "capabilities": {"experimentalApi": True},
            "runtimeHooks": {"runtimeHooksVersion": 1, "version": capabilities["version"],
                             "features": capabilities["features"]}})
        if set(result["runtimeHooks"]["features"]) != FEATURES:
            raise RuntimeError("App Server hook capabilities do not match")
        server.process.stdin.write(b'{"method":"initialized"}\n')
        server.process.stdin.flush()
        response = server.request("hooks/list", {"cwds": [str(project)]})
        hooks = [hook for entry in response["data"] for hook in entry["hooks"]]
        if len(hooks) != 6 or any(hook["pluginId"] != "watcher@orime" for hook in hooks):
            raise RuntimeError("Expected the six installed watcher hooks")
        return hooks
    finally:
        server.close()


def prepare(executable, home):
    marker = home / "panel-e2e-state.json"
    if marker.exists():
        state = json.loads(marker.read_text())
        if state["executable"] != str(executable) or state["marketplace"] != str(ROOT):
            raise ValueError("Existing acceptance home belongs to another runtime or checkout")
        return state
    if home.exists():
        raise ValueError("A new, empty acceptance home path is required")
    home.mkdir(parents=True, mode=0o700)
    project = home / "验收项目"
    project.mkdir()
    config = home / "config.toml"
    config.write_text('model = "mock-model"\nmodel_provider = "panel_e2e"\n'
                      'check_for_update_on_startup = false\napproval_policy = "never"\n'
                      '[model_providers.panel_e2e]\nname = "Offline panel acceptance"\n'
                      'base_url = "http://127.0.0.1:9/v1"\nwire_api = "responses"\n'
                      'requires_openai_auth = false\nsupports_websockets = false\n'
                      f'[projects.{json.dumps(str(project), ensure_ascii=False)}]\ntrust_level = "trusted"\n')
    environment = dict(os.environ, CODEX_HOME=str(home))
    commands = [["debug", "hook-capabilities", "--json"],
                ["plugin", "marketplace", "add", str(ROOT), "--json"],
                ["plugin", "add", "watcher@orime", "--json"]]
    capabilities = None
    for index, command in enumerate(commands):
        result = subprocess.run([str(executable), *command], env=environment, cwd=project,
                                capture_output=True, text=True, timeout=60)
        (home / f"prepare-{index}.stdout").write_text(result.stdout)
        (home / f"prepare-{index}.stderr").write_text(result.stderr)
        result.check_returncode()
        if index == 0:
            capabilities = json.loads(result.stdout)["client"]
            if capabilities["runtime_hooks_version"] != 1 or set(capabilities["features"]) != FEATURES:
                raise RuntimeError("The companion Codex build with four hook capabilities is required")
    hooks = list_hooks(executable, environment, project, capabilities, home / "hooks-before.stderr")
    with config.open("a") as stream:
        for hook in hooks:
            stream.write(f'\n[hooks.state.{json.dumps(hook["key"])}]\n'
                         f'trusted_hash = {json.dumps(hook["currentHash"])}\n')
    hooks = list_hooks(executable, environment, project, capabilities, home / "hooks-after.stderr")
    if any(hook["trustStatus"] != "trusted" for hook in hooks):
        raise RuntimeError("Installed watcher hooks are not trusted")
    (home / "installed-hooks.json").write_text(json.dumps(hooks, indent=2) + "\n")
    state = {"executable": str(executable), "marketplace": str(ROOT), "project": str(project),
             "client": capabilities, "prepared_at": time.time()}
    marker.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return state


class Acceptance:
    def __init__(self, home):
        self.home = home
        self.lock = threading.Lock()
        self.data = home / "plugins/data/watcher-orime/task-panel"
        self.wezterm = shutil.which("wezterm")
        self.parent = os.environ.get("WEZTERM_PANE")
        self.socket = os.environ.get("WEZTERM_UNIX_SOCKET")

    def record(self, entry):
        entry["at"] = time.time()
        with self.lock, (self.home / "panel-e2e-results.jsonl").open("a") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def binding(self):
        if not self.parent or not self.socket:
            raise RuntimeError("Run this acceptance session directly in WezTerm")
        key = binding_key(self.socket, self.parent)
        return json.loads((self.data / "bindings" / (key + ".json")).read_text())

    def inspect(self, action, resume_session=None):
        deadline = time.monotonic() + 4
        last_error = None
        while time.monotonic() < deadline:
            try:
                binding = self.binding()
                if binding["state"] != "visible" or binding["panel_pane"] is None:
                    raise ValueError("Task pane is not visible")
                if resume_session and binding["session_id"] != resume_session:
                    raise ValueError("Resumed pane is bound to a different session")
                path = self.data / "plans" / (binding["session_id"] + ".json")
                snapshot = json.loads(path.read_text()) if path.exists() else None
                startup = action in ("startup", "resume")
                expected = (snapshot["plan"] if snapshot else []) if startup else plan_for(action)
                if not startup and (snapshot is None or snapshot["plan"] != expected):
                    raise ValueError("Saved plan does not match the model tool call")
                result = subprocess.run([self.wezterm, "cli", "--no-auto-start", "get-text",
                                         "--pane-id", str(binding["panel_pane"])],
                                        capture_output=True, text=True, timeout=2, check=True)
                done = sum(item["status"] == "completed" for item in expected)
                if f"任务 {done}/{len(expected)}" not in result.stdout:
                    raise ValueError("Task pane count has not refreshed")
                if expected and expected[0]["step"] not in result.stdout:
                    raise ValueError("Task pane text has not refreshed")
                if not expected and snapshot is not None and "等待首次计划更新" in result.stdout:
                    raise ValueError("Cleared plan must retain its saved snapshot status")
                if snapshot is None and "等待首次计划更新" not in result.stdout:
                    raise ValueError("Empty session must display the initial waiting state")
                return {"action": action, "result": "passed", "binding": binding,
                        "snapshot": snapshot, "pane_text": result.stdout}
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                last_error = str(error)
                time.sleep(0.1)
        raise RuntimeError(f"Plan-to-pane acceptance failed: {last_error}")

    def observe_startup(self, stopped, previous_attachment, resume_session):
        deadline = time.monotonic() + 18
        while not stopped.is_set() and time.monotonic() < deadline:
            try:
                binding = self.binding()
                if binding["state"] == "visible" and binding["attachment_id"] != previous_attachment:
                    action = "resume" if resume_session else "startup"
                    self.record(self.inspect(action, resume_session))
                    return
            except (OSError, ValueError):
                pass
            except RuntimeError as error:
                self.record({"result": "failed", "error": str(error)})
                return
            stopped.wait(0.1)
        if not stopped.is_set():
            self.record({"result": "failed", "error": "No new visible attachment within 18 seconds"})


def summarize(path, started, resume):
    entries = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    current = [entry for entry in entries if entry["at"] >= started]
    passed = {entry.get("action") for entry in current if entry.get("result") == "passed"}
    required = {"resume"} if resume else {"startup", "initial", "advance", "clear", "long"}
    missing = sorted(required - passed)
    failed = [entry for entry in current if entry.get("result") == "failed"]
    return {"result": "passed" if not missing and not failed else "incomplete",
            "verified_actions": sorted(passed), "missing_actions": missing, "failures": failed}


def handler_for(acceptance):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            try:
                if self.path != "/v1/responses":
                    raise ValueError("Unexpected request path")
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 8 * 1024 * 1024:
                    raise ValueError("Invalid fixture request size")
                raw = self.rfile.read(size)
                encoding = self.headers.get("Content-Encoding", "identity")
                if encoding == "gzip":
                    raw = gzip.decompress(raw)
                elif encoding != "identity":
                    raise ValueError(f"Unsupported fixture encoding: {encoding}")
                action, completed = request_action(json.loads(raw))
                acceptance.record({"event": "model_request", "action": action, "tool_output_received": completed})
                if completed and action != "help":
                    acceptance.record(acceptance.inspect(action))
                payload = response_events(action, completed)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
            except Exception as error:
                acceptance.record({"result": "failed", "error": str(error)})
                payload = json.dumps({"error": {"message": str(error)}}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume-last", action="store_true")
    args = parser.parse_args(argv)
    if not args.codex.is_absolute() or not args.home.is_absolute():
        parser.error("--codex and --home require absolute paths")
    state = prepare(args.codex.resolve(strict=True), args.home)
    print(f"验收配置：{args.home}\n记录文件：{args.home / 'panel-e2e-results.jsonl'}", flush=True)
    if args.prepare_only:
        print("插件安装与六个 hook 的信任检查通过。", flush=True)
        return 0
    acceptance = Acceptance(args.home)
    if not acceptance.wezterm or not acceptance.parent or not acceptance.socket:
        raise RuntimeError("请在 WezTerm 终端内运行本脚本。")
    if args.resume_last and not state.get("last_session_id"):
        raise RuntimeError("独立验收配置尚无已记录会话，请先完成首次验收并用 /exit 退出。")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(acceptance))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = args.home / "config.toml"
    import re
    text, replacements = re.subn(r'(?m)^base_url = "http://127\.0\.0\.1:[0-9]+/v1"$',
                                f'base_url = "http://127.0.0.1:{server.server_port}/v1"', config.read_text())
    if replacements != 1:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        raise RuntimeError("Expected one isolated fixture provider URL")
    config.write_text(text)
    print("依次输入：开始验收、推进任务、清空计划、长列表、恢复列表。\n"
          "长列表可在下方用方向键及 PageUp/PageDown 检查滚动。\n"
          "使用 /exit 退出；再次加 --resume-last 运行本命令，检查保存计划恢复。\n"
          "本次验收最长运行 15 分钟。", flush=True)
    command = [state["executable"]]
    if args.resume_last:
        command.extend(["resume", "--last"])
    command.extend(["--cd", state["project"]])
    process = None
    started = time.time()
    stopped = threading.Event()
    observer = threading.Thread(target=acceptance.observe_startup, args=(
        stopped, state.get("last_attachment_id"), state.get("last_session_id") if args.resume_last else None),
        daemon=True)
    exit_code = 1
    try:
        process = subprocess.Popen(command, env=dict(os.environ, CODEX_HOME=str(args.home)))
        acceptance.record({"event": "tui_started", "pid": process.pid, "resume": args.resume_last})
        observer.start()
        try:
            exit_code = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            acceptance.record({"result": "failed", "error": "Acceptance session exceeded 15 minutes"})
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            exit_code = 1
    finally:
        stopped.set()
        if observer.ident is not None:
            observer.join(timeout=7)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        try:
            binding = acceptance.binding()
            state.update(last_session_id=binding["session_id"], last_attachment_id=binding["attachment_id"])
            (args.home / "panel-e2e-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        except (OSError, ValueError) as error:
            acceptance.record({"result": "failed", "error": str(error)})
        print(f"验收记录：{args.home / 'panel-e2e-results.jsonl'}", flush=True)
    summary = summarize(args.home / "panel-e2e-results.jsonl", started, args.resume_last)
    (args.home / "panel-e2e-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("本轮自动核对通过。" if summary["result"] == "passed" else "本轮验收尚未完成，请查看记录中的缺项或错误。", flush=True)
    return exit_code or (0 if summary["result"] == "passed" else 1)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"验收无法继续：{error}", file=sys.stderr)
        raise SystemExit(1)
