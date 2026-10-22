#!/usr/bin/env python3
"""Exercise private, atomic task-plan storage and binding transactions."""

import concurrent.futures
import importlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / "watcher" / "hooks"
sys.path.insert(0, str(HOOKS))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("task_panel_store")
        self.temporary = tempfile.TemporaryDirectory(prefix="watcher-panel-store-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "task-panel"
        self.store = self.module.Store(self.root)

    def binding(self, session="root-1"):
        return {"version": 1, "socket": "/tmp/wezterm.sock", "parent_pane": "13",
                "panel_pane": None, "session_id": session, "attachment_id": "attach-1",
                "nonce": "a" * 32, "state": "starting", "starting_created_at": 10.0,
                "starting_deadline": 14.0}

    def test_round_trip_preserves_unicode_order_and_statuses(self):
        plan = [{"step": "检查中文 e\u0301", "status": "completed"},
                {"step": "next", "status": "in_progress"}, {"step": "last", "status": "pending"}]
        self.store.save_plan("root-1", "项目", plan, updated_at=10.0)
        self.assertEqual(self.store.read_plan("root-1"),
                         {"version": 1, "session_id": "root-1", "title": "项目", "plan": plan, "updated_at": 10.0})

    def test_sessions_and_empty_plans_are_independent(self):
        plan = [{"step": "first", "status": "pending"}]
        self.store.save_plan("root-1", "one", plan)
        self.store.save_plan("root-2", "two", plan)
        self.store.save_plan("root-1", "one", [])
        self.assertEqual(self.store.read_plan("root-1")["plan"], [])
        self.assertEqual(self.store.read_plan("root-2")["plan"], plan)
        self.assertIsNone(self.store.read_plan("missing"))

    def test_invalid_plan_keeps_last_valid_snapshot(self):
        plan = [{"step": "first", "status": "pending"}]
        self.store.save_plan("root-1", "one", plan)
        for invalid in (None, {}, [None], [{"step": 4, "status": "pending"}],
                        [{"step": "bad", "status": "unknown"}], [{"step": "missing"}]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(self.module.StoreError):
                    self.store.save_plan("root-1", "one", invalid)
                self.assertEqual(self.store.read_plan("root-1")["plan"], plan)

    def test_invalid_plan_metadata_keeps_the_saved_record(self):
        self.store.save_plan("root-1", "saved", [], updated_at=1)
        previous = self.store.read_plan("root-1")
        for title, updated in ((None, 1), (3, 1), ("one", True),
                               ("one", "now"), ("one", float("inf")), ("one", float("nan"))):
            with self.subTest(title=title, updated=updated):
                with self.assertRaises(self.module.StoreError):
                    self.store.save_plan("root-1", title, [], updated_at=updated)
                self.assertEqual(self.store.read_plan("root-1"), previous)

    def test_large_plans_preserve_every_step(self):
        plan = [{"step": "task " + str(index) + "x" * 200, "status": "pending"} for index in range(2000)]
        self.store.save_plan("root-1", "large", plan)
        self.assertEqual(self.store.read_plan("root-1")["plan"], plan)

    def test_session_ids_cannot_escape_the_cache(self):
        for session in ("../escape", "/absolute", "", "a/b", "x" * 129, 4, "a\x00b"):
            with self.subTest(session=session):
                with self.assertRaises(self.module.StoreError):
                    self.store.save_plan(session, "one", [])
        self.assertFalse((self.root.parent / "escape.json").exists())

    def test_owned_directories_and_files_are_private(self):
        self.store.save_plan("root-1", "one", [])
        for directory in (self.root, self.root / "plans", self.root / "bindings"):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for path in (self.root / "plans").iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_corrupt_or_wrong_session_snapshots_report_errors(self):
        self.store.save_plan("root-1", "one", [])
        path = self.root / "plans/root-1.json"
        path.write_text("{")
        with self.assertRaises(self.module.StoreError):
            self.store.read_plan("root-1")
        path.write_text(json.dumps({"version": 1, "session_id": "another", "title": "one", "plan": [], "updated_at": 1}))
        with self.assertRaises(self.module.StoreError):
            self.store.read_plan("root-1")

    def test_symlink_records_are_rejected(self):
        outside = self.root.parent / "outside.json"
        payload = json.dumps({"version": 1, "session_id": "root-1", "title": "outside", "plan": [], "updated_at": 1})
        outside.write_text(payload)
        (self.root / "plans/root-1.json").symlink_to(outside)
        with self.assertRaises(self.module.StoreError):
            self.store.read_plan("root-1")
        self.assertEqual(outside.read_text(), payload)

    def test_binding_key_encodes_socket_and_parent(self):
        key = self.module.binding_key("/tmp/a", "13")
        self.assertEqual(key, self.module.binding_key("/tmp/a", "13"))
        self.assertNotEqual(key, self.module.binding_key("/tmp/a1", "3"))
        self.assertNotEqual(key, self.module.binding_key("/tmp/b", "13"))
        self.assertRegex(key, r"^[a-f0-9]{64}$")

    def test_binding_transactions_validate_and_round_trip(self):
        key = self.module.binding_key("/tmp/wezterm.sock", "13")
        with self.store.binding_transaction(key) as transaction:
            self.assertIsNone(transaction.read())
            transaction.write(self.binding())
        self.assertEqual(self.store.read_binding(key), self.binding())
        with self.store.binding_transaction(key) as transaction:
            invalid = self.binding()
            invalid["state"] = "unknown"
            with self.assertRaises(self.module.StoreError):
                transaction.write(invalid)
        self.assertEqual(self.store.read_binding(key), self.binding())

    def test_malformed_binding_fields_preserve_the_valid_binding(self):
        key = self.module.binding_key("/tmp/wezterm.sock", "13")
        previous = self.binding()
        with self.store.binding_transaction(key) as transaction:
            transaction.write(previous)
        for changes in ({"version": True}, {"version": 2}, {"socket": "relative"},
                        {"parent_pane": "-1"}, {"session_id": "../root"}, {"attachment_id": None},
                        {"nonce": "wrong"}, {"state": []}, {"panel_pane": []},
                        {"starting_created_at": None}, {"starting_deadline": None},
                        {"starting_deadline": float("inf")}):
            with self.subTest(changes=changes), self.store.binding_transaction(key) as transaction:
                with self.assertRaises(self.module.StoreError):
                    transaction.write(dict(previous, **changes))
            self.assertEqual(self.store.read_binding(key), previous)

    def test_owned_cache_directories_cannot_be_symlinked(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        other = self.root.parent / "other-cache"
        other.mkdir()
        (other / "plans").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(self.module.StoreError):
            self.module.Store(other)
        self.assertEqual(list(outside.iterdir()), [])

    def test_expired_transaction_cannot_write(self):
        key = self.module.binding_key("/tmp/wezterm.sock", "13")
        with self.store.binding_transaction(key) as transaction:
            transaction.write(self.binding())
        with self.assertRaises(self.module.StoreError):
            transaction.write(self.binding("root-2"))

    def test_binding_lock_wait_obeys_the_deadline(self):
        key = self.module.binding_key("/tmp/wezterm.sock", "13")
        program = "import sys,time; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from task_panel_store import Store; s=Store(Path(sys.argv[2]));\nwith s.binding_transaction(sys.argv[3]):\n print('locked',flush=True); time.sleep(0.25)"
        child = subprocess.Popen([sys.executable, "-c", program, str(HOOKS), str(self.root), key],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
            with self.assertRaises(self.module.StoreError):
                with self.store.binding_transaction(key, deadline=time.monotonic() + 0.03):
                    self.fail("Contended binding lock was acquired")
        finally:
            child.communicate(timeout=3)
            self.assertEqual(child.returncode, 0)

    def test_atomic_writes_remain_complete_during_concurrent_reads(self):
        def writer(number):
            for index in range(20):
                steps = [{"step": f"{number}:{index}", "status": "pending"}] * 10
                self.store.save_plan("root-1", str(number), steps)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(writer, number) for number in range(2)]
            for _ in range(100):
                snapshot = self.store.read_plan("root-1")
                if snapshot is not None:
                    self.assertEqual(len(snapshot["plan"]), 10)
                    self.assertEqual(len({item["step"] for item in snapshot["plan"]}), 1)
            for future in futures:
                future.result()
        self.assertEqual(list((self.root / "plans").glob("*.tmp")), [])

    def test_readers_keep_the_previous_snapshot_during_serialization(self):
        self.store.save_plan("root-1", "old", [])
        previous = self.store.read_plan("root-1")
        partial_write = threading.Event()
        resume = threading.Event()

        def paused_dump(value, stream, **kwargs):
            encoded = json.dumps(value, **kwargs)
            midpoint = len(encoded) // 2
            stream.write(encoded[:midpoint])
            stream.flush()
            partial_write.set()
            if not resume.wait(3):
                raise RuntimeError("Serialization test did not release its writer")
            stream.write(encoded[midpoint:])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(self.module.json, "dump", paused_dump):
                future = pool.submit(self.store.save_plan, "root-1", "new", [])
                try:
                    self.assertTrue(partial_write.wait(3))
                    self.assertEqual(self.store.read_plan("root-1"), previous)
                finally:
                    resume.set()
                    future.result()
        self.assertEqual(self.store.read_plan("root-1")["title"], "new")

    def test_notice_identity_is_deduplicated(self):
        self.assertTrue(self.store.notice_once("session:attach-1:capability"))
        self.assertFalse(self.store.notice_once("session:attach-1:capability"))
        self.assertTrue(self.store.notice_once("session:attach-2:capability"))


if __name__ == "__main__":
    unittest.main()
