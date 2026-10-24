#!/usr/bin/env python3
"""Exercise native session routing through actual terminal process identities."""

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'watcher/hooks'))
from task_panel_binding import SessionRouter
from task_panel_hook import Handler
from task_panel_launch import prepare
from task_panel_process import ProcessError
from task_panel_store import Store, StoreError, binding_key


class Processes:
    def __init__(self, *rows):
        self.rows = list(rows)

    def list(self, deadline=None):
        return self.rows.copy()

    def read(self, pid, deadline=None):
        return next((row for row in self.rows if row['pid'] == pid), None)


class SessionBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Store(self.root)
        self.first = dict(pid=101, cwd=str(self.root / 'project'), started_at=10.0)
        self.second = dict(pid=102, cwd=self.first['cwd'], started_at=20.0)
        self.processes = Processes(self.first)
        self.router = SessionRouter(self.store, self.processes)

    def event(self, identifier='session-A', **updates):
        return dict(session_id=identifier, cwd=self.first['cwd'], hook_event_name='SessionStart', **updates)

    def pane(self, process=None, parent='1'):
        process = process or self.first
        key, nonce = prepare(self.store, process, parent, '/tmp/session-panel.sock', str(int(parent) + 10), 'project')
        return key, nonce

    def test_native_event_updates_existing_viewer_identity_and_keeps_its_nonce(self):
        key, nonce = self.pane()
        self.router.observe(self.event())
        record = self.store.read_binding(key)
        self.assertEqual(record['session_id'], 'session-A')
        self.assertTrue(record['session_confirmed'])
        self.assertEqual(record['nonce'], nonce)
        self.assertEqual(record['panel_pane'], '11')

    def test_new_process_event_before_registration_keeps_existing_session(self):
        first_key, _ = self.pane()
        self.router.observe(self.event())
        self.processes.rows.append(self.second)
        self.router.observe(self.event('session-B'))
        self.assertEqual(self.store.read_binding(first_key)['session_id'], 'session-A')
        second_key, _ = self.pane(self.second, '2')
        self.router.attach(second_key)
        self.assertEqual(self.store.read_binding(second_key)['session_id'], 'session-B')

    def test_event_before_first_gui_observation_is_consumed_by_its_process(self):
        self.router.observe(self.event())
        key, _ = self.pane()
        self.router.attach(key)
        self.assertEqual(self.store.read_binding(key)['session_id'], 'session-A')
        self.assertEqual(self.store.read_binding(key)['owner_started_at'], 10.0)

    def test_known_session_wins_when_another_same_directory_process_starts(self):
        key, _ = self.pane()
        self.router.observe(self.event())
        self.processes.rows.append(self.second)
        self.router.observe(self.event())
        self.assertEqual(self.store.read_session('session-A')['owner_pid'], 101)
        self.assertEqual(self.store.read_binding(key)['session_id'], 'session-A')

    def test_same_process_new_session_updates_the_existing_pane(self):
        key, nonce = self.pane()
        self.router.observe(self.event())
        self.router.observe(self.event('session-B'))
        record = self.store.read_binding(key)
        self.assertEqual((record['session_id'], record['nonce']), ('session-B', nonce))

    def test_directory_of_another_project_is_not_selected(self):
        self.processes.rows[0] = dict(self.first, cwd=str(self.root / 'different'))
        self.router.observe(self.event())
        self.assertIsNone(self.store.read_session('session-A')['owner_pid'])

    def test_pid_reuse_uses_the_system_start_time(self):
        self.router.observe(self.event())
        self.processes.rows[0] = dict(self.first, started_at=30.0)
        self.router.observe(self.event())
        self.assertEqual(self.store.read_session('session-A')['owner_started_at'], 30.0)

    def test_absent_process_can_be_resolved_when_the_pane_registers(self):
        self.processes.rows.clear()
        self.router.observe(self.event())
        self.processes.rows.append(self.first)
        key, _ = self.pane()
        self.router.attach(key)
        self.assertEqual(self.store.read_binding(key)['session_id'], 'session-A')

    def test_closed_pane_remains_closed_when_the_plan_changes(self):
        key, _ = self.pane()
        self.router.observe(self.event())
        with self.store.binding_transaction(key) as transaction:
            transaction.write(dict(transaction.read(), state='closed'))
        self.router.observe(self.event('session-B'))
        self.assertEqual(self.store.read_binding(key)['state'], 'closed')

    def test_new_pid_can_resume_a_session_owned_by_a_dead_process(self):
        self.router.observe(self.event())
        self.processes.rows = [self.second]
        key, _ = self.pane(self.second, '2')
        self.router.observe(self.event())
        self.assertEqual(self.store.read_binding(key)['session_id'], 'session-A')
        self.assertEqual(self.store.read_session('session-A')['owner_pid'], 102)

    def test_ended_event_is_not_consumed_by_a_later_pane(self):
        self.router.observe(self.event())
        self.router.end('session-A')
        key, _ = self.pane()
        self.router.attach(key)
        self.assertFalse(self.store.read_binding(key)['session_confirmed'])

    def test_late_end_for_the_previous_session_keeps_the_new_session_connected(self):
        key, _ = self.pane()
        handler = Handler(self.store, session_router=self.router)
        handler.handle(self.event())
        handler.handle(self.event('session-B'))
        handler.handle(dict(session_id='session-A', cwd=self.first['cwd'], hook_event_name='SessionEnd'))
        self.assertNotEqual(self.store.read_binding(key)['state'], 'ended')

    def test_active_event_revives_an_ended_viewer(self):
        key, _ = self.pane()
        handler = Handler(self.store, session_router=self.router)
        handler.handle(self.event())
        handler.handle(dict(session_id='session-A', cwd=self.first['cwd'], hook_event_name='SessionEnd'))
        self.router.observe(self.event('session-B'))
        self.assertNotEqual(self.store.read_binding(key)['state'], 'ended')

    def test_handler_persists_native_plan_before_routing_and_clear(self):
        key, _ = self.pane()
        handler = Handler(self.store, session_router=self.router)
        for plan in ([dict(step='Task', status='in_progress')], []):
            event = self.event(tool_name='update_plan', tool_input={'plan': plan}, tool_response='Plan updated')
            event['hook_event_name'] = 'PostToolUse'
            handler.handle(event)
            self.assertEqual(self.store.read_plan('session-A')['plan'], plan)
            self.assertEqual(self.store.read_binding(key)['session_id'], 'session-A')

    def test_subagent_event_does_not_change_the_main_session(self):
        key, _ = self.pane()
        handler = Handler(self.store, session_router=self.router)
        handler.handle(self.event(agent_id='child'))
        self.assertFalse(self.store.read_binding(key)['session_confirmed'])
        self.assertEqual(self.store.session_keys(), [])

    def test_process_failure_preserves_the_plan_and_unclaimed_native_event(self):
        handler = Handler(self.store, session_router=self.router)
        event = self.event(tool_name='update_plan', tool_input={'plan': []}, tool_response='Plan updated')
        event['hook_event_name'] = 'PostToolUse'
        with patch.object(self.processes, 'list', side_effect=ProcessError('Process access denied')):
            with self.assertRaises(ProcessError):
                handler.handle(event)
        self.assertEqual(self.store.read_plan('session-A')['plan'], [])
        self.assertIsNone(self.store.read_session('session-A')['owner_pid'])

    def test_session_record_rejects_malformed_schema(self):
        self.router.observe(self.event())
        original = self.store.read_session('session-A')
        for change in ({'owner_pid':True}, {'owner_started_at':float('nan')},
                       {'owner_pid':None}, {'cwd':'relative'}, {'ended':1}, {'observed_at':float('inf')},
                       {'session_id':'another'}):
            with self.subTest(change=change):
                with self.assertRaises(StoreError):
                    with self.store.session_transaction('session-A') as transaction:
                        transaction.write(dict(original, **change))

    def test_binding_record_rejects_partial_or_invalid_process_fields(self):
        key, _ = self.pane()
        original = self.store.read_binding(key)
        for change in ({'owner_pid':True}, {'owner_pid':0}, {'owner_cwd':'relative'},
                       {'owner_started_at':float('nan')}, {'session_confirmed':'yes'}):
            with self.subTest(change=change):
                with self.assertRaises(StoreError):
                    with self.store.binding_transaction(key) as transaction:
                        transaction.write(dict(original, **change))


if __name__ == '__main__':
    unittest.main()
