"""Install the WezTerm integration for native Codex task events."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile

BEGIN = "-- BEGIN cc-hooks task panel"
END = "-- END cc-hooks task panel"
ASSETS = ("task_panel.py", "task_panel_store.py", "task_panel_layout.py", "task_panel_session.py",
          "task_panel_binding.py", "task_panel_process.py", "task_panel_launch.py", "task-panel-wezterm.lua")


def sync_runtime(data):
    target = Path(data) / "task-panel-integration"
    if not (target / "loader.lua").exists():
        return
    source = Path(__file__).parent
    for name in ASSETS:
        content = (source / name).read_bytes()
        destination = target / name
        if not destination.exists() or destination.read_bytes() != content:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target, prefix="." + name + "-", suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                temporary.replace(destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def lua_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def configure_wezterm(text, loader):
    block = BEGIN + "\ndofile(" + lua_string(loader) + ")\n" + END
    if BEGIN in text:
        return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, count=1, flags=re.S)
    return block + "\n" + (text or "return {}\n")


def replace_with_backup(path, content):
    previous = path.read_text() if path.exists() else None
    if previous == content:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if previous is not None:
        backup = path.with_name(path.name + ".cc-hooks-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
        backup.write_text(previous)
        backup.chmod(0o600)
    temporary = path.with_name(path.name + ".cc-hooks.tmp")
    temporary.write_text(content)
    temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    temporary.replace(path)
    return str(backup) if backup else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--wezterm-config", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    home = args.codex_home.expanduser().absolute()
    data = (args.data_dir or home / "plugins/data/watcher-orime").expanduser().absolute()
    config = home / "config.toml"
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "wezterm/wezterm.lua"
    terminal = (args.wezterm_config or (xdg if xdg.exists() else Path.home() / ".wezterm.lua")).expanduser().absolute()
    target = data / "task-panel-integration"
    try:
        terminal_text = configure_wezterm(terminal.read_text() if terminal.exists() else "", target / "loader.lua")
        result = {"codex_config": str(config), "wezterm_config": str(terminal), "data_dir": str(data),
                  "check_only": args.check}
        if not args.check:
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            loader = "local panel = dofile(" + lua_string(target / "task-panel-wezterm.lua") + ")\n"
            loader += "panel.setup { python = " + lua_string(sys.executable) + ", hooks = " + lua_string(target)
            loader += ", data_dir = " + lua_string(data) + " }\n"
            (target / "loader.lua").write_text(loader)
            sync_runtime(data)
            result["codex_backup"] = None
            result["wezterm_backup"] = replace_with_backup(terminal, terminal_text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"任务面板配置失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
