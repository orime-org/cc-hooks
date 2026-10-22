#!/usr/bin/env python3
"""Exercise Codex execution-context routing through the real Bash hook."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil


HOOK = Path(os.environ.get("GATE_HOOK", Path(__file__).resolve().parents[1] / "watcher/hooks/bash-gate.sh"))


class GateContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="codex-gate-context-")
        cls.root = Path(cls.temp.name)
        cls.main = cls.repo("main repository", "main")
        cls.task = cls.repo("task repository", "feat/context")
        cls.unmanaged = cls.repo("unmanaged", "main", managed=False)
        cls.plain_main = cls.repo("plain-main", "main")
        cls.option_path = cls.repo("repository -m bad", "feat/quoted-path")
        (cls.root / "container" / "nested").mkdir(parents=True)
        (cls.task / "subdirectory").mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def repo(cls, name, branch, managed=True):
        directory = cls.root / name
        directory.mkdir()
        subprocess.run(["git", "init", "-q", "-b", branch, str(directory)], check=True)
        if managed:
            (directory / ".watcher").mkdir()
        return directory

    def call(self, command, effective=None, *, cwd=None, context=None, codex=True):
        payload = {"cwd": str(cwd or self.main), "tool_input": {"command": command}}
        if effective is not None:
            payload["tool_execution_context"] = {"environment_id": "local", "is_remote": False, "cwd": str(effective)}
        if context is not None:
            payload["tool_execution_context"] = context
        return subprocess.run(["bash", str(HOOK)] + (["codex"] if codex else []), input=json.dumps(payload), text=True, capture_output=True)

    def verdict(self, command, effective, code, text=None, **kwargs):
        result = self.call(command, effective, **kwargs)
        self.assertEqual(result.returncode, code, result.stderr)
        if text:
            self.assertIn(text, result.stderr + result.stdout)
        return result

    def test_effective_feature_overrides_hook_main(self):
        self.verdict('git commit -m "feat: context"', self.task, 0)

    def test_effective_main_overrides_hook_feature(self):
        self.verdict('git commit -m "feat: context"', self.main, 2, "main", cwd=self.task)

    def test_missing_context_preserves_local_fallback(self):
        self.verdict('git commit -m "feat: context"', None, 0, cwd=self.task)

    def test_claude_uses_hook_directory(self):
        self.verdict('git commit -m "feat: context"', self.task, 2, "main", codex=False)

    def test_relative_cd_uses_effective_directory(self):
        self.verdict('cd "../main repository" && git commit -m "feat: context"', self.task, 2, "main", cwd=self.unmanaged)

    def test_sequential_cd_preserves_quoted_spaces(self):
        self.verdict('cd container && cd nested && cd "../../main repository" && git commit -m "feat: context"', self.root, 2, "main", cwd=self.unmanaged)

    def test_cd_then_relative_git_directory(self):
        self.verdict('cd container && git -C "../main repository" commit -m "feat: context"', self.root, 2, "main", cwd=self.unmanaged)

    def test_multiple_git_directories_are_sequential(self):
        self.verdict('git -C container -C "../main repository" commit -m "feat: context"', self.root, 2, "main", cwd=self.unmanaged)

    def test_git_directory_option_after_commit_is_message_reuse(self):
        self.verdict('git commit -C deadbeef', self.main, 2, "main", cwd=self.task)

    def test_second_commit_has_its_own_directory(self):
        self.verdict('git commit -m "feat: first"; cd "../main repository" && git commit -m "feat: second"', self.task, 2, "main")

    def test_second_managed_commit_after_unmanaged_is_checked(self):
        self.verdict('git commit -m "bad title"; cd "../main repository" && git commit -m "feat: second"', self.unmanaged, 2, "main")

    def test_second_commit_title_is_checked(self):
        self.verdict('git commit -m "feat: first" && git commit -m "bad title"', self.task, 2, "type")

    def test_git_directory_does_not_change_shell_directory(self):
        self.verdict('git -C "../task repository" commit -m "feat: first"; git commit -m "feat: second"', self.main, 2, "main", cwd=self.unmanaged)

    def test_trailing_cd_does_not_change_commit_target(self):
        self.verdict('git commit -m "feat: context"; cd "../task repository"', self.main, 2, "main")

    def test_unmanaged_effective_repository_passes(self):
        self.verdict('git commit -m "bad title"', self.unmanaged, 0)

    def test_non_commit_mention_passes(self):
        self.verdict('echo "git commit -m bad"', self.main, 0)

    def test_git_options_before_commit(self):
        self.verdict('git -c core.x=1 --no-pager -C "main repository" commit -m "feat: context"', self.root, 2, "main", cwd=self.unmanaged)

    def test_message_shell_operators_are_preserved(self):
        self.verdict('git commit -m "feat: support foo|bar & baz"', self.task, 0)

    def test_cd_back_uses_previous_directory(self):
        self.verdict('cd "../task repository" && cd - && git commit -m "feat: context"', self.main, 2, "main", cwd=self.unmanaged)

    def test_remote_commit_reports_support_boundary(self):
        context = {"environment_id": "ssh:example", "is_remote": True, "cwd": "ssh://example/work/repo"}
        result = self.call('git commit -m "bad title"', context=context)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("当前执行环境的 Git 策略需由远端配置提供", result.stderr + result.stdout)

    def test_remote_noncommit_passes_without_diagnostic(self):
        context = {"environment_id": "ssh:example", "is_remote": True, "cwd": "ssh://example/work/repo"}
        result = self.call('git status', context=context)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr + result.stdout, "")

    def test_context_schema_is_checked(self):
        invalid = [[], "local", {}, {"environment_id": "local", "is_remote": "false", "cwd": str(self.task)},
                   {"environment_id": "local", "is_remote": False, "cwd": "relative"},
                   {"environment_id": 1, "is_remote": False, "cwd": str(self.task)}]
        for context in invalid:
            with self.subTest(context=context):
                result = self.call('git commit -m "feat: context"', cwd=self.unmanaged, context=context)
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_invalid_context_does_not_block_diagnostic_command(self):
        result = self.call('git status', context=[])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_cd_followed_by_and_skips_commit(self):
        self.verdict('cd missing && git commit -m "feat: context"', self.main, 0)

    def test_failed_cd_followed_by_semicolon_keeps_directory(self):
        self.verdict('cd missing; git commit -m "feat: context"', self.main, 2, "main", cwd=self.unmanaged)

    def test_failed_cd_followed_by_or_runs_commit(self):
        self.verdict('cd missing || git commit -m "feat: context"', self.main, 2, "main", cwd=self.unmanaged)

    def test_successful_cd_followed_by_or_skips_commit(self):
        self.verdict('cd "../main repository" || git commit -m "feat: context"', self.task, 0)

    def test_newlines_keep_message_and_command_boundaries(self):
        self.verdict('git commit -m "feat: first\n\nbody"\ncd "../main repository"\ngit commit -m "feat: second"', self.task, 2, "main")

    def test_escaped_space_path(self):
        self.verdict('git -C main\\ repository commit -m "feat: context"', self.root, 2, "main", cwd=self.unmanaged)

    def test_cd_options(self):
        for option in ("-L", "-P", "--"):
            with self.subTest(option=option):
                self.verdict(f'cd {option} "../main repository" && git commit -m "feat: context"', self.task, 2, "main", cwd=self.unmanaged)

    def test_empty_git_directory_option_preserves_current(self):
        self.verdict('git -C "" commit -m "feat: context"', self.main, 2, "main", cwd=self.unmanaged)

    def test_literal_command_substitution_message_is_opaque(self):
        self.verdict('git commit -m "$(cat <<EOF\nfeat: context\nEOF\n)"', self.task, 0)

    def test_dynamic_directory_retains_legacy_verdict(self):
        commands = [
            'cd "$REPOSITORY" && git commit -m "feat: context"',
            'git -C "$REPOSITORY" commit -m "feat: context"',
            'cd "$(pwd)" && git commit -m "feat: context"',
            f'unknown-command && cd {self.plain_main} && git commit -m "feat: context"',
            f'unknown-command || cd {self.plain_main} && git commit -m "feat: context"',
            f'git --git-dir={self.plain_main}/.git --work-tree={self.plain_main} commit -m "feat: context"',
        ]
        for command in commands:
            with self.subTest(command=command):
                old = self.call(command, cwd=self.task, codex=False)
                current = self.call(command, self.task, cwd=self.unmanaged)
                self.assertEqual((current.returncode, current.stderr), (old.returncode, old.stderr))

    def test_tilde_directory_preserves_home_expansion(self):
        relative = os.path.relpath(self.plain_main, Path.home())
        command = f'git -C ~/{relative} commit -m "feat: context"'
        self.verdict(command, self.task, 2, "main", cwd=self.unmanaged)

    def test_git_global_option_text_is_not_commit_message(self):
        self.verdict('git -C "repository -m bad" commit -m "feat: context"', self.root, 0)

    def test_commit_word_in_global_path_is_not_subcommand(self):
        self.verdict('git -C "repository -m bad" -c note.text="commit" commit -m "bad title"', self.root, 2, "type")

    def test_noncommit_shell_parse_error_keeps_legacy_verdict(self):
        result = self.call('echo "unclosed', self.task)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_python_reports_commit_fault_and_allows_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="codex-gate-path-") as temp:
            for name in ("cat", "jq", "grep"):
                Path(temp, name).symlink_to(shutil.which(name))
            env = dict(os.environ, PATH=temp)
            for command, code in [('git commit -m "feat: context"', 2), ('git status', 0)]:
                with self.subTest(command=command):
                    payload = {"cwd": str(self.task), "tool_input": {"command": command}}
                    result = subprocess.run(["/bin/bash", str(HOOK), "codex"], env=env, input=json.dumps(payload), text=True, capture_output=True)
                    self.assertEqual(result.returncode, code, result.stderr)
                    if code:
                        self.assertIn("Python", result.stderr)

    def test_malformed_hook_input_preserves_commit_only_failure(self):
        for raw, code in [('{"tool_input":{"command":"git commit"', 2), ('{"tool_input":{"command":"git status"', 0)]:
            with self.subTest(raw=raw):
                result = subprocess.run(["bash", str(HOOK), "codex"], input=raw, text=True, capture_output=True)
                self.assertEqual(result.returncode, code, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
