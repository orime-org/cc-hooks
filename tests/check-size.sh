#!/bin/bash
# 校验 announce-intent.sh 注入内容不超过 hook 输出上限，防被 CC 截断。
# CC 判定口径 = JS 字符串 .length（UTF-16 code units），非字节、非 token。
# Keep 200 UTF-16 units below Claude Code's 10000-unit per-output cap.
# Measure the complete stdout, including its trailing newline.
# 每次改 announce-intent.sh 后、提交前跑一遍：过不了不许提交。
set -u

CEILING=9800
DIR="$(cd "$(dirname "$0")" && pwd)"
ANNOUNCE="$DIR/../watcher/hooks/announce-intent.sh"

if [ ! -f "$ANNOUNCE" ]; then
  echo "❌ 找不到 announce-intent.sh: $ANNOUNCE"
  exit 2
fi

# The ceiling applies to the Claude Code output (no argument).
OUTFILE=$(mktemp)
trap 'rm -f "$OUTFILE"' EXIT
echo '{"prompt":"x"}' | bash "$ANNOUNCE" > "$OUTFILE" 2>/dev/null

# 优先 node 量真实 .length（UTF-16 code units）；无 node 退 python3 的 utf-16 计数；都没有才退 wc -m。
if command -v node >/dev/null 2>&1; then
  LEN=$(node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(String(s.length)))' < "$OUTFILE")
elif command -v python3 >/dev/null 2>&1; then
  LEN=$(python3 -c 'import sys; s=sys.stdin.read(); print(len(s.encode("utf-16-le"))//2)' < "$OUTFILE")
else
  echo "⚠️ 无 node/python3，退回 wc -m（有 emoji 时会低估，announce 正文禁 emoji 以保准）"
  LEN=$(wc -m < "$OUTFILE" | tr -d ' ')
fi

if [ "$LEN" -gt "$CEILING" ]; then
  echo "❌ announce 注入 $LEN 字符 > 上限 $CEILING —— 会被 CC 截成 2000 预览、后面段落丢失。先压缩再提交。"
  exit 1
fi
echo "✅ announce 注入 $LEN 字符 ≤ 上限 $CEILING"

# Codex runs the hook with `additionalContextLimit: 0`, so its output has no ceiling; report it only.
CODEX_OUT=$(echo '{"prompt":"x"}' | PLUGIN_DATA= bash "$ANNOUNCE" codex 2>/dev/null)
if [ -z "$CODEX_OUT" ]; then
  echo "❌ announce 的 Codex 版输出为空"
  exit 1
fi
echo "ℹ️ Codex 版 $(printf '%s' "$CODEX_OUT" | wc -m | tr -d ' ') 字符（无上限）"
