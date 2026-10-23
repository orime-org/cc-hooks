#!/usr/bin/env python3
"""Resolve literal local command directories for the shared commit checks."""

import json
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WordPart:
    kind: str
    text: str


@dataclass(frozen=True)
class Word:
    parts: tuple[WordPart, ...]
    source: str
    span: tuple[int, int]

    @property
    def value(self):
        return "".join(part.text for part in self.parts)

    @property
    def dynamic(self):
        for part_index, part in enumerate(self.parts):
            if part.kind not in ("unquoted", "double"):
                continue
            for index, char in enumerate(part.text):
                if char == "`":
                    return True
                if char == "$" and index + 1 < len(part.text):
                    following = part.text[index + 1]
                    if following.isalnum() or following in "_@*#?$!{(-[":
                        return True
            if (part.kind == "unquoted" and part.text.endswith("$")
                    and part_index + 1 < len(self.parts)
                    and self.parts[part_index + 1].kind in ("single", "double")):
                return True
        return False

    def directory_value(self):
        if self.dynamic:
            raise LegacyDirectory
        if not self.value.startswith("~"):
            return self.value
        first = next(part for part in self.parts if part.text)
        if first.kind != "unquoted":
            return self.value
        # Mixed tilde prefixes depend on the execution shell and its active options.
        if first is not self.parts[0] or ("/" not in first.text and len(self.parts) > 1):
            raise LegacyDirectory
        prefix = self.value.split("/", 1)[0]
        if prefix.startswith(("~+", "~-")) or prefix[1:].isdigit():
            raise LegacyDirectory
        return os.path.expanduser(self.value)


def segments(command):
    """Read literal shell words and retain their source for message checks."""
    raw, words, ends, parts = [], [], [], []
    started = False
    word_start = 0
    quote = None
    connector = ";"
    index = 0

    def append_part(kind, text):
        if parts and parts[-1][0] == kind:
            parts[-1][1].append(text)
        else:
            parts.append((kind, [text]))

    def finish_word():
        frozen = tuple(WordPart(kind, "".join(chars)) for kind, chars in parts)
        words.append(Word(frozen, command[word_start:index], (word_start, index)))
        ends.append(len(raw))

    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            if index + 1 == len(command):
                raise ValueError("Trailing shell escape")
            following = command[index + 1]
            if following == "\n":
                index += 2
                continue
            if not started:
                word_start = index
            raw.extend((char, following))
            if quote == '"' and following not in '$`"\\':
                append_part("double", char + following)
            else:
                append_part("escaped", following)
            started = True
            index += 2
            continue
        if quote:
            raw.append(char)
            if char == quote:
                quote = None
            else:
                append_part("single" if quote == "'" else "double", char)
        elif char in "\"'":
            if not started:
                word_start = index
            raw.append(char)
            quote = char
            parts.append(("single" if char == "'" else "double", []))
            started = True
        elif char == "#" and not started:
            newline = command.find("\n", index)
            index = len(command) if newline == -1 else newline
            continue
        elif char in " \t\n;&|":
            if started:
                finish_word()
                parts = []
                started = False
            if char in " \t":
                raw.append(char)
                index += 1
                continue
            if char == "\n" and not words and connector in ("&&", "||", "|"):
                raw = []
                index += 1
                continue
            yield connector, "".join(raw), words, ends
            raw, words, ends = [], [], []
            connector = char
            if command[index:index + 2] in ("&&", "||"):
                connector = command[index:index + 2]
                index += 1
        else:
            if not started:
                word_start = index
            raw.append(char)
            append_part("unquoted", char)
            started = True
        index += 1
    if quote:
        raise ValueError("Unclosed shell quote")
    if started:
        finish_word()
    yield connector, "".join(raw), words, ends


def git_commit(words):
    """Read Git global options only before the subcommand."""
    if not words or words[0].value != "git":
        return None
    paths = []
    index = 1
    while index < len(words):
        word = words[index].value
        if word in ("-C", "-c", "--config-env", "--git-dir", "--work-tree", "--namespace"):
            if index + 1 >= len(words):
                return None
            if word == "-C":
                paths.append(words[index + 1])
            elif word in ("--git-dir", "--work-tree"):
                paths.append(None)
            index += 2
        elif word.startswith(("--git-dir=", "--work-tree=")):
            paths.append(None)
            index += 1
        elif word.startswith("-"):
            index += 1
        else:
            return (paths, index) if word == "commit" else None
    return None


class LegacyDirectory(Exception):
    """Retain the existing gate semantics for unresolved shell context."""


