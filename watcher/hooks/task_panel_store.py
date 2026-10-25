"""Own validated, private task-plan snapshots and pane-binding transactions."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

STATES = {"absent", "starting", "visible", "closed", "error", "ended"}
STATUSES = {"pending", "in_progress", "completed"}


class StoreError(ValueError):
    """A cache operation could not preserve its storage contract."""


def session_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise StoreError("Invalid session or attachment identifier")
    return value


def binding_key(socket, parent_pane):
    if not isinstance(socket, str) or not os.path.isabs(socket) or "\x00" in socket:
        raise StoreError("Invalid terminal socket path")
    if not isinstance(parent_pane, str) or not re.fullmatch(r"[0-9]{1,20}", parent_pane):
        raise StoreError("Invalid parent pane identifier")
    return hashlib.sha256(json.dumps([socket, parent_pane]).encode()).hexdigest()


def _number(value):
    return type(value) is int or type(value) is float and math.isfinite(value)


def _process_owner(pid, started, cwd, optional=False):
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or '\x00' in cwd:
        raise StoreError('Invalid process working directory')
    if optional and pid is None and started is None:
        return
    if type(pid) is not int or not 0 < pid < 2**31:
        raise StoreError('Invalid owner process identifier')
    if not _number(started) or started < 0:
        raise StoreError('Invalid owner process start time')


def _validate(kind, key, value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise StoreError("Unsupported cache record version")
    if kind == "plans":
        if session_id(value.get("session_id")) != key:
            raise StoreError("Plan session does not match its filename")
        if not isinstance(value.get("title"), str) or not _number(value.get("updated_at")):
            raise StoreError("Invalid plan metadata")
        if not isinstance(value.get("plan"), list):
            raise StoreError("Plan must be a list")
        for item in value["plan"]:
            if (not isinstance(item, dict) or not isinstance(item.get("step"), str)
                    or not isinstance(item.get("status"), str) or item["status"] not in STATUSES):
                raise StoreError("Invalid plan item")
    elif kind == 'sessions':
        if not {'session_id', 'cwd', 'owner_pid', 'owner_started_at', 'observed_at', 'ended'}.issubset(value):
            raise StoreError('Incomplete session event record')
        if session_id(value.get('session_id')) != key:
            raise StoreError('Session identity does not match its filename')
        _process_owner(value.get('owner_pid'), value.get('owner_started_at'), value.get('cwd'), optional=True)
        if not _number(value.get('observed_at')) or value['observed_at'] < 0 or type(value.get('ended')) is not bool:
            raise StoreError('Invalid session event metadata')
    elif kind == "bindings":
        if binding_key(value.get("socket"), value.get("parent_pane")) != key:
            raise StoreError("Pane binding does not match its filename")
        session_id(value.get("session_id"))
        session_id(value.get("attachment_id"))
        if not isinstance(value.get("nonce"), str) or not re.fullmatch(r"[a-f0-9]{32}", value["nonce"]):
            raise StoreError("Invalid pane instance nonce")
        if not isinstance(value.get("state"), str) or value["state"] not in STATES:
            raise StoreError("Invalid pane state")
        pane = value.get("panel_pane")
        if pane is not None and (not isinstance(pane, str) or not re.fullmatch(r"[0-9]{1,20}", pane)):
            raise StoreError("Invalid task pane identifier")
        ready = value.get("ready_nonce")
        if ready is not None and (not isinstance(ready, str) or ready != value["nonce"] or pane is None):
            raise StoreError("Ready confirmation must identify the current task pane")
        if "project_title" in value and (not isinstance(value["project_title"], str) or not value["project_title"]):
            raise StoreError("Invalid project title")
        for field in ("starting_created_at", "starting_deadline"):
            if field not in value or value[field] is not None and not _number(value[field]):
                raise StoreError("Invalid pane creation deadline")
        if value["state"] == "starting" and any(value[field] is None for field in ("starting_created_at", "starting_deadline")):
            raise StoreError("Starting pane requires a creation deadline")
        if any(field in value for field in ('owner_pid', 'owner_started_at', 'owner_cwd', 'session_confirmed')):
            _process_owner(value.get('owner_pid'), value.get('owner_started_at'), value.get('owner_cwd'))
            if type(value.get('session_confirmed')) is not bool:
                raise StoreError('Invalid session confirmation state')
    elif kind == "notices":
        if value.get("key") != key:
            raise StoreError("Notice identity does not match its filename")
    else:
        raise StoreError("Unknown cache record kind")
    return value


class _Transaction:
    def __init__(self, store, kind, key):
        self.store, self.kind, self.key = store, kind, key
        self.active = True

    def _check(self):
        if not self.active:
            raise StoreError("Cache transaction has already ended")

    def read(self):
        self._check()
        return self.store._read(self.kind, self.key)

    def write(self, value):
        self._check()
        _validate(self.kind, self.key, value)
        self.store._replace(self.kind, self.key, value)

    def delete(self):
        self._check()
        self.store._path(self.kind, self.key).unlink(missing_ok=True)


class Store:
    def __init__(self, root):
        self.root = Path(root).absolute()
        try:
            for directory in (self.root, self.root / "plans", self.root / "bindings", self.root / "notices", self.root / 'sessions'):
                if directory.is_symlink():
                    raise StoreError("Cache directory must not be a symlink")
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(directory, 0o700)
        except OSError as error:
            raise StoreError(f"Cannot initialize task cache: {error}") from error

    def _path(self, kind, key, suffix=".json"):
        if kind in ('plans', 'sessions'):
            session_id(key)
        elif kind in ("bindings", "notices"):
            if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
                raise StoreError("Invalid cache record key")
        else:
            raise StoreError("Unknown cache record kind")
        return self.root / kind / (key + suffix)

    def _read(self, kind, key):
        path = self._path(kind, key)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise StoreError("Cache record must be a regular file")
                return _validate(kind, key, json.load(stream))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as error:
            raise StoreError(f"Cannot read task cache record: {error}") from error

    def _replace(self, kind, key, value):
        path = self._path(kind, key)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix="." + key + "-", suffix=".tmp", dir=path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (OSError, ValueError, TypeError) as error:
            raise StoreError(f"Cannot save task cache record: {error}") from error
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def _transaction(self, kind, key, deadline=None):
        fd = None
        transaction = None
        try:
            fd = os.open(self._path(kind, key, ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StoreError("Cache lock must be a regular file")
            os.fchmod(fd, 0o600)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise StoreError("Task cache lock wait timed out")
                    time.sleep(0.01 if deadline is None else min(0.01, max(0, deadline - time.monotonic())))
            transaction = _Transaction(self, kind, key)
            yield transaction
        except OSError as error:
            raise StoreError(f"Cannot lock task cache: {error}") from error
        finally:
            if transaction is not None:
                transaction.active = False
            if fd is not None:
                os.close(fd)

    def binding_transaction(self, key, deadline=None):
        return self._transaction("bindings", key, deadline)

    def read_binding(self, key):
        return self._read("bindings", key)

    def binding_keys(self):
        return [path.stem for path in (self.root / "bindings").glob("*.json") if re.fullmatch(r"[a-f0-9]{64}", path.stem)]

    def session_transaction(self, identifier, deadline=None):
        return self._transaction('sessions', session_id(identifier), deadline)

    def read_session(self, identifier):
        return self._read('sessions', session_id(identifier))

    def session_keys(self):
        return [path.stem for path in (self.root / 'sessions').glob('*.json')
                if re.fullmatch(r'[A-Za-z0-9_-]{1,128}', path.stem)]

    def save_plan(self, identifier, title, plan, updated_at=None, only_if_missing=False):
        identifier = session_id(identifier)
        record = {"version": 1, "session_id": identifier, "title": title, "plan": plan,
                  "updated_at": time.time() if updated_at is None else updated_at}
        _validate("plans", identifier, record)
        with self._transaction("plans", identifier) as transaction:
            if only_if_missing and transaction.read() is not None:
                return False
            transaction.write(record)
            return True

    def read_plan(self, identifier):
        return self._read("plans", session_id(identifier))

    def notice_once(self, identity):
        key = hashlib.sha256(identity.encode()).hexdigest()
        with self._transaction("notices", key) as transaction:
            if transaction.read() is not None:
                return False
            transaction.write({"version": 1, "key": key})
            return True
