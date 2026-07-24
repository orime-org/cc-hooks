---
name: watcher-off
description: 关掉当前项目每轮收尾自动跑的 watcher 审计（项目级）
command: true
---

# 关掉当前项目每轮收尾自动跑的 watcher 审计

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
