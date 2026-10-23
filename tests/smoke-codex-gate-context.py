#!/usr/bin/env python3
"""Exercise Codex execution-context routing through the real Bash hook."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from shell_oracle import SHELLS
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
        cls.hash_main = cls.repo("main#project", "main")
        (cls.main / "subdirectory").mkdir()
        (cls.task / "main-link").symlink_to(cls.main / "subdirectory", target_is_directory=True)
        cls.option_path = cls.repo("repository -m bad", "feat/quoted-path")
        (cls.root / "container" / "nested").mkdir(parents=True)
        (cls.task / "subdirectory").mkdir()
        for outer, branch in ((cls.task, "main"), (cls.main, "feat/literal")):
            for name in ("~", "~root", "$repo", "`repo`", "with space $repo", "$"):
                cls.repo(str(outer.relative_to(cls.root) / name), branch)
        (cls.task / "~" / "nested").mkdir()
        (cls.task / "literal-link").symlink_to(cls.task / "~" / "nested", target_is_directory=True)

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

    def literal_oracle(self, prefix, effective, branch):
        for shell in SHELLS:
            with self.subTest(shell=shell, prefix=prefix):
                result = subprocess.run([shell, '-c', prefix + ' branch --show-current'],
                                        cwd=effective, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), branch)

    def test_protected_tilde_is_a_literal_directory(self):
        for spelling in ('"~"', "'~'", r'\~', '"~root"', "'~root'", r'\~root'):
            for prefix in ('git -C ' + spelling, 'cd ' + spelling + ' && git'):
                for effective, branch, code in ((self.task, 'main', 2), (self.main, 'feat/literal', 0)):
                    with self.subTest(prefix=prefix, effective=effective):
                        self.literal_oracle(prefix, effective, branch)
                        self.verdict(prefix + ' commit -m "feat: literal directory"', effective, code)

    def test_protected_expansion_characters_are_literal_directories(self):
        spellings = [r'\$repo', r'"\$repo"', "'$repo'", r'\`repo\`', r'"\`repo\`"', "'`repo`'",
                     r'"with space \$repo"', r'with\ space\ \$repo', "'with space $repo'"]
        for spelling in spellings:
            for prefix in ('git -C ' + spelling, 'cd ' + spelling + ' && git'):
                for effective, branch, code in ((self.task, 'main', 2), (self.main, 'feat/literal', 0)):
                    with self.subTest(prefix=prefix, effective=effective):
                        self.literal_oracle(prefix, effective, branch)
                        self.verdict(prefix + ' commit -m "feat: literal directory"', effective, code)

    def test_literal_word_parts_remain_literal_when_joined(self):
        for spelling in ("'$'repo", '"$"repo', r'\$"repo"', "'`'repo'`'", '"~"""', r'\~""'):
            for prefix in ('git -C ' + spelling, 'cd ' + spelling + ' && git'):
                with self.subTest(prefix=prefix):
                    self.literal_oracle(prefix, self.task, 'main')
                    self.verdict(prefix + ' commit -m "feat: joined literal"', self.task, 2)

    def test_bare_dollar_without_expansion_is_literal(self):
        for spelling in ('"$"', "'$'", '$'):
            prefix = 'git -C ' + spelling
            with self.subTest(prefix=prefix):
                self.literal_oracle(prefix, self.task, 'main')
                self.verdict(prefix + ' commit -m "feat: dollar literal"', self.task, 2)

    def test_literal_directories_compose_across_cd_and_git_options(self):
        for prefix in ('cd "~" && git -C .. -C "~"',
                       'git -C "~" -C .. -C "\\$repo"',
                       'cd "\\$repo" && cd .. && git -C "~"',
                       'cd -P literal-link/.. && git',
                       'cd -L literal-link/.. && git -C "~"'):
            with self.subTest(prefix=prefix):
                self.literal_oracle(prefix, self.task, 'main')
                self.verdict(prefix + ' commit -m "feat: composed directories"', self.task, 2)

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
            'echo value | git commit -m "feat: context"',
            'git commit -m "feat: context" & echo value',
            '(git commit -m "feat: context")',
            '{ git commit -m "feat: context"; }',
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

    def test_physical_directories_match_real_git_and_shell(self):
        prefixes = [
            'git -C main-link/..', 'git -C main-link -C ..',
            'cd -P main-link/.. && git', 'cd -L main-link/.. && git',
            'cd main-link/.. && git', 'git -C subdirectory/..',
        ]
        for prefix in prefixes:
            for shell in SHELLS:
                with self.subTest(prefix=prefix, shell=shell):
                    actual = subprocess.run([shell, '-c', prefix + ' branch --show-current'],
                                            cwd=self.task, capture_output=True, text=True, check=True)
                    expected = 2 if actual.stdout.strip() == 'main' else 0
                    self.verdict(prefix + ' commit -m "feat: context"', self.task, expected)

    def test_hash_in_literal_directory_matches_real_git(self):
        for spelling in ('../main#project', '../main\\#project', '"../main#project"', "'../main#project'"):
            with self.subTest(spelling=spelling):
                oracle = subprocess.run(['/bin/bash', '-c', f'git -C {spelling} branch --show-current'],
                                        cwd=self.task, capture_output=True, text=True, check=True)
                self.assertEqual(oracle.stdout.strip(), 'main')
                self.verdict(f'git -C {spelling} commit -m "feat: context"', self.task, 2, 'main')

    def test_comments_end_at_newline_before_command_splitting(self):
        commands = [
            'git status # ; git commit -m "bad title"',
            '# git commit -m "bad title"',
            'git status;# && git commit -m "bad title"',
            'git status # \\\ngit status',
            'git commit -m "feat: context" # ; git commit -m "bad title"',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.verdict(command, self.task, 0)
        self.verdict('git status # ignored; git status\ngit commit -m "bad title"', self.task, 2, 'type')

    def test_shell_continuations_preserve_commit_and_path(self):
        commands = [
            'git \\\ncommit -m "feat: context"',
            'git com\\\nmit -m "feat: context"',
            'git -C "../main\\\n repository" commit -m "feat: context"',
            'git -C ../main\\\n\\ repository commit -m "feat: context"',
            'git commit -m "feat: context" \\\n# ignored ; git status',
        ]
        for command in commands:
            with self.subTest(command=command):
                effective = self.main if '-C' not in command else self.task
                self.verdict(command, effective, 2, 'main')

    def test_continued_title_and_quoted_hash_remain_checked(self):
        for command in [
            'git commit -m "ba\\\nd title"',
            'git commit -m "feat: context" # --message="bad title"',
            'git commit -m "feat: support # and ;"',
            "git commit -m 'feat: support # and ;'",
            'git commit -m "feat: escaped \\" quote #"',
        ]:
            with self.subTest(command=command):
                self.verdict(command, self.task, 2 if command.startswith('git commit -m "ba') else 0)

    def test_newlines_and_comments_keep_pending_conditionals(self):
        for prefix, code in [('false &&', 0), ('true ||', 0), ('true &&', 2), ('false ||', 2)]:
            for gap in ('\n', '\n# ignored ; git status\n', ' # ignored ; git status\n'):
                with self.subTest(prefix=prefix, gap=gap):
                    command = prefix + gap + 'git commit -m "feat: context"'
                    for shell in SHELLS:
                        oracle = subprocess.run([shell, '-c', 'git() { printf executed; }; ' + command],
                                                capture_output=True, text=True)
                        self.assertEqual(oracle.stdout, 'executed' if code else '')
                    self.verdict(command, self.main, code)

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
