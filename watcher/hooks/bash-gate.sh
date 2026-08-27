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
# 作用域：仅管仓库根有 .watcher/ 的项目，与 suggest-watcher.sh 的 opt-in 一致。
# 没配 .watcher/ 的仓库（沙盘、别人的仓、本仓自身）一律放行。
#
# 测试：python3 watcher/scripts/smoke-bash-gate.py，不全绿不许提交。
set -u

INPUT=$(cat)

block() { printf '%s\n' "$1" >&2; exit 2; }

# ---------- 取输入 ----------
# 解析失败时不能拦死所有 Bash 调用（那会连诊断命令一起拦住，无法自救）。
# 先用文本兜底判断这条命令是不是 git commit / gh pr create：是才拦，其余放行。
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
if [ -z "$CMD" ]; then
  # 兜底匹配要放宽：git 与 commit 之间可能隔着带引号的参数（git -C "path" commit）
  if printf '%s' "$INPUT" | grep -qE 'git.*commit|gh.*pr.*create'; then
    block "拦截器无法读取输入（jq 缺失或 stdin 不是合法 JSON），无法校验这条 git/gh 命令。修好环境后重试。"
  fi
  exit 0
fi

SID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SID" ] && SID=nosession
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

# ---------- 切段 ----------
# 一条命令由 ; && || 分隔成多段。判定必须落到 commit 所在那一段：
# `cd repo && git commit && cd -` 的收尾 cd 不影响 commit 的工作目录。
# 且只认段首词是 git/gh 的段，避免把 echo "…git commit…" 里的文本当成真提交。
# 真实换行先换成 \x01：引号内的换行属于 message 内容，不能当命令分隔符切开。
# 判定完成后按 \x01 切首行即可。
NL=$(printf '\001')
CMD_FLAT=$(printf '%s' "$CMD" | tr '\n' "$NL")

