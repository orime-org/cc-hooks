#!/bin/bash
# Dispatch Codex panel events with an actionable runtime prerequisite check.
set -u

[ "${1:-}" = "codex" ] || exit 0

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' '{"systemMessage":"自动任务面板需要 Python 3.11 或更新版本。请安装 Python 后重新打开或恢复 Codex。"}'
  exit 0
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
  printf '%s\n' '{"systemMessage":"自动任务面板需要 Python 3.11 或更新版本。请安装匹配版本后重新打开或恢复 Codex。"}'
  exit 0
fi

HOOK_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$HOOK_DIR/task_panel_hook.py"
