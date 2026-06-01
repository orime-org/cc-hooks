---
name: watcher-on
description: 重新开启当前项目每轮收尾自动跑的 watcher 审计（项目级）
command: true
---

# 重新开启当前项目每轮收尾自动跑的 watcher 审计

直接执行以下操作，不要询问、不要复述、不要发起其他工具调用：

1. 用 Bash 工具跑：`rm -f .watcher/.stop-disabled`
2. 给用户一句话回话：「✅ 已开 — 当前项目每轮收尾的 watcher 自动审计已恢复。」

## 行为说明

- 删除 `<当前项目>/.watcher/.stop-disabled` 标记文件（不存在也无所谓，幂等）
- Stop hook 恢复正常 block + reason 流程，下轮结束自动提醒调 watcher skill
- 不影响其他项目
