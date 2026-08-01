---
name: watcher-configure
description: 建/改当前项目的 .watcher/ 审计配置（项目级三件套）
command: true
---

# 建/改当前项目的 `.watcher/` 审计配置

跑 `skills/watcher/references/setup-flow.md` 的完整流程，在**当前目录**建或改 `.watcher/` 项目级配置。

**先读那份文档再动手**——它定义了状态分支（首次建 / 局部补全 / 修订）、要问用户哪几个问题、三个文件各写什么。

## 硬约束

- **草稿必须展示给用户，用户回「OK」/「确认」后才用 Write 工具落盘**——禁止跳过确认直接写文件。
- 只动**当前目录**的 `.watcher/`，不碰父目录、不碰其他项目。
- 落盘后**不自动跑 audit**——让用户亲眼看到效果、自己决定何时审查。收尾输出：「已写入 `.watcher/`，请手动输入 `/watcher:watcher` 验证。」

## 建出来的三件套

| 文件 | 内容 |
|---|---|
| `project-summary.md` | 一段话讲清"这是什么项目" |
| `doc-inventory.md` | 这个项目应该有哪些文档 + 改动时的提示 |
| `watchlist.md` | 用户自定义的关注点（随时加 / 改） |

## 跟另外两个命令的关系

| 命令 | 干啥 |
|---|---|
| `/watcher:watcher-configure` | **配置**——建/改 `.watcher/` 三件套（就是本命令） |
| `/watcher:watcher-on` / `-off` | **开关**——本项目每轮收尾自动审计的开 / 关 |
| `/watcher:watcher` | **审计**——手动跑一次知识库审查 |
