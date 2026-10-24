#!/usr/bin/env python3
"""Check native process discovery on the host platform."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "watcher/hooks"))
from task_panel_process import ProcessReader


def main():
    if sys.platform == "darwin":
        reader = ProcessReader()
        records = reader.list()
        assert records, "Start Codex before running the macOS native process smoke test"
        checked = 0
        for record in records:
            current = reader.read(record["pid"])
            if current is not None:
                assert current == record, "Single-process read and discovery disagree"
                checked += 1
        assert checked, "No Codex process remained available for verification"
        print(json.dumps(dict(result="passed", platform=sys.platform, discovered=len(records),
                              matching_single_reads=checked, read_only=True)))
        return
    sleeper = shutil.which("sleep")
    if sleeper is None:
        raise RuntimeError("The system sleep executable is required for this smoke test")
    with tempfile.TemporaryDirectory(prefix="task-panel-process-") as temporary:
        root = Path(temporary).resolve()
        cwd = root / "项目 with spaces"
        cwd.mkdir()
        executable = root / "codex"
        shutil.copyfile(sleeper, executable)
        executable.chmod(0o700)
        before = time.time()
        fixture = subprocess.Popen([str(executable), "20"],
                                   cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        record = None
        try:
            reader = ProcessReader()
            record = reader.read(fixture.pid)
            assert record is not None, "Native fixture was not recognized"
            assert record["cwd"] == str(cwd), "Native cwd was not preserved"
            assert before - 1 <= record["started_at"] <= time.time(), "Native start time is incorrect"
            found = next((candidate for candidate in reader.list() if candidate["pid"] == fixture.pid), None)
            assert found == record, "Single-process read and discovery disagree"
        finally:
            if fixture.poll() is None:
                fixture.terminate()
            fixture.communicate(timeout=5)
        assert ProcessReader().read(fixture.pid) is None, "Exited fixture remained visible"
        print(json.dumps(dict(result="passed", platform=sys.platform, process=record,
                              exit_code=fixture.returncode, remaining=False), ensure_ascii=False))


if __name__ == "__main__":
    main()
