#!/usr/bin/env python3
"""Stop hook (suggest-watcher.sh) 的 smoke 测试 —— 构造真实 stdin 跑 hook、断言输出协议。

跑法：python3 tests/smoke-stop-hook.py          # Claude Code branch
      python3 tests/smoke-stop-hook.py codex    # Codex branch (watcher/hooks/codex-hooks.json passes `codex`)
改 suggest-watcher.sh 后、提交前必跑：不全绿不许提交。

两条输出通路（CC 2.1.220 二进制实证）：
  - {"decision":"block","reason":X}      → Claude 看得到 X、CC **启动下一轮**（用于 ON 分支叫 Claude 跑 audit）
  - {"continue":false,"stopReason":X}    → CC **直接停、不启动下一轮**；用户终端当场显示
                                            "Operation stopped by hook: X"；Claude 当轮读不到 X，
                                            下次用户发言时它以 "Stop hook stopped continuation: X" 进上下文
                                            （用于只报状态的 OFF / 没配分支）
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watcher", "hooks", "suggest-watcher.sh")
PLATFORM = sys.argv[1] if len(sys.argv) > 1 else ""
CODEX = PLATFORM == "codex"
ARGS = [PLATFORM] if PLATFORM else []
# One writable plugin data dir for the whole suite; Codex hands status text over through it.
PLUGIN_DATA = tempfile.mkdtemp()
PENDING_DIR = os.path.join(PLUGIN_DATA, "pending-stop")
# What the ON reason says to start the audit on each platform.
AUDIT_MARK = "`watcher:watcher` skill" if CODEX else "调用 Skill"


def new_proj(with_watcher=True):
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "proj")
    os.makedirs(proj)
    if with_watcher:
        os.makedirs(os.path.join(proj, ".watcher"))
    tr = os.path.join(tmp, "t.jsonl")
    with open(tr, "w") as f:
        f.write(json.dumps({"type": "assistant", "message": {"usage": {
            "input_tokens": 70000, "cache_read_input_tokens": 5000,
            "cache_creation_input_tokens": 0}}}) + "\n")
    return proj, tr


def sp(proj):
    return os.path.join(proj, ".watcher", "audit-state.json")


def read_state(proj):
    p = sp(proj)
    return json.load(open(p)) if os.path.exists(p) else None


def write_state(proj, obj):
    with open(sp(proj), "w") as f:
        json.dump(obj, f)


def run(proj, tr, active=False, last="done", bg=False, env=None):
    stdin = {"session_id": "s", "stop_hook_active": active, "cwd": proj,
             "transcript_path": tr}
    if last is not None:
        stdin["last_assistant_message"] = last
    if bg:
        stdin["background_tasks"] = [{"type": "subagent", "status": "running"}]
    return run_stdin(stdin, env)


def run_stdin(stdin, env=None):
    return subprocess.run(["bash", HOOK, *ARGS], input=json.dumps(stdin),
                          capture_output=True, text=True,
                          env={**os.environ, "PLUGIN_DATA": PLUGIN_DATA, **(env or {})})


def out_json(p):
    """hook 的 stdout 解析成 dict；空输出返回 None。"""
    s = p.stdout.strip()
    return json.loads(s) if s else None


def audit_reason(p):
    """ON 分支（block 通路）的 reason；不是 block 通路就返回 None。"""
    o = out_json(p)
    return o.get("reason") if o and o.get("decision") == "block" else None


def is_status_exit(o):
    """Status-only exit: Claude Code stops with continue:false, Codex shows a systemMessage and goes on."""
    if not o or "decision" in o:
        return False
    if CODEX:
        return "systemMessage" in o and "continue" not in o and "stopReason" not in o
    return o.get("continue") is False


def status_text(p):
    """只报状态分支的文字（CC 的 stopReason / Codex 的 systemMessage）；不是该通路就返回 None。"""
    o = out_json(p)
    if not is_status_exit(o):
        return None
    return o.get("systemMessage") if CODEX else o.get("stopReason")


# A. 没配 .watcher/（临时夹/新项目/cwd 路径错）→ continue:false 显状态+没配提示、不建文件、无 audit 字样
proj, tr = new_proj(with_watcher=False)
p = run(proj, tr)
o = out_json(p)
assert o is not None, f"A: 应有输出，实际空={p.stdout!r}"
assert is_status_exit(o), f"A: 应走只报状态的通路，实际={o!r}"
s = status_text(p)
assert "没有 .watcher" in s, f"A: 应提示没配 .watcher，stopReason={s!r}"
assert AUDIT_MARK not in s, f"A: 没配分支绝不能含任何让 CC audit 的字样！stopReason={s!r}"
assert ("上下文已用" in s) or ("UTC" in s), f"A: 应含时间/token 状态，stopReason={s!r}"
assert read_state(proj) is None, "A: 不该建 state 文件（只显示、不建）"
print("A OK — 没配 .watcher/ → continue:false 显时间+token+没配提示、无 audit 字样、不建文件")

# B. 迁移 纯 .watcher（orime 升级）→ 默认 enable=true → audit（block 通路）
proj, tr = new_proj(True)
p = run(proj, tr)
r = audit_reason(p)
assert r and AUDIT_MARK in r, f"B: 应走 block 通路叫 Claude 跑 audit，实际={out_json(p)!r}"
assert read_state(proj) == {"enable-audit": True, "unaudited-rounds": 0}, f"B: 迁移应建默认 true，实际={read_state(proj)}"
print("B OK — 纯 .watcher/ 迁移建默认 enable=true → block 通路 audit")

# C. 迁移 .stop-disabled + .skip-count=5 → enable=false, rounds 保留 → off（continue:false 通路）
proj, tr = new_proj(True)
open(os.path.join(proj, ".watcher", ".stop-disabled"), "w").close()
with open(os.path.join(proj, ".watcher", ".skip-count"), "w") as f:
    f.write("5\n")
p = run(proj, tr)
s = status_text(p)
assert s and "audit 已关" in s, f"C: 应走 continue:false 显 off 状态，实际={out_json(p)!r}"
assert "已连续 6 轮" in s, f"C: 应 5+1=6 轮，实际 stopReason={s!r}"
st = read_state(proj)
assert st["enable-audit"] is False and st["unaudited-rounds"] == 6, f"C: state 错={st}"
assert not os.path.exists(os.path.join(proj, ".watcher", ".stop-disabled")), "C: 旧 .stop-disabled 应删"
assert not os.path.exists(os.path.join(proj, ".watcher", ".skip-count")), "C: 旧 .skip-count 应删"
print("C OK — 旧 off+计数 迁移成 enable=false+rounds、删旧文件、走 continue:false")

# D. enable=true 有积压 3 → audit 带放宽提示；hook 不清零（清零归 skill 进入时做）→ 文件仍是 3
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 3})
p = run(proj, tr)
r = audit_reason(p)
assert r and "已累计 3 轮" in r and AUDIT_MARK in r, f"D: 应带放宽提示，reason={r!r}"
assert read_state(proj)["unaudited-rounds"] == 3, "D: hook 不再清零（清零挪给 skill 进入时做），文件应仍是 3"
print("D OK — enable=true 有积压 → reason 带快照 3；hook 不清零、文件仍 3（清零归 skill）")

# E. enable=false off → continue:false 显状态 + bump
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": False, "unaudited-rounds": 2})
p = run(proj, tr)
o = out_json(p)
assert is_status_exit(o), f"E: OFF 应走只报状态的通路，实际={o!r}"
s = status_text(p)
assert s and "audit 已关" in s and "已连续 3 轮" in s, f"E: stopReason={s!r}"
assert read_state(proj)["unaudited-rounds"] == 3, "E: off 应 bump 2→3"
print("E OK — enable=false → continue:false 显状态 + bump")

# F. bg-pending → skip + bump
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
p = run(proj, tr, bg=True)
assert p.stdout.strip() == "", "F: 应 skip（空输出）"
assert read_state(proj)["unaudited-rounds"] == 1, "F: 应 bump"
print("F OK — bg-pending skip + bump")

# G. no-last-msg → skip + bump
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
p = run(proj, tr, last=None)
assert p.stdout.strip() == "", "G: 应 skip（空输出）"
assert read_state(proj)["unaudited-rounds"] == 1, "G: 应 bump"
print("G OK — no-last-msg skip + bump")

# H. active → skip, 不 bump（防递归，唯一保险）
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 4})
p = run(proj, tr, active=True)
assert p.stdout.strip() == "", "H: 应 skip（空输出）"
assert read_state(proj)["unaudited-rounds"] == 4, "H: active 不该 bump"
print("H OK — active 防递归 skip、不 bump")

# I. 损坏 JSON → 兜底 enable=true → audit
proj, tr = new_proj(True)
with open(sp(proj), "w") as f:
    f.write("{ broken json ")
p = run(proj, tr)
r = audit_reason(p)
assert r and AUDIT_MARK in r, f"I: 损坏应兜底 audit，实际={out_json(p)!r}"
print("I OK — 损坏 JSON → 兜底 enable=true → audit")

# J. 并发（固化 HIGH bug）：50 并发 off 轮 → state 不 corrupt、OFF 不翻 audit
import concurrent.futures
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    list(ex.map(lambda _: run(proj, tr), range(50)))
raw = open(sp(proj)).read()
try:
    st = json.loads(raw)
except Exception as e:
    raise AssertionError(f"J: state 文件 corrupt（非法 JSON）: {raw!r} ({e})")
assert st.get("enable-audit") is False, f"J: enable 被翻转={st}"
s = status_text(run(proj, tr))
assert s and "audit 已关" in s and AUDIT_MARK not in s, f"J: OFF 被误翻 audit！stopReason={s!r}"
print(f"J OK — 50 并发 off，state 合法 JSON、OFF 未翻 audit（rounds={st['unaudited-rounds']}）")

# K. 八进制：unaudited-rounds 字符串 "08" + enable=false → 仍走 OFF，不 fall through 到 audit
proj, tr = new_proj(True)
with open(sp(proj), "w") as f:
    json.dump({"enable-audit": False, "unaudited-rounds": "08"}, f)
s = status_text(run(proj, tr))
assert s and "audit 已关" in s and AUDIT_MARK not in s, f"K: '08' fall through 到 audit！stopReason={s!r}"
print("K OK — unaudited-rounds='08' 不再 fall through 到 audit")

# L. 无尾换行 + 末两行都有 usage 的 transcript → 不崩、正常输出
proj, tr = new_proj(True)
tr2 = os.path.join(os.path.dirname(tr), "t2.jsonl")
with open(tr2, "w") as f:
    f.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 900000}}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 350000}}}))  # 无尾换行
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
stdin = {"session_id": "s", "stop_hook_active": False, "cwd": proj,
         "last_assistant_message": "done", "transcript_path": tr2}
p = run_stdin(stdin)
r = audit_reason(p)
assert r and AUDIT_MARK in r, f"L: 崩了/无输出，stderr={p.stderr!r}"
assert "integer expression" not in p.stderr and "too great" not in p.stderr, f"L: stderr 有算术报错={p.stderr!r}"
print("L OK — 无尾换行双 usage transcript 不崩、无 stderr 报错，token 显示:",
      "有" if "上下文已用" in r else "降级时钟")

# M. 没配 + 无 transcript → 仍 continue:false 显时间（降级无 token）+ 没配提示、无 audit 字样
proj, tr = new_proj(with_watcher=False)
stdin = {"session_id": "s", "stop_hook_active": False, "cwd": proj,
         "last_assistant_message": "done", "transcript_path": "/nonexistent-xyz.jsonl"}
p = run_stdin(stdin)
s = status_text(p)
assert s and "没有 .watcher" in s and "UTC" in s and AUDIT_MARK not in s, f"M: stopReason={s!r}"
assert read_state(proj) is None, "M: 不该建 state 文件"
print("M OK — 没配 + 无 transcript → 仍 continue:false 显时间+没配提示、无 audit 字样")

# N. 通路互斥（本次改动的核心不变量）：只报状态的两个分支绝不带 decision:block，ON 分支绝不带 continue:false
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
off_o = out_json(run(proj, tr))
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
on_o = out_json(run(proj, tr))
nowatcher_o = out_json(run(*new_proj(with_watcher=False)))
assert is_status_exit(off_o), f"N: OFF 通路错={off_o!r}"
assert is_status_exit(nowatcher_o), f"N: 没配 通路错={nowatcher_o!r}"
assert on_o.get("decision") == "block" and on_o.get("continue") is None, f"N: ON 通路错={on_o!r}"
print("N OK — 通路互斥：OFF/没配 走 continue:false（停），ON 走 decision:block（继续跑 audit）")

# O. Every branch carries the cleanup line. It lives on STATUS_LINE rather than
# in the audit block so a project with watcher off still gets it — that is the
# only state where a session runs for hours without ever being reminded.
CLEANUP_MARK = "清进程"
BOUNDARY_MARK = "只清自己起的"

proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
on_r = audit_reason(run(proj, tr))
assert on_r and CLEANUP_MARK in on_r and BOUNDARY_MARK in on_r, \
    f"O1: the ON branch must carry the cleanup line, reason={on_r!r}"

write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
off_s = status_text(run(proj, tr))
assert off_s and CLEANUP_MARK in off_s and BOUNDARY_MARK in off_s, \
    f"O2: the OFF branch must carry the cleanup line, stopReason={off_s!r}"

proj2, tr2 = new_proj(with_watcher=False)
none_s = status_text(run(proj2, tr2))
assert none_s and CLEANUP_MARK in none_s and BOUNDARY_MARK in none_s, \
    f"O3: the unconfigured branch must carry the cleanup line, stopReason={none_s!r}"
print("O OK — all three branches carry the cleanup line")

# P. CPU and memory are disclosed as numbers, the way tokens already are.
# No threshold, no verdict: a predicate tuned on one machine is wrong on the
# next one, and this repo only ever measured a single macOS box.
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
r = audit_reason(run(proj, tr))
assert re.search(r"CPU \d+%", r), f"P1: the status line must disclose CPU, reason={r!r}"
assert re.search(r"内存 [\d.]+G / \d+G（\d+%）", r), \
    f"P2: the status line must disclose memory as used / total (pct), reason={r!r}"
print("P OK — CPU and memory disclosed as plain numbers")

# Q. Nothing judges processes any more. These strings belong to the scan that
# was removed; their return would mean the predicate came back.
for mark in ("空转", "孤儿", "ORPHAN_MIN", "ORPHAN_WHITELIST"):
    assert mark not in r, f"Q: {mark!r} means the process predicate is back, reason={r!r}"
hook_src = open(HOOK).read()
for mark in ("ORPHAN_MIN_CPU", "ORPHAN_WHITELIST", "空转孤儿"):
    assert mark not in hook_src, f"Q: {mark!r} still in the hook source"
print("Q OK — no process predicate left in output or source")

# R. Every exit tells Claude the readings are for the user: not relayed, no compact advice, 🧹 still acted on
OFF_NOTE = "状态读数（开头那一行的时间、上下文、CPU、内存，以及未 audit 轮数）是给用户看的，不要转述，也不建议压缩；🧹 那一行照做；务必不要 audit"
NO_WATCHER_NOTE = "状态读数（开头那一行的时间、上下文、CPU、内存）是给用户看的，不要转述，也不建议压缩；🧹 那一行照做；务必不要 audit"
ON_NOTE = "开头那一行的读数（时间、上下文、CPU、内存）是给用户看的，audit 摘要里不转述，也不建议压缩；🧹 那一行照做"
for label, with_watcher, state, note in (("no-watcher", False, None, NO_WATCHER_NOTE),
                                        ("off", True, {"enable-audit": False, "unaudited-rounds": 0}, OFF_NOTE)):
    proj, tr = new_proj(with_watcher=with_watcher)
    if state is not None:
        write_state(proj, state)
    s = status_text(run(proj, tr))
    assert s and note in s, f"R({label}): status-only reason must carry its no-relay note, stopReason={s!r}"
    assert "只报状态" not in s, f"R({label}): status-only reason must not ask Claude to report the status, stopReason={s!r}"


def transcript_with(tokens):
    tmp = tempfile.mkdtemp()
    tr = os.path.join(tmp, "t.jsonl")
    with open(tr, "w") as f:
        f.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": tokens}}}) + "\n")
    return tr


def codex_rollout(total_tokens, window, input_tokens=None, trailing_null=False):
    """A Codex rollout file: an older token_count, the latest one, optionally a null-info one after it."""
    tmp = tempfile.mkdtemp()
    tr = os.path.join(tmp, "rollout.jsonl")

    def event(total, inp):
        return {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": inp, "cached_input_tokens": 0, "output_tokens": total - inp,
                                 "reasoning_output_tokens": 0, "total_tokens": total},
            "model_context_window": window}}}

    with open(tr, "w") as f:
        f.write(json.dumps({"type": "session_meta", "payload": {"id": "x"}}) + "\n")
        f.write(json.dumps(event(1000, 900)) + "\n")
        f.write(json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant"}}) + "\n")
        f.write(json.dumps(event(total_tokens, input_tokens if input_tokens is not None else total_tokens)) + "\n")
        if trailing_null:
            f.write(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": None}}) + "\n")
    return tr


def pending_file(session):
    return os.path.join(PENDING_DIR, session + ".txt")


def codex_only():
    # CX1. Context reading comes from the last non-null token_count: total_tokens over model_context_window.
    proj, _ = new_proj(True)
    r = audit_reason(run(proj, codex_rollout(300000, 475000, input_tokens=200000, trailing_null=True)))
    assert r and "上下文已用 300K / 63%" in r and "窗口 475K" in r, f"CX1: reading must be total_tokens / window, reason={r!r}"
    assert "compact" not in r and "⚠️" not in r, f"CX1: Codex compacts by itself, no manual advice, reason={r!r}"

    # CX2. Above 85% still only reports the reading.
    r = audit_reason(run(proj, codex_rollout(450000, 475000)))
    assert r and r.startswith("📊") and "上下文已用 450K / 94%" in r and "compact" not in r, f"CX2: reason={r!r}"

    # CX3. transcript_path null (codex exec --ephemeral): no context segment, the rest still shows.
    stdin = {"session_id": "s-null", "stop_hook_active": False, "cwd": proj,
             "last_assistant_message": "done", "transcript_path": None}
    r = audit_reason(run_stdin(stdin))
    assert r and "UTC" in r and "上下文已用" not in r and "清进程" in r, f"CX3: reason={r!r}"

    # CX4. ON names the watcher:watcher skill and an existing absolute SKILL.md path; user commands use $ form.
    r = audit_reason(run(proj, codex_rollout(300000, 475000)))
    m = re.search(r"先读 `(/[^`]+/skills/watcher/SKILL\.md)`", r or "")
    assert m and os.path.isfile(m.group(1)), f"CX4: ON must point at an existing SKILL.md, reason={r!r}"
    assert "Skill 工具" not in r and "/watcher:" not in r, f"CX4: no Claude Code forms, reason={r!r}"
    assert "$watcher:watcher-off" in r and "$watcher:watcher-on" in r, f"CX4: switch commands in Codex form, reason={r!r}"

    # CX5. OFF and no-config texts use the $ form and are handed to the next prompt, keyed by session_id.
    proj, tr = new_proj(True)
    write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
    base = {"stop_hook_active": False, "cwd": proj, "last_assistant_message": "done", "transcript_path": tr}
    s1 = status_text(run_stdin({**base, "session_id": "sess-A"}))
    assert s1 and "/watcher:" not in s1 and "$watcher:watcher-on" in s1, f"CX5: OFF text={s1!r}"
    assert open(pending_file("sess-A")).read() == s1, "CX5: handoff file must hold the exact status text"
    s2 = status_text(run_stdin({**base, "session_id": "sess-A"}))
    assert "已连续 2 轮" in s2 and open(pending_file("sess-A")).read() == s2, "CX5: a later Stop overwrites the handoff"

    proj2, tr2 = new_proj(with_watcher=False)
    s3 = status_text(run_stdin({"session_id": "sess-B", "stop_hook_active": False, "cwd": proj2,
                                "last_assistant_message": "done", "transcript_path": tr2}))
    assert s3 and "/watcher:" not in s3 and "$watcher:watcher-configure" in s3, f"CX5: no-config text={s3!r}"
    assert open(pending_file("sess-B")).read() == s3, "CX5: no-config also hands the text over"

    # CX6. ON goes to the model directly and leaves no handoff file.
    proj, tr = new_proj(True)
    audit_reason(run_stdin({"session_id": "sess-C", "stop_hook_active": False, "cwd": proj,
                            "last_assistant_message": "done", "transcript_path": tr}))
    assert not os.path.exists(pending_file("sess-C")), "CX6: ON must not write a handoff file"

    # CX7. Skips (active / no last message / background wait) print nothing and leave no handoff file.
    proj, tr = new_proj(True)
    write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
    for sid, extra in (("sess-D1", {"stop_hook_active": True}),
                       ("sess-D2", {"last_assistant_message": None}),
                       ("sess-D3", {"background_tasks": [{"type": "subagent", "status": "running"}]})):
        stdin = {"session_id": sid, "stop_hook_active": False, "cwd": proj,
                 "last_assistant_message": "done", "transcript_path": tr, **extra}
        if stdin["last_assistant_message"] is None:
            del stdin["last_assistant_message"]
        p = run_stdin(stdin)
        assert p.stdout.strip() == "" and not os.path.exists(pending_file(sid)), f"CX7({sid}): stdout={p.stdout!r}"

    # CX8. Without PLUGIN_DATA the status still shows and nothing is written.
    proj, tr = new_proj(with_watcher=False)
    p = run_stdin({"session_id": "sess-E", "stop_hook_active": False, "cwd": proj,
                   "last_assistant_message": "done", "transcript_path": tr}, env={"PLUGIN_DATA": ""})
    assert status_text(p) and not os.path.exists(pending_file("sess-E")), f"CX8: stdout={p.stdout!r}"

    # CX9. A session_id that is not a plain id never names a file outside the handoff dir.
    run_stdin({"session_id": "../escape", "stop_hook_active": False, "cwd": proj,
               "last_assistant_message": "done", "transcript_path": tr})
    assert not os.path.exists(os.path.join(PLUGIN_DATA, "escape.txt")), "CX9: path escaped the handoff dir"
    print("CX OK — Codex reading, ON/OFF/no-config texts, handoff file, skips and PLUGIN_DATA rules")


def mask(text):
    """Drop the live readings (time, CPU, memory) so two runs of the Stop hook compare byte for byte."""
    text = re.sub(r"UTC \d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "UTC <time>", text)
    text = re.sub(r"｜CPU \d+%", "", text)
    return re.sub(r"｜内存 [\d.]+G / \d+G（\d+%）", "", text)


def cc_only():
    # CC1. The Claude Code branch never writes a handoff file.
    assert not os.path.exists(PENDING_DIR), "CC1: the Claude Code branch must not hand text over"

    # CC2. With no argument the output equals origin/main's hook once live readings are masked.
    main_src = subprocess.run(["git", "show", "origin/main:watcher/hooks/suggest-watcher.sh"],
                              cwd=os.path.dirname(HOOK), capture_output=True, text=True, check=True).stdout
    main_hook = os.path.join(tempfile.mkdtemp(), "suggest-watcher.sh")
    with open(main_hook, "w") as f:
        f.write(main_src)
    cases = (("on", True, {"enable-audit": True, "unaudited-rounds": 2}),
             ("off", True, {"enable-audit": False, "unaudited-rounds": 2}),
             ("none", False, None))
    for label, with_watcher, state in cases:
        for with_transcript in (True, False):
            outs = []
            for hook in (main_hook, HOOK):
                proj, tr = new_proj(with_watcher)
                if state is not None:
                    write_state(proj, state)
                stdin = {"session_id": "s", "stop_hook_active": False, "cwd": proj,
                         "last_assistant_message": "done", "transcript_path": tr if with_transcript else ""}
                p = subprocess.run(["bash", hook], input=json.dumps(stdin), capture_output=True, text=True)
                outs.append(mask(p.stdout))
            assert outs[0] == outs[1], f"CC2({label}, transcript={with_transcript}): output differs from origin/main"
    print("CC OK — no handoff file, output byte-identical to origin/main after masking live readings")


for label, tokens, icon in (() if CODEX else (("below-threshold", 300000, "📊"), ("above-threshold", 900000, "⚠️"))):
    proj, _ = new_proj(True)
    r = audit_reason(run(proj, transcript_with(tokens)))
    assert r and r.startswith(icon) and "上下文已用" in r, f"R(on {label}): status line must open with {icon} and carry the reading, reason={r!r}"
    assert ON_NOTE in r, f"R(on {label}): audit reason must carry the no-relay note, reason={r!r}"
    assert "务必不要 audit" not in r, f"R(on {label}): audit reason must not forbid the audit it asks for, reason={r!r}"

# A GNU-like tail that rejects -r must still yield the context reading
shim = tempfile.mkdtemp()
real_tail = shutil.which("tail")
with open(os.path.join(shim, "tail"), "w") as f:
    f.write('#!/bin/bash\nfor a in "$@"; do [ "$a" = "-r" ] && { echo "tail: invalid option -- \'r\'" >&2; exit 1; }; done\nexec ' + real_tail + ' "$@"\n')
if shutil.which("tac") is None:
    with open(os.path.join(shim, "tac"), "w") as f:
        f.write('#!/bin/bash\nexec ' + real_tail + ' -r "$@"\n')
for name in os.listdir(shim):
    os.chmod(os.path.join(shim, name), 0o755)
proj, _ = new_proj(True)
gnu_tr = codex_rollout(300000, 475000) if CODEX else transcript_with(300000)
r = audit_reason(run(proj, gnu_tr, env={"PATH": shim + os.pathsep + os.environ["PATH"]}))
assert r and "上下文已用" in r, f"R(gnu tail): status line must still carry the context reading, reason={r!r}"
print("R OK — all three exits carry their no-relay note, both thresholds read tokens, and GNU tail falls back to tac")

if CODEX:
    codex_only()
else:
    cc_only()

print(f"\nALL SMOKE PASS ({PLATFORM or 'claude-code'})")
