"""Read official session identity and recover successful saved plan calls."""

import json
from pathlib import Path
import re

from task_panel_store import StoreError, session_id

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def displayed_session(title, text):
    """Use a full native status UUID, corroborated by its native title item."""
    for identifier in reversed(re.findall(UUID, text.lower())):
        if identifier in title.lower() or identifier[:29] + "..." in title.lower():
            return identifier
    return None


def recover_plan(store, identifier, transcript):
    """Seed a missing snapshot from this session's last successful plan call."""
    identifier = session_id(identifier)
    if store.read_plan(identifier) is not None or not transcript:
        return False
    pending, latest, cwd = {}, None, ""
    try:
        with Path(transcript).open(encoding="utf-8") as stream:
            header = json.loads(next(stream))
            metadata = header.get("payload", {})
            if header.get("type") != "session_meta" or metadata.get("id") != identifier:
                return False
            cwd = metadata.get("cwd", "")
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                payload = row.get("payload", {})
                if row.get("type") != "response_item" or not isinstance(payload, dict):
                    continue
                call = payload.get("call_id")
                if not isinstance(call, str):
                    continue
                if payload.get("type") == "function_call" and payload.get("name") == "update_plan":
                    try:
                        arguments = json.loads(payload["arguments"])
                        if isinstance(arguments, dict) and "plan" in arguments:
                            pending[call] = arguments["plan"]
                    except (ValueError, TypeError, KeyError):
                        continue
                elif payload.get("type") == "function_call_output" and call in pending:
                    plan = pending.pop(call)
                    if payload.get("output") == "Plan updated":
                        latest = plan
    except (FileNotFoundError, StopIteration, ValueError):
        return False
    if latest is None:
        return False
    title = (Path(cwd).name if isinstance(cwd, str) and cwd else "Codex") or "Codex"
    try:
        return store.save_plan(identifier, title, latest, only_if_missing=True)
    except StoreError:
        return False


def find_transcript(home, identifier):
    identifier = session_id(identifier)
    return next((Path(home) / "sessions").glob(f"**/*-{identifier}.jsonl"), None)