@dataclass(frozen=True)
class DirectoryResult:
    cwd: str | None

    @property
    def succeeded(self):
        return self.cwd is not None


def logical_directory(path):
    root = "//" if path.startswith("//") and not path.startswith("///") else "/"
    current = root
    for component in path.split("/"):
        if component in ("", "."):
            continue
        if component == "..":
            current = os.path.dirname(current) or root
        else:
            current = os.path.join(current, component)
            # A prefix must be a directory before logical parent traversal can remove it.
            if not os.path.isdir(current):
                return None
    return current


def evaluate_directory(base, value, *, physical=False):
    if "\0" in value:
        raise ValueError("目录含非法字符")
    path = os.path.join(base, value)
    if not physical:
        logical = logical_directory(path)
        if logical is not None and os.access(logical, os.X_OK):
            return DirectoryResult(logical)
    # Default shell cd can retry its original path after a failed logical candidate.
    if os.path.isdir(path) and os.access(path, os.X_OK):
        try:
            return DirectoryResult(os.path.realpath(path, strict=True))
        except OSError:
            pass
    return DirectoryResult(None)


def legacy_context(cwd, command):
    return [{"cwd": cwd, "command": command, "legacy": True}]


def resolve(payload):
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        raise ValueError("command 必须是字符串")
    try:
        parsed = list(segments(command))
    except ValueError:
        context = payload.get("tool_execution_context")
        current = payload.get("cwd")
        if isinstance(context, dict) and context.get("is_remote") is False and isinstance(context.get("cwd"), str):
            current = context["cwd"]
        return legacy_context(current, command)
    if not any(git_commit(words) is not None for _, _, words, _ in parsed):
        return []
    context = payload.get("tool_execution_context")
    if context is not None:
        if (not isinstance(context, dict) or not isinstance(context.get("environment_id"), str)
                or not context["environment_id"] or type(context.get("is_remote")) is not bool
                or not isinstance(context.get("cwd"), str) or not context["cwd"]):
            raise ValueError("tool_execution_context 结构无效")
        if context["is_remote"]:
            print("当前执行环境的 Git 策略需由远端配置提供。请在远端配置提交策略后重试。", file=sys.stderr)
            return []
        current = context["cwd"]
        if not os.path.isabs(current) or "\0" in current:
            raise ValueError("本地 tool_execution_context.cwd 必须是有效绝对路径")
    else:
        current = payload.get("cwd")
        if not isinstance(current, str) or not os.path.isabs(current) or "\0" in current:
            raise ValueError("cwd 必须是有效绝对路径")
    initial = current
    if any(connector in ("|", "&") or words and words[0].value.startswith(("(", "{"))
           for connector, _, words, _ in parsed):
        return legacy_context(initial, command)
    previous = None
    status = True
    results = []
    for connector, raw, words, ends in parsed:
        if not words:
            continue
        if connector == "&&" and status is False or connector == "||" and status is True:
            continue
        uncertain = connector in ("&&", "||") and status is None
        if words[0].value == "cd":
            if uncertain:
                return legacy_context(initial, command)
            args = words[1:]
            physical = False
            if args and args[0].value in ("-L", "-P"):
                physical = args.pop(0).value == "-P"
            if args and args[0].value == "--":
                args.pop(0)
            if len(args) != 1:
                return legacy_context(initial, command)
            if args[0].value == "-":
                if previous is None:
                    return legacy_context(initial, command)
                value = previous
            else:
                try:
                    value = args[0].directory_value()
                except LegacyDirectory:
                    return legacy_context(initial, command)
            result = evaluate_directory(current, value, physical=physical)
            status = result.succeeded
            if status:
                previous, current = current, result.cwd
        else:
            paths = git_commit(words)
            if paths is not None:
                paths, commit_index = paths
                directory = DirectoryResult(current)
                for path in paths:
                    if path is None:
                        return legacy_context(initial, command)
                    try:
                        directory = evaluate_directory(directory.cwd, path.directory_value(), physical=True)
                    except LegacyDirectory:
                        return legacy_context(initial, command)
                    if not directory.succeeded:
                        break
                if directory.succeeded:
                    results.append({"cwd": directory.cwd, "command": "git commit " + raw[ends[commit_index]:]})
                status = None if directory.succeeded else False
                continue
            status = True if words[0].value in ("true", ":") else False if words[0].value == "false" else None
    return results


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook 输入必须是对象")
        print(json.dumps(resolve(payload), ensure_ascii=False))
    except (ValueError, TypeError, AttributeError, OSError) as error:
        print(f"拦截器无法解析 Codex 执行目录：{error}。请使用明确的本地目录后重试。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
