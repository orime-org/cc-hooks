#!/usr/bin/env python3
"""Display the current root-session plan inside its owned WezTerm pane.

Character-cell clipping and curses drawing derive from multi-cc-im's
scripts/task-panel.py. See third-party/multi-cc-im.LICENSE for its MIT license.
"""

import argparse
import curses
from datetime import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import unicodedata

from task_panel_store import Store, StoreError, binding_key
from task_panel_layout import Height, desired_height, visible_capacity


class PanelError(ValueError):
    """The terminal pane could not be queried safely."""


class BindingChanged(Exception):
    """The displayed binding was replaced during terminal IO."""


def _characters(text):
    for char in str(text):
        category = unicodedata.category(char)
        if category.startswith("C"):
            continue
        cells = 0 if category in ("Mn", "Me") else (
            2 if unicodedata.east_asian_width(char) in ("W", "F") else 1)
        yield char, cells


def cell_width(text):
    return sum(cells for _, cells in _characters(text))


def clip(text, width):
    """Clip sanitized text by terminal cells and mark omitted characters."""
    if width <= 0:
        return ""
    characters = list(_characters(text))
    first = next((index for index, (_, cells) in enumerate(characters) if cells), len(characters))
    characters = characters[first:]
    truncated = sum(cells for _, cells in characters) > width
    limit = width - 1 if truncated else width
    result, used = [], 0
    for char, cells in characters:
        if used + cells > limit:
            break
        result.append(char)
        used += cells
    return "".join(result) + ("…" if truncated else "")


def render_frame(binding, plan, height, width, offset=0, error=None, manual=False):
    """Keep title and range visible while selecting a scrollable task window."""
    height, width = max(0, height), max(0, width - 1)
    items = plan["plan"] if plan else []
    total = len(items)
    capacity = visible_capacity(height)
    offset = max(0, min(offset, max(0, total - max(1, capacity))))
    done = sum(item["status"] == "completed" for item in items)
    title = binding.get("project_title") or (plan["title"] if plan else "Codex")
    header = f"任务 {done}/{total} · {title}"
    if error == "plan":
        status = "无法读取已保存的任务，修复缓存后自动重试"
    elif error == "terminal":
        status = "无法连接 WezTerm，正在重试"
    elif error == "binding":
        status = "无法读取任务面板绑定，正在重试"
    elif error == "height":
        status = "无法读取面板尺寸，正在重试" if manual else "高度调整失败，正在重试"
    elif plan:
        try:
            saved = datetime.fromtimestamp(plan["updated_at"]).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            saved = "时间超出显示范围"
        status = f"已保存计划 {saved}"
    elif binding.get('session_confirmed') is False:
        status = '等待当前会话信息'
    else:
        status = "等待首次计划更新"
    connection = {"absent": "等待连接", "starting": "连接中", "closed": "已关闭",
                  "ended": "会话已结束", "error": "连接异常"}.get(binding.get("state"), "已连接")
    if error == "terminal":
        connection = "连接中断"
    elif error == "binding":
        connection = "连接状态未知"
    status = f"{connection} · {status}"
    first = offset + 1 if total and capacity else 0
    last = min(total, offset + capacity) if capacity else 0
    mode = "" if manual is None else " · 手动 · a自动" if manual else " · 自动 · m手动"
    footer = f"{first}–{last}/{total}{mode} · ↑↓滚动 PgUp/PgDn 翻页 q关闭"
    hidden = total - (last - first + 1 if first else 0)
    if hidden:
        prefix = f"… 还有 {hidden} 条 · "
        if cell_width(prefix + f"{first}–{last}/{total}") <= width:
            footer = prefix + footer
        else:
            footer = f"{first}–{last}/{total} · … +{hidden}"
    if error == "height":
        diagnostic = "无法读取面板尺寸，正在重试" if manual else "高度调整失败，正在重试"
        footer = f"{diagnostic} · {footer}"
    footer += " · 先点面板"
    if height == 0:
        lines = []
    elif height == 1:
        lines = [header]
    elif height == 2:
        lines = [header, footer]
    else:
        symbols = {"completed": "[x] 已完成 ·", "in_progress": "[>] 进行中 ·", "pending": "[ ] 待处理 ·"}
        tasks = [symbols[item["status"]] + " " + item["step"] for item in items[offset:offset + capacity]]
        lines = [header, status, *tasks]
        lines.extend([""] * (height - 1 - len(lines)))
        lines.append(footer)
    return [clip(line, width) for line in lines], offset, capacity


def cli_command(arguments):
    return [os.environ.get("CC_HOOKS_WEZTERM") or "wezterm", "cli", "--no-auto-start", *arguments]


