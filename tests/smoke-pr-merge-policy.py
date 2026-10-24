#!/usr/bin/env python3
"""Verify that the actual prompt hook reserves PR merging for the user."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = Path(os.environ.get("ANNOUNCE_HOOK", ROOT / "watcher/hooks/announce-intent.sh"))


class PrMergePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = {}
        with tempfile.TemporaryDirectory(prefix="pr-merge-policy-") as data:
            for platform, arguments in (("claude", []), ("codex", ["codex"])):
                result = subprocess.run(["bash", str(HOOK), *arguments],
                                        input=json.dumps({"prompt": "continue", "session_id": "merge-policy"}),
                                        env={**os.environ, "PLUGIN_DATA": data},
                                        text=True, capture_output=True, timeout=5)
                if result.returncode:
                    raise RuntimeError(result.stderr)
                cls.outputs[platform] = result.stdout

    def test_only_the_user_can_check_and_merge(self):
        for platform, output in self.outputs.items():
            with self.subTest(platform=platform):
                self.assertIn("PR只能由用户check后亲自合并", output)
                self.assertIn("你无权合并或启用自动合并", output)

    def test_workflow_waits_for_the_user_to_merge(self):
        for platform, output in self.outputs.items():
            with self.subTest(platform=platform):
                self.assertIn("等用户合并", output)
                self.assertNotIn("跟踪CI/review/合并", output)


if __name__ == "__main__":
    unittest.main()
