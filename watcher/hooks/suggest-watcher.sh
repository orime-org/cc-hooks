#!/bin/bash
# Stop hook: 每轮结束时按项目的 audit-state 决定报什么——
#   状态存 <项目>/.watcher/audit-state.json：{ "enable-audit": true/false, "unaudited-rounds": N }
#   - 文件不存在（没配 .watcher/ 或 cwd 路径错）→ 静默 exit：fail-safe，宁可不审也不误触发
#       治根：后台任务完成唤醒轮 CC 传的 cwd 可能不是项目根，找不到 state 文件就保守静默、不再误 audit
#   - enable-audit=false（用户 /watcher-off）→ block 显状态（token/时间/未审轮次），不 audit、轮次 +1
#   - enable-audit=true（用户 /watcher-on，默认）→ block + audit 提醒（带 unaudited-rounds 放宽范围）
#   - 都靠 stop_hook_active=true 防递归：block 后 CC 自动起的那轮 active=true → skip → 真正结束
#   - 后台 subagent/workflow running/pending、或本轮无收尾文本 → skip（不 block）+ 轮次 +1；等真收尾那轮再处理
#
# ★ 状态 = 一个文件的字段（不是文件存在性）：on/off 只改 enable-audit 字段、都不删文件。
#   这样「文件找不到」只剩一个含义 = 路径错/未配 → 静默；跟「用户 off（字段 false、文件在）」彻底分开。
#
# ★ 并发安全：多 CC 实例 / 共享仓可能有多个 Stop hook 同时写同一个 state 文件。所有写都走 update_state /
#   migrate_state 的「temp 文件 + mv 原子替换」——mv 是原子的，读者永远看到完整文件、绝不会读到截断的空文件
#   （空文件会让 enable-audit 读空→兜底 true→把 OFF 误翻成 audit，这是必须堵死的）。
#   残留：并发下 unaudited-rounds 计数可能少算（两个进程各读旧值各 +1，后写覆盖先写）——只影响 audit 放宽
#   范围、不影响 on/off 判定，属低危；没加文件锁是因为锁的 stale/死锁风险比「计数偶尔少算」更麻烦。
#
# 顺序铁律：迁移旧格式 → 三个 skip 判定（active/bg-pending/no-last-msg）→ 算 token/时间 → state 分支
#   skip 判定必须排在 state 分支前——否则 OFF 也 block 会在后台唤醒流误触、或漏 active 防护死循环。
#
# 跟 CC 设计对齐：
#   - Stop hook 想让 Claude 看到东西只能走 block + reason（reason 包成 "Stop hook feedback:\n<reason>" 进 transcript）
#   - token/时间从 transcript_path 的最后一条 assistant usage 算（所有 hook 输入都带 transcript_path）
#   - token = input + cache_read + cache_creation（不含 output，贴近喂给模型的输入水位、跟 /context 口径一致）

set -u

LOG=/tmp/cc-token-watch.log
TS=$(date '+%Y-%m-%d %H:%M:%S')

INPUT=$(cat)
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
ACTIVE=$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
# CC 只在「最后一条 assistant 消息有纯文本」时才填 last_assistant_message（源码 utils/hooks.ts:3662-3668）；
# 缺失/null/空 = 本轮不是「给了最终收尾文本的正常 stop」（中途停 / 结尾是工具调用）
LAST_MSG=$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
# 对话记录文件路径：用来算当前上下文 token 水位（所有 hook 输入都带这个字段）
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

# 项目状态文件（CWD 为空时 STATE_FILE 也为空，后面所有判定都会退到「静默不审」）
STATE_FILE="${CWD:+$CWD/.watcher/audit-state.json}"

# 原子更新 state 文件：$1 = jq 变换 filter。temp 文件 + mv 原子替换，杜绝并发读到截断的空文件。
# 计数自增用 jq 的数字运算（不用 bash $(()）——避开 "08"/"09" 被当八进制导致 $((08+1)) 报错的坑）。
update_state() {
  [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ] || return 1
  local out tmp="$STATE_FILE.tmp.$$"
  out=$(jq "$1" "$STATE_FILE" 2>/dev/null)
  if [ -n "$out" ]; then
    printf '%s\n' "$out" > "$tmp" 2>/dev/null && mv -f "$tmp" "$STATE_FILE" 2>/dev/null
  fi
  rm -f "$tmp" 2>/dev/null
}

