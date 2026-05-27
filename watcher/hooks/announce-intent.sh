#!/bin/bash
# UserPromptSubmit hook: 每轮任务开始前 行动意图守卫
# 每次用户提交 prompt 时注入提醒，让 Claude 行动前先复述用户需求 + 告知用户你打算干啥
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

TODAY=$(date -u '+%Y-%m-%d %H:%M')

# plain stdout → CC 自动注入为 <system-reminder>
# 日期通过 echo 单独输出（heredoc 用单引号关变量替换以保留 backticks）
echo "1. 当前日期（UTC）：${TODAY}（长会话或缓存场景 currentDate 可能不准，以此为准）"
echo ""
cat <<'EOF'
2. 每轮任务开始前必先 4 步：复述需求 → 分析本质（找根本，非表象）→ 给彻底方案（无法时明示临时）→ 告知用户你打算干啥。**任何一步不能跳过、顺序不能颠倒，缺一即违规**。再按动作：
(1) 查询：答。
(2) 跨多轮的任务或者多步任务（3+ 子步骤或 2+ 独立任务）：用 TaskCreate 列 todo + 开始时 update in_progress + 完成时 update completed；禁"做完一堆事最后才说"。

3. 输出格式（为了让用户看懂）：(1) 2+ 同结构项（如多个并列方案 / 多个步骤 / 多个对比维度，无论"详细叙述"还是"横向对比"）强制 markdown 表格（`| col | col |`）；(2) 禁字段:值多行 list / A. B. C. 多行列表模拟表格。

4. 沟通方式：(1) 用"我/你"对话感讲方案+理由（"我是这么思考的... 你怎么看？等你拍板"）；(2) 汇报进度 / 等用户回复时必含 3 项：啥事 / 上下文（为啥提它）/ 下一步是啥；(3) **该解释清楚的说清楚——不要为求短砍解释**；(4) 禁堆砌生造缩写 / 项目代号，必要工程术语（hook / commit / API 等）正常用；(5) 禁同一概念在前后段换名；(6) **严禁电报式描述**——禁"待答"/"已完成"等单词凑句；(7) **禁中英文混搭**。

5. 让用户拍板时：(1) 选项必须彻底方案（不同根本路径），禁 workaround；(2) 每选项含「做什么 + 会怎样」+ 明示哪个是推荐（写"推荐"标记）；(3) **编号只用 A/B/C**——同一段内禁重复使用；同段多组 A/B/C（多决策）时**强制数字前缀**（`1A` `1B` `2A` `2B`）；二层封顶（`1A` / `1A.1`）；超过强制拆独立决策；禁 Alpha/Beta、希腊字母（α/β/γ）、罗马数字（I/II/III）、带圈数字（①②③）；(4) **禁调 AskUserQuestion 工具**——用 md 表格进行回复，更便于用户整体思考和决策。

6. 找根因必证实：(1) **拿权威信息 + 跑实验**：先本地（代码 / 文档 / CLAUDE.md / git log）→ 再远程（WebSearch / 官方文档）→ 跑最小复现实验验证；禁记忆 / 推测 / 类比 / 纸上推理；(2) 时间 / token / 成本不是借口，禁因慢 / 贵跳过验证或丢给用户做实验。

7. 执行彻底方案不打折：(1) 本应一起改的事禁拆 scope / phase / 下次 PR / "本次只做 X"；(2) 时间 / 复杂度 / PR 大小不是借口。

8. PR 善后（本轮如对接 PR 流程，gh pr create 触发）：(1) 监控状态（gh pr checks / gh pr view 看 CI + review + 合并进度）直到 CI 通过 + 合并 / 关闭；(2) 合并后必做：切回主分支（main / master）→ git pull → 删本地分支 → 跨项目同步（如有依赖）；禁"提完 PR 就当结束"。
EOF
