#!/usr/bin/env python3
"""Check manual audit policy through real Stop output and private state files."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = Path(os.environ.get("STOP_HOOK", ROOT / "watcher/hooks/suggest-watcher.sh"))
SKILL = ROOT / "watcher/skills/watcher/SKILL.md"
CODEX = len(sys.argv) > 1 and sys.argv[1] == "codex"
COMMAND = "$watcher:watcher" if CODEX else "/watcher:watcher"


class ManualAuditPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="manual-audit-policy-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        self.state = self.project / ".watcher/audit-state.json"
        self.environment = {**os.environ, "PLUGIN_DATA": str(Path(self.temporary.name) / "data")}
        Path(self.environment["PLUGIN_DATA"]).mkdir()

    def write_state(self, enabled, rounds):
        self.state.parent.mkdir(exist_ok=True)
        self.state.write_text(json.dumps({"enable-audit": enabled, "unaudited-rounds": rounds,
                                         "project-note": "preserve"}))

    def stop(self):
        payload = {"session_id": "manual-audit-policy", "cwd": str(self.project),
                   "stop_hook_active": False, "last_assistant_message": "done"}
        result = subprocess.run(["bash", str(HOOK), *(["codex"] if CODEX else [])],
                                input=json.dumps(payload), text=True, capture_output=True,
                                env=self.environment, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_manual_policy(self, response):
        self.assertNotIn("decision", response)
        if CODEX:
            self.assertNotIn("continue", response)
            message = response["systemMessage"]
        else:
            self.assertIs(response["continue"], False)
            message = response["stopReason"]
        self.assertIn("禁止自行触发 audit", message)
        self.assertIn(f"用户手动输入 `{COMMAND}` 时执行一次审计", message)
        self.assertNotIn("务必不要 audit", message)
        return message

    def test_off_allows_manual_audit_without_enabling_automatic_audit(self):
        self.write_state(False, 7)
        message = self.assert_manual_policy(self.stop())
        self.assertIn("自动开关保持关闭", message)
        state = json.loads(self.state.read_text())
        self.assertIs(state["enable-audit"], False)
        self.assertEqual(state["unaudited-rounds"], 8)

    def test_unconfigured_project_allows_explicit_manual_audit(self):
        self.assert_manual_policy(self.stop())
        self.assertFalse(self.state.exists())

    def test_manual_entry_resets_rounds_and_preserves_the_off_switch(self):
        self.write_state(False, 7)
        entry = re.search(r"```bash\n(.*?)\n```", SKILL.read_text(), re.S)
        self.assertIsNotNone(entry, "The actual audit entry must define its state reset")
        result = subprocess.run(["bash", "-c", entry.group(1)], cwd=self.project,
                                text=True, capture_output=True, env=self.environment, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.state.read_text()),
                         {"enable-audit": False, "unaudited-rounds": 0, "project-note": "preserve"})
        self.assert_manual_policy(self.stop())
        self.assertEqual(json.loads(self.state.read_text())["unaudited-rounds"], 1)

    def test_on_still_requests_the_automatic_audit(self):
        self.write_state(True, 7)
        response = self.stop()
        self.assertEqual(response["decision"], "block")
        marker = "`watcher:watcher` skill" if CODEX else "调用 Skill"
        self.assertIn(marker, response["reason"])
        self.assertNotIn("禁止自行触发 audit", response["reason"])
        self.assertIs(json.loads(self.state.read_text())["enable-audit"], True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
