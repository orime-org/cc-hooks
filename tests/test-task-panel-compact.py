#!/usr/bin/env python3
"""Verify compact rendering and owned pane height through the viewer loop."""

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / "watcher/hooks"
sys.path.insert(0, str(HOOKS))
import task_panel as viewer
import task_panel_hook as hook
from task_panel_store import Store, binding_key

spec = importlib.util.spec_from_file_location("viewer_fixtures", Path(__file__).with_name("test-task-panel-viewer.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class CompactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(temporary.name)
        self.key = binding_key("/tmp/compact.sock", "13")
        self.record = dict(version=1, socket="/tmp/compact.sock", parent_pane="13",
                           panel_pane="14", session_id="root-a", attachment_id="attach-a",
                           nonce="a" * 32, ready_nonce="a" * 32, state="visible",
                           starting_created_at=None, starting_deadline=None)
        self.write(self.record)
        self.panel = viewer.Panel(self.store, self.key, self.record["nonce"], self.record["socket"], "13")
        self.screen = fixtures.Screen([], size=(3, 130))
        self.adjustments = []
        self.failures = 0
        self.fail_after_apply = False
        self.limit = None
        self.after_adjust = None
        self.foreign = False

    def write(self, record):
        with self.store.binding_transaction(self.key) as transaction:
            transaction.write(record)

    def save(self, count):
        self.store.save_plan("root-a", "中文项目", [dict(step=f"任务 {n+1}", status="pending")
                                                  for n in range(count)], 1780000000)

    def terminal(self, command, **kwargs):
        self.assertEqual(kwargs["env"]["WEZTERM_UNIX_SOCKET"], self.record["socket"])
        self.assertGreater(kwargs["timeout"], 0)
        self.assertLessEqual(kwargs["timeout"], 5)
        if "adjust-pane-size" in command:
            self.assertEqual(command[command.index("--pane-id") + 1], "14")
            if self.failures:
                self.failures -= 1
                raise subprocess.TimeoutExpired(command, .1)
            amount = int(command[command.index("--amount") + 1])
            direction = command[-1]
            rows, cols = self.screen.size
            rows += amount if direction == "Up" else -amount
            if self.limit is not None:
                rows = min(rows, self.limit)
            self.screen.size = (rows, cols)
            self.adjustments.append((direction, amount, rows))
            if self.fail_after_apply:
                self.fail_after_apply = False
                raise subprocess.TimeoutExpired(command, .1)
            if self.after_adjust:
                callback, self.after_adjust = self.after_adjust, None
                callback()
            return subprocess.CompletedProcess(command, 0, "", "")
        self.assertIn("list", command)
        panes = [dict(pane_id=13, window_id=1, tab_id=1, title="Codex"),
                 dict(pane_id=14, window_id=1, tab_id=1,
                      title="foreign" if self.foreign else "cc-hooks-task-panel:" + self.record["nonce"],
                      size=dict(rows=self.screen.size[0], cols=self.screen.size[1]))]
        return subprocess.CompletedProcess(command, 0, json.dumps(panes), "")

    def run_viewer(self, events):
        now = [100.0]
        def idle(screen):
            now[0] += screen.delay / 1000
        self.screen.events = iter(idle if event == -1 else event for event in events)
        with patch.object(viewer.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(viewer.subprocess, "run", side_effect=self.terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        return ["\n".join(text for _, text in frame) for frame in self.screen.frames]

    @contextmanager
    def height_in_flight(self, phase):
        entered, release = threading.Event(), threading.Event()
        result, errors = [], []
        blocked = False

        def terminal(command, **kwargs):
            nonlocal blocked
            if not blocked and ((phase == "query" and "list" in command)
                                or (phase == "adjust" and "adjust-pane-size" in command)):
                blocked = True
                entered.set()
                if not release.wait(2):
                    raise AssertionError("Height probe was not released")
            return self.terminal(command, **kwargs)

        def fit():
            try:
                result.append(self.panel.fit_height(self.record, self.store.read_plan("root-a")))
            except Exception as error:
                errors.append(error)

        with patch.object(viewer.subprocess, "run", side_effect=terminal):
            worker = threading.Thread(target=fit)
            worker.start()
            try:
                self.assertTrue(entered.wait(1), "Height probe did not start")
                yield result
            finally:
                release.set()
                worker.join(3)
                self.assertFalse(worker.is_alive(), "Height probe thread must finish")
        self.assertEqual(errors, [])

    def replace_pending_binding(self, record):
        failure = None
        try:
            with self.store.binding_transaction(self.key, time.monotonic() + .1) as transaction:
                transaction.write(record)
        except Exception as error:
            failure = error
        self.assertIsNone(failure, "Binding updates must complete while height IPC is pending")

    def test_session_end_completes_during_height_query_and_adjustment(self):
        for phase in ("query", "adjust"):
            with self.subTest(phase=phase):
                self.write(self.record)
                self.panel = viewer.Panel(self.store, self.key, self.record["nonce"], self.record["socket"], "13")
                self.screen.size = (3, 130)
                self.save(0 if phase == "query" else 25)
                other = dict(self.record, parent_pane="15", panel_pane="16")
                other_key = binding_key(other["socket"], other["parent_pane"])
                with self.store.binding_transaction(other_key) as transaction:
                    transaction.write(other)
                with self.height_in_flight(phase) as result:
                    failure = None
                    try:
                        hook.Handler(self.store).handle(dict(hook_event_name="SessionEnd", session_id="root-a"))
                    except Exception as error:
                        failure = error
                    self.assertIsNone(failure, "SessionEnd must complete while height IPC is pending")
                    self.assertEqual(self.store.read_binding(self.key)["state"], "ended")
                    self.assertEqual(self.store.read_binding(other_key)["state"], "ended")
                self.assertEqual(result, [True])
                self.assertEqual(self.store.read_binding(self.key)["state"], "ended")

    def test_new_binding_during_height_query_stops_before_adjustment(self):
        changes = (dict(attachment_id="attach-b"), dict(session_id="root-b"),
                   dict(panel_pane="15"), dict(state="closed"),
                   dict(nonce="b" * 32, ready_nonce="b" * 32))
        for change in changes:
            with self.subTest(change=change):
                self.write(self.record)
                self.panel = viewer.Panel(self.store, self.key, self.record["nonce"], self.record["socket"], "13")
                self.screen.size = (3, 130)
                self.adjustments = []
                self.save(25)
                replacement = dict(self.record, **change)
                with self.height_in_flight("query") as result:
                    self.replace_pending_binding(replacement)
                self.assertEqual(result, [False])
                self.assertEqual(self.adjustments, [])
                self.assertEqual(self.store.read_binding(self.key), replacement)

    def test_new_binding_during_inflight_adjustment_remains_current(self):
        for change in (dict(attachment_id="attach-b"), dict(session_id="root-b"),
                       dict(nonce="b" * 32, ready_nonce="b" * 32)):
            with self.subTest(change=change):
                self.write(self.record)
                self.panel = viewer.Panel(self.store, self.key, self.record["nonce"], self.record["socket"], "13")
                self.screen.size = (3, 130)
                self.save(25)
                replacement = dict(self.record, **change)
                with self.height_in_flight("adjust") as result:
                    self.replace_pending_binding(replacement)
                self.assertEqual(result, [False])
                self.assertEqual(self.store.read_binding(self.key), replacement)

    def test_task_window_is_limited_to_four_at_every_height(self):
        self.save(25)
        for height in (0, 1, 2, 3, 4, 6, 7, 10, 14, 100):
            for offset in (0, 1, 23, 100):
                with self.subTest(height=height, offset=offset):
                    lines, start, capacity = viewer.render_frame(self.record, self.store.read_plan("root-a"), height, 130, offset)
                    self.assertEqual(capacity, min(4, max(0, height - 3)))
                    shown = sum(line.startswith("[ ]") for line in lines)
                    self.assertEqual(shown, min(capacity, 25))
                    if height >= 2:
                        self.assertIn(f"还有 {25-shown} 条", lines[-1])
                        self.assertIn("/25", lines[-1])

    def test_idle_refreshes_do_not_query_wezterm(self):
        self.save(0)
        counts = []
        commands = []

        def terminal(command, **kwargs):
            commands.append(command)
            return self.terminal(command, **kwargs)

        def observe(screen):
            counts.append(len(commands))

        self.screen.events = iter([observe] * 10 + [ord("q")])
        with patch.object(viewer.subprocess, "run", side_effect=terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        self.assertEqual(counts, [counts[0]] * 10)
        self.assertNotIn("无法连接 WezTerm", "\n".join(text for _, text in self.screen.frames[-1]))

    def test_height_failure_waits_before_retrying_and_keeps_updates_visible(self):
        self.save(25)
        self.screen.size = (6, 130)
        now = [100.0]
        attempts = []

        def terminal(command, **kwargs):
            if "adjust-pane-size" in command:
                attempts.append(now[0])
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return self.terminal(command, **kwargs)

        def update(screen):
            now[0] += .1
            self.store.save_plan("root-a", "中文项目", [dict(step="更新仍然可见", status="in_progress")], 1780000001)

        self.screen.events = iter([update] * 8 + [ord("q")])
        with patch.object(viewer.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(viewer.subprocess, "run", side_effect=terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.store.read_plan("root-a")["plan"][0]["step"], "更新仍然可见")
        self.assertIn("更新仍然可见", "\n".join(text for _, text in self.screen.frames[-1]))

    def test_height_query_allows_a_response_slower_than_one_second(self):
        self.save(1)

        def terminal(command, **kwargs):
            if "list" in command and kwargs["timeout"] < 1.2:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return self.terminal(command, **kwargs)

        self.screen.events = iter([ord("q")])
        with patch.object(viewer.subprocess, "run", side_effect=terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        self.assertEqual(self.screen.size[0], 4)

    def test_plan_content_updates_at_the_same_height_do_not_query_wezterm(self):
        self.save(6)
        counts, commands = [], []

        def terminal(command, **kwargs):
            commands.append(command)
            return self.terminal(command, **kwargs)

        def update(screen):
            counts.append(len(commands))
            self.store.save_plan("root-a", "中文项目", [dict(step="任务内容已更新", status="completed")
                                                      for _ in range(6)], 1780000001)

        self.screen.events = iter([update] * 4 + [ord("q")])
        with patch.object(viewer.subprocess, "run", side_effect=terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        self.assertEqual(counts, [counts[0]] * 4)
        self.assertIn("任务内容已更新", "\n".join(text for _, text in self.screen.frames[-1]))

    def test_repeated_height_failures_back_off_to_thirty_seconds(self):
        self.save(1)
        now, attempts = [100.0], []

        def terminal(command, **kwargs):
            attempts.append(now[0])
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        def advance(seconds):
            def event(screen):
                now[0] += seconds
            return event

        self.screen.events = iter([advance(n) for n in (2, 4, 8, 16, 30, 30)] + [ord("q")])
        with patch.object(viewer.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(viewer.subprocess, "run", side_effect=terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        self.assertEqual(attempts, [100, 102, 106, 114, 130, 160, 190])

    def test_auto_height_tracks_zero_one_four_five_and_twenty_five(self):
        self.save(0)
        def change(count):
            return lambda screen: self.save(count)
        frames = self.run_viewer([change(1), change(4), change(5), change(25), change(0), ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [3, 4, 7, 7, 7, 3])
        self.assertEqual([row[2] for row in self.adjustments], [4, 7, 3])
        self.assertIn("还有 21 条", frames[4])

    def test_manual_resize_survives_plan_changes_until_new_attach(self):
        self.save(25)
        def manual(screen):
            screen.size = (10, 130)
        def reduce(screen):
            self.save(1)
        def attach(screen):
            self.write(dict(self.record, attachment_id="attach-b"))
        frames = self.run_viewer([ord("m"), manual, reduce, attach, ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [7, 7, 10, 10, 4])
        self.assertEqual([row[2] for row in self.adjustments], [7, 4])
        self.assertEqual(sum(line.startswith("[ ]") for _, line in self.screen.frames[2]), 4)
        self.assertIn("1–1/1", frames[-1])

    def test_explicit_manual_mode_preserves_width_and_two_rows_remain_operable(self):
        self.save(25)
        def width(screen):
            screen.size = (7, 100)
        def shrink(screen):
            screen.size = (2, 100)
            self.save(1)
        self.run_viewer([ord("m"), width, shrink, ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [7, 7, 7, 2])
        self.assertEqual(len(self.adjustments), 1)
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_height_failure_is_visible_then_retries_with_the_plan(self):
        self.save(25)
        self.failures = 1
        frames = self.run_viewer([-1, -1, ord("q")])
        self.assertIn("高度调整失败", frames[0])
        self.assertIn("还有 25 条", frames[0])
        self.assertIn("任务 1", frames[2])
        self.assertNotIn("高度调整失败", frames[2])
        self.assertEqual(self.screen.size[0], 7)

    def test_manual_resize_cancels_a_pending_retry(self):
        self.save(25)
        self.failures = 1
        def manual(screen):
            screen.size = (10, 130)
        frames = self.run_viewer([ord("m"), manual, ord("q")])
        self.assertEqual(self.adjustments, [])
        self.assertNotIn("高度调整失败", frames[-1])
        self.assertEqual(self.screen.size[0], 10)

    def test_platform_clamp_is_recorded_until_capacity_changes(self):
        self.save(25)
        self.limit = 5
        def reduce(screen):
            self.save(1)
        self.run_viewer([-1, reduce, ord("q")])
        self.assertEqual([row[2] for row in self.adjustments], [5, 4])

    def test_timeout_after_resize_keeps_automatic_height(self):
        self.save(25)
        self.fail_after_apply = True
        def reduce(screen):
            self.save(1)
        self.run_viewer([-1, -1, reduce, ord("q")])
        self.assertEqual([row[2] for row in self.adjustments], [7, 4])

    def test_clamped_timeout_keeps_explicit_automatic_mode(self):
        self.save(25)
        self.limit, self.fail_after_apply = 5, True
        def reduce(screen):
            self.save(1)
        frames = self.run_viewer([-1, -1, reduce, ord("q")])
        self.assertEqual(self.screen.size[0], 4)
        self.assertFalse(self.panel.height.manual)
        self.assertIn("自动", frames[-1])

    def test_manual_key_preserves_pending_target_size_after_failure(self):
        self.save(25)
        self.failures = 1
        def drag(screen):
            screen.size = (7, 130)
        def reduce(screen):
            self.save(1)
        frames = self.run_viewer([ord("m"), drag, reduce, ord("q")])
        self.assertEqual(self.adjustments, [])
        self.assertEqual(self.screen.size[0], 7)
        self.assertTrue(self.panel.height.manual)
        self.assertIn("手动", frames[-1])
        self.assertIn("a自动", frames[-1])

    def test_mode_keys_control_resize_and_auto_key_restores_current_plan(self):
        self.save(25)
        def drag(screen):
            screen.size = (10, 130)
        def reduce(screen):
            self.save(1)
        frames = self.run_viewer([ord("M"), drag, reduce, ord("A"), ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [7, 7, 10, 10, 4])
        self.assertIn("手动", frames[1])
        self.assertIn("自动", frames[-1])
        self.assertIn("m手动", frames[-1])

    def test_auto_mode_reasserts_content_height_after_external_resize(self):
        self.save(25)
        def drag(screen):
            screen.size = (10, 130)
        self.run_viewer([drag, ord("q")])
        self.assertFalse(self.panel.height.manual)
        self.assertEqual(self.screen.size[0], 7)

    def test_mode_key_on_a_replaced_attachment_does_not_change_its_mode(self):
        self.save(25)
        def replace(event):
            if event == ord("m"):
                self.write(dict(self.record, attachment_id="attach-b"))
        self.screen.action = replace
        self.run_viewer([ord("m"), ord("q")])
        self.assertFalse(self.panel.height.manual)

    def test_manual_mode_can_be_selected_after_failed_geometry_read(self):
        self.save(25)
        self.foreign = True
        frames = self.run_viewer([ord("m"), ord("q")])
        self.assertTrue(self.panel.height.manual)
        self.assertEqual(self.adjustments, [])
        self.assertIn("手动", frames[-1])
        self.assertIn("无法读取面板尺寸", frames[-1])

    def test_read_only_snapshot_omits_live_height_mode(self):
        self.save(1)
        lines, _, _ = viewer.render_frame(self.record, self.store.read_plan("root-a"), 4, 130, manual=None)
        self.assertIn("1–1/1", lines[-1])
        self.assertNotIn("m手动", lines[-1])
        self.assertNotIn("a自动", lines[-1])

    def test_stale_attachment_is_rejected_before_terminal_io(self):
        self.save(25)
        for changes in (dict(attachment_id="attach-b"), dict(session_id="root-b"),
                        dict(panel_pane="15"), dict(state="closed")):
            with self.subTest(changes=changes):
                self.write(dict(self.record, **changes))
                with patch.object(viewer.subprocess, "run", side_effect=AssertionError("Stale viewer performed terminal IO")):
                    self.assertFalse(self.panel.fit_height(self.record, self.store.read_plan("root-a")))

    def test_cache_error_shrinks_then_recovers_automatically(self):
        self.save(25)
        def corrupt(screen):
            (self.store.root / "plans/root-a.json").write_text("{broken")
        def recover(screen):
            self.save(25)
        frames = self.run_viewer([corrupt, recover, ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [7, 3, 7])
        self.assertIn("无法读取已保存的任务", frames[1])

    def test_foreign_pane_and_replaced_binding_are_never_resized(self):
        self.save(25)
        self.foreign = True
        frames = self.run_viewer([ord("q")])
        self.assertEqual(self.adjustments, [])
        self.assertIn("高度调整失败", frames[0])
        self.write(dict(self.record, nonce="b" * 32, ready_nonce="b" * 32))
        self.screen.frames = []
        self.run_viewer([])
        self.assertEqual(self.screen.frames, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
