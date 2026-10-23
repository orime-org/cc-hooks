#!/usr/bin/env python3
"""Compare literal shell scanning with actual Bash and zsh argument parsing."""

import importlib.util
from pathlib import Path
import subprocess
import unittest

from shell_oracle import SHELLS


SOURCE = Path(__file__).resolve().parents[1] / "watcher/hooks/codex_gate_context.py"
SPEC = importlib.util.spec_from_file_location("codex_gate_context", SOURCE)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class LiteralScannerTests(unittest.TestCase):
    def oracle(self, command):
        parsed = list(GATE.segments(command))
        actual_words = [word.value for _, _, words, _ in parsed for word in words[1:]]
        for shell in SHELLS:
            with self.subTest(command=command, shell=shell):
                result = subprocess.run(
                    [shell, "-c", "capture() { printf '%s\\0' \"$@\"; }; " + command],
                    capture_output=True, check=True,
                )
                expected = result.stdout.decode().split("\0")[:-1]
                self.assertEqual(actual_words, expected)
        return parsed

    def test_unquoted_hash_is_literal_inside_words(self):
        self.oracle("capture main#project prefix# suffix##")

    def test_empty_quote_and_escaped_space_keep_hash_in_word(self):
        self.oracle("capture ''#literal \"\"#literal \\ #literal \\#literal")

    def test_comments_ignore_quotes_operators_and_escapes(self):
        self.oracle('capture first # ; && || capture "unclosed \\\ncapture second')

    def test_comment_after_separator_and_at_start(self):
        self.oracle('# ignored; capture bad\ncapture good;# ignored\ncapture last')

    def test_single_quotes_keep_all_content(self):
        self.oracle("capture 'single \\ $ ` ; & | # \" quotes' 'line\\\nnext'")

    def test_double_quotes_decode_only_shell_escapes(self):
        self.oracle('capture "a\\qb" "a\\#b" "a\\$b" "a\\`b" "a\\\\b" "a\\\"b"')

    def test_unquoted_escapes_preserve_word_boundaries(self):
        self.oracle(r'capture escaped\ space escaped\;word escaped\&word escaped\|word escaped\"word')

    def test_continuation_between_and_inside_words(self):
        self.oracle('capture \\\nfirst mid\\\ndle \\\n# ignored\ncapture last')

    def test_continuation_inside_double_quotes(self):
        self.oracle('capture "dou\\\nble" "# first\\\n; last"')

    def test_single_quote_continuation_is_literal(self):
        self.oracle("capture 'sin\\\ngle'")

    def test_real_newlines_inside_quotes_remain_literal(self):
        self.oracle('capture "first\nsecond" \'third\nfourth\'')

    def test_quote_concatenation_empty_words_and_tabs(self):
        self.oracle('capture \tplain\'joined\'"word" "" \'\' a\rb')

    def test_quoted_and_escaped_operators_are_not_separators(self):
        parsed = self.oracle('capture "a;b" \'c&&d\' e\\|f; capture next\ncapture last')
        self.assertEqual([connector for connector, _, _, _ in parsed], [';', ';', '\n'])

    def test_connectors_are_preserved(self):
        parsed = list(GATE.segments('true && git status || false; true | cat & true\ngit status'))
        self.assertEqual([item[0] for item in parsed], [';', '&&', '||', ';', '|', '&', '\n'])
        parsed = self.oracle('capture first |\n# ignored\ncat')
        self.assertEqual([item[0] for item in parsed], [';', '|'])

    def test_empty_source_and_comment_only_source_have_no_words(self):
        for command in ('', ' \t', '# trailing comment', '# first\n# last'):
            with self.subTest(command=command):
                self.assertTrue(all(not words for _, _, words, _ in GATE.segments(command)))

    def test_original_message_spelling_and_word_ends_are_preserved(self):
        command = 'git -C main#project -c note="commit" com\\\nmit -m "feat: a \\\"quote\\\" # ;" # ignored'
        _, raw, words, ends = list(GATE.segments(command))[0]
        paths, index = GATE.git_commit(words)
        self.assertEqual([path.value for path in paths], ['main#project'])
        self.assertEqual(raw[ends[index]:], ' -m "feat: a \\\"quote\\\" # ;" ')

    def test_invalid_quotes_and_trailing_escape_raise(self):
        for command in ('capture "unclosed', "capture 'unclosed", 'capture trailing\\'):
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    list(GATE.segments(command))

    def test_static_directory_words_match_actual_shell_expansion(self):
        spellings = ['~', '~root', '~/',
                     '"~"', "'~root'", r'\~', '~/' + '"with space"',
                     "~/'$repo'", r'~/with\ space', "'~'/repo", "\"\"'~'"]
        for spelling in spellings:
            word = list(GATE.segments('capture ' + spelling))[0][2][1]
            for shell in SHELLS:
                with self.subTest(spelling=spelling, shell=shell):
                    result = subprocess.run([shell, '-c', "capture() { printf '%s' \"$1\"; }; "
                                             + 'capture ' + spelling], capture_output=True, text=True, check=True)
                    self.assertEqual(word.directory_value(), result.stdout)

    def test_dynamic_directory_words_use_existing_legacy_context(self):
        spellings = ['$repo', '${repo}', '"$repo"', '`pwd`', '"`pwd`"', '$(pwd)',
                     '$((1))', '$[1]', '$\'escaped\\tword\'', '$"translated"',
                     '$1', '$$', '$?', '$!', '$#', '$@', '$*', '$-', '$_',
                     '$\\\nrepo', '"$\\\nrepo"', '~+', '~-', '~1', '~+2', '~-2']
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                command = 'git -C ' + spelling + ' commit -m "feat: dynamic"'
                contexts = GATE.resolve({'cwd': '/private/tmp', 'tool_input': {'command': command}})
                self.assertEqual(contexts, [{'cwd': '/private/tmp', 'command': command, 'legacy': True}])

    def test_mixed_tilde_prefixes_keep_runtime_dependent_context(self):
        for spelling in ['""~', '~""', "''~", "~''", '~"root"', "~'root'", r'~\root', '~"/tmp"']:
            with self.subTest(spelling=spelling):
                command = 'git -C ' + spelling + ' commit -m "feat: runtime prefix"'
                contexts = GATE.resolve({'cwd': '/private/tmp', 'tool_input': {'command': command}})
                self.assertTrue(contexts[0].get('legacy'), contexts)

    def test_words_preserve_raw_spans_parts_and_empty_quotes(self):
        command = 'capture ""~ \\$repo \'~\' "\\$repo" mid\\\nword'
        words = list(GATE.segments(command))[0][2][1:]
        for word in words:
            self.assertEqual(command[word.span[0]:word.span[1]], word.source)
            self.assertEqual(''.join(part.text for part in word.parts), word.value)
        self.assertEqual([(part.kind, part.text) for part in words[0].parts],
                         [('double', ''), ('unquoted', '~')])
        self.assertEqual(words[-1].source, 'mid\\\nword')
        self.assertEqual(words[-1].value, 'midword')


if __name__ == '__main__':
    unittest.main(verbosity=2)
