#!/usr/bin/env python3
"""bash-gate.sh 的 smoke 测试 —— 构造真实 stdin 和真实 git 仓库跑 hook、断言拦放。

跑法：python3 watcher/scripts/smoke-bash-gate.py
改 bash-gate.sh 后、提交前必跑：不全绿不许提交。

被测对象是 PreToolUse[Bash] 拦截器，协议（2.1.221 二进制 + 官方 hooks 文档实证）：
  - exit 2  → 拦截工具调用，stderr 回传给模型
  - exit 0  → 放行
  - exit 1  → 非阻塞错误，工具照常执行（所以本脚本任何情况都不该用 1）

覆盖的规范条目：
  4.1.3 主分支不得 commit
  4.7.7 commit 标题格式、禁 Co-Authored-By
  4.7.5 提 PR 前须有本会话验证标记
  1.3.6 检查器自身故障不得静默放行
"""
import json
import os
import subprocess
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "bash-gate.sh")

failures = []
checks = 0


def new_repo(branch="main", with_watcher=True):
    """建一个真实 git 仓库，切到指定分支，可选建 .watcher/ 目录。"""
    d = tempfile.mkdtemp()
    run = lambda *a: subprocess.run(a, cwd=d, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    open(os.path.join(d, "f.txt"), "w").write("x")
    run("git", "add", ".")
    run("git", "commit", "-q", "-m", "init")
    run("git", "branch", "-M", branch)
    if with_watcher:
        os.makedirs(os.path.join(d, ".watcher"), exist_ok=True)
    return d


def call(command, cwd, session="sess1", raw_stdin=None):
    """跑 hook，返回 (exit_code, stderr)。raw_stdin 非 None 时直接喂原始字节。"""
    payload = raw_stdin
    if payload is None:
        payload = json.dumps({
            "session_id": session,
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        })
    p = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
    return p.returncode, p.stderr


def check(name, got, want, stderr="", expect_in_stderr=None):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}: 期望 exit {want}，实际 exit {got}；stderr={stderr[:200]!r}")
        return
    if expect_in_stderr and expect_in_stderr not in stderr:
        failures.append(f"{name}: exit 对了但 stderr 未含 {expect_in_stderr!r}；实际 stderr={stderr[:200]!r}")


def check_stderr(name, stderr, must_have=(), must_not=()):
    """Assert on the block message itself, independent of the exit code."""
    global checks
    checks += 1
    for s in must_have:
        if s not in stderr:
            failures.append(f"{name}: stderr missing {s!r}; got {stderr[:200]!r}")
    for s in must_not:
        if s in stderr:
            failures.append(f"{name}: stderr must not contain {s!r}; got {stderr[:200]!r}")


# ---------- 4.1.3 主分支保护 ----------

repo_main = new_repo("main")
repo_master = new_repo("master")
repo_task = new_repo("feat/x")

c, e = call('git commit -m "feat: add thing"', repo_main)
check("A 主分支 main 上 commit 应拦", c, 2, e, "main")

c, e = call('git commit -m "feat: add thing"', repo_master)
check("A2 主分支 master 上 commit 应拦", c, 2, e, "master")

c, e = call('git commit -m "feat: add thing"', repo_task)
check("B 任务分支上合规 commit 应放行", c, 0, e)

# 对抗挑出：cd 与 -C 两种写法必须判出「命令真正要提交的那个仓库」的分支，
# 而不是 stdin 的 cwd。PreToolUse 在命令执行前触发，cd 尚未发生。
c, e = call(f'cd {repo_main} && git commit -m "feat: x"', repo_task)
check("G cd 到主分支仓库再 commit 应拦（stdin cwd 在任务分支）", c, 2, e)

c, e = call(f'git -C {repo_main} commit -m "feat: x"', repo_task)
check("H git -C 指向主分支仓库应拦（stdin cwd 在任务分支）", c, 2, e)

c, e = call(f'git -C {repo_task} commit -m "feat: x"', repo_main)
check("H2 git -C 指向任务分支应放行（stdin cwd 在主分支）", c, 0, e)

# 对抗挑出：分支取不到时必须拦（1.3.6 不得伪造通过），不能因为空串「不是 main」就放行
_nogit = tempfile.mkdtemp()
os.makedirs(os.path.join(_nogit, ".watcher"))
c, e = call('git commit -m "feat: x"', _nogit)
check("O 受管目录但非 git 仓库时 commit 应拦，不得因取不到分支名而放行", c, 2, e)

