---
name: watcher-on
description: 重新开启当前项目每轮收尾自动跑的 watcher 审计（项目级）
command: true
---

# 重新开启当前项目每轮收尾自动跑的 watcher 审计

直接执行以下操作，不要询问、不要复述、不要发起其他工具调用：

1. 用 Bash 工具跑（把 audit-state.json 的 enable-audit 写成 true，保留已攒的 unaudited-rounds；文件不存在就建）：

```bash
mkdir -p .watcher
if [ -f .watcher/audit-state.json ]; then
  tmp=$(jq '.["enable-audit"]=true' .watcher/audit-state.json) && printf '%s\n' "$tmp" > .watcher/audit-state.json
else
  jq -n '{"enable-audit":true,"unaudited-rounds":0}' > .watcher/audit-state.json
fi
rm -f .watcher/.stop-disabled .watcher/.skip-count
```

2. 给用户一句话回话：「✅ 已开 — 当前项目每轮收尾的 watcher 自动审计已恢复。」

## 行为说明

- 把 `<当前项目>/.watcher/audit-state.json` 的 `enable-audit` 字段改成 `true`（文件不存在就建，默认审）
- Stop hook 读到 `enable-audit=true` → 恢复每轮 block + audit 提醒；若 off 期间攒了 `unaudited-rounds`，下次 audit 会一并补审
- 顺手清掉旧版 `.stop-disabled` / `.skip-count`（已被 `audit-state.json` 取代）
- 不影响其他项目