# —— 迁移：有 .watcher/ 但还没 audit-state.json → 建之 ——
# 默认 enable-audit=true（配了 .watcher/ 就默认审）；旧 .stop-disabled → false、旧 .skip-count → 轮次，迁完删旧文件。
# ★ 只在有 .watcher/ 目录时建：没 .watcher/（未配 / cwd 路径错）绝不建，保持「文件不存在 = 静默不审」的 fail-safe。
# 写用 temp + mv 原子替换（并发 migrate 幂等：内容一致、各自 tmp.$$ 不踩踏）。
migrate_state() {
  [ -n "$CWD" ] && [ -d "$CWD/.watcher" ] || return 0
  [ -f "$STATE_FILE" ] && return 0
  local enable="true" rounds=0 tmp="$STATE_FILE.tmp.$$"
  local old_disabled="$CWD/.watcher/.stop-disabled"
  local old_skip="$CWD/.watcher/.skip-count"
  [ -f "$old_disabled" ] && enable="false"
  if [ -f "$old_skip" ]; then
    rounds=$(cat "$old_skip" 2>/dev/null || echo 0)
    case "$rounds" in ''|*[!0-9]*) rounds=0;; esac
    [ "${#rounds}" -gt 12 ] && rounds=999999999999
    rounds=$((10#$rounds))
  fi
  if jq -n --argjson e "$enable" --argjson r "$rounds" '{"enable-audit":$e,"unaudited-rounds":$r}' > "$tmp" 2>/dev/null; then
    mv -f "$tmp" "$STATE_FILE" 2>/dev/null && rm -f "$old_disabled" "$old_skip"
  fi
  rm -f "$tmp" 2>/dev/null
}
migrate_state

# unaudited-rounds +1：没审的工作轮攒计数，给 audit 放宽范围用。文件不存在（路径错/未配）→ no-op。
BUMP_CNT=""
bump_unaudited() {
  [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ] || return 0
  # jq 里数字化再 +1：非数字（含字符串 "08"）一律当 0，避开八进制与类型坑
  update_state '.["unaudited-rounds"] = (((.["unaudited-rounds"] // 0) | if type=="number" then . else (tonumber? // 0) end) + 1)'
  BUMP_CNT=$(jq -r '.["unaudited-rounds"] // 0' "$STATE_FILE" 2>/dev/null)
  case "$BUMP_CNT" in ''|*[!0-9]*) BUMP_CNT=0;; esac
}

# —— skip 判定（必须最先、排在 state 分支前）——

# 防递归：block 后 CC 自动起的那轮结束时 active=true → skip
# ★ active=true 是 CC 喂的「已 block 过一次」信号，跳过它是防死循环的唯一保险——绝不能动
if [ "$ACTIVE" = "true" ]; then
  printf '[%s] session=%s status=skip-stop-hook-active\n' "$TS" "${SESSION:-?}" >> "$LOG"
  exit 0
fi

# 后台任务暂停判定（v2.1.168 起 Stop hook stdin 带 background_tasks，optional，可能整个缺失）：
# 有 type 为 subagent/workflow 且 status running/pending 的后台任务 → 这一轮是「派活后暂停等唤醒」、非真收尾
# → skip（不 block，别干扰唤醒流）+ 轮次 +1，等任务跑完唤醒那轮再处理、范围自动放宽。
# 只认 subagent/workflow（会重新唤醒会话的派活）；monitor/shell/session_crons 故意不跳过。jq 出错/字段缺失 → 兜底 0 → 不跳过。
BG_WAIT=$(printf '%s' "$INPUT" | jq -r '[(.background_tasks // [])[] | select((.type=="subagent" or .type=="workflow") and (.status=="running" or .status=="pending"))] | length' 2>/dev/null)
case "$BG_WAIT" in ''|*[!0-9]*) BG_WAIT=0;; esac
if [ "$BG_WAIT" -gt 0 ]; then
  bump_unaudited
  printf '[%s] session=%s cwd=%s status=skip-bg-pending bgwait=%s rounds=%s\n' "$TS" "${SESSION:-?}" "${CWD:-?}" "$BG_WAIT" "${BUMP_CNT:-NA}" >> "$LOG"
  exit 0