# ---------- 4.7.7 commit 标题格式 ----------

c, e = call('git commit -m "add thing"', repo_task)
check("C 标题缺 type 应拦", c, 2, e, "type")

c, e = call('git commit -m "feat: ' + "x" * 80 + '"', repo_task)
check("D 标题超 72 字符应拦", c, 2, e)

c, e = call('git commit -m "feat: add thing."', repo_task)
check("E 标题以英文句号结尾应拦", c, 2, e)

c, e = call('git commit -m "feat: add thing。"', repo_task)
check("E2 标题以中文句号结尾应拦", c, 2, e)

c, e = call('git commit -m "fix(scope): handle empty input"', repo_task)
check("B2 带 scope 的合规标题应放行", c, 0, e)

# 对抗挑出：-am 与无引号写法的 message 也在命令行文本里，不能静默跳过检查
c, e = call('git commit -am "add thing"', repo_task)
check("N -am 写法缺 type 也应拦", c, 2, e, "type")

c, e = call('git commit -am "feat: add thing"', repo_task)
check("N2 -am 写法合规应放行", c, 0, e)

# ---------- 4.7.7 禁署名 ----------

# 对抗挑出：判据应是「message 里含」，不是「整条命令含」
c, e = call('git commit -m "feat: x" -m "body\n\nCo-Authored-By: A <a@b>"', repo_task)
check("F message 里含 Co-Authored-By 应拦", c, 2, e, "Co-Authored-By")

c, e = call('echo "Co-Authored-By is banned by 4.7.7"', repo_task)
check("F2 非 commit 命令里出现该词不应拦", c, 0, e)

# ---------- 4.7.5 提 PR 前置 ----------

c, e = call("gh pr create --fill", repo_task, session="sess-no-mark")
check("I 无验证标记时提 PR 应拦", c, 2, e)

marker = "/tmp/cc-sess-marked-verified"
open(marker, "w").close()
try:
    c, e = call("gh pr create --fill", repo_task, session="sess-marked")
    check("J 有验证标记时提 PR 应放行", c, 0, e)
finally:
    os.path.exists(marker) and os.remove(marker)

# 拦截文案不得原样给出绕过命令（对抗挑出：那等于把绕过成本降到照抄一行）
c, e = call("gh pr create --fill", repo_task, session="sess-no-mark2")
check_stderr("I2 block text must not spell out the touch bypass", e,
             must_not=("touch /tmp/cc-",))

# A block message tells the reader what tripped and what to do. A rule number is
# a lookup address (1.1.4) and stays; copied rule text is a second source that
# drifts from announce, so it goes.
c, e = call("gh pr create --fill", repo_task, session="sess-no-mark3")
check_stderr("I3 PR block cites 4.7.5 without copying its text", e,
             must_have=("4.7.5",),
             must_not=("smoke/E2E", "验收清单逐项通过", "1.3.1"))

# ---------- 1.3.6 检查器自身故障 ----------

c, e = call(None, repo_task, raw_stdin='{"tool_input":{"command":"git commit -m \\"x\\""}')
check("K 输入不是合法 JSON 且命令是 git commit 时应拦", c, 2, e)
check_stderr("K2 parser-failure block states the fault, not the rule behind it", e,
             must_not=("1.3.6",))

# .git removed but .watcher/ kept: rev-parse fails, the directory is still in
# scope, so the branch read fails and the gate must fail closed.
repo_broken = new_repo("main")
subprocess.run(["rm", "-rf", os.path.join(repo_broken, ".git")], capture_output=True)
c, e = call('git commit -m "feat: x"', repo_broken)
check("K3 分支取不到时应拦", c, 2, e)
check_stderr("K4 branch-unreadable block cites 4.1.3, not 1.3.6", e,
             must_have=("4.1.3",),
             must_not=("1.3.6",))

# 对抗挑出：解析失败时不该把所有 Bash 命令一起拦死，只拦 git / gh 两类
c, e = call(None, repo_task, raw_stdin='{"tool_input":{"command":"ls -la"}')  # 截断的 JSON
check("M 解析失败但命令非 git/gh 时应放行，不得拦死全部 Bash", c, 0, e)

# ---------- 项目级 opt-in ----------

# 对抗挑出：插件是用户级启用，无 opt-in 会拦死所有仓库（含 orime 自身）。
# 与 suggest-watcher.sh 一致：项目根无 .watcher/ 即不管。
repo_no_watcher = new_repo("main", with_watcher=False)
c, e = call('git commit -m "whatever"', repo_no_watcher)
check("P 项目根无 .watcher/ 时不拦（与 suggest-watcher.sh 的 opt-in 一致）", c, 0, e)

