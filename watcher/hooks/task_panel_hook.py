"""Save root plans and coordinate an owned WezTerm task pane."""

import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import uuid

from task_panel_store import Store, StoreError, binding_key, session_id
from task_panel_layout import desired_height
from task_panel_session import recover_plan
from task_panel_setup import sync_runtime

ATTEMPT_SECONDS = 4.0
CLI_SECONDS = 3.0
COORDINATION_SECONDS = 10.0
TITLE_PREFIX = "cc-hooks-task-panel:"


def project_title(cwd):
    return (Path(cwd).name if isinstance(cwd, str) and cwd else "Codex") or "Codex"


def confirmed_ready(record):
    # Version-one viewers expressed their ready acknowledgment as visible.
    return record.get("ready_nonce") == record["nonce"] or (
        "ready_nonce" not in record and record["state"] == "visible")


class PanelError(ValueError):
    """A terminal operation cannot meet the pane contract."""


class WezTerm:
    def __init__(self, context):
        try:
            importlib.import_module("curses")
        except ImportError as error:
            raise PanelError("Python curses is unavailable; install Python with curses support") from error
        self.socket = context["wezterm_unix_socket"]
        binding_key(self.socket, context["wezterm_pane"])
        info = os.lstat(self.socket)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise PanelError("WezTerm socket must belong to the current user")
        self.executable = shutil.which("wezterm")
        if not self.executable:
            raise PanelError("WezTerm CLI is missing from PATH")
        self.environment = dict(os.environ, WEZTERM_UNIX_SOCKET=self.socket, WEZTERM_PANE=context["wezterm_pane"])

    def _run(self, arguments, timeout):
        try:
            result = subprocess.run([self.executable, "cli", "--no-auto-start", *arguments],
                                    env=self.environment, capture_output=True, text=True,
                                    timeout=timeout, check=True)
        except (OSError, subprocess.SubprocessError, UnicodeError) as error:
            raise PanelError(f"WezTerm CLI failed: {error}") from error
        return result.stdout.strip()

    def list(self, timeout):
        try:
            panes = json.loads(self._run(["list", "--format", "json"], timeout))
            if not isinstance(panes, list):
                raise ValueError("pane list must be an array")
            for pane in panes:
                if (not isinstance(pane, dict) or type(pane.get("pane_id")) is not int
                        or type(pane.get("window_id")) is not int or type(pane.get("tab_id")) is not int
                        or not isinstance(pane.get("title"), str)):
                    raise ValueError("invalid pane list entry")
            return panes
        except (ValueError, TypeError) as error:
            raise PanelError(f"Cannot read WezTerm pane list: {error}") from error

    def split(self, parent, command, timeout, cells=3):
        pane = self._run(["split-pane", "--pane-id", parent, "--bottom", "--cells", str(cells), "--", *command], timeout)
        if not pane.isascii() or not pane.isdigit():
            raise PanelError("WezTerm returned an invalid pane identifier")
        return pane

    def activate(self, parent, timeout):
        self._run(["activate-pane", "--pane-id", parent], timeout)


