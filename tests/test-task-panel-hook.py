#!/usr/bin/env python3
"""Test hook routing and bounded pane coordination against a terminal model."""

import importlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from contextlib import contextmanager
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / "watcher/hooks"
sys.path.insert(0, str(HOOKS))
from task_panel_store import Store, binding_key
from task_panel import Panel

FEATURES = ["effective_tool_context", "interactive_terminal_context", "session_start_on_attach", "committed_plan_callbacks"]


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


class Terminal:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock
        self.panes = [{"pane_id": 13, "window_id": 1, "tab_id": 1, "title": "Codex"}]
        self.pending = []
        self.calls = []
        self.delay = 0.1
        self.failure = None
        self.on_list = None

    def list(self, timeout):
        self.calls.append(("list", timeout))
        if self.on_list:
            callback, self.on_list = self.on_list, None
            callback()
        if self.failure == "list":
            raise OSError("terminal unavailable")
        for pending in list(self.pending):
            if pending[0] > self.clock.now:
                continue
            _, nonce, pane = pending
            key = binding_key("/tmp/wezterm.sock", "13")
            with self.store.binding_transaction(key) as transaction:
                record = transaction.read()
                if record and record["nonce"] == nonce and record["state"] != "closed":
                    self.panes.append({"pane_id": int(pane), "window_id": 1, "tab_id": 1,
                                       "title": "cc-hooks-task-panel:" + nonce})
            Panel(self.store, key, nonce, "/tmp/wezterm.sock", "13").ready(pane)
            self.pending.remove(pending)
        return list(self.panes)

    def split(self, parent, command, timeout):
        self.calls.append(("split", parent, command, timeout))
        if self.failure == "split":
            raise TimeoutError("split response timed out")
        pane = str(14 + len([call for call in self.calls if call[0] == "split"]))
        nonce = command[command.index("--nonce") + 1]
        self.pending.append((self.clock.now + self.delay, nonce, pane))
        return pane

    def activate(self, parent, timeout):
        self.calls.append(("activate", parent, timeout))
        if self.failure == "activate":
            raise OSError("focus request failed")


class HookTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("task_panel_hook")
        temporary = tempfile.TemporaryDirectory(prefix="watcher-panel-hook-")
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "task-panel")
        self.clock = Clock()
        self.terminal = Terminal(self.store, self.clock)
        self.handler = self.module.Handler(self.store, lambda context: self.terminal, self.clock)
        self.key = binding_key("/tmp/wezterm.sock", "13")

    def event(self, **changes):
        event = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "root-1", "cwd": "/work/project",
                 "client_context": {"frontend": "tui", "terminal_program": "WezTerm", "wezterm_pane": "13",
                                    "wezterm_unix_socket": "/tmp/wezterm.sock", "attachment_id": "attach-1"},
                 "hook_capabilities": {"runtime_hooks_version": 1, "client_version": "client-commit",
                                       "server_version": "server-commit", "features": list(FEATURES)}}
        event.update(changes)
        return event

    def plan(self, session="root-1", **changes):
        event = self.event(hook_event_name="PostToolUse", session_id=session, tool_name="update_plan",
                           tool_input={"plan": [{"step": "检查中文", "status": "in_progress"}]})
        event.update(changes)
        return event

    def seed_starting(self, deadline=1004.0, attachment="old-attach"):
        record = {"version": 1, "socket": "/tmp/wezterm.sock", "parent_pane": "13", "panel_pane": None,
                  "session_id": "old-root", "attachment_id": attachment, "nonce": "a" * 32, "state": "starting",
                  "starting_created_at": 1000.0, "starting_deadline": deadline}
        with self.store.binding_transaction(self.key) as transaction:
            transaction.write(record)
        return record

    def test_root_plan_saves_exact_order_status_and_empty_clear(self):
        self.assertIsNone(self.handler.handle(self.plan()))
        self.assertEqual(self.store.read_plan("root-1")["plan"], [{"step": "检查中文", "status": "in_progress"}])
        self.handler.handle(self.plan(tool_input={"plan": []}))
        self.assertEqual(self.store.read_plan("root-1")["plan"], [])

    def test_plan_sessions_stay_independent(self):
        self.handler.handle(self.plan())
        self.handler.handle(self.plan("root-2", tool_input={"plan": []}))
        self.assertEqual(len(self.store.read_plan("root-1")["plan"]), 1)
        self.assertEqual(self.store.read_plan("root-2")["plan"], [])

    def test_subagents_and_other_tools_do_not_change_root_plans(self):
        self.handler.handle(self.plan(agent_id="child-1"))
        self.handler.handle(self.plan(tool_name="exec_command"))
        self.assertIsNone(self.store.read_plan("root-1"))

    def test_invalid_plan_preserves_the_previous_snapshot(self):
        self.handler.handle(self.plan())
        with self.assertRaises((self.module.PanelError, ValueError)):
            self.handler.handle(self.plan(tool_input={"plan": [{"step": "bad", "status": "invalid"}]}))
        self.assertEqual(self.store.read_plan("root-1")["plan"][0]["step"], "检查中文")

    def test_startup_creates_one_pane_and_restores_parent_focus(self):
        self.assertIsNone(self.handler.handle(self.event()))
        record = self.store.read_binding(self.key)
        self.assertEqual(record["state"], "visible")
        self.assertEqual(record["session_id"], "root-1")
        self.assertEqual(self.terminal.calls[-1][0:2], ("activate", "13"))
        split = next(call for call in self.terminal.calls if call[0] == "split")
        self.assertIn(str(HOOKS / "task_panel.py"), split[2])
        self.assertEqual(len([call for call in self.terminal.calls if call[0] == "split"]), 1)

    def test_duplicate_and_new_attachment_reuse_the_visible_pane(self):
        self.handler.handle(self.event())
        pane = self.store.read_binding(self.key)["panel_pane"]
        self.handler.handle(self.event())
        event = self.event(session_id="root-2")
        event["client_context"]["attachment_id"] = "attach-2"
        self.handler.handle(event)
        self.assertEqual(self.store.read_binding(self.key)["panel_pane"], pane)
        self.assertEqual(self.store.read_binding(self.key)["session_id"], "root-2")
        self.assertEqual(len([call for call in self.terminal.calls if call[0] == "split"]), 1)

    def test_startup_recovers_extreme_persisted_creation_metadata(self):
        path = self.store.root / "bindings" / (self.key + ".json")
        for field in ("starting_created_at", "starting_deadline"):
            for number in (10 ** 400, -(10 ** 400)):
                with self.subTest(field=field, number=number):
                    self.terminal.panes = self.terminal.panes[:1]
                    self.terminal.pending.clear()
                    self.terminal.calls.clear()
                    record = self.seed_starting(deadline=self.clock.time() + 4)
                    path.write_text(json.dumps(dict(record, **{field: number})), encoding="utf-8")
                    self.assertIsNone(self.handler.handle(self.event()))
                    restored = self.store.read_binding(self.key)
                    self.assertEqual(restored["state"], "visible")
                    self.assertEqual(restored["ready_nonce"], restored["nonce"])
                    self.assertNotEqual(restored["nonce"], record["nonce"])
                    self.assertGreaterEqual(restored["starting_created_at"], self.clock.time() - 1)
                    self.assertLessEqual(restored["starting_deadline"], self.clock.time() + 4)
                    self.assertEqual(sum(call[0] == "split" for call in self.terminal.calls), 1)

    def test_ready_pane_recovers_after_focus_or_list_failure(self):
        for failure in ("activate", "list"):
            with self.subTest(failure=failure):
                self.terminal.failure = None
                with self.store.binding_transaction(self.key) as transaction:
                    transaction.delete()
                self.terminal.panes = self.terminal.panes[:1]
                self.terminal.calls.clear()
                if failure == "list":
                    self.assertIsNone(self.handler.handle(self.event()))
                self.terminal.failure = failure
                self.assertIsNotNone(self.handler.handle(self.event()))
                failed = self.store.read_binding(self.key)
                self.assertEqual(failed["state"], "error")
                self.terminal.failure = None
                event = self.event()
                event["client_context"]["attachment_id"] = "attach-retry"
                self.assertIsNone(self.handler.handle(event))
                restored = self.store.read_binding(self.key)
                self.assertEqual(restored["state"], "visible")
                self.assertEqual(restored["panel_pane"], failed["panel_pane"])
                self.assertEqual(restored["ready_nonce"], restored["nonce"])
                self.assertEqual(sum(call[0] == "split" for call in self.terminal.calls), 1)
                self.assertEqual(self.terminal.calls[-1][0:2], ("activate", "13"))

    def test_unconfirmed_owned_title_cannot_replace_viewer_ready(self):
        record = self.seed_starting(deadline=999.0)
        record.update(panel_pane="14", ready_nonce=None, state="error")
        with self.store.binding_transaction(self.key) as transaction:
            transaction.write(record)
        self.terminal.panes.append(dict(pane_id=14, window_id=1, tab_id=1,
                                       title="cc-hooks-task-panel:" + record["nonce"]))
        self.assertIsNone(self.handler.handle(self.event()))
        restored = self.store.read_binding(self.key)
        self.assertNotEqual(restored["nonce"], record["nonce"])
        self.assertEqual(restored["ready_nonce"], restored["nonce"])
        self.assertEqual(sum(call[0] == "split" for call in self.terminal.calls), 1)

    def test_legacy_visible_binding_preserves_its_ready_pane(self):
        self.assertIsNone(self.handler.handle(self.event()))
        previous = self.store.read_binding(self.key)
        with self.store.binding_transaction(self.key) as transaction:
            legacy = transaction.read()
            legacy.pop("ready_nonce")
            legacy.pop("project_title")
            transaction.write(legacy)
        self.assertIsNone(self.handler.handle(self.event()))
        record = self.store.read_binding(self.key)
        self.assertEqual(record["panel_pane"], previous["panel_pane"])
        self.assertEqual(record["ready_nonce"], previous["nonce"])
        self.assertEqual(record["project_title"], "project")
        self.assertEqual(sum(call[0] == "split" for call in self.terminal.calls), 1)

    def test_startup_and_clear_target_save_project_without_a_plan(self):
        for session, attachment, cwd, title in (("root-1", "attach-1", "/work/第一个项目", "第一个项目"),
                                                ("root-2", "attach-2", "/work/第二个项目", "第二个项目")):
            event = self.event(session_id=session, cwd=cwd)
            event["client_context"]["attachment_id"] = attachment
            self.assertIsNone(self.handler.handle(event))
            self.assertEqual(self.store.read_binding(self.key)["project_title"], title)
            self.assertIsNone(self.store.read_plan(session))

    def test_disappeared_ready_pane_gets_a_new_confirmation(self):
        self.assertIsNone(self.handler.handle(self.event()))
        previous = self.store.read_binding(self.key)
        self.terminal.panes = self.terminal.panes[:1]
        event = self.event()
        event["client_context"]["attachment_id"] = "reopened"
        self.assertIsNone(self.handler.handle(event))
        record = self.store.read_binding(self.key)
        self.assertNotEqual(record["nonce"], previous["nonce"])
        self.assertEqual(record["ready_nonce"], record["nonce"])
        self.assertNotEqual(record["panel_pane"], previous["panel_pane"])

    def test_session_end_ignores_a_locked_unrelated_binding(self):
        self.assertIsNone(self.handler.handle(self.event()))
        other_key = binding_key("/tmp/wezterm.sock", "99")
        with self.store.binding_transaction(other_key) as transaction:
            transaction.write(dict(self.store.read_binding(self.key), parent_pane="99", session_id="root-2"))
        target = self.store.binding_keys()[-1]
        unrelated = self.store.binding_keys()[0]
        target_session = self.store.read_binding(target)["session_id"]
        handler = self.module.Handler(self.store)
        with self.store.binding_transaction(unrelated):
            self.assertIsNone(handler.handle(self.event(hook_event_name="SessionEnd", session_id=target_session)))
        self.assertEqual(self.store.read_binding(target)["state"], "ended")
        self.assertEqual(self.store.read_binding(unrelated)["state"], "visible")

    def test_session_end_rechecks_the_target_after_acquiring_its_lock(self):
        self.assertIsNone(self.handler.handle(self.event()))
        original = self.store.binding_transaction

        @contextmanager
        def switch_before_lock(key, deadline=None):
            with original(key) as transaction:
                record = transaction.read()
                record["session_id"] = "new-root"
                transaction.write(record)
            with original(key, deadline) as transaction:
                yield transaction

        with patch.object(self.store, "binding_transaction", side_effect=switch_before_lock):
            self.handler.handle(self.event(hook_event_name="SessionEnd"))
        record = self.store.read_binding(self.key)
        self.assertEqual(record["session_id"], "new-root")
        self.assertEqual(record["state"], "visible")

    def test_closed_attachment_stays_closed_and_new_attachment_can_reopen(self):
        self.handler.handle(self.event())
        with self.store.binding_transaction(self.key) as transaction:
            record = transaction.read(); record["state"] = "closed"; transaction.write(record)
        self.terminal.panes = self.terminal.panes[:1]
        self.handler.handle(self.event())
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")
        event = self.event(); event["client_context"]["attachment_id"] = "attach-2"
        self.handler.handle(event)
        self.assertEqual(self.store.read_binding(self.key)["state"], "visible")

    def test_interrupted_start_recovers_while_the_reopened_session_is_idle(self):
        previous = self.seed_starting()
        self.assertIsNone(self.handler.handle(self.event()))
        record = self.store.read_binding(self.key)
        self.assertEqual(record["state"], "visible")
        self.assertNotEqual(record["nonce"], previous["nonce"])
        self.assertGreaterEqual(self.clock.now, 1004.0)
        self.assertLess(self.clock.now, 1010.0)
        self.assertTrue(self.clock.sleeps)

    def test_killed_hook_releases_its_lock_and_the_next_attach_recovers(self):
        marker = self.store.root.parent / "starting-written"
        program = """
import importlib.util,json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from task_panel_store import Store
from task_panel_hook import Handler
spec=importlib.util.spec_from_file_location('hook_fixtures',sys.argv[2])
fixtures=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
store=Store(sys.argv[3]); clock=fixtures.Clock()
terminal=fixtures.Terminal(store,clock)
replace=store._replace
def interrupt(kind,key,value):
    replace(kind,key,value)
    if kind=='bindings' and value['state']=='starting':
        Path(sys.argv[4]).write_text('persisted')
        time.sleep(5)
store._replace=interrupt
Handler(store,lambda context:terminal,clock).handle(json.loads(sys.argv[5]))
"""
        child = subprocess.Popen([sys.executable, "-c", program, str(HOOKS), str(Path(__file__).resolve()),
                                  str(self.store.root), str(marker), json.dumps(self.event())],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 3
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), "Child hook did not reach the persisted starting state")
            nonce = self.store.read_binding(self.key)["nonce"]
            child.kill()
            child.communicate(timeout=3)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            with self.store.binding_transaction(self.key, deadline=time.monotonic() + 0.1):
                pass
            event = self.event(); event["client_context"]["attachment_id"] = "reopened-attach"
            self.assertIsNone(self.handler.handle(event))
            record = self.store.read_binding(self.key)
            self.assertEqual(record["state"], "visible")
            self.assertNotEqual(record["nonce"], nonce)
            self.assertEqual(record["attachment_id"], "reopened-attach")
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=3)

    def test_pending_old_instance_is_adopted_before_its_deadline(self):
        previous = self.seed_starting()
        self.terminal.pending.append((1001.0, previous["nonce"], "22"))
        self.handler.handle(self.event())
        record = self.store.read_binding(self.key)
        self.assertEqual(record["panel_pane"], "22")
        self.assertEqual(record["nonce"], previous["nonce"])
        self.assertFalse(any(call[0] == "split" for call in self.terminal.calls))

    def test_clock_rollback_does_not_extend_the_old_attempt(self):
        self.seed_starting(deadline=2004.0)
        self.handler.handle(self.event())
        self.assertEqual(self.store.read_binding(self.key)["state"], "visible")
        self.assertLess(self.clock.now, 1001.0)

    def test_stalled_viewer_reaches_a_diagnosed_budget_limit(self):
        self.terminal.delay = 100
        message = self.handler.handle(self.event())
        self.assertIn("超时", message)
        self.assertIn("恢复", message)
        self.assertEqual(self.store.read_binding(self.key)["state"], "error")
        self.assertLessEqual(self.clock.now, 1010.001)

    def test_late_old_instance_does_not_replace_the_new_binding(self):
        old = self.seed_starting(deadline=999.0)
        self.terminal.pending.append((1000.1, old["nonce"], "22"))
        self.handler.handle(self.event())
        record = self.store.read_binding(self.key)
        self.assertNotEqual(record["nonce"], old["nonce"])
        self.assertNotEqual(record["panel_pane"], "22")

    def test_newer_attachment_prevents_old_coordinator_result_writes(self):
        self.seed_starting()
        def take_over():
            with self.store.binding_transaction(self.key) as transaction:
                record = transaction.read(); record["attachment_id"] = "newer"; record["session_id"] = "root-2"; transaction.write(record)
        self.terminal.on_list = take_over
        self.handler.handle(self.event())
        record = self.store.read_binding(self.key)
        self.assertEqual(record["attachment_id"], "newer")
        self.assertEqual(record["session_id"], "root-2")
        self.assertEqual(record["state"], "starting")
        self.assertFalse(any(call[0] == "split" for call in self.terminal.calls))

    def test_cli_attempt_budget_stops_before_another_rpc(self):
        self.seed_starting()
        self.terminal.on_list = lambda: setattr(self.clock, "now", self.clock.now + 3)
        message = self.handler.handle(self.event())
        self.assertIn("超时", message)
        self.assertEqual(len(self.terminal.calls), 1)
        self.assertEqual(self.store.read_binding(self.key)["state"], "error")

    def test_list_split_and_focus_errors_leave_an_actionable_failure(self):
        for failure in ("list", "split", "activate"):
            with self.subTest(failure=failure):
                self.terminal.failure = failure
                message = self.handler.handle(self.event())
                self.assertIsInstance(message, str)
                self.assertIn("WezTerm", message)
                self.assertIn("恢复", message)
                self.assertEqual(self.store.read_binding(self.key)["state"], "error")
                self.terminal.failure = None

    def test_missing_parent_removes_only_its_own_binding(self):
        self.seed_starting()
        self.terminal.panes = []
        self.handler.handle(self.event())
        self.assertIsNone(self.store.read_binding(self.key))

    def test_terminal_dependency_failure_is_saved_for_the_next_attachment(self):
        def unavailable(context):
            raise self.module.PanelError("WezTerm CLI unavailable")
        handler = self.module.Handler(self.store, unavailable, self.clock)
        message = handler.handle(self.event())
        self.assertIn("WezTerm", message)
        self.assertEqual(self.store.read_binding(self.key)["state"], "error")
        self.handler.handle(self.event())
        self.assertEqual(self.store.read_binding(self.key)["state"], "visible")

    def test_late_failure_does_not_mark_a_new_nonce_as_failed(self):
        self.seed_starting()
        def replace_attempt():
            with self.store.binding_transaction(self.key) as transaction:
                record = transaction.read(); record["nonce"] = "b" * 32; record["state"] = "visible"; record["panel_pane"] = "22"; transaction.write(record)
        self.terminal.on_list = replace_attempt
        self.terminal.failure = "list"
        self.handler.handle(self.event())
        self.assertEqual(self.store.read_binding(self.key)["state"], "visible")
        self.assertEqual(self.store.read_binding(self.key)["nonce"], "b" * 32)

    def test_ended_failed_start_can_restart_without_a_saved_deadline(self):
        record = self.seed_starting()
        record.update(state="error", starting_created_at=None, starting_deadline=None)
        with self.store.binding_transaction(self.key) as transaction:
            transaction.write(record)
        self.handler.handle(self.event(hook_event_name="SessionEnd", session_id="old-root"))
        self.assertIsNone(self.handler.handle(self.event()))
        self.assertEqual(self.store.read_binding(self.key)["state"], "visible")

    def test_capability_mismatch_is_deduplicated_per_attachment(self):
        event = self.event(hook_capabilities={"runtime_hooks_version": 1, "client_version": "old", "server_version": "new", "features": []})
        message = self.handler.handle(event)
        self.assertIn("effective_tool_context", message)
        self.assertIn("old", message)
        self.assertIn("new", message)
        self.assertIsNone(self.handler.handle(event))
        event["client_context"]["attachment_id"] = "attach-2"
        self.assertIsInstance(self.handler.handle(event), str)
        self.assertEqual(self.terminal.calls, [])

    def test_official_runtime_without_capabilities_has_installation_guidance(self):
        event = self.event(); event.pop("hook_capabilities"); event.pop("client_context")
        message = self.handler.handle(event)
        self.assertIn("安装", message)
        self.assertIn("重开", message)

    def test_malformed_capability_fields_cannot_enable_mounting(self):
        for index, changes in enumerate(({"runtime_hooks_version": True}, {"runtime_hooks_version": 2},
                                         {"client_version": 4}, {"server_version": None},
                                         {"features": [None]}, {"features": {"unexpected": True}})):
            event = self.event(); event["client_context"]["attachment_id"] = "attach-" + str(index)
            event["hook_capabilities"].update(changes)
            with self.subTest(changes=changes):
                self.assertIn("安装", self.handler.handle(event))
        self.assertEqual(self.terminal.calls, [])

    def test_supported_runtime_reports_missing_terminal_context(self):
        event = self.event(); event.pop("client_context")
        self.assertIn("client_context", self.handler.handle(event))
        event = self.event(); event["client_context"].pop("wezterm_pane")
        self.assertIn("wezterm_pane", self.handler.handle(event))
        event = self.event(); event["client_context"]["frontend"] = 4
        self.assertIn("frontend", self.handler.handle(event))
        self.assertEqual(self.terminal.calls, [])

    def test_headless_other_terminals_and_subagents_skip_mounting(self):
        for changes in ({"frontend": "exec"}, {"terminal_program": "other"}):
            event = self.event(); event["client_context"].update(changes)
            self.assertIsNone(self.handler.handle(event))
        self.assertIsNone(self.handler.handle(self.event(agent_id="child")))
        self.assertEqual(self.terminal.calls, [])
        self.assertEqual(self.store.binding_keys(), [])

    def test_session_end_does_not_end_the_new_binding_target(self):
        self.handler.handle(self.event())
        self.handler.handle(self.event(hook_event_name="SessionEnd", session_id="other-root"))
        self.assertEqual(self.store.read_binding(self.key)["state"], "visible")
        self.handler.handle(self.event(hook_event_name="SessionEnd"))
        self.assertEqual(self.store.read_binding(self.key)["state"], "ended")

    def test_session_end_respects_a_closed_attachment(self):
        self.handler.handle(self.event())
        with self.store.binding_transaction(self.key) as transaction:
            record = transaction.read(); record["state"] = "closed"; transaction.write(record)
        self.handler.handle(self.event(hook_event_name="SessionEnd"))
        self.assertEqual(self.store.read_binding(self.key)["state"], "closed")


class TerminalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("task_panel_hook")
        self.context = {"wezterm_unix_socket": "/tmp/current-client.sock", "wezterm_pane": "13"}

    def terminal(self):
        with patch.object(self.module.os, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=os.getuid())), patch.object(self.module.shutil, "which", return_value="/usr/local/bin/wezterm"):
            return self.module.WezTerm(self.context)

    def test_cli_selects_the_current_socket_parent_and_bottom_height(self):
        terminal = self.terminal()
        outputs = ['[{"pane_id":13,"window_id":1,"tab_id":1,"title":"Codex"}]', '14', '']
        with patch.object(self.module.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0, text, "") for text in outputs]) as run:
            self.assertEqual(terminal.list(1)[0]["pane_id"], 13)
            self.assertEqual(terminal.split("13", ["/python", "/plugin/task_panel.py", "--nonce", "a" * 32], 1), "14")
            terminal.activate("13", 1)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], ["/usr/local/bin/wezterm", "cli", "--no-auto-start", "list", "--format", "json"])
        self.assertEqual(commands[1][3:10], ["split-pane", "--pane-id", "13", "--bottom", "--cells", "10", "--"])
        self.assertEqual(commands[2][3:], ["activate-pane", "--pane-id", "13"])
        self.assertTrue(all(call.kwargs["env"]["WEZTERM_UNIX_SOCKET"] == self.context["wezterm_unix_socket"] for call in run.call_args_list))
        self.assertTrue(all(call.kwargs["timeout"] == 1 and call.kwargs["check"] for call in run.call_args_list))

    def test_invalid_pane_list_and_split_responses_are_diagnosed(self):
        terminal = self.terminal()
        for text in ('{}', 'null', '[{}]', 'broken', '[{"pane_id":true,"window_id":1,"tab_id":1,"title":"bad"}]'):
            with patch.object(self.module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, text, "")):
                with self.assertRaises(self.module.PanelError):
                    terminal.list(1)
        for text in ('bad', '14\n15', '-1', '١٤'):
            with patch.object(self.module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, text, "")):
                with self.assertRaises(self.module.PanelError):
                    terminal.split("13", ["/python"], 1)

    def test_socket_ownership_and_runtime_dependencies_are_checked(self):
        for info in (SimpleNamespace(st_mode=stat.S_IFREG, st_uid=os.getuid()),
                     SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=os.getuid() + 1)):
            with patch.object(self.module.os, "lstat", return_value=info), patch.object(self.module.shutil, "which", return_value="/wezterm"):
                with self.assertRaises(self.module.PanelError):
                    self.module.WezTerm(self.context)
        with patch.object(self.module.os, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=os.getuid())), patch.object(self.module.shutil, "which", return_value=None):
            with self.assertRaises(self.module.PanelError):
                self.module.WezTerm(self.context)

    def test_missing_curses_is_diagnosed_before_creating_a_pane(self):
        with patch.object(self.module.os, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=os.getuid())), patch.object(self.module.shutil, "which", return_value="/wezterm"), patch("importlib.import_module", side_effect=ImportError("curses missing")):
            with self.assertRaisesRegex(self.module.PanelError, "curses"):
                self.module.WezTerm(self.context)


if __name__ == "__main__":
    unittest.main()
