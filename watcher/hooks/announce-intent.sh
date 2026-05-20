#!/bin/bash
# UserPromptSubmit hook: Pre-turn 行动意图守卫
# 每次用户提交 prompt 时注入提醒，让 Claude 行动前先复述用户需求 + 告知意图
# plain stdout 注入为 <system-reminder>，Claude 当前 turn 看到（不进 transcript）

set -u

LOG=/tmp/cc-prompt-submit.log
TS=$(date '+%Y-%m-%d %H:%M:%S')

INPUT=$(cat)
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
PROMPT=$(printf '%s' "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
PROMPT_LEN=${#PROMPT}

# 日志（只记长度不记内容，避免泄漏 + 不浪费日志容量）
printf '[%s] session=%s prompt_len=%d status=inject\n' "$TS" "${SESSION:-?}" "$PROMPT_LEN" >> "$LOG"

# plain stdout → CC 自动注入为 <system-reminder>
cat <<'EOF'
🎯 [Pre-turn] 必先 4 步：复述需求 → 分析本质（找根本，非表象）→ 给彻底方案（无法时明示临时）→ 告知意图。再按动作：
(1) 查询：答。
(2) 1 处工具：先说要用啥工具，再动手。
(3) 多处工具：列计划（含 skill / 工具清单）等确认。
(4) 调 skill / Task：先说调哪个，按其流程走。

📝 表达原则：精确不话痨——关键词 > 长句；emoji > 完整描述；3+ 同结构项强制 markdown 表格（`| col | col |`），禁字段:值多行 list / lettered list 模拟表格。

🛑 让用户拍板时：① 选项必须彻底方案（不同根本路径），禁 workaround / 补丁；② **说人话**——禁术语/缩写/内部代号，每选项写"做什么 + 后果"+ 标推荐 + 一句理由；③ **编号只用 A/B/C**（子项 `A.1` `A.2`），禁 Alpha/Beta、希腊字母（α/β/γ）、罗马数字（I/II/III）、带圈数字（①②③）。
EOF
