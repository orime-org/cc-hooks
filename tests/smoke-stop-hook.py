#!/usr/bin/env python3
"""Stop hook (suggest-watcher.sh) 的 smoke 测试 —— 构造真实 stdin 跑 hook、断言输出协议。

跑法：python3 tests/smoke-stop-hook.py
改 suggest-watcher.sh 后、提交前必跑：不全绿不许提交。

两条输出通路（CC 2.1.220 二进制实证）：
  - {"decision":"block","reason":X}      → Claude 看得到 X、CC **启动下一轮**（用于 ON 分支叫 Claude 跑 audit）
  - {"continue":false,"stopReason":X}    → Claude 看不到 X、用户终端显示 "Operation stopped by hook: X"、
                                            CC **直接停、不启动下一轮**（用于只报状态的 OFF / 没配分支）
"""
import json
import os
import re
import subprocess
import tempfile
import time

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watcher", "hooks", "suggest-watcher.sh")


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
    return subprocess.run(["bash", HOOK], input=json.dumps(stdin),
                          capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def out_json(p):
    """hook 的 stdout 解析成 dict；空输出返回 None。"""
    s = p.stdout.strip()
    return json.loads(s) if s else None


def audit_reason(p):
    """ON 分支（block 通路）的 reason；不是 block 通路就返回 None。"""
    o = out_json(p)
    return o.get("reason") if o and o.get("decision") == "block" else None


def status_text(p):
    """只报状态分支（continue:false 通路）的 stopReason；不是该通路就返回 None。"""
    o = out_json(p)
    return o.get("stopReason") if o and o.get("continue") is False else None


# A. 没配 .watcher/（临时夹/新项目/cwd 路径错）→ continue:false 显状态+没配提示、不建文件、无 audit 字样
proj, tr = new_proj(with_watcher=False)
p = run(proj, tr)
o = out_json(p)
assert o is not None, f"A: 应有输出，实际空={p.stdout!r}"
assert o.get("continue") is False, f"A: 应走 continue:false 急停通路（显示完就停），实际={o!r}"
assert "decision" not in o, f"A: 不该再带 decision（那是叫 CC 继续的通路），实际={o!r}"
s = status_text(p)
assert "没有 .watcher" in s, f"A: 应提示没配 .watcher，stopReason={s!r}"
assert "调用 Skill" not in s, f"A: 没配分支绝不能含任何让 CC audit 的字样！stopReason={s!r}"
assert ("上下文已用" in s) or ("UTC" in s), f"A: 应含时间/token 状态，stopReason={s!r}"
assert read_state(proj) is None, "A: 不该建 state 文件（只显示、不建）"
print("A OK — 没配 .watcher/ → continue:false 显时间+token+没配提示、无 audit 字样、不建文件")

# B. 迁移 纯 .watcher（orime 升级）→ 默认 enable=true → audit（block 通路）
proj, tr = new_proj(True)
p = run(proj, tr)
r = audit_reason(p)
assert r and "调用 Skill" in r, f"B: 应走 block 通路叫 Claude 跑 audit，实际={out_json(p)!r}"
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
assert r and "已累计 3 轮" in r and "调用 Skill" in r, f"D: 应带放宽提示，reason={r!r}"
assert read_state(proj)["unaudited-rounds"] == 3, "D: hook 不再清零（清零挪给 skill 进入时做），文件应仍是 3"
print("D OK — enable=true 有积压 → reason 带快照 3；hook 不清零、文件仍 3（清零归 skill）")

# E. enable=false off → continue:false 显状态 + bump
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": False, "unaudited-rounds": 2})
p = run(proj, tr)
o = out_json(p)
assert o.get("continue") is False and "decision" not in o, f"E: OFF 应走 continue:false 急停通路，实际={o!r}"
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
assert r and "调用 Skill" in r, f"I: 损坏应兜底 audit，实际={out_json(p)!r}"
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
assert s and "audit 已关" in s and "调用 Skill" not in s, f"J: OFF 被误翻 audit！stopReason={s!r}"
print(f"J OK — 50 并发 off，state 合法 JSON、OFF 未翻 audit（rounds={st['unaudited-rounds']}）")

# K. 八进制：unaudited-rounds 字符串 "08" + enable=false → 仍走 OFF，不 fall through 到 audit
proj, tr = new_proj(True)
with open(sp(proj), "w") as f:
    json.dump({"enable-audit": False, "unaudited-rounds": "08"}, f)
s = status_text(run(proj, tr))
assert s and "audit 已关" in s and "调用 Skill" not in s, f"K: '08' fall through 到 audit！stopReason={s!r}"
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
p = subprocess.run(["bash", HOOK], input=json.dumps(stdin), capture_output=True, text=True)
r = audit_reason(p)
assert r and "调用 Skill" in r, f"L: 崩了/无输出，stderr={p.stderr!r}"
assert "integer expression" not in p.stderr and "too great" not in p.stderr, f"L: stderr 有算术报错={p.stderr!r}"
print("L OK — 无尾换行双 usage transcript 不崩、无 stderr 报错，token 显示:",
      "有" if "上下文已用" in r else "降级时钟")

# M. 没配 + 无 transcript → 仍 continue:false 显时间（降级无 token）+ 没配提示、无 audit 字样
proj, tr = new_proj(with_watcher=False)
stdin = {"session_id": "s", "stop_hook_active": False, "cwd": proj,
         "last_assistant_message": "done", "transcript_path": "/nonexistent-xyz.jsonl"}
p = subprocess.run(["bash", HOOK], input=json.dumps(stdin), capture_output=True, text=True)
s = status_text(p)
assert s and "没有 .watcher" in s and "UTC" in s and "调用 Skill" not in s, f"M: stopReason={s!r}"
assert read_state(proj) is None, "M: 不该建 state 文件"
print("M OK — 没配 + 无 transcript → 仍 continue:false 显时间+没配提示、无 audit 字样")

# N. 通路互斥（本次改动的核心不变量）：只报状态的两个分支绝不带 decision:block，ON 分支绝不带 continue:false
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
off_o = out_json(run(proj, tr))
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
on_o = out_json(run(proj, tr))
nowatcher_o = out_json(run(*new_proj(with_watcher=False)))
assert off_o.get("continue") is False and off_o.get("decision") is None, f"N: OFF 通路错={off_o!r}"
assert nowatcher_o.get("continue") is False and nowatcher_o.get("decision") is None, f"N: 没配 通路错={nowatcher_o!r}"
assert on_o.get("decision") == "block" and on_o.get("continue") is None, f"N: ON 通路错={on_o!r}"
print("N OK — 通路互斥：OFF/没配 走 continue:false（停），ON 走 decision:block（继续跑 audit）")

# O. 机器干净时不提孤儿进程 —— 这一行每轮都跑，无命中必须一个字不输出
proj, tr = new_proj(True)
write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
r = audit_reason(run(proj, tr))
assert "空转" not in r and "孤儿" not in r, f"O: 机器干净时不该提孤儿，reason={r!r}"
print("O OK — 无命中时静默")

# P. 造真孤儿：PPID=1、CPU 打满、命令行可识别；三条 state 分支都要报出来
def spawn_orphans(n=2):
    """起 n 个空转子进程，父 shell 立刻退出，子进程被 init 收养。"""
    # The children inherit the pipe fd, so capture_output would block until they
    # exit — which is never. Send their streams to /dev/null instead.
    subprocess.run(["/bin/sh", "-c",
                    "i=0; while [ $i -lt %d ]; do (while :; do :; done) >/dev/null 2>&1 & i=$((i+1)); done" % n],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    time.sleep(2)


def orphan_pids():
    """PID of every spin loop the tests spawned, whatever its parent is."""
    out = subprocess.run(["ps", "-eo", "pid,ppid,command"],
                         capture_output=True, text=True).stdout
    hits = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) == 3 and "while :; do :; done" in parts[2]:
            hits.append(parts[0])
    return hits


# The hook only reports processes older than 10 minutes; tests cannot wait that
# long, so they lower the floor to 0 through the same knob the hook reads.
# A spin loop only reaches ~99% CPU on an idle machine; under load it drops
# below the 80 the hook ships with, so the floors move for the test alone.
FRESH = {"ORPHAN_MIN_MINUTES": "0", "ORPHAN_MIN_CPU": "1"}

spawn_orphans(2)
try:
    pids = orphan_pids()
    assert len(pids) >= 2, f"P: 造孤儿失败，只找到 {pids}"

    # ON 分支（block 通路）
    proj, tr = new_proj(True)
    write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
    r = audit_reason(run(proj, tr, env=FRESH))
    assert r and "空转" in r, f"P1: ON 分支应报孤儿，reason={r!r}"
    assert pids[0] in r, f"P1: 应列出 PID {pids[0]}，reason={r!r}"

    # OFF 分支（continue:false 通路）
    write_state(proj, {"enable-audit": False, "unaudited-rounds": 0})
    s = status_text(run(proj, tr, env=FRESH))
    assert s and "空转" in s, f"P2: OFF 分支应报孤儿，stopReason={s!r}"

    # 没配 .watcher/ 分支
    proj2, tr2 = new_proj(with_watcher=False)
    s = status_text(run(proj2, tr2, env=FRESH))
    assert s and "空转" in s, f"P3: 没配分支应报孤儿，stopReason={s!r}"

    # 只报不杀：hook 跑完孤儿还活着
    assert len(orphan_pids()) >= 2, "P4: hook 不得杀进程，跑完孤儿应仍在"
    print("P OK — 有孤儿时三条分支都报出 PID，且只报不杀")
finally:
    subprocess.run(["pkill", "-f", "while :; do :; done"], capture_output=True)
    time.sleep(0.5)

# Q. A whitelisted executable path is never reported, however it scores.
# On macOS every launchd-started daemon has PPID 1 from birth, so PPID alone
# separates nothing — the whitelist is what tells a system daemon apart from a
# process that was spawned during a session and left behind.
#
# The shipped list is read out of the hook rather than restated here: the env
# var replaces the whole list, so a copy would silently drop the system paths
# and turn this into a test of nothing.
hook_src = open(HOOK).read()
_wl = re.search(r'ORPHAN_WHITELIST="\$\{ORPHAN_WHITELIST:-([^}]*)\}"', hook_src)
assert _wl, "Q: cannot read the shipped whitelist out of the hook"
SHIPPED_WHITELIST = _wl.group(1)
WHITELISTED = dict(FRESH, ORPHAN_WHITELIST=SHIPPED_WHITELIST + " /bin/")

spawn_orphans(2)
try:
    pids = orphan_pids()
    assert len(pids) >= 2, f"Q: spawning orphans failed, found {pids}"

    proj, tr = new_proj(True)
    write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})

    r = audit_reason(run(proj, tr, env=WHITELISTED))
    assert "空转" not in r, f"Q1: a whitelisted path must not be reported, reason={r!r}"

    # Same processes, same run, whitelist alone removed: they must reappear.
    # Without this the Q1 silence could equally mean the spawn never worked.
    r2 = audit_reason(run(proj, tr, env=FRESH))
    assert "空转" in r2 and pids[0] in r2, \
        f"Q2: outside the whitelist the same process must be reported, reason={r2!r}"
    print("Q OK — whitelist decides; the same process reports without it")