def parent_exists(socket, parent):
    environment = dict(os.environ, WEZTERM_UNIX_SOCKET=socket)
    try:
        result = subprocess.run(cli_command(["list", "--format", "json"]),
                                env=environment, capture_output=True, text=True, timeout=1, check=True)
        panes = json.loads(result.stdout)
        if not isinstance(panes, list) or any(
                not isinstance(pane, dict) or type(pane.get("pane_id")) not in (int, str)
                or not re.fullmatch(r"[0-9]{1,20}", str(pane["pane_id"])) for pane in panes):
            raise ValueError("Invalid WezTerm pane list")
        return any(str(pane["pane_id"]) == parent for pane in panes)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise PanelError("Cannot query the parent pane") from error


class Panel:
    def __init__(self, store, key, nonce, socket, parent):
        self.store, self.key, self.nonce = store, key, nonce
        self.socket, self.parent = socket, parent
        self.stop_requested = False
        self.last_attachment = None
        self.height = Height()
        if binding_key(socket, parent) != key or not re.fullmatch(r"[a-f0-9]{32}", nonce):
            raise PanelError("Invalid pane ownership identity")

    def owns(self, record):
        return bool(record and record["nonce"] == self.nonce
                    and record["socket"] == self.socket and record["parent_pane"] == self.parent)

    def ready(self, pane):
        if not isinstance(pane, str) or not re.fullmatch(r"[0-9]{1,20}", pane):
            raise PanelError("Invalid task pane identifier")
        with self.store.binding_transaction(self.key, time.monotonic() + 1) as transaction:
            record = transaction.read()
            if not self.owns(record) or record["state"] == "closed":
                return False
            record["panel_pane"] = pane
            record["ready_nonce"] = self.nonce
            if record["state"] != "ended":
                record["state"] = "visible"
            transaction.write(record)
            self.last_attachment = record["attachment_id"]
        return True

    def close(self, attachment):
        with self.store.binding_transaction(self.key, time.monotonic() + 1) as transaction:
            record = transaction.read()
            if not self.owns(record) or record["attachment_id"] != attachment:
                return False
            record["state"] = "closed"
            transaction.write(record)
        return True

    def parent_alive(self):
        if parent_exists(self.socket, self.parent):
            return True
        with self.store.binding_transaction(self.key, time.monotonic() + 1) as transaction:
            if self.owns(transaction.read()):
                transaction.delete()
        return False

    def finish(self):
        try:
            if not self.parent_alive():
                return
        except PanelError:
            print("无法确认 WezTerm 父面板状态，已保留任务面板绑定。", file=sys.stderr)
        if self.last_attachment is not None:
            self.close(self.last_attachment)

    def request_stop(self, number, frame):
        self.stop_requested = True

    def current(self, binding):
        latest = self.store.read_binding(self.key)
        return (self.owns(latest) and latest["state"] != "closed"
                and all(latest[field] == binding[field]
                        for field in ("attachment_id", "session_id", "panel_pane")))

    def fit_height(self, binding, plan):
        pane_id = binding.get("panel_pane")
        if pane_id is None:
            return True
        deadline = time.monotonic() + 5
        environment = dict(os.environ, WEZTERM_UNIX_SOCKET=self.socket)

        def call(arguments):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PanelError("Pane height update timed out")
            try:
                return subprocess.run(cli_command(arguments),
                                      env=environment, capture_output=True, text=True,
                                      timeout=remaining, check=True).stdout
            except (OSError, subprocess.SubprocessError, UnicodeError) as error:
                raise PanelError("Cannot update the task pane height") from error

        def geometry():
            try:
                panes = json.loads(call(["list", "--format", "json"]))
                parent = next(pane for pane in panes if str(pane["pane_id"]) == self.parent)
                pane = next(pane for pane in panes if str(pane["pane_id"]) == pane_id
                            and pane["title"] == "cc-hooks-task-panel:" + self.nonce
                            and pane["window_id"] == parent["window_id"] and pane["tab_id"] == parent["tab_id"])
                size = pane["size"]
                if any(type(size[key]) is not int or size[key] < 1 for key in ("rows", "cols")):
                    raise ValueError("Invalid pane dimensions")
                return size["rows"], size["cols"]
            except (ValueError, TypeError, KeyError, StopIteration) as error:
                raise PanelError("Cannot identify the owned task pane dimensions") from error

        def resize(delta):
            if not self.current(binding):
                raise BindingChanged()
            call(["adjust-pane-size", "--pane-id", pane_id, "--amount", str(abs(delta)),
                  "Up" if delta > 0 else "Down"])
            return geometry()

        if not self.current(binding):
            return False
        try:
            self.height.fit((binding["session_id"], binding["attachment_id"]), geometry(), desired_height(plan), resize)
        except BindingChanged:
            return False
        return self.current(binding)


