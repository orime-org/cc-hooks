#!/usr/bin/env python3
"""Drive the installed hook entrypoint with native hook JSON fixtures."""

import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "watcher/hooks/task-panel.sh"


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="watcher-panel-entry-")
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.environment = dict(os.environ, PLUGIN_DATA=str(self.data))

    def run_hook(self, event, argument="codex", environment=None, raw=False):
        return subprocess.run(["/bin/bash", str(SCRIPT), argument], input=event if raw else json.dumps(event),
                              env=environment or self.environment, capture_output=True, text=True, timeout=5)

    def plan(self, plan=None):
        return {"hook_event_name": "PostToolUse", "session_id": "root-1", "tool_name": "update_plan",
                "cwd": "/work/project", "tool_input": {"plan": [{"step": "检查中文", "status": "pending"}] if plan is None else plan}}

    def test_post_tool_use_entrypoint_saves_and_clears_a_plan(self):
        result = self.run_hook(self.plan())
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.data / "task-panel/plans/root-1.json"
        self.assertEqual(json.loads(path.read_text())["plan"], [{"step": "检查中文", "status": "pending"}])
        self.assertEqual(self.run_hook(self.plan([])).returncode, 0)
        self.assertEqual(json.loads(path.read_text())["plan"], [])

    def test_failed_plan_input_is_nonblocking_and_preserves_the_snapshot(self):
        self.assertEqual(self.run_hook(self.plan()).returncode, 0)
        path = self.data / "task-panel/plans/root-1.json"
        previous = path.read_bytes()
        result = self.run_hook(self.plan([{"step": "bad", "status": "unknown"}]))
        self.assertEqual(result.returncode, 1)
        self.assertIn("任务面板处理失败", result.stderr)
        self.assertEqual(path.read_bytes(), previous)

    def test_subagent_entrypoint_does_not_save_a_root_plan(self):
        event = self.plan(); event["agent_id"] = "child"
        result = self.run_hook(event)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.data / "task-panel").exists())

    def test_official_runtime_receives_one_capability_diagnostic(self):
        event = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "root-1", "cwd": "/work"}
        first = self.run_hook(event)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("安装", json.loads(first.stdout)["systemMessage"])
        second = self.run_hook(event)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(second.stdout, "")

    def test_missing_python_has_a_localized_recovery_message(self):
        environment = dict(self.environment, PATH=str(self.data))
        result = self.run_hook(self.plan(), environment=environment)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Python", json.loads(result.stdout)["systemMessage"])
        self.assertIn("安装", json.loads(result.stdout)["systemMessage"])

    def test_unsupported_python_version_has_a_recovery_message(self):
        executable = self.data / "python3"
        executable.write_text("#!/bin/sh\nexit 1\n")
        executable.chmod(0o700)
        result = self.run_hook(self.plan(), environment=dict(self.environment, PATH=str(self.data)))
        self.assertEqual(result.returncode, 0)
        self.assertIn("3.11", json.loads(result.stdout)["systemMessage"])

    def test_other_platform_arguments_skip_the_entrypoint(self):
        result = self.run_hook(self.plan(), argument="claude")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.data / "task-panel").exists())

    def test_invalid_json_and_missing_plugin_data_are_diagnosed(self):
        result = self.run_hook("{", raw=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("恢复", json.loads(result.stdout)["systemMessage"])
        environment = dict(self.environment); environment.pop("PLUGIN_DATA")
        result = self.run_hook({"hook_event_name": "SessionStart"}, environment=environment)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PLUGIN_DATA", json.loads(result.stdout)["systemMessage"])

    def test_manifest_wires_the_three_runtime_events_and_timeouts(self):
        config = json.loads((ROOT / "watcher/hooks/codex-hooks.json").read_text())["hooks"]
        expected = {"SessionStart": 12, "PostToolUse": 5, "SessionEnd": 3}
        for event, timeout in expected.items():
            with self.subTest(event=event):
                handler = config[event][0]["hooks"][0]
                self.assertIn('${PLUGIN_ROOT}/hooks/task-panel.sh', handler["command"])
                self.assertEqual(handler["timeout"], timeout)
                self.assertFalse(handler.get("async", False))
        self.assertEqual(config["PostToolUse"][0]["matcher"], "^update_plan$")

    def test_copied_plugin_includes_the_runtime_and_source_license(self):
        plugin = self.data / "installed plugin"
        shutil.copytree(ROOT / "watcher", plugin, ignore=shutil.ignore_patterns("__pycache__"))
        license_text = (plugin / "third-party/multi-cc-im.LICENSE").read_text()
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 orime-org and contributors", license_text)
        result = subprocess.run(["/bin/bash", str(plugin / "hooks/task-panel.sh"), "codex"],
                                input=json.dumps(self.plan()), env=self.environment, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.data / "task-panel/plans/root-1.json").read_text())["plan"][0]["step"], "检查中文")
        self.assertTrue((plugin / "hooks/task_panel.py").is_file())


if __name__ == "__main__":
    unittest.main()
