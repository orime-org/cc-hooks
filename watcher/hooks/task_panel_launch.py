"""Start a viewer in the pane created by the local WezTerm Lua observer."""

import argparse
import os
from pathlib import Path
import sys
import time
import uuid

from task_panel import main as viewer_main
from task_panel_binding import SessionRouter
from task_panel_process import ProcessReader
from task_panel_store import Store, StoreError, binding_key


def prepare(store, owner, parent, socket, pane, title):
    identifier = f"pending-{owner['pid']}"
    key, nonce = binding_key(socket, parent), uuid.uuid4().hex
    now = time.time()
    with store.binding_transaction(key, time.monotonic() + 1) as transaction:
        transaction.write({"version": 1, "socket": socket, "parent_pane": parent, "panel_pane": pane,
                           "session_id": identifier, "attachment_id": f"process-{owner['pid']}", "nonce": nonce,
                           "state": "starting", "ready_nonce": None,
                           "project_title": title or Path(owner['cwd']).name or "Codex",
                           "starting_created_at": now, "starting_deadline": now + 4,
                           "owner_pid": owner['pid'], "owner_cwd": str(Path(owner['cwd']).resolve()),
                           "owner_started_at": owner['started_at'], "session_confirmed": False})
    return key, nonce


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-dir", "parent"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument('--owner', type=int, required=True)
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    try:
        socket, pane = os.environ.get("WEZTERM_UNIX_SOCKET"), os.environ.get("WEZTERM_PANE")
        store = Store(Path(args.data_dir) / "task-panel")
        processes = ProcessReader()
        owner = processes.read(args.owner)
        if owner is None:
            raise ValueError('Interactive Codex process is no longer available')
        key, nonce = prepare(store, owner, args.parent, socket, pane, args.title)
        SessionRouter(store, processes).attach(key)
        return viewer_main(["--data-dir", str(store.root), "--binding", key, "--nonce", nonce,
                            "--socket", socket, "--parent", args.parent])
    except (OSError, StoreError, ValueError) as error:
        print(f"任务面板启动失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
