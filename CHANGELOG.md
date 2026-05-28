# Changelog

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
