#!/usr/bin/env python3
"""Verify compact rendering and owned pane height through the viewer loop."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / "watcher/hooks"
sys.path.insert(0, str(HOOKS))
import task_panel as viewer
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
        self.assertLessEqual(kwargs["timeout"], 1)
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
        self.screen.events = iter(events)
        with patch.object(viewer.subprocess, "run", side_effect=self.terminal), patch.object(viewer.curses, "curs_set"):
            viewer.show_panel(self.screen, self.panel)
        return ["\n".join(text for _, text in frame) for frame in self.screen.frames]

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
        frames = self.run_viewer([manual, reduce, attach, ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [7, 10, 10, 4])
        self.assertEqual([row[2] for row in self.adjustments], [7, 4])
        self.assertEqual(sum(line.startswith("[ ]") for _, line in self.screen.frames[1]), 4)
        self.assertIn("1–1/1", frames[-1])

    def test_width_change_enters_manual_mode_and_two_rows_remain_operable(self):
        self.save(25)
        def width(screen):
            screen.size = (7, 100)
        def shrink(screen):
            screen.size = (2, 100)
            self.save(1)
        self.run_viewer([width, shrink, ord("q")])
        self.assertEqual([len(frame) for frame in self.screen.frames], [7, 7, 2])
        self.assertEqual(len(self.adjustments), 1)
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")

    def test_height_failure_is_visible_then_retries_with_the_plan(self):
        self.save(25)
        self.failures = 1
        frames = self.run_viewer([-1, ord("q")])
        self.assertIn("高度调整失败", frames[0])
        self.assertIn("还有 25 条", frames[0])
        self.assertIn("任务 1", frames[1])
        self.assertNotIn("高度调整失败", frames[1])
        self.assertEqual(self.screen.size[0], 7)

    def test_manual_resize_cancels_a_pending_retry(self):
        self.save(25)
        self.failures = 1
        def manual(screen):
            screen.size = (10, 130)
        frames = self.run_viewer([manual, ord("q")])
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
        self.run_viewer([-1, reduce, ord("q")])
        self.assertEqual([row[2] for row in self.adjustments], [7, 4])

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
