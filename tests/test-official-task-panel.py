#!/usr/bin/env python3
"""Exercise official hook payloads, session identity and saved-plan recovery."""

import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "watcher/hooks"))
from task_panel_hook import Handler
from task_panel_store import Store
from task_panel_session import recover_plan, displayed_session
from task_panel_setup import configure_codex, configure_wezterm

FIRST = "01a16cdd-6a06-7ca3-85aa-a19bf12990a4"
SECOND = "01a16cdd-6f48-71f1-96e6-2cd6dcfb791f"
PLAN = [{"step": "读取当前会话", "status": "in_progress"}]


class OfficialSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Store(self.root / "cache")

    def transcript(self, identifier=FIRST, tail=()):
        path = self.root / "session.jsonl"
        rows = [{"type": "session_meta", "payload": {"id": identifier, "cwd": "/work/project"}}]
        rows.extend(tail)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def call(self, identifier="call-1", plan=PLAN):
        return {"type": "response_item", "payload": {"type": "function_call", "name": "update_plan",
                "call_id": identifier, "arguments": json.dumps({"plan": plan})}}

    def result(self, identifier="call-1", output="Plan updated"):
        return {"type": "response_item", "payload": {"type": "function_call_output",
                "call_id": identifier, "output": output}}

    def test_native_identity_matches_title_and_full_status_id(self):
        self.assertEqual(displayed_session("project | " + FIRST[:29] + "...", "footer " + FIRST), FIRST)
        self.assertIsNone(displayed_session("project | " + FIRST[:29] + "...", "footer " + SECOND))
        self.assertIsNone(displayed_session("project", "quoted " + FIRST))

    def test_same_folder_sessions_recover_their_own_plan(self):
        first = self.transcript(tail=[self.call(), self.result()])
        self.assertTrue(recover_plan(self.store, FIRST, first))
        second = self.transcript(SECOND, [self.call(plan=[]), self.result()])
        self.assertTrue(recover_plan(self.store, SECOND, second))
        self.assertEqual(self.store.read_plan(FIRST)["plan"], PLAN)
        self.assertEqual(self.store.read_plan(SECOND)["plan"], [])

    def test_recovery_uses_last_successful_update(self):
        path = self.transcript(tail=[self.call(), self.result(), self.call("clear", []), self.result("clear"),
                                     self.call("failed"), self.result("failed", "Error: invalid plan"),
                                     self.call("unfinished")])
        self.assertTrue(recover_plan(self.store, FIRST, path))
        self.assertEqual(self.store.read_plan(FIRST)["plan"], [])

    def test_other_session_and_unfinished_calls_do_not_seed_cache(self):
        path = self.transcript(SECOND, [self.call(), self.result()])
        self.assertFalse(recover_plan(self.store, FIRST, path))
        path = self.transcript(tail=[self.call()])
        self.assertFalse(recover_plan(self.store, FIRST, path))
        self.assertIsNone(self.store.read_plan(FIRST))

    def test_existing_hook_snapshot_wins_over_historical_recovery(self):
        self.store.save_plan(FIRST, "project", [], 200)
        path = self.transcript(tail=[self.call(), self.result()])
        recover_plan(self.store, FIRST, path)
        self.assertEqual(self.store.read_plan(FIRST)["plan"], [])

    def test_official_session_start_reads_without_custom_runtime_or_terminal_environment(self):
        path = self.transcript(tail=[self.call(), self.result()])
        handler = Handler(self.store, lambda context: self.fail("Hooks must not select a terminal"))
        self.assertIsNone(handler.handle({"hook_event_name": "SessionStart", "source": "resume",
                                         "session_id": FIRST, "cwd": "/work/project", "transcript_path": str(path)}))
        self.assertEqual(self.store.read_plan(FIRST)["plan"], PLAN)
        self.assertEqual(self.store.binding_keys(), [])

    def test_official_plan_hook_updates_only_its_session(self):
        handler = Handler(self.store)
        for identifier, plan in ((FIRST, PLAN), (SECOND, [])):
            handler.handle({"hook_event_name": "PostToolUse", "session_id": identifier, "cwd": "/work/project",
                            "tool_name": "update_plan", "tool_input": {"plan": plan}, "tool_response": "Plan updated"})
        self.assertEqual(self.store.read_plan(FIRST)["plan"], PLAN)
        self.assertEqual(self.store.read_plan(SECOND)["plan"], [])

    def test_setup_preserves_settings_and_can_be_repeated(self):
        text = 'model = "existing"\n[tui]\nstatus_line = [\n"current-dir",\n"task-progress",\n]\nterminal_title = ["thread-name"]\n[other]\nenabled = true\n'
        configured = configure_codex(text)
        self.assertEqual(configure_codex(configured), configured)
        parsed = tomllib.loads(configured)
        self.assertEqual(parsed["model"], "existing")
        self.assertEqual(parsed["other"], {"enabled": True})
        self.assertEqual(parsed["tui"]["status_line"], ["session-id", "current-dir", "task-progress"])
        self.assertEqual(parsed["tui"]["terminal_title"], ["thread-name", "session-id"])

    def test_setup_creates_missing_table_without_changing_other_tables(self):
        configured = configure_codex('[other]\nsecret = "preserved"\n')
        self.assertEqual(tomllib.loads(configured)["other"], {"secret": "preserved"})
        self.assertIn("session-id", tomllib.loads(configured)["tui"]["status_line"])

    def test_wezterm_setup_preserves_return_and_replaces_only_managed_block(self):
        text = 'local config = { font_size = 15 }\nreturn config\n'
        configured = configure_wezterm(text, self.root / "loader.lua")
        self.assertTrue(configured.endswith(text))
        self.assertEqual(configure_wezterm(configured, self.root / "loader.lua"), configured)
        changed = configure_wezterm(configured, self.root / "next.lua")
        self.assertTrue(changed.endswith(text))
        self.assertEqual(changed.count("-- BEGIN cc-hooks task panel"), 1)


if __name__ == "__main__":
    unittest.main()