def show_panel(screen, panel):
    """Refresh the current binding and task window after keys and resizes."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    if hasattr(screen, "keypad"):
        screen.keypad(True)
    screen.timeout(1000)
    offset, identity, previous = 0, None, None
    height_request, height_error = None, False
    height_retry_at, height_retry_delay = 0, 2
    while True:
        if panel.stop_requested:
            panel.finish()
            return
        refresh_deadline = time.monotonic() + 1
        plan, error = None, None
        try:
            binding = panel.store.read_binding(panel.key)
            if not panel.owns(binding) or binding["state"] == "closed":
                return
            previous = binding
        except StoreError:
            if previous is None:
                previous = {"session_id": "Codex", "attachment_id": "", "state": "error"}
            binding, error = previous, "binding"
        target = (binding["session_id"], binding["attachment_id"])
        if identity != target:
            offset, identity = 0, target
            panel.height.attach(target)
            height_request, height_error = None, False
            height_retry_at, height_retry_delay = 0, 2
        try:
            plan = panel.store.read_plan(binding["session_id"])
        except StoreError:
            error = error or "plan"
        if error != "binding":
            request = (target, desired_height(plan), screen.getmaxyx(), panel.height.manual)
            if time.monotonic() >= height_retry_at and (request != height_request or height_error):
                try:
                    if not panel.fit_height(binding, plan):
                        continue
                except (PanelError, StoreError):
                    height_error = True
                    height_retry_at = time.monotonic() + height_retry_delay
                    height_retry_delay = min(30, height_retry_delay * 2)
                else:
                    height_request = (target, desired_height(plan), screen.getmaxyx(), panel.height.manual)
                    height_error = False
                    height_retry_at, height_retry_delay = 0, 2
            if height_error:
                error = error or "height"
        screen.erase()
        height, width = screen.getmaxyx()
        lines, offset, capacity = render_frame(binding, plan, height, width, offset, error, panel.height.manual)
        if error != "binding":
            panel.last_attachment = binding["attachment_id"]
        for row, line in enumerate(lines):
            try:
                screen.addstr(row, 0, line)
            except curses.error:
                # Resizes can invalidate the dimensions used to build this frame.
                break
        screen.refresh()
        screen.timeout(max(0, min(1000, round((refresh_deadline - time.monotonic()) * 1000))))
        key = screen.getch()
        if panel.stop_requested:
            continue
        if key in (ord("q"), ord("Q")):
            try:
                if panel.close(binding["attachment_id"]):
                    return
            except StoreError:
                continue
        elif key in (ord("m"), ord("M"), ord("a"), ord("A")):
            panel.height.choose(target, key in (ord("m"), ord("M")))
            height_request, height_error = None, False
            height_retry_at, height_retry_delay = 0, 2
        elif key == curses.KEY_DOWN:
            offset += 1
        elif key == curses.KEY_UP:
            offset = max(0, offset - 1)
        elif key == curses.KEY_NPAGE:
            offset += max(1, capacity)
        elif key == curses.KEY_PPAGE:
            offset = max(0, offset - max(1, capacity))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    previous_handlers = {}
    try:
        panel = Panel(Store(args.data_dir), args.binding, args.nonce, args.socket, args.parent)
        if args.once:
            binding = panel.store.read_binding(panel.key)
            if not panel.owns(binding):
                return 0
            try:
                plan, error = panel.store.read_plan(binding["session_id"]), None
            except StoreError:
                plan, error = None, "plan"
            size = shutil.get_terminal_size((100, 24))
            lines, _, _ = render_frame(binding, plan, size.lines, size.columns, error=error, manual=None)
            print("\n".join(lines))
            return 0
        for number in (signal.SIGHUP, signal.SIGTERM):
            previous_handlers[number] = signal.signal(number, panel.request_stop)
        print(f"\033]2;cc-hooks-task-panel:{panel.nonce}\007", end="", flush=True)
        if not panel.ready(os.environ.get("WEZTERM_PANE")):
            return 0
        curses.wrapper(show_panel, panel)
    except KeyboardInterrupt:
        try:
            panel.finish()
        except (StoreError, UnboundLocalError):
            pass
    except (StoreError, PanelError, curses.error):
        print("任务面板无法启动，请检查缓存目录、Python curses 与 WezTerm 后重新打开或恢复 Codex。", file=sys.stderr)
        return 1
    finally:
        for number, handler in previous_handlers.items():
            signal.signal(number, handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
