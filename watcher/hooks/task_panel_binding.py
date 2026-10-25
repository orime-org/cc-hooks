"""Associate native Codex sessions with local interactive process instances."""

from pathlib import Path
import time

from task_panel_process import ProcessError, ProcessReader
from task_panel_store import session_id


def identity(record):
    return record.get('owner_pid'), record.get('owner_started_at')


def process_identity(process):
    return process['pid'], process['started_at']


class SessionRouter:
    def __init__(self, store, processes=None, clock=time):
        self.store = store
        self.processes = processes if processes is not None else ProcessReader()
        self.clock = clock

    def _sessions(self):
        return [record for key in self.store.session_keys() if (record := self.store.read_session(key))]

    def _select(self, record, deadline):
        if record['owner_pid'] is not None:
            known = self.processes.read(record['owner_pid'], deadline)
            if known is not None and process_identity(known) == identity(record):
                return known
        candidates = [process for process in self.processes.list(deadline)
                      if str(Path(process['cwd']).resolve()) == record['cwd']]
        claimed = {identity(session) for session in self._sessions() if not session['ended']}
        unclaimed = [process for process in candidates if process_identity(process) not in claimed]
        return max(unclaimed or candidates, key=lambda process: (process['started_at'], process['pid']), default=None)

    def _save(self, record):
        with self.store.session_transaction(record['session_id'], self.clock.monotonic() + 1) as transaction:
            transaction.write(record)

    def _claim(self, record, deadline):
        try:
            process = self._select(record, deadline)
        except ProcessError:
            record.update(owner_pid=None, owner_started_at=None)
            self._save(record)
            raise
        if process is not None:
            record.update(owner_pid=process['pid'], owner_started_at=process['started_at'])
        else:
            record.update(owner_pid=None, owner_started_at=None)
        self._save(record)
        return record

    def observe(self, event):
        identifier = session_id(event.get('session_id'))
        cwd = event.get('cwd')
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError('Native session event requires an absolute working directory')
        previous = self.store.read_session(identifier)
        record = dict(version=1, session_id=identifier, cwd=str(Path(cwd).resolve()),
                      owner_pid=previous.get('owner_pid') if previous else None,
                      owner_started_at=previous.get('owner_started_at') if previous else None,
                      observed_at=self.clock.time(), ended=False)
        record = self._claim(record, self.clock.monotonic() + 2)
        if record['owner_pid'] is not None:
            for key in self.store.binding_keys():
                self._apply(key, record)

    def _apply(self, key, session):
        snapshot = self.store.read_binding(key)
        if snapshot is None or identity(snapshot) != identity(session):
            return False
        with self.store.binding_transaction(key, self.clock.monotonic() + 1) as transaction:
            record = transaction.read()
            if record is None or identity(record) != identity(session):
                return False
            record.update(session_id=session['session_id'], session_confirmed=True,
                          attachment_id=f"{session['owner_pid']}-{session['session_id']}")
            if record['state'] == 'ended':
                record['state'] = 'visible' if record['ready_nonce'] else 'starting'
            transaction.write(record)
        return True

    def attach(self, key):
        binding = self.store.read_binding(key)
        if binding is None or binding.get('owner_pid') is None:
            return
        deadline = self.clock.monotonic() + 2
        sessions = sorted(self._sessions(), key=lambda record: record['observed_at'], reverse=True)
        for record in sessions:
            if record['ended']:
                continue
            if record['owner_pid'] is None and record['cwd'] == binding['owner_cwd']:
                record = self._claim(record, deadline)
            if identity(record) == identity(binding) and self._apply(key, record):
                return

    def end(self, identifier):
        with self.store.session_transaction(identifier, self.clock.monotonic() + 1) as transaction:
            record = transaction.read()
            if record is not None:
                record.update(ended=True, observed_at=self.clock.time())
                transaction.write(record)