# ---------- 无关命令 ----------

c, e = call("ls -la", repo_main)
check("L 普通命令应放行", c, 0, e)

c, e = call("git status", repo_main)
check("L2 非 commit 的 git 命令应放行", c, 0, e)


# ========== 实现对抗第 1 轮报出的 9 个问题，逐条固化 ==========

# 组一：目标目录定位（问题 1/2/4/5）
_sub = os.path.join(repo_main, "sub"); os.makedirs(_sub, exist_ok=True)
c, e = call('git commit -m "feat: x"', _sub)
check("R1-1 受管仓库的子目录里 commit 也要拦（.watcher 在仓库根）", c, 2, e)

c, e = call(f'cd {repo_main} && git commit -m "feat: x" && cd -', repo_task)
check("R1-2 commit 后还有 cd 时，判的应是 commit 所在段的目录", c, 2, e)

c, e = call(f'git -c core.x=1 -C {repo_main} commit -m "feat: x"', repo_task)
check("R1-4a git -c k=v -C <path> 也要取到 path", c, 2, e)

c, e = call(f'git --no-pager -C {repo_main} commit -m "feat: x"', repo_task)
check("R1-4b git --no-pager -C <path> 也要取到 path", c, 2, e)

c, e = call(f'cd "{repo_main}" && git commit -m "feat: x"', repo_task)
check("R1-5 路径带引号也要取到", c, 2, e)

# 组二：命令识别（问题 6/9）
c, e = call('echo "记得 git commit -m x 到任务分支"', repo_task)
check("R1-6a echo 里提到 git commit 不得误拦", c, 0, e)

c, e = call('echo "跑完再 gh pr create"', repo_task)
check("R1-6b echo 里提到 gh pr create 不得误拦", c, 0, e)

c, e = call(None, repo_task, raw_stdin='{"tool_input":{"command":"git -C \\"/x\\" commit -m \\"y\\""}')
check("R1-9 解析失败兜底要认出带引号参数的 git commit", c, 2, e)

# 组三：message 提取与判定（问题 3/7/8）
c, e = call('git commit --message="add thing"', repo_task)
check("R1-3a --message= 长写法缺 type 要拦", c, 2, e, "type")

c, e = call('git commit --message "add thing"', repo_task)
check("R1-3b --message 空格分隔缺 type 要拦", c, 2, e, "type")

c, e = call('git commit -m"add thing"', repo_task)
check("R1-3c -m 紧贴引号缺 type 要拦", c, 2, e, "type")

c, e = call('git commit --message="feat: x" --message="Co-Authored-By: A <a@b>"', repo_task)
check("R1-3d 长写法里的署名也要拦", c, 2, e, "Co-Authored-By")

c, e = call('git commit -m "$(cat <<EOF\nfeat: add gate\nEOF\n)"', repo_task)
check("R1-7 命令替换取不到 message 时不得当成违规误拦", c, 0, e)

c, e = call('git commit -m "feat: short title\n\nbody line that is quite long and would exceed seventy two characters easily"', repo_task)
check("R1-8 多行 message 的标题只取首行，不得把整坨当标题判长度", c, 0, e)

# ========== 第 2 轮：两条会挡住开发的误拦 ==========

c, e = call('git commit --amend --no-edit', repo_task)
check("R2-1a git commit --amend --no-edit 不得误拦", c, 0, e)

c, e = call('git commit --amend -m "fix: correct the title"', repo_task)
check("R2-1b git commit --amend -m 合规标题不得误拦", c, 0, e)

c, e = call('git commit -m "chore: update deps & lockfile"', repo_task)
check("R2-2a 标题含 & 不得误拦", c, 0, e)

c, e = call('git commit -m "docs: update\n\nUse git add -A && git commit"', repo_task)
check("R2-2b 正文含 && 不得误拦", c, 0, e)

c, e = call('git commit -m "feat: support foo|bar alternation"', repo_task)
check("R2-2c 标题含 | 不得误拦", c, 0, e)

c, e = call('git commit --amend -m "bad title"', repo_task)
check("R2-1c --amend 带违规标题仍要拦", c, 2, e, "type")

# ---------- 汇总 ----------

if failures:
    print(f"❌ {len(failures)}/{checks} 项不通过：\n")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print(f"✅ 全部 {checks} 项通过")
