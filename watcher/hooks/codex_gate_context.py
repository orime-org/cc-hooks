#!/usr/bin/env python3
"""Resolve literal local command directories for the shared commit checks."""

import json
import os
import shlex
import sys


def segments(command):
    """Keep quoted operators and escaped separators inside their command."""
    start = 0
    quote = None
    escaped = False
    connector = ";"
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
        elif char == "\\" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in ";&|\n":
            yield connector, command[start:index]
            connector = char
            if command[index:index + 2] in ("&&", "||"):
                connector = command[index:index + 2]
                index += 1
            start = index + 1
        index += 1
    yield connector, command[start:]


def git_commit(words):
    """Read Git global options only before the subcommand."""
    if not words or words[0] != "git":
        return None
    paths = []
    index = 1
    while index < len(words):
        word = words[index]
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


def commit_segment(raw, index):
    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    for _ in range(index + 1):
        lexer.get_token()
    return "git commit " + raw[lexer.instream.tell():]


class LegacyDirectory(Exception):
    """Retain the existing gate semantics for unresolved shell context."""


def literal_directory(base, value, *, physical=False):
    if any(marker in value for marker in ("$", "`")):
        raise LegacyDirectory
    value = os.path.expanduser(value)
    if "\0" in value:
        raise ValueError("目录含非法字符")
    path = os.path.normpath(os.path.join(base, value))
    return os.path.realpath(path) if physical else path


def legacy_context(cwd, command):
    return [{"cwd": cwd, "command": command, "legacy": True}]


def resolve(payload):
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        raise ValueError("command 必须是字符串")
    try:
        parsed = [(connector, raw, shlex.split(raw, comments=True)) for connector, raw in segments(command)]
    except ValueError:
        context = payload.get("tool_execution_context")
        current = payload.get("cwd")
        if isinstance(context, dict) and context.get("is_remote") is False and isinstance(context.get("cwd"), str):
            current = context["cwd"]
        return legacy_context(current, command)
    if not any(git_commit(words) is not None for _, _, words in parsed):
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
    if any(connector in ("|", "&") or words and words[0].startswith(("(", "{"))
           for connector, _, words in parsed):
        return legacy_context(initial, command)
    previous = None
    status = True
    results = []
    for connector, raw, words in parsed:
        if not words:
            continue
        if connector == "&&" and status is False or connector == "||" and status is True:
            continue
        uncertain = connector in ("&&", "||") and status is None
        if words[0] == "cd":
            if uncertain:
                return legacy_context(initial, command)
            args = words[1:]
            physical = False
            if args and args[0] in ("-L", "-P"):
                physical = args.pop(0) == "-P"
            if args and args[0] == "--":
                args.pop(0)
            if len(args) != 1:
                return legacy_context(initial, command)
            if args[0] == "-":
                if previous is None:
                    return legacy_context(initial, command)
                target = previous
            else:
                try:
                    target = literal_directory(current, args[0], physical=physical)
                except LegacyDirectory:
                    return legacy_context(initial, command)
            status = os.path.isdir(target) and os.access(target, os.X_OK)
            if status:
                previous, current = current, target
        else:
            paths = git_commit(words)
            if paths is not None:
                paths, commit_index = paths
                directory = current
                for path in paths:
                    if path is None:
                        return legacy_context(initial, command)
                    try:
                        directory = literal_directory(directory, path, physical=True)
                    except LegacyDirectory:
                        return legacy_context(initial, command)
                results.append({"cwd": directory, "command": commit_segment(raw, commit_index)})
            status = True if words[0] in ("true", ":") else False if words[0] == "false" else None
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