# 切段要认引号：引号内的 ; & | 是 message 内容，不是命令分隔符。
# sed 做不到跟踪引号状态，用 awk 逐字符扫。
segments() {
  printf '%s' "$1" | awk '
    BEGIN { q = "" ; seg = "" }
    {
      for (i = 1; i <= length($0); i++) {
        c = substr($0, i, 1)
        if (q == "") { if (c == "\"" || c == "'"'"'") { q = c; seg = seg c; continue } }
        else { if (c == q) { q = "" }; seg = seg c; continue }
        if (c == ";" || c == "&" || c == "|") { if (seg != "") print seg; seg = ""; continue }
        seg = seg c
      }
    }
    END { if (seg != "") print seg }'
}

seg_first_word() { printf '%s' "$1" | sed -E 's/^[[:space:]]*//' | awk '{print $1}'; }

clean_path() {
  local p="$1"
  p=${p%\"}; p=${p#\"}
  p=${p%\'}; p=${p#\'}
  case "$p" in "~"|"~/"*) p="$HOME${p#\~}" ;; esac
  printf '%s' "$p"
}

COMMIT_SEG=""; COMMIT_CD=""; PR_SEG=""; CD_DIR=""
while IFS= read -r seg; do
  [ -z "$seg" ] && continue
  w=$(seg_first_word "$seg")
  if [ "$w" = "cd" ]; then
    d=$(printf '%s' "$seg" | sed -E 's/^[[:space:]]*cd[[:space:]]+//' | awk '{print $1}')
    if [ -n "$d" ] && [ "$d" != "-" ]; then CD_DIR=$(clean_path "$d"); fi
  fi
  if [ -z "$COMMIT_SEG" ] && [ "$w" = "git" ] && printf '%s' "$seg" | grep -qE '(^|[[:space:]])commit([[:space:]]|$)'; then
    COMMIT_SEG="$seg"; COMMIT_CD="$CD_DIR"
  fi
  if [ -z "$PR_SEG" ] && [ "$w" = "gh" ] && printf '%s' "$seg" | grep -qE '(^|[[:space:]])pr[[:space:]]+create([[:space:]]|$)'; then
    PR_SEG="$seg"
  fi
done <<SEGLOOP
$(segments "$CMD_FLAT")
SEGLOOP

[ -z "$COMMIT_SEG" ] && [ -z "$PR_SEG" ] && exit 0

# ---------- 定位命令真正操作的仓库 ----------
# 优先级：commit 段里的 git -C 路径 > commit 之前生效的 cd 路径 > stdin 的 cwd
# -C 之前允许任意其他选项（git -c k=v -C p、git --no-pager -C p）
resolve_dir() {
  local seg="$1" fallback="$2" d
  if printf '%s' "$seg" | grep -qE '[[:space:]]-C[[:space:]]'; then
    d=$(printf '%s' "$seg" | sed -E 's/.*[[:space:]]-C[[:space:]]+//' | awk '{print $1}')
    if [ -n "$d" ]; then clean_path "$d"; return; fi
  fi
  printf '%s' "$fallback"
}

if [ -n "$COMMIT_SEG" ]; then
  DIR=$(resolve_dir "$COMMIT_SEG" "${COMMIT_CD:-$CWD}")
else
  DIR="${CD_DIR:-$CWD}"
fi
[ -z "$DIR" ] && DIR="$CWD"

# ---------- 作用域：仓库根没配 .watcher/ 就不管 ----------
# 用 rev-parse 取仓库根，这样在受管仓库的任意子目录里干活也受管
ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)
if [ -n "$ROOT" ]; then
  [ -d "$ROOT/.watcher" ] || exit 0
else
  # 不是 git 仓库：目录本身配了 .watcher/ 才继续（继续后分支必然取不到，走 fail-closed）
  { [ -n "$DIR" ] && [ -d "$DIR/.watcher" ]; } || exit 0
fi

# ---------- git commit ----------
if [ -n "$COMMIT_SEG" ]; then

  # 4.1.3 主分支保护。取不到分支名一律拦（1.3.6：不得因取不到而伪造通过）
  BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null)
  if [ -z "$BRANCH" ]; then
    block "拦截器读不出 $DIR 的当前分支（不是 git 仓库或 git 不可用），无法校验 4.1.3。修好后重试。"
  fi
  if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    block "违反 4.1.3：$DIR 当前在主分支（${BRANCH}）。先从主分支建任务分支再 commit。"
  fi

  # 4.7.7 message 检查。
  # message 来自命令替换、反引号、heredoc、-F 时，命令行文本里没有真实内容，
  # 此时不做判定 —— 拿截出来的伪 message 判违规会误拦合规提交。
  if printf '%s' "$COMMIT_SEG" | grep -qE '\$\(|`|<<|[[:space:]]-F([[:space:]]|=)'; then
    MSG_OPAQUE=1
  else
    MSG_OPAQUE=0
  fi

  if [ "$MSG_OPAQUE" = "0" ]; then
    # 覆盖全部合法写法：-m x、-m"x"、-am x、-m=x、--message x、--message=x
    ALL_MSG=$(printf '%s' "$COMMIT_SEG" \
      | grep -oE -- '(^|[[:space:]])(--message|-[a-zA-Z]*m)[= ]*("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]]+)' \
      | sed -E 's/^[[:space:]]*(--message|-[a-zA-Z]*m)[= ]*//' \
      | sed -E 's/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//')

    if [ -n "$ALL_MSG" ]; then
      if printf '%s' "$ALL_MSG" | grep -qi 'Co-Authored-By'; then
        block "违反 4.7.7：commit message 里不得出现 Co-Authored-By 署名行。"
      fi

      # 标题＝第一个 message 参数的第一行。命令文本里的 \n 是字面两字符，也当换行切
      FIRST=$(printf '%s' "$ALL_MSG" | head -1 | sed -E "s/${NL}.*//" | sed -E 's/\\n.*//')
      if ! printf '%s' "$FIRST" | grep -qE '^(feat|fix|refactor|docs|test|chore|perf|ci)(\([^)]+\))?: .+'; then
        block "违反 4.7.7：commit 标题须为 type: summary，type 只取 feat/fix/refactor/docs/test/chore/perf/ci。当前标题：$FIRST"
      fi
      # 4.7.7 caps the summary, so measure past the `type(scope): ` prefix
      SUMMARY=$(printf '%s' "$FIRST" | sed -E 's/^[a-z]+(\([^)]+\))?: //')
      LEN=$(printf '%s' "$SUMMARY" | wc -m | tr -d ' ')
      if [ "$LEN" -gt 72 ]; then
        block "违反 4.7.7：summary 超过 72 字符（当前 ${LEN}）。"
      fi
      case "$FIRST" in
        *.|*。) block "违反 4.7.7：summary 结尾不加句号。" ;;
      esac
    fi
  fi
fi

# ---------- gh pr create ----------
if [ -n "$PR_SEG" ]; then
  if [ ! -f "/tmp/cc-$SID-verified" ]; then
    block "违反 4.7.5：本会话没有验证通过标记。按 4.7.5 完成本次任务类型对应的全部交付验证，做完后再写入本会话标记。未验证而写标记即为虚报。"
  fi
fi

exit 0
