---
name: watcher-off
description: 关掉当前项目每轮收尾自动跑的 watcher 审计（项目级）
command: true
---

# 关掉当前项目每轮收尾自动跑的 watcher 审计

直接执行以下操作，不要询问、不要复述、不要发起其他工具调用：

1. 用 Bash 工具跑：`mkdir -p .watcher && touch .watcher/.stop-disabled`
2. 给用户一句话回话：「✅ 已关 — 当前项目每轮收尾的 watcher 自动审计已停。重新打开请用 `/watcher:watcher-on`。」

## 行为说明

- 创建 `<当前项目>/.watcher/.stop-disabled` 标记文件
- Stop hook (`suggest-watcher.sh`) 检测到该文件存在 → 直接 exit 0 不阻拦
- 不影响 `UserPromptSubmit` 的 announce 规则注入
- 不影响其他项目（开关是按项目目录走的）