class Handler:
    def __init__(self, store, terminal_factory=WezTerm, clock=time, session_router=None):
        self.store, self.terminal_factory, self.clock = store, terminal_factory, clock
        self.session_router = session_router
        if self.session_router is None and (store.root.parent / 'task-panel-integration/loader.lua').exists():
            from task_panel_binding import SessionRouter
            self.session_router = SessionRouter(store, clock=clock)

    def handle(self, event):
        if not isinstance(event, dict):
            raise PanelError("Hook input must be an object")
        if event.get("agent_id") is not None:
            return None
        kind = event.get("hook_event_name")
        if kind == "PostToolUse" and event.get("tool_name") == "update_plan":
            tool_input = event.get("tool_input")
            if not isinstance(tool_input, dict) or "plan" not in tool_input:
                raise PanelError("Plan hook input is missing its plan")
            self.store.save_plan(event.get("session_id"), project_title(event.get("cwd")),
                                 tool_input["plan"], updated_at=self.clock.time())
        elif kind in ("SessionStart", "UserPromptSubmit"):
            sync_runtime(self.store.root.parent)
            recover_plan(self.store, event.get("session_id"), event.get("transcript_path"))
        elif kind == "SessionEnd":
            self._end(event)
            if self.session_router is not None:
                self.session_router.end(event.get('session_id'))
        if self.session_router is not None and (kind in ('SessionStart', 'UserPromptSubmit')
                or kind == 'PostToolUse' and event.get('tool_name') == 'update_plan'):
            self.session_router.observe(event)
        return None

    def attach(self, event):
        """Coordinate an explicit terminal attachment without runtime extensions."""
        context = event.get("terminal_context")
        context = context if isinstance(context, dict) else {}
        if isinstance(context.get("frontend"), str) and context["frontend"] not in ("", "tui"):
            return None
        key = None
        attempt = {"nonce": None}
        deadline = self.clock.monotonic() + COORDINATION_SECONDS
        try:
            if not isinstance(context.get("frontend"), str) or not context["frontend"]:
                raise PanelError("terminal_context.frontend is missing from the observer input")
            if context.get("frontend") != "tui" or context.get("terminal_program") != "WezTerm":
                return None
            for field in ("attachment_id", "wezterm_pane", "wezterm_unix_socket"):
                if not isinstance(context.get(field), str) or not context[field]:
                    raise PanelError(f"terminal_context.{field} is missing from the observer input")
            identifier = session_id(event.get("session_id"))
            attachment = session_id(context.get("attachment_id"))
            key = binding_key(context.get("wezterm_unix_socket"), context.get("wezterm_pane"))
            with self.store.binding_transaction(key, deadline) as transaction:
                record = transaction.read()
                if record is None:
                    record = {"version": 1, "socket": context["wezterm_unix_socket"],
                              "parent_pane": context["wezterm_pane"], "panel_pane": None,
                              "session_id": identifier, "attachment_id": attachment,
                              "nonce": uuid.uuid4().hex, "state": "absent",
                              "ready_nonce": None,
                              "starting_created_at": None, "starting_deadline": None}
                elif record["state"] == "closed" and record["attachment_id"] == attachment:
                    return None
                elif record["state"] == "closed":
                    record.update(state="absent", panel_pane=None, ready_nonce=None,
                                  starting_created_at=None, starting_deadline=None)
                elif record["state"] == "ended":
                    if confirmed_ready(record) and record["panel_pane"]:
                        record["state"] = "visible"
                    elif record["starting_deadline"] is not None:
                        record["state"] = "starting"
                    else:
                        record["state"] = "absent"
                if confirmed_ready(record):
                    record["ready_nonce"] = record["nonce"]
                record.update(session_id=identifier, attachment_id=attachment,
                              project_title=project_title(event.get("cwd")))
                record.pop("error_message", None)
                transaction.write(record)
                attempt["nonce"] = record["nonce"]
            terminal = self.terminal_factory(context)
            self._coordinate(key, attachment, terminal, deadline, attempt)
            return None
        except (StoreError, PanelError, OSError) as error:
            message = f"任务面板暂不可用：{error}。请检查 WezTerm 后重新打开或恢复 Codex。"
            if key is not None:
                try:
                    with self.store.binding_transaction(key, deadline) as transaction:
                        record = transaction.read()
                        if (record and record["attachment_id"] == context.get("attachment_id")
                                and record["nonce"] == attempt["nonce"] and record["state"] != "closed"):
                            record.update(state="error", error_message=message)
                            transaction.write(record)
                except StoreError:
                    pass
            return message

    def _coordinate(self, key, attachment, terminal, deadline, attempt):
        cli_remaining = CLI_SECONDS

        def call(method, *arguments, **options):
            nonlocal cli_remaining
            before = self.clock.monotonic()
            remaining = min(cli_remaining, deadline - before)
            if remaining <= 0:
                raise PanelError("WezTerm 启动协调超时")
            result = method(*arguments, timeout=remaining, **options)
            cli_remaining -= max(0, self.clock.monotonic() - before)
            return result

        while self.clock.monotonic() < deadline:
            panes = call(terminal.list)
            command = None
            with self.store.binding_transaction(key, deadline) as transaction:
                record = transaction.read()
                if record is None or record["attachment_id"] != attachment or record["state"] == "closed":
                    return
                attempt["nonce"] = record["nonce"]
                parent = next((pane for pane in panes if str(pane["pane_id"]) == record["parent_pane"]), None)
                if parent is None:
                    transaction.delete()
                    return
                owned = next((pane for pane in panes
                              if pane["title"] == TITLE_PREFIX + record["nonce"]
                              and pane["window_id"] == parent["window_id"] and pane["tab_id"] == parent["tab_id"]), None)
                ready = confirmed_ready(record)
                if owned is not None and ready and record["panel_pane"] == str(owned["pane_id"]):
                    if record["state"] != "ended":
                        record["state"] = "visible"
                    record["ready_nonce"] = record["nonce"]
                    record.pop("error_message", None)
                    transaction.write(record)
                    call(terminal.activate, record["parent_pane"])
                    return
                now = self.clock.time()
                attempt_deadline = record["starting_deadline"]
                pending = attempt_deadline is not None and now < attempt_deadline <= now + ATTEMPT_SECONDS
                if not pending and (owned is None or not ready):
                    cli_remaining = CLI_SECONDS
                    nonce = uuid.uuid4().hex
                    record.update(nonce=nonce, panel_pane=None, state="starting", ready_nonce=None,
                                  starting_created_at=now, starting_deadline=now + ATTEMPT_SECONDS)
                    attempt["nonce"] = nonce
                    transaction.write(record)
                    command = [sys.executable, str(Path(__file__).with_name("task_panel.py")),
                               "--data-dir", str(self.store.root), "--binding", key, "--nonce", nonce,
                               "--socket", record["socket"], "--parent", record["parent_pane"]]
            if command is not None:
                try:
                    plan = self.store.read_plan(record["session_id"])
                except StoreError:
                    plan = None
                pane_id = call(terminal.split, record["parent_pane"], command, cells=desired_height(plan))
                with self.store.binding_transaction(key, deadline) as transaction:
                    latest = transaction.read()
                    if latest and latest["nonce"] == record["nonce"] and latest["state"] != "closed":
                        latest["panel_pane"] = pane_id
                        transaction.write(latest)
            remaining = deadline - self.clock.monotonic()
            if remaining > 0:
                self.clock.sleep(min(0.05, remaining))
        raise PanelError("WezTerm 启动协调超时")

    def _end(self, event):
        identifier = session_id(event.get("session_id"))
        deadline = self.clock.monotonic() + 0.5
        for key in self.store.binding_keys():
            snapshot = self.store.read_binding(key)
            if snapshot is None or snapshot["session_id"] != identifier:
                continue
            with self.store.binding_transaction(key, deadline) as transaction:
                record = transaction.read()
                if record and record["session_id"] == identifier and record["state"] not in ("closed", "absent"):
                    record["state"] = "ended"
                    transaction.write(record)


def main():
    event = None
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise PanelError("Hook input must be an object")
        if event.get("agent_id") is not None:
            return 0
        data = os.environ.get("PLUGIN_DATA")
        if not data or not os.path.isabs(data):
            raise PanelError("PLUGIN_DATA 必须是插件可写目录的完整路径，请重新安装插件后恢复会话")
        message = Handler(Store(Path(data) / "task-panel")).handle(event)
        if message:
            print(json.dumps({"systemMessage": message}, ensure_ascii=False))
        return 0
    except (StoreError, PanelError, OSError, ValueError) as error:
        message = f"任务面板处理失败：{error}。请检查插件数据目录后重新打开或恢复 Codex。"
        if isinstance(event, dict) and event.get("hook_event_name") == "PostToolUse":
            print(message, file=sys.stderr)
            return 1
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
