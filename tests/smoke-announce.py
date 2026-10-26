#!/usr/bin/env python3
"""Smoke test for announce-intent.sh on both platforms.

Run: python3 tests/smoke-announce.py

Claude Code calls the hook with no argument; Codex calls it with `codex`
(watcher/hooks/codex-hooks.json). Claude Code emits the current shared spec
verbatim. The Codex output is the same spec with Codex tool names, is empty
for spawned subagents, and carries the previous Stop hook's status text once.
"""
import json
import os
import re
import subprocess
import tempfile
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOK = os.path.join(ROOT, "watcher", "hooks", "announce-intent.sh")
HANDOFF_HEADER = "上一轮结束时 Stop hook 的输出："

failures = []
checks = 0


def check(name, ok, detail=""):
    global checks
    checks += 1
    if not ok:
        failures.append(f"{name}: {detail}")


def run(args, stdin, plugin_data):
    env = {**os.environ, "PLUGIN_DATA": plugin_data}
    return subprocess.run(["bash", HOOK, *args], input=json.dumps(stdin), capture_output=True, text=True, env=env)


def write_pending(plugin_data, session, text, age_days=0):
    d = os.path.join(plugin_data, "pending-stop")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, session + ".txt")
    with open(path, "w") as f:
        f.write(text)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


with open(HOOK) as source:
    shared_spec = re.search(r"cat <<'EOF'\n(.*?)\nEOF", source.read(), re.S).group(1) + "\n"
root_stdin = {"session_id": "sess-1", "prompt": "x", "hook_event_name": "UserPromptSubmit"}

# A. Claude Code emits the current shared spec verbatim and preserves handoff files.
data = tempfile.mkdtemp()
pending = write_pending(data, "sess-1", "STATUS_FOR_CODEX")
cc = run([], root_stdin, data)
check("A1 Claude Code emits the current shared spec verbatim", cc.stdout == shared_spec,
      f"len spec={len(shared_spec)} now={len(cc.stdout)}")
check("A2 Claude Code leaves the handoff file alone", os.path.exists(pending))

# B. Codex output: same spec, Codex names, no Claude Code names.
data = tempfile.mkdtemp()
cx = run(["codex"], root_stdin, data).stdout
for banned in ("workflow", "TaskCreate", "TaskUpdate", "WebSearch", "AskUserQuestion", "CLAUDE.md", "/watcher:"):
    check(f"B1 Codex output has no {banned!r}", banned not in cx)
for wanted in ("spawn_agent", "update_plan", "联网搜索", "request_user_input", "AGENTS.md",
               "`watcher:playbook` skill", "`watcher:visual-adversary` skill"):
    check(f"B2 Codex output has {wanted!r}", wanted in cx)
check("B3 Codex output keeps every spec line", cx.count("\n") == shared_spec.count("\n"),
      f"lines spec={shared_spec.count(chr(10))} codex={cx.count(chr(10))}")
check("B4 Codex output without a handoff carries no handoff header", HANDOFF_HEADER not in cx)
check("B5 Codex asks its current user after normal investigation remains inconclusive",
      "正常查证后仍无法确定的，询问当前用户并按答复处理" in cx)
check("B6 Claude Code retains its shared rule", "正常查证后仍无法确定的" not in cc.stdout)

# C. A spawned subagent gets nothing and does not touch the root's handoff file (same session_id).
data = tempfile.mkdtemp()
pending = write_pending(data, "sess-1", "STATUS_FOR_ROOT")
sub = run(["codex"], {**root_stdin, "agent_id": "child-1", "agent_type": "default"}, data)
check("C1 subagent prompt prints nothing", sub.stdout == "", f"stdout={sub.stdout[:80]!r}")
check("C2 subagent prompt leaves the handoff file", os.path.exists(pending))

# D. The next root prompt appends the whole status text after the spec and deletes the file.
status = "📊 现在 UTC 2026-10-22 08:00:00\n\n🧹 清进程：…\n\n🔕 audit 已关，已连续 3 轮未 audit"
pending = write_pending(data, "sess-1", status)
root = run(["codex"], root_stdin, data).stdout
check("D1 root prompt starts with the spec", root.startswith(cx), "spec body changed")
check("D2 root prompt ends with header + full status", root.endswith(HANDOFF_HEADER + "\n" + status + "\n"),
      f"tail={root[-120:]!r}")
check("D3 handoff file is deleted after use", not os.path.exists(pending))
again = run(["codex"], root_stdin, data).stdout
check("D4 the status is delivered once", HANDOFF_HEADER not in again)

# E. Files older than 7 days are removed; fresh files of other sessions stay.
data = tempfile.mkdtemp()
old = write_pending(data, "sess-old", "OLD", age_days=8)
fresh = write_pending(data, "sess-other", "FRESH")
run(["codex"], root_stdin, data)
check("E1 a handoff file older than 7 days is removed", not os.path.exists(old))
check("E2 a fresh handoff file of another session stays", os.path.exists(fresh))

# F. Without PLUGIN_DATA the spec still goes out.
p = run(["codex"], root_stdin, "")
check("F1 empty PLUGIN_DATA still prints the spec", p.returncode == 0 and p.stdout == cx, f"rc={p.returncode}")

# G. Both hosts receive the agreed task-summary contract before work starts.
for platform, output in (("Claude Code", cc.stdout), ("Codex", cx)):
    section = re.search(r"2\.4任务收尾\n(.*?)\n3\.通用工作规程", output, re.S)
    check(f"G1 {platform} receives the task-summary section", section is not None)
    summary = section.group(1) if section else ""
    for field in ("当前任务≤20字", "当前任务的阶段≤20字", "工作纪律自评≤30字"):
        check(f"G2 {platform} receives {field}", field in summary)
    check(f"G3 {platform} limits summaries to concrete work",
          "本轮推进设计、实现、审查、测试、文档同步等工作时" in summary and "普通问答和讨论直接回答" in summary)
    check(f"G4 {platform} receives evidence-based discipline self-assessment",
          "按本轮事实" in summary and "具体偏离及正确做法" in summary)
    check(f"G5 {platform} keeps the pre-send self-check",
          "结束前自检格式和字数" in summary)
    check(f"G7 {platform} receives the character-counting convention",
          "标点、数字和英文字母各计1字，字段名不计" in summary)

# H. An unavailable temporary directory must fail the size gate.
with tempfile.TemporaryDirectory() as size_fixture:
    unavailable = os.path.join(size_fixture, "missing")
    size = subprocess.run(["bash", os.path.join(ROOT, "tests", "check-size.sh")],
                          capture_output=True, text=True, timeout=30,
                          env={**os.environ, "TMPDIR": unavailable, "PLUGIN_DATA": ""})
    check("H1 size gate fails when temporary output cannot be created",
          size.returncode != 0 and "✅" not in size.stdout,
          f"rc={size.returncode} output={size.stdout!r} error={size.stderr!r}")

if failures:
    print(f"❌ {len(failures)}/{checks} checks failed:\n")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print(f"✅ all {checks} checks passed")
