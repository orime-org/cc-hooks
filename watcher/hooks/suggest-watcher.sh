#!/bin/bash
# Stop hook: 每轮结束建议调 watcher 跑收尾审查
#
# 设计：每轮 block 1 次 → 注入 reason → CC 自动启动新 turn 让 Claude 决定是否调 watcher
#       新 turn 结束时 stop_hook_active=true → skip → 真正结束
#
# 跟 CC 设计的对齐：
#   - Stop hook 不支持 additionalContext（utils/hooks.ts schema 不列）
#   - 想让 Claude 看到提醒，只能走 block + reason 路径
#   - reason 会包装成 "Stop hook feedback:\n<reason>" 进 transcript user message

set -u

LOG=/tmp/cc-token-watch.log
TS=$(date '+%Y-%m-%d %H:%M:%S')

INPUT=$(cat)
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
ACTIVE=$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
# CC 只在「最后一条 assistant 消息有纯文本」时才填 last_assistant_message（源码 utils/hooks.ts:3662-3668）；
# 字段缺失/null/空 = 本轮不是「给了最终收尾文本的正常 stop」（中途停 / 结尾是工具调用）→ 不该跑 audit
LAST_MSG=$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
# 对话记录文件路径：用来算当前上下文 token 水位（所有 hook 输入都带这个字段）
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

# 跳过计数：累计「距上次 audit 攒了多少轮没审计」，给最终 audit 放宽范围用。
# 文件放项目本地 .watcher/.skip-count（项目相关逻辑）；仅当 .watcher/ 已存在时计，不污染未配置项目。
# 计 2 类 skip：中途无收尾文本(skip-no-last-msg)、watcher 手动关闭期间(skip-project-disabled)。
# active=true（audit 自己那轮）不计。
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

# 防递归：第二次 Stop hook 调用（block 后 CC 自动启动的 turn 结束时）skip
# ★ active=true 是 CC 喂的「已 block 过一次」信号，跳过它是防死循环的唯一保险——绝不能动
if [ "$ACTIVE" = "true" ]; then
  printf '[%s] session=%s status=skip-stop-hook-active\n' "$TS" "${SESSION:-?}" >> "$LOG"
  exit 0
fi

# 项目级开关：当前项目存在 .watcher/.stop-disabled 文件 → skip 本轮提醒
# 用户用 /watcher-off 创建该文件，用 /watcher-on 删除
if [ -n "$CWD" ] && [ -f "$CWD/.watcher/.stop-disabled" ]; then
  bump_skip_count
  printf '[%s] session=%s cwd=%s status=skip-project-disabled skipcount=%s\n' "$TS" "${SESSION:-?}" "$CWD" "${SKIP_CNT:-NA}" >> "$LOG"
  exit 0
fi

# 只有「正常 stop」才进 watcher：CC 给了最终收尾文本（last_assistant_message 非空）才提醒跑 audit。
# 字段缺失 = CC 不是正常收尾（中途停 / 结尾工具调用 / 无最终文本）→ skip，不打扰 CC 干活
if [ -z "$LAST_MSG" ]; then
  bump_skip_count
  printf '[%s] session=%s status=skip-no-last-msg skipcount=%s\n' "$TS" "${SESSION:-?}" "${SKIP_CNT:-NA}" >> "$LOG"
  exit 0
fi

# 正常 stop，要提醒跑 audit：读跳过计数 → 拼进 reason（让 audit 把这 N 轮一起审）→ 清零
SKIPPED=0
if [ -n "$CWD" ] && [ -f "$CWD/.watcher/.skip-count" ]; then
  SKIPPED=$(cat "$CWD/.watcher/.skip-count" 2>/dev/null || echo 0)
  case "$SKIPPED" in ''|*[!0-9]*) SKIPPED=0;; esac
  rm -f "$CWD/.watcher/.skip-count"
fi
printf '[%s] session=%s status=remind skipped_since_last=%d\n' "$TS" "${SESSION:-?}" "$SKIPPED" >> "$LOG"

# reason 正文用单引号 heredoc 保留 backtick/引号原样；跳过提示按需前置；jq 负责 JSON 转义
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

# 上下文 token 水位：从 transcript 最后一条 assistant 的 usage 算当前 context 大小。
# token = input + cache_read + cache_creation（不含 output，贴近「喂给模型的输入水位」，跟 /context 口径一致）。
# 窗口按 1M 算百分比；每轮都显示 K + %，≥85% 切成压缩告警
# （CC 自动压缩被服务端 reactive-only 模式关掉，靠这个提醒用户手动 /compact）。
TOKEN_LINE=""
CTX_WINDOW=1000000
COMPACT_PCT=85
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  TOKENS=""
  while IFS= read -r __line; do
    __t=$(printf '%s' "$__line" | jq -r 'if (.message.usage.input_tokens // empty) then (.message.usage.input_tokens + (.message.usage.cache_read_input_tokens//0) + (.message.usage.cache_creation_input_tokens//0)) else empty end' 2>/dev/null)
    if [ -n "$__t" ] && [ "$__t" != "null" ]; then TOKENS="$__t"; break; fi
  done < <(tail -r "$TRANSCRIPT" 2>/dev/null)
  if [ -n "$TOKENS" ] && [ "$TOKENS" -gt 0 ] 2>/dev/null; then
    PCT=$((TOKENS * 100 / CTX_WINDOW))
    TOKENS_K=$((TOKENS / 1000))
    if [ "$PCT" -ge "$COMPACT_PCT" ]; then
      TOKEN_LINE="⚠️ 上下文已用 ${TOKENS_K}K / ${PCT}%（超过 ${COMPACT_PCT}%）——建议你手动输入 /compact 压缩会话。"$'\n\n'
    else
      TOKEN_LINE="📊 上下文已用 ${TOKENS_K}K / ${PCT}%（窗口 1M，未到 ${COMPACT_PCT}% 不用压）"$'\n\n'
    fi
  fi
fi

jq -n --arg reason "${TOKEN_LINE}${SKIP_PREFIX}${STATIC_REASON}" '{decision:"block", reason:$reason}'