fi

# 本轮无最终收尾文本（中途停 / 结尾是工具调用）→ 非正常 stop → skip（不显示，别打扰干活）+ 轮次 +1
if [ -z "$LAST_MSG" ]; then
  bump_unaudited
  printf '[%s] session=%s cwd=%s status=skip-no-last-msg rounds=%s\n' "$TS" "${SESSION:-?}" "${CWD:-?}" "${BUMP_CNT:-NA}" >> "$LOG"
  exit 0
fi

# —— 到这里是「正常 stop」：算 token/时间水位（显示状态 / audit 提醒都要用）——
# 窗口按 1M 算百分比；≥85% 切成压缩告警（CC 自动压缩被服务端 reactive-only 关掉，靠这个提醒用户手动 /compact）。
NOW_UTC=$(date -u '+%Y-%m-%d %H:%M:%S')
CTX_WINDOW=1000000
COMPACT_PCT=85
STATUS_LINE="🕐 现在 UTC ${NOW_UTC}"
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  TOKENS=""
  # `|| [ -n "$__line" ]`：兜住最后一行没有尾换行的情况；`head -1` + 数字校验：兜住 tail -r 把无尾换行的末行
  # 与前一行合并、单行含两个 JSON 对象导致 jq 吐出多行数字的情况（否则 TOKENS 会变成 "N1\nN2" 后续比较报错）。
  while IFS= read -r __line || [ -n "$__line" ]; do
    __t=$(printf '%s' "$__line" | jq -r 'if (.message.usage.input_tokens // empty) then (.message.usage.input_tokens + (.message.usage.cache_read_input_tokens//0) + (.message.usage.cache_creation_input_tokens//0)) else empty end' 2>/dev/null | head -1)
    case "$__t" in ''|*[!0-9]*) __t="";; esac
    if [ -n "$__t" ]; then TOKENS="$__t"; break; fi
  done < <(tail -r "$TRANSCRIPT" 2>/dev/null)
  if [ -n "$TOKENS" ] && [ "${#TOKENS}" -le 15 ] && [ "$TOKENS" -gt 0 ] 2>/dev/null; then
    PCT=$((TOKENS * 100 / CTX_WINDOW))
    TOKENS_K=$((TOKENS / 1000))
    if [ "$PCT" -ge "$COMPACT_PCT" ]; then
      STATUS_LINE="⚠️ 现在 UTC ${NOW_UTC}｜上下文已用 ${TOKENS_K}K / ${PCT}%（超过 ${COMPACT_PCT}%）——建议手动输入 /compact 压缩会话"
    else
      STATUS_LINE="📊 现在 UTC ${NOW_UTC}｜上下文已用 ${TOKENS_K}K / ${PCT}%（窗口 1M，未到 ${COMPACT_PCT}% 不用压）"
    fi
  fi
fi

# —— state 分支 ——

# 文件不存在（没配 .watcher/ 或 cwd 路径错）→ 静默不审（fail-safe，治后台唤醒轮 cwd 变的误 audit）
if [ -z "$STATE_FILE" ] || [ ! -f "$STATE_FILE" ]; then
  printf '[%s] session=%s cwd=%s status=skip-no-state\n' "$TS" "${SESSION:-?}" "${CWD:-?}" >> "$LOG"
  exit 0
fi

