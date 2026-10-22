---
name: watcher-off
description: 关掉当前项目每轮收尾自动跑的 watcher 审计（项目级）
---

# 关掉当前项目每轮收尾自动跑的 watcher 审计

## 平台对照

本 skill 在 Claude Code 和 Codex 里都会用到。正文按 Claude Code 的说法写，在 Codex 里按下表换成对应的东西：

| 正文里的写法 | 在 Codex 里 |
|---|---|
| Claude Code、CC | Codex |
| Read、Edit、Write、Bash 工具 | 用 `exec_command` 读文件和跑命令，用 `apply_patch` 改文件 |
| WebSearch、WebFetch | 联网搜索 |
| workflow | 用 `spawn_agent` 派子代理；判对抗是否跑成，看每个子代理的 `wait` 结果都是 completed、没有报错（对应 `agents_error`、`agents_done`、`agent_count`） |
| Monitor | 用 `gh pr checks <N> --watch` 盯 CI，用 `gh pr view <N> --json state,mergeStateStatus,reviewDecision` 看合并和 review |
| `/watcher:xxx`、`/watcher` | `$watcher:xxx`、`$watcher:watcher` |
| `CLAUDE.md` | `AGENTS.md` |
| `${CLAUDE_SKILL_DIR}` | 本 SKILL.md 所在目录的绝对路径 |
| Skill 工具 | 读对应 skill 的 SKILL.md |

直接执行以下操作，不要询问、不要复述、不要发起其他工具调用：

1. 用 Bash 工具跑（把 audit-state.json 的 enable-audit 写成 false，保留已攒的 unaudited-rounds；文件不存在就建）：

```bash
mkdir -p .watcher
if [ -f .watcher/audit-state.json ]; then
  tmp=$(jq '.["enable-audit"]=false' .watcher/audit-state.json) && printf '%s\n' "$tmp" > .watcher/audit-state.json
else
  jq -n '{"enable-audit":false,"unaudited-rounds":0}' > .watcher/audit-state.json
fi
rm -f .watcher/.stop-disabled .watcher/.skip-count
```

2. 给用户一句话回话：「✅ 已关 — 当前项目每轮收尾的 watcher 自动审计已停。重新打开请用 `/watcher:watcher-on`。」

## 行为说明

- 把 `<当前项目>/.watcher/audit-state.json` 的 `enable-audit` 字段改成 `false`（**不删文件**——文件在才代表「这个项目已配置 watcher」，跟「文件找不到 = 路径错/未配」区分开）
- Stop hook (`suggest-watcher.sh`) 读到 `enable-audit=false` → 只显示 token/时间/未审轮次状态、不 audit
- off 期间照样每轮把 `unaudited-rounds` +1，`/watcher:watcher-on` 恢复后一并补审
- 顺手清掉旧版 `.stop-disabled` / `.skip-count`（已被 `audit-state.json` 取代）
- 不影响 `UserPromptSubmit` 的 announce 规则注入，也不影响其他项目
