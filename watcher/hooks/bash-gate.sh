#!/bin/bash
# PreToolUse[Bash] 拦截器：把协作规范三条从文字约束变成工具层面拦截。
#   4.1.3  不得在主分支 commit
#   4.7.7  commit 标题格式（type: summary、≤72 字符、无句号结尾）、禁 Co-Authored-By
#   4.7.5  提 PR 前须有本会话验证标记
#
# 协议（2.1.221 二进制 + 官方 hooks 文档实证）：
#   exit 2 → 拦截调用，stderr 回传给模型
#   exit 0 → 放行
#   exit 1 → 非阻塞错误，工具照常执行（本脚本任何路径都不用 1）
#
# 依赖 jq —— 与 announce-intent.sh、suggest-watcher.sh 一致，不引入第二个运行时。
#
# 作用域：仅管目标仓库根有 .watcher/ 的项目，与 suggest-watcher.sh 的 opt-in 一致。
# 没配 .watcher/ 的仓库（沙盘、别人的仓、本仓自身）一律放行。
#
# 测试：python3 watcher/scripts/smoke-bash-gate.py，不全绿不许提交。
set -u

INPUT=$(cat)

block() { printf '%s\n' "$1" >&2; exit 2; }

# ---------- 取输入 ----------
# 解析失败时不能拦死所有 Bash 调用（那会连诊断命令一起拦住，无法自救）。
# 先用文本兜底判断这条命令是不是 git commit / gh pr create：
#   是  → 拦住并说明检查器故障（1.3.6 不得伪造通过）
#   不是 → 放行
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
if [ -z "$CMD" ]; then
  if printf '%s' "$INPUT" | grep -qE 'git[^"]*commit|gh[^"]*pr[^"]*create'; then
    block "拦截器无法读取输入（jq 缺失或 stdin 不是合法 JSON），无法校验这条 git/gh 命令。修好环境后重试。依 1.3.6，校验器不可用时不得放行。"
  fi
  exit 0
fi

SID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SID" ] && SID=nosession
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

# ---------- 定位命令真正操作的仓库 ----------
# stdin 的 cwd 是会话目录，不等于这条命令要操作的仓库：
#   git -C <path> commit  → 目标是 <path>
#   cd <path> && git ...  → PreToolUse 在执行前触发，cd 尚未发生，cwd 还是旧值
# 优先级：git -C 的路径 > 命令里最后一个 cd 的路径 > stdin 的 cwd
target_dir() {
  local d
  d=$(printf '%s' "$CMD" | sed -nE 's/.*git[[:space:]]+(-[^C][[:space:]]+)*-C[[:space:]]+([^[:space:];&|]+).*/\2/p' | head -1)
  if [ -z "$d" ]; then
    d=$(printf '%s' "$CMD" | sed -nE 's/.*(^|[;&|][[:space:]]*)cd[[:space:]]+([^[:space:];&|]+).*/\2/p' | tail -1)
  fi
  [ -z "$d" ] && d="$CWD"
  printf '%s' "$d"
}

DIR=$(target_dir)

# ---------- 作用域：目标仓库没配 .watcher/ 就不管 ----------
[ -n "$DIR" ] && [ -d "$DIR/.watcher" ] || exit 0

# ---------- git commit ----------
# 匹配 `git commit`，允许中间夹选项（git -C /path commit、git --no-pager commit）
if printf '%s' "$CMD" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]-][^[:space:]]*)?)*[[:space:]]+commit([[:space:]]|$)'; then

  # 4.1.3 主分支保护。取不到分支名一律拦（1.3.6：不得因取不到而伪造通过）
  BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null)
  if [ -z "$BRANCH" ]; then
    block "拦截器读不出 $DIR 的当前分支（不是 git 仓库或 git 不可用），无法校验 4.1.3。修好后重试。依 1.3.6，校验器不可用时不得放行。"
  fi
  if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    block "违反 4.1.3：$DIR 当前在主分支（${BRANCH}）。先从主分支建任务分支再 commit。"
  fi

  # 多个 -m 时逐个取，拼成整段 message 供署名检查用
  FLAT=$(printf '%s' "$CMD" | tr '\n' ' ')
  ALL_MSG=$(printf '%s' "$FLAT" | grep -oE -- '-[a-zA-Z]*m[= ]+("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:];&|]+)' | sed -E 's/^-[a-zA-Z]*m[= ]+//; s/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')

  if [ -n "$ALL_MSG" ]; then
    # 禁署名：只看 message，不看整条命令（命令里提到该词不等于加了这条 trailer）
    if printf '%s' "$ALL_MSG" | grep -qi 'Co-Authored-By'; then
      block "违反 4.7.7：commit message 里不得出现 Co-Authored-By 署名行。"
    fi

    FIRST=$(printf '%s' "$ALL_MSG" | head -1)
    if ! printf '%s' "$FIRST" | grep -qE '^(feat|fix|refactor|docs|test|chore|perf|ci)(\([^)]+\))?: .+'; then
      block "违反 4.7.7：commit 标题须为 type: summary，type 只取 feat/fix/refactor/docs/test/chore/perf/ci。当前标题：$FIRST"
    fi
    LEN=$(printf '%s' "$FIRST" | wc -m | tr -d ' ')
    if [ "$LEN" -gt 72 ]; then
      block "违反 4.7.7：summary 超过 72 字符（当前 ${LEN}）。"
    fi
    case "$FIRST" in
      *.|*。) block "违反 4.7.7：summary 结尾不加句号。" ;;
    esac
  fi
fi

# ---------- gh pr create ----------
if printf '%s' "$CMD" | grep -qE '(^|[;&|[:space:]])gh[[:space:]]+pr[[:space:]]+create([[:space:]]|$)'; then
  if [ ! -f "/tmp/cc-$SID-verified" ]; then
    block "违反 4.7.5：本会话没有验证通过标记。按 4.7.5 完成本次任务类型对应的全部交付验证（设计/代码/测试齐备、验收清单逐项通过、单测与 smoke/E2E 通过、要求的 UI 实际使用通过、实现对抗与文案对抗通过、无必修遗留），验证真正做完后再写入本会话标记。未验证而写标记即为虚报，违反 1.3.1。"
  fi
fi

exit 0