finally:
    subprocess.run(["pkill", "-f", "while :; do :; done"], capture_output=True)
    time.sleep(0.5)

# R. The shipped defaults, asserted at the source. The tests override both
# floors to run at all, so nothing else here can catch a wrong default.
assert 'ORPHAN_MIN_CPU:-30' in hook_src, "R1: the CPU floor must ship as 30"
assert 'ORPHAN_MIN_MINUTES:-10' in hook_src, "R2: the age floor must ship as 10 minutes"

shipped = SHIPPED_WHITELIST.split()
for prefix in ("/System/", "/usr/libexec/", "/usr/sbin/", "/Library/",
               "/Applications/", "/opt/homebrew/"):
    assert prefix in shipped, f"R3: {prefix} must ship in the whitelist, got {shipped}"
# Sessions spawn their processes through these two, so a whitelist covering
# them would hide exactly what this check exists to surface.
for cc_path in ("/bin/", "/usr/bin/"):
    assert cc_path not in shipped, \
        f"R4: {cc_path} is where sessions spawn processes; it must stay out, got {shipped}"
print(f"R OK — shipped floors and {len(shipped)} whitelist prefixes are the intended ones")

# S. The notice reports and stops there. An instruction to decide what to clean
# reads as a task and gets acted on, which is what "只报不杀" exists to prevent.
spawn_orphans(1)
try:
    proj, tr = new_proj(True)
    write_state(proj, {"enable-audit": True, "unaudited-rounds": 0})
    r = audit_reason(run(proj, tr, env=FRESH))
    assert "空转" in r, f"S: no orphan reported, cannot check the wording, reason={r!r}"
    assert "这是提示不是判定" in r, f"S1: the notice must say it is not a verdict, reason={r!r}"
    assert "确认哪些该清" not in r, f"S2: the notice must not hand out an action, reason={r!r}"
    print("S OK — the notice reports without instructing")
finally:
    subprocess.run(["pkill", "-f", "while :; do :; done"], capture_output=True)
    time.sleep(0.5)

print("\nALL SMOKE PASS")
