# Changelog

## 0.1.2 — 2026-05-28

### Module: Watcher

- announce 段 7 标题升级为硬命令句全句风：`解决任何问题必须先找根因，并且根因必须靠真正的证据来决定`
- announce 段 8 标题升级为硬命令句全句风：`解决问题必须用彻底的解决方案，严禁打任何折扣`
- 新增 announce 段 11 `死刑底线`——治理框架顶规则封顶强调
- README.md / README.zh-CN.md 同步:组件表/章节标题/列表 10 段 → 11 段
- slash command 命名引用 `/watcher-off` `/watcher-on` → `/watcher:watcher-off` `/watcher:watcher-on`（修 0.1.1 命名引用 bug，跟实际 plugin 加载形态对齐）
- 段内 bullet 内容不变,只升级段标语气

## 0.1.1 — 2026-05-28

### Module: Watcher
- Per-project Stop hook toggle: `/watcher:watcher-off` and `/watcher:watcher-on` slash commands
- Stop hook reads `cwd` from stdin and skips reminder if `<cwd>/.watcher/.stop-disabled` exists
- UserPromptSubmit announce rules remain active when Stop reminder is toggled off

## 0.1.0 — 2026-05-15

Initial release.

### Module: Watcher
- `UserPromptSubmit` hook: Pre-turn 4-step intent guard
- `Stop` hook: Knowledge audit reminder + root-cause review trigger
- `watcher` skill (two modes: audit / configure)
- Project-level config support via `<project>/.watcher/` (3 files: project-summary / doc-inventory / watchlist)
