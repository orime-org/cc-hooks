#!/usr/bin/env python3
"""Exercise task-pane rendering, input and binding ownership."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / "watcher" / "hooks"
sys.path.insert(0, str(HOOKS))
from task_panel_store import Store, binding_key

spec = importlib.util.spec_from_file_location("task_panel", HOOKS / "task_panel.py")
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)


class Screen:
    def __init__(self, events, size=(8, 70), action=None):
        self.events = iter(events)
        self.size, self.action = size, action
        self.frames, self.lines = [], []

    def timeout(self, milliseconds):
        self.delay = milliseconds

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.lines = []

    def addstr(self, row, column, text):
        self.lines.append((row, text))

    def refresh(self):
        self.frames.append(list(self.lines))

    def getch(self):
        event = next(self.events)
        if callable(event):
            event(self)
            return viewer.curses.KEY_RESIZE
        if self.action:
            self.action(event)
        return event


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.socket, self.parent, self.nonce = "/tmp/viewer-test.sock", "13", "a" * 32
        self.key = binding_key(self.socket, self.parent)
        self.record = dict(version=1, socket=self.socket, parent_pane=self.parent,
                           panel_pane=None, session_id="root-a", attachment_id="attach-a",
                           nonce=self.nonce, state="starting", starting_created_at=1,
                           starting_deadline=5)
        self.write_binding(self.record)
        self.panel = viewer.Panel(self.store, self.key, self.nonce, self.socket, self.parent)

    def write_binding(self, record):
        with self.store.binding_transaction(self.key) as transaction:
            transaction.write(record)

    def save(self, count=12):
        self.store.save_plan("root-a", "中文项目", [dict(step=f"任务 {n}", status=
                             "completed" if n == 0 else "pending") for n in range(count)], 1780000000)

    def test_clip_uses_terminal_cells_marks_and_safe_text(self):
        for text, width, expected in [("中文ABC", 5, "中文…"), ("e\u0301中", 3, "e\u0301中"),
                                      ("\x1b[31mA\nB\t", 20, "[31mAB"),
                                      ("中文", 1, "…"), ("text", 0, ""),
                                      ("\u0301A", 2, "A"), ("\u200d字", 2, "字")]:
            with self.subTest(text=text, width=width):
                self.assertEqual(viewer.clip(text, width), expected)

    def test_cli_uses_the_terminal_executable_under_a_minimal_path(self):
        executable = "/Applications/WezTerm.app/Contents/MacOS/wezterm"
        self.assertTrue(self.panel.ready("14"))
        record = self.store.read_binding(self.key)
        panes = [{"pane_id": 13, "window_id": 1, "tab_id": 1},
                 {"pane_id": 14, "window_id": 1, "tab_id": 1,
                  "title": "cc-hooks-task-panel:" + self.nonce, "size": {"rows": 3, "cols": 100}}]
        result = subprocess.CompletedProcess([], 0, json.dumps(panes), "")
        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "CC_HOOKS_WEZTERM": executable}, clear=True), \
                patch.object(viewer.subprocess, "run", return_value=result) as run:
            self.assertTrue(viewer.parent_exists(self.socket, self.parent))
            self.assertTrue(self.panel.fit_height(record, None))
        self.assertEqual([call.args[0][0] for call in run.call_args_list], [executable, executable])

    def test_frame_shows_chinese_states_timestamp_and_range(self):
        self.save()
        lines, offset, capacity = viewer.render_frame(self.record, self.store.read_plan("root-a"), 8, 90)
        self.assertIn("中文项目", lines[0])
        self.assertIn("1/12", lines[0])
        self.assertIn("已保存计划", lines[1])
        self.assertIn("2026", lines[1])
        self.assertIn("1–4/12", lines[-1])
        self.assertTrue(lines[2].startswith("[x]"))
        self.assertIn("已完成", lines[2])
        self.assertEqual((offset, capacity), (0, 4))
        waiting, _, _ = viewer.render_frame(self.record, None, 5, 90)
        self.assertIn("等待首次计划更新", " ".join(waiting))
        ended, _, _ = viewer.render_frame(dict(self.record, state="ended"), None, 5, 90)
        self.assertIn("会话已结束", " ".join(ended))
        failed, _, _ = viewer.render_frame(self.record, None, 5, 90, error="plan")
        self.assertIn("无法读取已保存的任务", " ".join(failed))

    def test_all_statuses_and_empty_plan_are_visible(self):
        plan = dict(title="项目", updated_at=0, plan=[dict(step="一个任务", status=status)
                    for status in ("pending", "in_progress", "completed")])
        lines, _, _ = viewer.render_frame(self.record, plan, 7, 80)
        for status in ("待处理", "进行中", "已完成"):
            self.assertIn(status, " ".join(lines))
        empty, _, _ = viewer.render_frame(self.record, dict(plan, plan=[]), 4, 80)
        self.assertIn("0–0/0", empty[-1])
        self.assertIn("已保存计划", empty[1])

    def test_small_sizes_keep_title_and_visible_range(self):
        self.save()
        for height in range(0, 5):
            lines, offset, capacity = viewer.render_frame(self.record, self.store.read_plan("root-a"), height, 18, 100)
            self.assertLessEqual(len(lines), height)
            if height:
                self.assertIn("任务", lines[0])
            if height >= 2:
                self.assertIn("/12", lines[-1])
            for line in lines:
                self.assertLessEqual(viewer.cell_width(line), 17)

    def test_ready_adopts_current_session_and_preserves_ended(self):
        self.write_binding(dict(self.record, session_id="root-b", attachment_id="attach-b", state="ended"))
        self.assertTrue(self.panel.ready("14"))
        record = self.store.read_binding(self.key)
        self.assertEqual((record["session_id"], record["state"], record["panel_pane"]), ("root-b", "ended", "14"))

    def test_ready_persists_confirmation_for_its_exact_instance(self):
        self.assertTrue(self.panel.ready("14"))
        record = self.store.read_binding(self.key)
        self.assertEqual(record["ready_nonce"], self.nonce)
        self.assertEqual(record["panel_pane"], "14")
        with self.assertRaises(ValueError):
            self.write_binding(dict(record, nonce="b" * 32))

    def test_empty_frames_keep_project_session_and_connection_identity(self):
        binding = dict(self.record, project_title="中文项目")
        for state, connection in (("visible", "已连接"), ("starting", "连接中"),
                                  ("ended", "会话已结束"), ("error", "连接异常"),
                                  ("absent", "等待连接"), ("closed", "已关闭")):
            with self.subTest(state=state):
                lines, _, _ = viewer.render_frame(dict(binding, state=state), None, 10, 120)
                self.assertIn("中文项目", lines[0])
                self.assertIn("会话 root-a", lines[1])
                self.assertIn(connection, lines[1])
                self.assertIn("等待首次计划更新", lines[1])

    def test_binding_identity_survives_plan_and_terminal_errors(self):
        binding = dict(self.record, state="visible", project_title="当前项目")
        plan = dict(title="旧项目", updated_at=1780000000, plan=[])
        for error, connection in ((None, "已连接"), ("plan", "已连接"),
                                  ("terminal", "连接中断"), ("binding", "连接状态未知")):
            with self.subTest(error=error):
                lines, _, _ = viewer.render_frame(binding, plan, 10, 150, error=error)
                self.assertIn("当前项目", lines[0])
                self.assertIn("会话 root-a", lines[1])
                self.assertIn(connection, lines[1])

    def test_late_ready_and_close_leave_new_instance_untouched(self):
        self.write_binding(dict(self.record, nonce="b" * 32))
        self.assertFalse(self.panel.ready("14"))
        self.assertFalse(self.panel.close("attach-a"))
        self.assertEqual(self.store.read_binding(self.key)["nonce"], "b" * 32)

    def test_closed_ready_and_wrong_parent_are_rejected(self):
        self.write_binding(dict(self.record, state="closed"))
        self.assertFalse(self.panel.ready("14"))
        with self.assertRaises(viewer.PanelError):
            viewer.Panel(self.store, self.key, self.nonce, self.socket, "99")

    def test_close_is_scoped_to_displayed_attachment(self):
        self.write_binding(dict(self.record, attachment_id="attach-b"))
        self.assertFalse(self.panel.close("attach-a"))
        self.assertTrue(self.panel.close("attach-b"))
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_parent_gone_deletes_only_own_binding(self):
        with patch.object(viewer, "parent_exists", return_value=False):
            self.assertFalse(self.panel.parent_alive())
        self.assertIsNone(self.store.read_binding(self.key))
        self.write_binding(dict(self.record, nonce="b" * 32))
        with patch.object(viewer, "parent_exists", return_value=False):
            self.panel.parent_alive()
        self.assertIsNotNone(self.store.read_binding(self.key))

    def test_cli_uses_explicit_socket_and_distinguishes_fault_from_absence(self):
        with patch.object(viewer.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '[{"pane_id":13}]', "")) as run:
            self.assertTrue(viewer.parent_exists(self.socket, self.parent))
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["wezterm", "cli", "--no-auto-start", "list", "--format", "json"])
            self.assertEqual(kwargs["env"]["WEZTERM_UNIX_SOCKET"], self.socket)
            self.assertLessEqual(kwargs["timeout"], 1)
        with patch.object(viewer.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '[]', "")):
            self.assertFalse(viewer.parent_exists(self.socket, self.parent))
        for payload in ('{}', '[{}]', 'broken'):
            with patch.object(viewer.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, payload, "")):
                with self.assertRaises(viewer.PanelError):
                    viewer.parent_exists(self.socket, self.parent)
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("wezterm", 1),
                      subprocess.CalledProcessError(1, "wezterm")):
            with patch.object(viewer.subprocess, "run", side_effect=error):
                with self.assertRaises(viewer.PanelError):
                    viewer.parent_exists(self.socket, self.parent)

    def test_keyboard_scroll_resize_refresh_and_close(self):
        self.save()
        screen = Screen([viewer.curses.KEY_DOWN, viewer.curses.KEY_NPAGE,
                         viewer.curses.KEY_PPAGE, viewer.curses.KEY_UP,
                         lambda s: setattr(s, "size", (3, 32)), ord("q")])
        with patch.object(viewer, "parent_exists", return_value=True), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(screen, self.panel)
        self.assertGreaterEqual(screen.delay, 0)
        self.assertLessEqual(screen.delay, 1000)
        footers = [frame[-1][1] for frame in screen.frames]
        self.assertIn("1–4/12", footers[0])
        self.assertIn("2–5/12", footers[1])
        self.assertIn("6–9/12", footers[2])
        self.assertIn("2–5/12", footers[3])
        self.assertIn("1–4/12", footers[4])
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_read_error_recovers_and_target_switch_resets_scroll(self):
        self.save()
        path = Path(self.temp.name) / "plans/root-a.json"
        path.write_text("{broken", encoding="utf-8")
        def recover(screen):
            self.save()
        def switch(screen):
            self.store.save_plan("root-b", "第二个项目", [dict(step="新的任务", status="in_progress")], 1)
            self.write_binding(dict(self.record, session_id="root-b", attachment_id="attach-b"))
        screen = Screen([recover, viewer.curses.KEY_NPAGE, switch, ord("q")])
        with patch.object(viewer, "parent_exists", return_value=True), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(screen, self.panel)
        text = [" ".join(line for _, line in frame) for frame in screen.frames]
        self.assertIn("无法读取已保存的任务", text[0])
        self.assertIn("中文项目", text[1])
        self.assertIn("新的任务", text[-1])
        self.assertIn("1–1/1", text[-1])

    def test_terminal_failure_and_binding_failure_recover(self):
        self.save()
        binding_path = Path(self.temp.name) / "bindings" / (self.key + ".json")
        def corrupt(screen):
            binding_path.write_text("broken", encoding="utf-8")
        def recover(screen):
            self.write_binding(self.record)
        screen = Screen([corrupt, recover, ord("q")])
        with patch.object(viewer, "parent_exists", side_effect=[viewer.PanelError("failure"), True, True]), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(screen, self.panel)
        text = [" ".join(line for _, line in frame) for frame in screen.frames]
        self.assertIn("无法连接 WezTerm", text[0])
        self.assertIn("无法读取任务面板绑定", text[1])
        self.assertIn("已保存计划", text[2])

    def test_drawing_resize_errors_and_cursor_failure_are_recoverable(self):
        self.save()
        screen = Screen([ord("Q")])
        with patch.object(viewer, "parent_exists", return_value=True), patch.object(viewer.curses, "curs_set", side_effect=viewer.curses.error), patch.object(screen, "addstr", side_effect=viewer.curses.error):
            viewer.show_panel(screen, self.panel)
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_closed_and_replaced_bindings_exit_without_input(self):
        for change in (dict(state="closed"), dict(nonce="b" * 32)):
            self.write_binding(dict(self.record, **change))
            screen = Screen([])
            with patch.object(viewer.curses, "curs_set"):
                viewer.show_panel(screen, self.panel)
            self.assertEqual(screen.frames, [])

    def test_quit_during_new_attach_preserves_its_binding_and_continues(self):
        self.save()
        def switch_on_first_quit(event):
            if self.store.read_binding(self.key)["attachment_id"] == "attach-a":
                self.write_binding(dict(self.record, attachment_id="attach-b"))
        screen = Screen([ord("q"), ord("q")], action=switch_on_first_quit)
        with patch.object(viewer, "parent_exists", return_value=True), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(screen, self.panel)
        self.assertEqual(len(screen.frames), 2)
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_cli_once_is_read_only_and_chinese(self):
        self.save()
        command = [sys.executable, str(HOOKS / "task_panel.py"), "--data-dir", self.temp.name,
                   "--binding", self.key, "--nonce", self.nonce, "--socket", self.socket,
                   "--parent", self.parent, "--once"]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("中文项目", result.stdout)
        self.assertNotIn("\x1b", result.stdout)
        self.assertEqual(self.store.read_binding(self.key)["state"], "starting")

    def test_cli_once_preserves_tasks_across_extreme_saved_times(self):
        self.save(count=1)
        path = Path(self.temp.name) / "plans/root-a.json"
        plan = json.loads(path.read_text())
        command = [sys.executable, str(HOOKS / "task_panel.py"), "--data-dir", self.temp.name,
                   "--binding", self.key, "--nonce", self.nonce, "--socket", self.socket,
                   "--parent", self.parent, "--once"]
        for timestamp in (10 ** 400, -(10 ** 400), 1780000000):
            with self.subTest(timestamp=timestamp):
                path.write_text(json.dumps(dict(plan, updated_at=timestamp)), encoding="utf-8")
                result = subprocess.run(command, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("任务 0", result.stdout)
                self.assertIn("中文项目", result.stdout)
                expected = "时间超出显示范围" if abs(timestamp) > 10 ** 20 else "2026"
                self.assertIn(expected, result.stdout)
                self.assertEqual(result.stderr, "")

    def test_cli_once_reads_extreme_binding_metadata_and_restores(self):
        self.save(count=1)
        path = Path(self.temp.name) / "bindings" / (self.key + ".json")
        command = [sys.executable, str(HOOKS / "task_panel.py"), "--data-dir", self.temp.name,
                   "--binding", self.key, "--nonce", self.nonce, "--socket", self.socket,
                   "--parent", self.parent, "--once"]
        for field in ("starting_created_at", "starting_deadline"):
            for number in (10 ** 400, -(10 ** 400), 1.0):
                with self.subTest(field=field, number=number):
                    path.write_text(json.dumps(dict(self.record, **{field: number})), encoding="utf-8")
                    result = subprocess.run(command, text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("中文项目", result.stdout)
                    self.assertIn("已保存计划", result.stdout)
                    self.assertEqual(result.stderr, "")

    def test_terminal_close_signals_defer_io_and_close_current_attachment(self):
        self.save()
        handlers = {}
        def install(number, handler):
            handlers[number] = handler
            return signal.SIG_DFL
        def run_screen(function, panel):
            def close_window(screen):
                with patch.object(panel.store, "binding_transaction", side_effect=AssertionError("Signal handler performed cache IO")):
                    handlers[signal.SIGHUP](signal.SIGHUP, None)
                self.assertTrue(panel.stop_requested)
            function(Screen([close_window]), panel)
        args = ["--data-dir", self.temp.name, "--binding", self.key, "--nonce", self.nonce,
                "--socket", self.socket, "--parent", self.parent]
        with patch.dict(os.environ, WEZTERM_PANE="14"), patch.object(viewer.signal, "signal", side_effect=install), patch.object(viewer, "parent_exists", return_value=True), patch.object(viewer.curses, "wrapper", side_effect=run_screen), patch.object(viewer.curses, "curs_set"), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(viewer.main(args), 0)
        self.assertIn("cc-hooks-task-panel:" + self.nonce, output.getvalue())
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_terminal_close_preserves_new_attachment_and_prioritizes_parent_exit(self):
        self.panel.last_attachment = "attach-a"
        self.write_binding(dict(self.record, attachment_id="attach-b"))
        with patch.object(viewer, "parent_exists", return_value=True):
            self.panel.finish()
        self.assertEqual(self.store.read_binding(self.key)["state"], "starting")
        with patch.object(viewer, "parent_exists", return_value=False):
            self.panel.finish()
        self.assertIsNone(self.store.read_binding(self.key))

    def test_terminal_close_during_ipc_failure_retains_closed_binding_and_diagnoses(self):
        self.panel.last_attachment = "attach-a"
        with patch.object(viewer, "parent_exists", side_effect=viewer.PanelError("failure")), patch("sys.stderr", new_callable=io.StringIO) as diagnostic:
            self.panel.finish()
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")
        self.assertIn("无法确认 WezTerm", diagnostic.getvalue())

    def test_ready_rejects_invalid_child_identifier(self):
        for pane in (None, "", "child", "../14", 14):
            with self.assertRaises(viewer.PanelError):
                self.panel.ready(pane)
        self.assertEqual(self.store.read_binding(self.key)["state"], "starting")


if __name__ == "__main__":
    unittest.main()
