#!/bin/bash
# Stop hook: 每轮结束时——
#   - watcher ON：block + reason（token/时间水位 + audit 提醒）→ CC 起新 turn 让 Claude 跑收尾审查
#   - watcher OFF（<项目>/.watcher/.stop-disabled 存在）：block + reason（token/时间/未审轮次，不 audit）→ 状态照显示、不审查
#   - 两种都靠 stop_hook_active=true 防递归：block 后 CC 自动起的那轮结束时 active=true → skip → 真正结束
#   - 后台有 subagent/workflow running/pending、或本轮无收尾文本 → skip（不 block、不显示）；等真收尾那轮再处理
#
# 顺序铁律：防递归(active) / 后台任务在飞(bg-pending) / 无收尾文本(no-last-msg) 三个 skip 判定
# 必须排在 on/off 分支之前——否则 OFF 也 block 会在后台唤醒流里误触、或漏了 active 防护造成死循环。
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

# 跳过计数：累计「距上次 audit 攒了多少轮没审计」，给最终 audit 放宽范围用。
# 文件放项目本地 .watcher/.skip-count（仅当 .watcher/ 已存在时计，不污染未配置项目）。
SKIP_CNT=""
bump_skip_count() {
  [ -n "$CWD" ] && [ -d "$CWD/.watcher" ] || return 0
  local f="$CWD/.watcher/.skip-count" c
  c=$(cat "$f" 2>/dev/null || echo 0)
  case "$c" in ''|*[!0-9]*) c=0;; esac
  c=$((c + 1))
  echo "$c" > "$f"
  SKIP_CNT="$c"
}

# —— skip 判定（必须最先、排在 on/off 分支前）——

# 防递归：block 后 CC 自动起的那轮结束时 active=true → skip
# ★ active=true 是 CC 喂的「已 block 过一次」信号，跳过它是 ON/OFF 都防死循环的唯一保险——绝不能动
if [ "$ACTIVE" = "true" ]; then
  printf '[%s] session=%s status=skip-stop-hook-active\n' "$TS" "${SESSION:-?}" >> "$LOG"
  exit 0
fi

# 后台任务暂停判定（v2.1.168 起 Stop hook stdin 带 background_tasks，optional，可能整个缺失）：
# 有 type 为 subagent/workflow 且 status running/pending 的后台任务 → 这一轮是「派活后暂停等唤醒」、非真收尾
# → skip（不 block，别干扰唤醒流）+ 累加 skip-count，等任务跑完唤醒那轮再处理、范围自动放宽。
# 只认 subagent/workflow（会重新唤醒会话的派活）；monitor/shell/session_crons 故意不跳过。
# jq 出错/字段缺失 → BG_WAIT 兜底 0 → 不跳过。
BG_WAIT=$(printf '%s' "$INPUT" | jq -r '[(.background_tasks // [])[] | select((.type=="subagent" or .type=="workflow") and (.status=="running" or .status=="pending"))] | length' 2>/dev/null)
case "$BG_WAIT" in ''|*[!0-9]*) BG_WAIT=0;; esac
if [ "$BG_WAIT" -gt 0 ]; then
  bump_skip_count
  printf '[%s] session=%s status=skip-bg-pending bgwait=%s skipcount=%s\n' "$TS" "${SESSION:-?}" "$BG_WAIT" "${SKIP_CNT:-NA}" >> "$LOG"
  exit 0
fi

# 本轮无最终收尾文本（中途停 / 结尾是工具调用）→ 非正常 stop → skip（ON/OFF 都不显示，别打扰干活）
if [ -z "$LAST_MSG" ]; then
  bump_skip_count
  printf '[%s] session=%s status=skip-no-last-msg skipcount=%s\n' "$TS" "${SESSION:-?}" "${SKIP_CNT:-NA}" >> "$LOG"
  exit 0
fi