# ★ 不能用 jq `// true`：`//` 对 null 和 false 都取备选，会把 enable-audit=false 吃成 true。直接取值、再显式兜底。
ENABLE=$(jq -r '.["enable-audit"]' "$STATE_FILE" 2>/dev/null)
[ "$ENABLE" = "true" ] || [ "$ENABLE" = "false" ] || ENABLE="true"   # null / 字段缺失 / 文件损坏 → 兜底 true（配了就审）
UNAUDITED=$(jq -r '.["unaudited-rounds"] // 0' "$STATE_FILE" 2>/dev/null)
case "$UNAUDITED" in ''|*[!0-9]*) UNAUDITED=0;; esac
[ "${#UNAUDITED}" -gt 12 ] && UNAUDITED=999999999999   # 防超大数把后面 $(()) 撑溢出
UNAUDITED=$((10#$UNAUDITED))                            # 强制十进制，避开 "08"/"09" 八进制坑

# enable-audit=false → OFF：显状态（token/时间/未审轮次）+ 轮次 +1，不 audit
if [ "$ENABLE" = "false" ]; then
  bump_unaudited
  printf '[%s] session=%s cwd=%s status=off-show-status rounds=%s\n' "$TS" "${SESSION:-?}" "$CWD" "${BUMP_CNT:-NA}" >> "$LOG"
  OFF_REASON="${STATUS_LINE}"$'\n'"🔕 audit 已关，已连续 ${BUMP_CNT} 轮未 audit（恢复审计后一并补审）"$'\n\n'"（本轮只报状态、不 audit；恢复审计输入 \`/watcher:watcher-on\`。这条只是状态提醒、无需专门回应，继续即可。）"
  jq -n --arg reason "$OFF_REASON" '{decision:"block", reason:$reason}'
  exit 0
fi

# —— enable-audit=true → ON：token/时间水位 + audit 提醒 ——
# 读 unaudited-rounds 拼进 reason（让 audit 把这 N 轮一起审）。
# ★ 不在这清零——清零唯一交给 skill 在 audit 真跑完时做（见 SKILL.md 第四步）：
#   hook「提醒 audit」≠ audit 真发生（手动 /watcher 绕过 hook、或提醒后没真审），提醒即清会「清了没审、丢工作」。
#   skill 自己读 audit-state.json 定放宽范围、审完把 unaudited-rounds 写 0（不删文件，删了 enable 也没了），是唯一真相源；这里只读不写。
printf '[%s] session=%s cwd=%s status=remind unaudited=%s\n' "$TS" "${SESSION:-?}" "$CWD" "$UNAUDITED" >> "$LOG"

# reason 正文用单引号 heredoc 保留 backtick/引号原样；jq 负责 JSON 转义
STATIC_REASON=$(cat <<'EOF'
📋 调用 Skill 工具 `skill='watcher'`（默认 audit，不传 args）跑本轮收尾。

按 SKILL.md 走完整 5 步流程 + 摘要（详见 SKILL.md）。

关键边界：
- 自检根因：本轮方案是真解决根本 vs workaround？workaround 必须明示
- Claude 不应自作主张转 configure 模式
- 如 .watcher/ 缺失，提示用户手动 /watcher configure
- 跑完 watcher audit 后，必须自己处理 audit 结果（按自检发现的问题做修正）；处理完如果原任务还没干完，继续把原任务干完，别停在 audit 这一步

开关：若想关掉每轮的自动 watcher，可手动输入 `/watcher:watcher-off` 关掉本项目的该功能，`/watcher:watcher-on` 重新打开（只影响当前项目）。这是留给用户的开关，Claude 别自作主张去关。
EOF
)

SKIP_PREFIX=""
if [ "$UNAUDITED" -gt 0 ]; then
  SKIP_PREFIX="⚠️ 距上次 audit 已累计 ${UNAUDITED} 轮 stop 没审计（中途无收尾文本 / 后台等待 / watcher 关闭期间）——这次 audit 范围要从「只本轮」放宽到「本轮 + 这 ${UNAUDITED} 轮被跳过的工作」一起审，别只盯最后一轮。"$'\n\n'
fi

jq -n --arg reason "${STATUS_LINE}"$'\n\n'"${SKIP_PREFIX}${STATIC_REASON}" '{decision:"block", reason:$reason}'
