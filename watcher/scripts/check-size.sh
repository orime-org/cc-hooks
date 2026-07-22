#!/bin/bash
# 校验 announce-intent.sh 注入内容不超过 hook 输出上限，防被 CC 截断。
# CC 判定口径 = JS 字符串 .length（UTF-16 code units），非字节、非 token。
# hook 硬上限 10000（超限 CC 只留 2000 字符预览、后面段落全丢）；这里守 8500 留余量。
# 每次改 announce-intent.sh 后、提交前跑一遍：过不了不许提交。
set -u

CEILING=8500
DIR="$(cd "$(dirname "$0")" && pwd)"
ANNOUNCE="$DIR/../hooks/announce-intent.sh"

if [ ! -f "$ANNOUNCE" ]; then
  echo "❌ 找不到 announce-intent.sh: $ANNOUNCE"
  exit 2
fi

OUT=$(echo '{"prompt":"x"}' | bash "$ANNOUNCE" 2>/dev/null)

# 优先 node 量真实 .length（UTF-16 code units）；无 node 退 python3 的 utf-16 计数；都没有才退 wc -m。
if command -v node >/dev/null 2>&1; then
  LEN=$(printf '%s' "$OUT" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(String(s.length)))')
elif command -v python3 >/dev/null 2>&1; then
  LEN=$(printf '%s' "$OUT" | python3 -c 'import sys; s=sys.stdin.read(); print(len(s.encode("utf-16-le"))//2)')
else
  echo "⚠️ 无 node/python3，退回 wc -m（有 emoji 时会低估，announce 正文禁 emoji 以保准）"
  LEN=$(printf '%s' "$OUT" | wc -m | tr -d ' ')
fi

if [ "$LEN" -gt "$CEILING" ]; then
  echo "❌ announce 注入 $LEN 字符 > 上限 $CEILING —— 会被 CC 截成 2000 预览、后面段落丢失。先压缩再提交。"
  exit 1
fi
echo "✅ announce 注入 $LEN 字符 ≤ 上限 $CEILING"