# —— 到这里是「正常 stop」：算 token/时间水位（ON/OFF 都要显示）——
# 窗口按 1M 算百分比；≥85% 切成压缩告警（CC 自动压缩被服务端 reactive-only 关掉，靠这个提醒用户手动 /compact）。
NOW_UTC=$(date -u '+%Y-%m-%d %H:%M:%S')
CTX_WINDOW=1000000
COMPACT_PCT=85
STATUS_LINE="🕐 现在 UTC ${NOW_UTC}"
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  TOKENS=""
  # `|| [ -n "$__line" ]`：兜住最后一行没有尾换行的情况（tail -r 反转后它是第一行、恰是最新 usage），否则会被 read 漏掉
  while IFS= read -r __line || [ -n "$__line" ]; do
    __t=$(printf '%s' "$__line" | jq -r 'if (.message.usage.input_tokens // empty) then (.message.usage.input_tokens + (.message.usage.cache_read_input_tokens//0) + (.message.usage.cache_creation_input_tokens//0)) else empty end' 2>/dev/null)
    if [ -n "$__t" ] && [ "$__t" != "null" ]; then TOKENS="$__t"; break; fi
  done < <(tail -r "$TRANSCRIPT" 2>/dev/null)
  if [ -n "$TOKENS" ] && [ "$TOKENS" -gt 0 ] 2>/dev/null; then
    PCT=$((TOKENS * 100 / CTX_WINDOW))
    TOKENS_K=$((TOKENS / 1000))
    if [ "$PCT" -ge "$COMPACT_PCT" ]; then
      STATUS_LINE="⚠️ 现在 UTC ${NOW_UTC}｜上下文已用 ${TOKENS_K}K / ${PCT}%（超过 ${COMPACT_PCT}%）——建议手动输入 /compact 压缩会话"
    else
      STATUS_LINE="📊 现在 UTC ${NOW_UTC}｜上下文已用 ${TOKENS_K}K / ${PCT}%（窗口 1M，未到 ${COMPACT_PCT}% 不用压）"
    fi
  fi
fi

# —— watcher OFF：只报 token/时间/未审轮次，不 audit ——
# .stop-disabled 由 /watcher-off 建、/watcher-on 删。off 期间照样每轮攒 skip-count，将来恢复审计一起审。
if [ -n "$CWD" ] && [ -f "$CWD/.watcher/.stop-disabled" ]; then
  bump_skip_count
  printf '[%s] session=%s cwd=%s status=off-show-status skipcount=%s\n' "$TS" "${SESSION:-?}" "$CWD" "${SKIP_CNT:-NA}" >> "$LOG"
  OFF_REASON="${STATUS_LINE}"$'\n'"🔕 audit 已关，已连续 ${SKIP_CNT} 轮未 audit（恢复审计后一并补审）"$'\n\n'"（本轮只报状态、不 audit；恢复审计输入 \`/watcher:watcher-on\`。这条只是状态提醒、无需专门回应，继续即可。）"
  jq -n --arg reason "$OFF_REASON" '{decision:"block", reason:$reason}'
  exit 0
fi

# —— watcher ON：token/时间水位 + audit 提醒 ——
# 读跳过计数 → 拼进 reason（让 audit 把这 N 轮一起审）。
# ★ 不在这清零——清零唯一交给 skill 在 audit 真跑完时做（见 SKILL.md 第四步）：
#   hook「提醒 audit」≠ audit 真发生（手动 /watcher 绕过 hook、或提醒后没真审），提醒即清会「清了没审、丢工作」。
#   skill 自己读 .skip-count 定放宽范围、审完才 rm，是唯一真相源；这里只读不删。
SKIPPED=0
if [ -n "$CWD" ] && [ -f "$CWD/.watcher/.skip-count" ]; then
  SKIPPED=$(cat "$CWD/.watcher/.skip-count" 2>/dev/null || echo 0)
  case "$SKIPPED" in ''|*[!0-9]*) SKIPPED=0;; esac
fi
printf '[%s] session=%s status=remind skipped_since_last=%d\n' "$TS" "${SESSION:-?}" "$SKIPPED" >> "$LOG"

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
if [ "$SKIPPED" -gt 0 ]; then
  SKIP_PREFIX="⚠️ 距上次 audit 已累计 ${SKIPPED} 轮 stop 没审计（中途无收尾文本 / watcher 手动关闭期间）——这次 audit 范围要从「只本轮」放宽到「本轮 + 这 ${SKIPPED} 轮被跳过的工作」一起审，别只盯最后一轮。"$'\n\n'
fi

jq -n --arg reason "${STATUS_LINE}"$'\n\n'"${SKIP_PREFIX}${STATIC_REASON}" '{decision:"block", reason:$reason}'
