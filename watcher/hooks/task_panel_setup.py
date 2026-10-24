"""Install the official Codex status identity and WezTerm panel integration."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib

BEGIN = "-- BEGIN cc-hooks task panel"
END = "-- END cc-hooks task panel"
ASSETS = ("task_panel.py", "task_panel_store.py", "task_panel_layout.py", "task_panel_session.py",
          "task_panel_launch.py", "task-panel-wezterm.lua")


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


def configure_codex(text):
    original = tomllib.loads(text)
    tui = original.get("tui", {})
    updates = {}
    defaults = {"status_line": ["model-with-reasoning", "current-dir", "thread-name"],
                "terminal_title": ["activity", "thread-name", "project-name"]}
    for key, default in defaults.items():
        current = tui.get(key, default)
        if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
            raise ValueError(f"tui.{key} must be an array of strings")
        if key == "status_line":
            updates[key] = ["session-id"] + [item for item in current if item not in ("session-id", "thread-id")]
        else:
            updates[key] = current if any(item in current for item in ("session-id", "thread-id")) else [*current, "session-id"]
    header = re.search(r"(?m)^\[tui\][ \t]*(?:#.*)?$", text)
    if header:
        start = header.end()
        following = re.search(r"(?m)^\[", text[start:])
        end = start + following.start() if following else len(text)
        section = text[start:end]
        for key, items in updates.items():
            assignment = re.search(r"(?m)^" + key + r"\s*=", section)
            replacement = key + " = " + json.dumps(items)
            if assignment:
                position = section.find("\n", assignment.end())
                while True:
                    position = len(section) if position < 0 else position
                    try:
                        tomllib.loads(section[assignment.start():position])
                        break
                    except tomllib.TOMLDecodeError:
                        if position == len(section):
                            raise ValueError(f"Cannot locate tui.{key} assignment")
                        position = section.find("\n", position + 1)
                section = section[:assignment.start()] + replacement + section[position:]
            else:
                section = section.rstrip() + "\n" + replacement + "\n"
        result = text[:start] + section + text[end:]
    else:
        result = text.rstrip() + "\n\n[tui]\n" + "".join(key + " = " + json.dumps(items) + "\n" for key, items in updates.items())
    parsed = tomllib.loads(result)
    expected = dict(original)
    expected["tui"] = dict(tui, **updates)
    if parsed != expected:
        raise ValueError("Codex configuration uses a different TOML layout; existing settings were preserved")
    return result


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
        codex_text = configure_codex(config.read_text() if config.exists() else "")
        terminal_text = configure_wezterm(terminal.read_text() if terminal.exists() else "", target / "loader.lua")
        result = {"codex_config": str(config), "wezterm_config": str(terminal), "data_dir": str(data),
                  "check_only": args.check}
        if not args.check:
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            loader = "local panel = dofile(" + lua_string(target / "task-panel-wezterm.lua") + ")\n"
            loader += "panel.setup { python = " + lua_string(sys.executable) + ", hooks = " + lua_string(target)
            loader += ", data_dir = " + lua_string(data) + ", codex_home = " + lua_string(home) + " }\n"
            (target / "loader.lua").write_text(loader)
            sync_runtime(data)
            result["codex_backup"] = replace_with_backup(config, codex_text)
            result["wezterm_backup"] = replace_with_backup(terminal, terminal_text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"任务面板配置失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
