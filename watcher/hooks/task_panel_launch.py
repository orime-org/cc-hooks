"""Start a viewer in the pane created by the local WezTerm Lua observer."""

import argparse
import os
from pathlib import Path
import sys
import time
import uuid

from task_panel import main as viewer_main
from task_panel_session import find_transcript, recover_plan
from task_panel_store import Store, StoreError, binding_key, session_id


def prepare(store, identifier, parent, attachment, socket, pane, title, home):
    identifier = session_id(identifier)
    key, nonce = binding_key(socket, parent), uuid.uuid4().hex
    recover_plan(store, identifier, find_transcript(home, identifier))
    now = time.time()
    with store.binding_transaction(key, time.monotonic() + 1) as transaction:
        transaction.write({"version": 1, "socket": socket, "parent_pane": parent, "panel_pane": pane,
                           "session_id": identifier, "attachment_id": session_id(attachment), "nonce": nonce,
                           "state": "starting", "ready_nonce": None, "project_title": title or "Codex",
                           "starting_created_at": now, "starting_deadline": now + 4})
    return key, nonce


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-dir", "session", "parent", "attachment", "codex-home"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--title", default="Codex")
    args = parser.parse_args()
    try:
        socket, pane = os.environ.get("WEZTERM_UNIX_SOCKET"), os.environ.get("WEZTERM_PANE")
        store = Store(Path(args.data_dir) / "task-panel")
        key, nonce = prepare(store, args.session, args.parent, args.attachment, socket, pane,
                             args.title, args.codex_home)
        return viewer_main(["--data-dir", str(store.root), "--binding", key, "--nonce", nonce,
                            "--socket", socket, "--parent", args.parent])
    except (OSError, StoreError, ValueError) as error:
        print(f"任务面板启动失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
