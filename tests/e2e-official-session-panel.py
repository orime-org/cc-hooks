#!/usr/bin/env python3
"""Exercise native Codex hooks and real WezTerm panes in an isolated home."""

import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / 'watcher/hooks'


class Provider(BaseHTTPRequestHandler):
    plan = [dict(step='核对当前会话任务', status='in_progress'), dict(step='验证面板同步', status='pending')]

    def log_message(self, *_args):
        pass

    def do_POST(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(data)
        inputs = json.loads(data).get('input', [])
        last_user = max((i for i, item in enumerate(inputs) if item.get('role') == 'user'), default=-1)
        done = any(item.get('type') == 'function_call_output' for item in inputs[last_user + 1:])
        identifier = 'panel-' + str(time.time_ns())
        if done or self.plan is None:
            item = dict(type='message', role='assistant', id=identifier,
                        content=[dict(type='output_text', text='验证完成。')])
        else:
            item = dict(type='function_call', call_id=identifier, name='update_plan',
                        arguments=json.dumps(dict(plan=self.plan), ensure_ascii=False))
        events = [dict(type='response.created', response=dict(id=identifier)),
                  dict(type='response.output_item.done', item=item),
                  dict(type='response.completed', response=dict(id=identifier, usage=dict(
                      input_tokens=0, output_tokens=0, total_tokens=0)))]
        payload = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', default=shutil.which('codex'))
    application = '/Applications/WezTerm.app/Contents/MacOS/wezterm'
    parser.add_argument('--wezterm', default=application if Path(application).exists() else shutil.which('wezterm'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--early-events', action='store_true')
    args = parser.parse_args()
    binary = str(Path(args.codex).resolve())
    out = args.output or Path(tempfile.mkdtemp(prefix='official-session-panel-'))
    out.mkdir(parents=True, exist_ok=True)
    home, project, data = out / 'home', out / 'project', out / 'plugin-data'
    for directory in (home, project, data):
        directory.mkdir()
    environment = dict(os.environ, CODEX_HOME=str(home))
    http = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    http.daemon_threads = True
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    capture = out / 'capture.py'
    capture.write_text('import io,json,os,pathlib,sys,time\nevent=json.load(sys.stdin)\n'
                       f'with pathlib.Path({str(out / "hooks.jsonl")!r}).open("a") as f:'
                       'f.write(json.dumps({"event":event,"at":time.time()})+"\\n")\n'
                       f'os.environ["PLUGIN_DATA"]={str(data)!r}\nsys.path.insert(0,{str(HOOKS)!r})\n'
                       'from task_panel_hook import main\nsys.stdin=io.StringIO(json.dumps(event))\n'
                       'raise SystemExit(main())\n')
    config = home / 'config.toml'
    configuration = (f'model="mock-model"\nmodel_provider="fixture"\ncheck_for_update_on_startup=false\n'
                     '[tools.update_plan]\nenabled=true\n[model_providers.fixture]\nname="Offline panel fixture"\n'
                     f'base_url="http://127.0.0.1:{http.server_port}/v1"\nwire_api="responses"\n'
                     f'requires_openai_auth=false\nsupports_websockets=false\n[projects.{json.dumps(str(project))}]\n'
                     'trust_level="trusted"\n[tui]\nterminal_title=["thread-name"]\n'
                     'status_line=["model-with-reasoning","current-dir"]\n')
    for event in ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'SessionEnd'):
        configuration += f'\n[[hooks.{event}]]\n'
        if event == 'PostToolUse':
            configuration += 'matcher="^update_plan$"\n'
        configuration += f'[[hooks.{event}.hooks]]\ntype="command"\ncommand={json.dumps(sys.executable + " " + str(capture))}\ntimeout=5\n'
    config.write_text(configuration)
    spec = importlib.util.spec_from_file_location('native_fixture', ROOT / 'tests/e2e-codex-task-panel.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    server = fixture.StdioServer(binary, environment, out / 'app-server.stderr')
    try:
        server.request('initialize', dict(clientInfo=dict(name='codex_app_server_daemon', version='fixture'),
                                          capabilities=dict(experimentalApi=True)))
        server.process.stdin.write(b'{"method":"initialized"}\n')
        server.process.stdin.flush()
        response = server.request('hooks/list', dict(cwds=[str(project)]))
        hooks = [hook for entry in response['data'] for hook in entry['hooks']]
        server.request('config/batchWrite', dict(edits=[dict(keyPath='hooks.state', mergeStrategy='upsert',
                       value={hook['key']: dict(trusted_hash=hook['currentHash']) for hook in hooks})]))
    finally:
        server.close()
    saved_config = config.read_bytes()
    lua = out / 'wezterm.lua'
    lua.write_text('return {status_update_interval=200,initial_cols=140,initial_rows=42,font_size=12,'
                   'window_close_confirmation="NeverPrompt",exit_behavior="Close"}\n')
    subprocess.run([sys.executable, str(HOOKS / 'task_panel_setup.py'), '--codex-home', str(home),
                    '--data-dir', str(data), '--wezterm-config', str(lua)], check=True, capture_output=True)
    assert config.read_bytes() == saved_config, 'Panel setup changed the Codex configuration'
    configured_lua = lua.read_text()
    if args.early_events:
        lua.write_text("local wz=require 'wezterm'\nwz.on('user-var-changed',function(window,pane,name,value) "
                       "if name=='cc_hooks_test_reload' then wz.reload_configuration() end end)\n"
                       'return {status_update_interval=200,initial_cols=140,initial_rows=42,font_size=12,'
                       'window_close_confirmation="NeverPrompt",exit_behavior="Close"}\n')
    report, gui = dict(result='failed', observations=[]), None
    gui_log = (out / 'wezterm.log').open('w')
    terminal_environment = dict(os.environ)

    def cli(*arguments):
        return subprocess.check_output([args.wezterm, 'cli', '--no-auto-start', *map(str, arguments)],
                                       env=terminal_environment, text=True, timeout=6)

    def panes():
        return json.loads(cli('list', '--format', 'json'))

    def wait_for(predicate):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.2)
        raise AssertionError('Timed out waiting for a native panel condition')

    def binding(parent):
        return next((value for path in (data / 'task-panel/bindings').glob('*.json')
                     if (value := json.loads(path.read_text()))['parent_pane'] == str(parent)), None)

    def ready(parent):
        value = binding(parent)
        return value if value and value['state'] == 'visible' else None

    def panel_text(parent):
        value = binding(parent)
        if value is None:
            return ''
        pane = next((pane for pane in panes() if str(pane['pane_id']) == value['panel_pane']), None)
        if pane is None:
            return ''
        lines = cli('get-text', '--pane-id', value['panel_pane']).splitlines()
        return '\n'.join(lines[-pane['size']['rows']:])

    def submit(parent, text):
        cli('send-text', '--pane-id', parent, '--no-paste', text)
        time.sleep(.5)
        cli('send-text', '--pane-id', parent, '--no-paste', '\x1b[13u')

    def spawn(*extra):
        return int(cli('spawn', '--new-window', '--cwd', project, '--', '/usr/bin/env',
                       'CODEX_HOME=' + str(home), binary, *extra))

    def observe(label, parent):
        record = binding(parent)
        text = panel_text(parent)
        assert record['owner_cwd'] == str(project.resolve()), 'The binding uses a different project directory'
        assert record['project_title'] == project.name, 'The panel title uses a different project directory'
        assert record['session_id'] not in text, 'Session identifier is visible in the panel'
        assert record['session_id'][:8] not in text, 'Short session identifier is visible in the panel'
        (out / (label + '.txt')).write_text(text)
        report['observations'].append(dict(label=label, binding=record, text=text, panes=panes()))
        if sys.platform == 'darwin':
            gui_pid = int(socket.name.rsplit('-', 1)[-1])
            script = ('ObjC.import("CoreGraphics"); JSON.stringify(ObjC.deepUnwrap('
                      'ObjC.castRefToObject($.CGWindowListCopyWindowInfo(1,0))).filter('
                      f'w => w.kCGWindowOwnerPID === {gui_pid} && w.kCGWindowLayer === 0));')
            windows = json.loads(subprocess.check_output(['osascript', '-l', 'JavaScript', '-e', script],
                                                        text=True, timeout=10))
            assert windows, 'The owned WezTerm test window is not visible'
            screenshots = []
            for index, window in enumerate(windows):
                screenshot = out / (label + ('' if index == 0 else f'-window-{index + 1}') + '.png')
                subprocess.run(['/usr/sbin/screencapture', '-x', '-o', '-l', str(window['kCGWindowNumber']),
                                str(screenshot)], check=True, capture_output=True, timeout=10)
                screenshots.append(str(screenshot))
            report['observations'][-1]['screenshots'] = screenshots

    try:
        sockets = Path.home() / '.local/share/wezterm'
        before = set(sockets.glob('gui-sock-*'))
        command = [args.wezterm, '--config-file', str(lua), 'start', '--always-new-process',
                                '--class', 'cc-hooks-session-panel-test', '--cwd', str(project), '--',
                                '/usr/bin/env', 'CODEX_HOME=' + str(home), binary]
        if args.early_events:
            command.append('同步当前会话任务')
        gui = subprocess.Popen(command,
                               env=environment, stdout=gui_log, stderr=gui_log)
        socket = wait_for(lambda: next(iter(set(sockets.glob('gui-sock-*')) - before), None))
        terminal_environment['WEZTERM_UNIX_SOCKET'] = str(socket)
        first = wait_for(panes)[0]['pane_id']
        if args.early_events:
            wait_for(lambda: list((data / 'task-panel/plans').glob('*.json')))
            assert binding(first) is None, 'The observer was enabled before the early event'
            lua.write_text(configured_lua)
            trigger = int(cli('spawn', '--cwd', project, '--', sys.executable, '-c',
                              'import sys,time;sys.stdout.write("\\x1b]1337;SetUserVar=cc_hooks_test_reload=MQ==\\x07");'
                              'sys.stdout.flush();time.sleep(1)'))
            wait_for(lambda: all(pane['pane_id'] != trigger for pane in panes()))
        wait_for(lambda: ready(first))
        wait_for(lambda: 'Ask Codex' in cli('get-text', '--pane-id', first))
        if not args.early_events:
            assert '等待当前会话信息' in panel_text(first)
            observe('startup', first)
            submit(first, '同步当前会话任务')
        wait_for(lambda: '核对当前会话任务' in panel_text(first))
        first_session = binding(first)['session_id']
        observe('first-plan', first)
        Provider.plan = [dict(step=f'当前会话任务 {i + 1}', status='pending') for i in range(6)]
        second_arguments = ['-c', 'tui.terminal_title=[]', '-c', 'tui.status_line=[]']
        if args.early_events:
            release = out / 'allow-second-registration'
            launcher = data / 'task-panel-integration/task_panel_launch.py'
            source = launcher.read_text()
            marker = '        key, nonce = prepare(store, owner, args.parent, socket, pane, args.title)'
            assert marker in source
            gate = ('        deadline = time.monotonic() + 20\n'
                    f'        while not Path({str(release)!r}).exists() and time.monotonic() < deadline:\n'
                    '            time.sleep(.05)\n')
            launcher.write_text(source.replace(marker, gate + marker))
            second_arguments.append('更新六条任务')
        second = spawn(*second_arguments)
        if args.early_events:
            wait_for(lambda: len(list((data / 'task-panel/plans').glob('*.json'))) == 2)
            assert binding(second) is None, 'The second pane registered before its early event'
            assert binding(first)['session_id'] == first_session
            release.write_text('ready')
        wait_for(lambda: ready(second))
        wait_for(lambda: 'Ask Codex' in cli('get-text', '--pane-id', second))
        if not args.early_events:
            submit(second, '更新六条任务')
        wait_for(lambda: '还有 2 条' in panel_text(second))
        assert sum(line.startswith('[') for line in panel_text(second).splitlines()) == 4
        assert binding(second)['session_id'] != first_session
        assert '核对当前会话任务' in panel_text(first)
        observe('six-tasks', second)
        Provider.plan = []
        submit(second, '清空当前计划')
        wait_for(lambda: '任务 0/0' in panel_text(second))
        observe('clear', second)
        previous_pid = binding(first)['owner_pid']
        cli('kill-pane', '--pane-id', first)
        sys.path.insert(0, str(HOOKS))
        from task_panel_process import ProcessReader
        wait_for(lambda: ProcessReader().read(previous_pid) is None)
        (data / 'task-panel/plans' / (first_session + '.json')).unlink()
        Provider.plan = None
        resumed = spawn('resume', first_session)
        wait_for(lambda: ready(resumed))
        wait_for(lambda: 'Ask Codex' in cli('get-text', '--pane-id', resumed))
        assert '等待当前会话信息' in panel_text(resumed)
        assert not (data / 'task-panel/plans' / (first_session + '.json')).exists()
        submit(resumed, '继续当前会话')
        wait_for(lambda: '核对当前会话任务' in panel_text(resumed))
        assert binding(resumed)['session_id'] == first_session
        observe('resume-after-first-event', resumed)
        owned = binding(resumed)['panel_pane']
        cli('send-text', '--pane-id', owned, '--no-paste', 'q')
        wait_for(lambda: all(str(pane['pane_id']) != owned for pane in panes()))
        Provider.plan = [dict(step='关闭面板后继续保存', status='pending')]
        submit(resumed, '继续更新任务')
        wait_for(lambda: json.loads((data / 'task-panel/plans' / (first_session + '.json')).read_text())['plan'] == Provider.plan)
        assert binding(resumed)['state'] == 'closed'
        assert all(str(pane['pane_id']) != owned for pane in panes())
        report.update(result='passed', config_unchanged=config.read_bytes() == saved_config,
                      q_stays_closed=True, resume_restored_after_first_event=True, early_events=args.early_events,
                      project=str(project))
    finally:
        cleanup_errors = []
        if 'WEZTERM_UNIX_SOCKET' in terminal_environment and gui is not None and gui.poll() is None:
            try:
                current = panes()
                for pane in current:
                    (out / ('final-pane-' + str(pane['pane_id']) + '.txt')).write_text(cli('get-text', '--pane-id', pane['pane_id']))
                for pane in sorted(current, key=lambda value: value['pane_id'], reverse=True):
                    cli('kill-pane', '--pane-id', pane['pane_id'])
            except subprocess.SubprocessError as error:
                cleanup_errors.append(str(error))
        if gui is not None:
            try:
                gui.wait(timeout=10)
            except subprocess.TimeoutExpired:
                gui.terminate()
                gui.wait(timeout=5)
            report['gui_exit'] = gui.returncode
        gui_log.close()
        try:
            owned = {}
            prefix = str(home / 'packages/app-server-daemon/')
            for row in subprocess.check_output(['/bin/ps', '-axo', 'pid=,command='], text=True).splitlines():
                fields = row.strip().split(None, 1)
                if len(fields) == 2 and fields[1].startswith(prefix):
                    pid = int(fields[0])
                    identity = subprocess.check_output(['/bin/ps', '-p', str(pid), '-o', 'lstart=',
                                                        '-o', 'command='], text=True).strip()
                    owned[pid] = identity
            (out / 'owned-daemon-processes.json').write_text(json.dumps(owned, indent=2))
            try:
                stopped = subprocess.run([binary, 'app-server', 'daemon', 'stop'], env=environment,
                                         capture_output=True, timeout=12)
                report['daemon_stop_exit'] = stopped.returncode
            except subprocess.TimeoutExpired:
                report['daemon_stop_timed_out'] = True
            for pid, identity in owned.items():
                current = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='],
                                         text=True, capture_output=True, timeout=3)
                if current.returncode == 1:
                    continue
                if current.returncode or current.stdout.strip() != identity:
                    raise RuntimeError(f'Owned process identity changed: {pid}')
                os.kill(pid, signal.SIGTERM)
                report.setdefault('terminated_daemon_processes', []).append(pid)
            deadline = time.monotonic() + 8
            while True:
                live = {int(row.split(None, 1)[0]) for row in subprocess.check_output(
                    ['/bin/ps', '-axo', 'pid='], text=True).splitlines()}
                remaining = sorted(live.intersection(owned))
                if not remaining or time.monotonic() >= deadline:
                    break
                time.sleep(.2)
            report['remaining_owned_daemon_processes'] = remaining
            if remaining:
                raise RuntimeError(f'Owned daemon processes remain: {remaining}')
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            cleanup_errors.append(str(error))
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=3)
        if cleanup_errors:
            report.update(result='failed', cleanup_errors=cleanup_errors)
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(dict(result=report['result'], report=str(out / 'report.json')), ensure_ascii=False))


if __name__ == '__main__':
    main()
