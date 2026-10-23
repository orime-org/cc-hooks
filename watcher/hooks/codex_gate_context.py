#!/usr/bin/env python3
"""Resolve literal local command directories for the shared commit checks."""

import json
import os
import sys


def segments(command):
    """Read literal shell words and retain their source for message checks."""
    raw, words, ends, word = [], [], [], []
    started = False
    quote = None
    connector = ";"
    index = 0
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            if index + 1 == len(command):
                raise ValueError("Trailing shell escape")
            following = command[index + 1]
            if following == "\n":
                index += 2
                continue
            raw.extend((char, following))
            if quote == '"' and following not in '$`"\\':
                word.append(char)
            word.append(following)
            started = True
            index += 2
            continue
        if quote:
            raw.append(char)
            if char == quote:
                quote = None
            else:
                word.append(char)
        elif char in "\"'":
            raw.append(char)
            quote = char
            started = True
        elif char == "#" and not started:
            newline = command.find("\n", index)
            index = len(command) if newline == -1 else newline
            continue
        elif char in " \t\n;&|":
            if started:
                words.append("".join(word))
                ends.append(len(raw))
                word = []
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
            raw.append(char)
            word.append(char)
            started = True
        index += 1
    if quote:
        raise ValueError("Unclosed shell quote")
    if started:
        words.append("".join(word))
        ends.append(len(raw))
    yield connector, "".join(raw), words, ends


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


class LegacyDirectory(Exception):
    """Retain the existing gate semantics for unresolved shell context."""


def literal_directory(base, value, *, physical=False):
    if any(marker in value for marker in ("$", "`")):
        raise LegacyDirectory
    value = os.path.expanduser(value)
    if "\0" in value:
        raise ValueError("目录含非法字符")
    path = os.path.join(base, value)
    return os.path.realpath(path) if physical else os.path.normpath(path)


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
    if any(connector in ("|", "&") or words and words[0].startswith(("(", "{"))
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
                results.append({"cwd": directory, "command": "git commit " + raw[ends[commit_index]:]})
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
