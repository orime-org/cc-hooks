#!/usr/bin/env python3
"""Measure idle CLI traffic and controls in an isolated native WezTerm GUI."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "watcher/hooks"
sys.path.insert(0, str(HOOKS))
from task_panel_store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wezterm", default="/Applications/WezTerm.app/Contents/MacOS/wezterm")
    parser.add_argument("--panels", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    out = args.output or Path(tempfile.mkdtemp(prefix="panel-refresh-"))
    out.mkdir(parents=True, exist_ok=True)
    data, traffic = out / "data", out / "cli.jsonl"
    store = Store(data)
    traffic.touch()
    wrapper = out / "wezterm-probe"
    wrapper.write_text(f"#!{sys.executable}\nimport json,os,sys,time\n"
                       f"with open({str(traffic)!r},'a') as stream:\n"
                       " stream.write(json.dumps({'at':time.time(),'args':sys.argv[1:]})+'\\n')\n"
                       f"os.execv({args.wezterm!r},[{args.wezterm!r},*sys.argv[1:]])\n")
    wrapper.chmod(0o700)
    launcher = out / "viewer.py"
    launcher.write_text(
        "import os,sys\n"
        f"sys.path.insert(0,{str(HOOKS)!r})\n"
        "from task_panel_launch import prepare\nfrom task_panel import main\n"
        "from task_panel_store import Store\n"
        f"store=Store({str(data)!r})\n"
        "owner={'pid':os.getpid(),'cwd':os.getcwd(),'started_at':1}\n"
        "socket=os.environ['WEZTERM_UNIX_SOCKET']\n"
        "key,nonce=prepare(store,owner,sys.argv[1],socket,os.environ['WEZTERM_PANE'],'refresh-test')\n"
        "with store.binding_transaction(key) as transaction:\n"
        " record=transaction.read();record['session_id']='refresh-'+sys.argv[1]\n"
        " record['session_confirmed']=True;transaction.write(record)\n"
        "raise SystemExit(main(['--data-dir',str(store.root),'--binding',key,'--nonce',nonce,"
        "'--socket',socket,'--parent',sys.argv[1]]))\n")
    lua = out / "wezterm.lua"
    lua.write_text(
        "local wz=require 'wezterm'\n"
        "wz.on('gui-startup',function()\n local win\n"
        f" for i=1,{args.panels} do\n local tab,parent\n"
        " if win then tab,parent=win:spawn_tab{args={'/bin/sleep','180'}}\n"
        " else tab,parent,win=wz.mux.spawn_window{args={'/bin/sleep','180'}} end\n"
        " parent:split{direction='Bottom',size=3,"
        f"set_environment_variables={{CC_HOOKS_WEZTERM={json.dumps(str(wrapper))}}},"
        f"args={{{json.dumps(sys.executable)},{json.dumps(str(launcher))},tostring(parent:pane_id())}}}}\n"
        " end\nend)\n"
        "return {initial_cols=130,initial_rows=35,font_size=12,"
        "window_close_confirmation='NeverPrompt',exit_behavior='Close'}\n")
    environment = dict(os.environ)
    environment.pop("WEZTERM_UNIX_SOCKET", None)
    log = (out / "wezterm.log").open("w")
    report = dict(result="failed", panel_count=args.panels)
    gui = subprocess.Popen([args.wezterm, "--config-file", str(lua), "start", "--always-new-process",
                            "--class", "cc-hooks-refresh-test"], env=environment, stdout=log, stderr=log)
    report["gui_pid"] = gui.pid
    (out / "owned-process.json").write_text(json.dumps(dict(pid=gui.pid, args=gui.args), indent=2))

    def wait_for(predicate, description):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            if gui.poll() is not None:
                raise AssertionError(f"WezTerm exited during {description}")
            time.sleep(.25)
        raise AssertionError(f"Timed out during {description}")

    def bindings():
        return [record for path in (data / "bindings").glob("*.json")
                if (record := json.loads(path.read_text()))["state"] == "visible"]

    def cli(*arguments):
        return subprocess.check_output([args.wezterm, "cli", "--no-auto-start", *map(str, arguments)],
                                       env=environment, text=True, timeout=12)

    def screen(record):
        return cli("get-text", "--pane-id", record["panel_pane"])

    def save(record, count):
        store.save_plan(record["session_id"], "refresh-test", [dict(step=f"验证任务 {n}", status="pending")
                                                              for n in range(count)], time.time())

    try:
        records = wait_for(lambda: (items if len(items := bindings()) == args.panels else None), "panel startup")
        environment["WEZTERM_UNIX_SOCKET"] = records[0]["socket"]
        for record in records:
            save(record, 6)
        wait_for(lambda: "还有 2 条" in screen(records[0]), "plan display")
        time.sleep(3)
        before = len(traffic.read_text().splitlines())
        error_before = (out / "wezterm.log").read_text().count("Broken pipe")
        time.sleep(8)
        after = len(traffic.read_text().splitlines())
        error_after = (out / "wezterm.log").read_text().count("Broken pipe")
        report.update(idle_seconds=8, idle_cli_calls=after - before, idle_broken_pipe=error_after - error_before)
        assert report["idle_cli_calls"] == 0, report
        assert report["idle_broken_pipe"] == 0, report
        current = json.loads(cli("list", "--format", "json"))
        sizes = {str(pane["pane_id"]): pane["size"]["rows"] for pane in current}
        assert all(sizes[record["panel_pane"]] == 7 for record in records), sizes
        report["all_panels_seven_rows"] = True
        first = records[0]
        cli("send-text", "--pane-id", first["panel_pane"], "--no-paste", "\x1bOB")
        wait_for(lambda: "2–5/6" in screen(first), "scroll")
        cli("send-text", "--pane-id", first["panel_pane"], "--no-paste", "m")
        wait_for(lambda: "手动" in screen(first), "manual mode")
        save(first, 1)
        wait_for(lambda: "1–1/1" in screen(first), "plan update in manual mode")
        current = json.loads(cli("list", "--format", "json"))
        assert next(pane["size"]["rows"] for pane in current if str(pane["pane_id"]) == first["panel_pane"]) == 7
        cli("send-text", "--pane-id", first["panel_pane"], "--no-paste", "a")
        wait_for(lambda: any(str(pane["pane_id"]) == first["panel_pane"] and pane["size"]["rows"] == 4
                            for pane in json.loads(cli("list", "--format", "json"))), "automatic height")
        text = screen(first)
        assert "无法连接 WezTerm" not in text and "高度调整失败" not in text, text
        (out / "panel.txt").write_text(text)
        cli("send-text", "--pane-id", first["panel_pane"], "--no-paste", "q")
        wait_for(lambda: store.read_binding(next(path.stem for path in (data / "bindings").glob("*.json")
                    if json.loads(path.read_text())["parent_pane"] == first["parent_pane"]))["state"] == "closed", "close")
        report.update(result="passed", scroll=True, manual_preserves_height=True, auto_restores_height=True, q_closes=True)
    finally:
        if gui.poll() is None:
            gui.terminate()
        gui.wait(timeout=10)
        report["gui_exit"] = gui.returncode
        log.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(dict(result=report["result"], report=str(out / "report.json"))))


if __name__ == "__main__":
    main()
