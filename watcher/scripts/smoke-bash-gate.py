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
checks += 1
if "touch /tmp/cc-" in e:
    failures.append("I2 拦截文案不应原样给出 touch 绕过命令；实际 stderr=" + repr(e[:200]))

# ---------- 1.3.6 检查器自身故障 ----------

c, e = call(None, repo_task, raw_stdin='{"tool_input":{"command":"git commit -m \\"x\\""}')
check("K 输入不是合法 JSON 且命令是 git commit 时应拦", c, 2, e)

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

# ---------- 汇总 ----------

if failures:
    print(f"❌ {len(failures)}/{checks} 项不通过：\n")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print(f"✅ 全部 {checks} 项通过")
