"""Read local interactive Codex processes within a shared time budget."""

import ctypes
import errno
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

HEADLESS = {"exec", "app-server", "mcp-server"}


class ProcessError(ValueError):
    """System process information could not be read."""


def decode_mac_argv(data):
    try:
        count = struct.unpack_from("=i", data)[0]
        _, separator, arguments = data[4:].partition(b"\0")
        values = arguments.lstrip(b"\0").split(b"\0")
        if count < 0 or not separator or len(values) < count:
            raise ValueError("Invalid argument buffer")
        return [os.fsdecode(value) for value in values[:count]]
    except (struct.error, ValueError) as error:
        raise ProcessError("Cannot decode process arguments") from error


def _mac_argv(pid):
    # KERN_PROCARGS2 retains argv boundaries that ps's display string loses.
    library = ctypes.CDLL(None, use_errno=True)
    function = library.sysctl
    function.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
    function.restype = ctypes.c_int
    mib = (ctypes.c_int * 3)(1, 49, pid)
    size = ctypes.c_size_t(os.sysconf("SC_ARG_MAX"))
    buffer = ctypes.create_string_buffer(size.value)
    if function(mib, 3, buffer, ctypes.byref(size), None, 0):
        code = ctypes.get_errno()
        if code in (errno.ESRCH, errno.ENOENT, errno.EINVAL):
            raise ProcessLookupError(code, "Process arguments are unavailable")
        raise OSError(code, "Cannot read process arguments")
    return decode_mac_argv(buffer.raw[:size.value])


def _interactive(executable, arguments):
    return Path(executable.removesuffix(" (deleted)")).name == "codex" and bool(arguments) \
        and not any(argument in HEADLESS for argument in arguments[1:])


def session_directory(cwd, arguments):
    directory = Path(cwd)
    options = iter(arguments[1:])
    selected = None
    for argument in options:
        if argument == "--":
            break
        if argument in ("--cd", "-C"):
            selected = next(options, None)
            if selected is None:
                raise ProcessError("Missing Codex working directory argument")
        elif argument.startswith("--cd="):
            selected = argument[len("--cd="):]
        elif argument.startswith("-C"):
            selected = argument[2:]
            if selected.startswith("="):
                selected = selected[1:]
    return directory / selected if selected is not None else directory


class ProcessReader:
    def __init__(self, platform=None, proc_root="/proc", runner=None, argv_reader=None,
                 clock=None, ticks_per_second=None):
        self.platform = platform or sys.platform
        self.proc_root = Path(proc_root)
        self.runner = runner or subprocess.run
        self.argv_reader = argv_reader or _mac_argv
        self.clock = clock or time.monotonic
        self.ticks_per_second = ticks_per_second

    def _deadline(self, deadline):
        if deadline is None:
            deadline = self.clock() + 2
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ProcessError("Invalid process read deadline")
        self._remaining(deadline)
        return deadline

    def _remaining(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise ProcessError("Process read timed out")
        return remaining

    def _run(self, arguments, deadline):
        try:
            result = self.runner(arguments, capture_output=True, text=True,
                                 env=dict(os.environ, LC_ALL="C"), timeout=self._remaining(deadline))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProcessError(f"Cannot read process information: {error}") from error
        self._remaining(deadline)
        if result.returncode and result.stderr.strip():
            message = result.stderr.strip()
            if "permission" in message.lower() or "permitted" in message.lower():
                raise ProcessError("Cannot access process information") from PermissionError(message)
            raise ProcessError(f"Process command failed: {message}")
        return result

    def _ps(self, pid, field, deadline):
        result = self._run(["/bin/ps", "-p", str(pid), "-o", field + "="], deadline)
        if result.returncode == 1 and not result.stdout.strip():
            return None
        if result.returncode:
            raise ProcessError("Process query failed")
        return result.stdout.strip()

    def _record(self, pid, cwd, started_at):
        if not Path(cwd).is_absolute() or not math.isfinite(started_at):
            raise ProcessError("Invalid process identity")
        return dict(pid=pid, cwd=str(Path(cwd).resolve()), started_at=float(started_at))

    def _read_mac(self, pid, deadline, executable=None):
        executable = executable if executable is not None else self._ps(pid, "comm", deadline)
        if not executable or Path(executable).name != "codex":
            return None
        self._remaining(deadline)
        try:
            arguments = self.argv_reader(pid)
        except ProcessLookupError:
            return None
        except OSError as error:
            raise ProcessError(f"Cannot read process arguments: {error}") from error
        self._remaining(deadline)
        if not _interactive(executable, arguments):
            return None
        started = self._ps(pid, "lstart", deadline)
        if started is None:
            return None
        try:
            started_at = time.mktime(time.strptime(started, "%a %b %d %H:%M:%S %Y"))
        except ValueError as error:
            raise ProcessError("Cannot parse process start time") from error
        result = self._run(["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], deadline)
        cwd = next((line[1:] for line in result.stdout.splitlines() if line.startswith("n")), None)
        if result.returncode or cwd is None:
            if self._ps(pid, "comm", deadline) is None:
                return None
            raise ProcessError("Cannot read process working directory")
        return self._record(pid, session_directory(cwd, arguments), started_at)

    def _read_linux(self, pid, deadline):
        directory = self.proc_root / str(pid)
        executable = os.readlink(directory / "exe")
        if Path(executable.removesuffix(" (deleted)")).name != "codex":
            return None
        arguments = [os.fsdecode(value) for value in (directory / "cmdline").read_bytes().split(b"\0")]
        if arguments and arguments[-1] == "":
            arguments.pop()
        if not _interactive(executable, arguments):
            return None
        cwd = os.readlink(directory / "cwd")
        fields = (directory / "stat").read_text().rsplit(")", 1)[1].split()
        try:
            metadata = (self.proc_root / "stat").read_text()
        except FileNotFoundError as error:
            raise ProcessError("Linux process metadata is unavailable") from error
        boot = next(line.split()[1] for line in metadata.splitlines() if line.startswith("btime "))
        ticks = self.ticks_per_second or os.sysconf("SC_CLK_TCK")
        started_at = float(boot) + int(fields[19]) / ticks
        self._remaining(deadline)
        return self._record(pid, session_directory(cwd, arguments), started_at)

    def read(self, pid, deadline=None):
        if type(pid) is not int or not 0 < pid <= 2**31 - 1:
            raise ProcessError("Invalid process identifier")
        deadline = self._deadline(deadline)
        try:
            if self.platform == "darwin":
                return self._read_mac(pid, deadline)
            if self.platform.startswith("linux"):
                return self._read_linux(pid, deadline)
            raise ProcessError(f"Unsupported process platform: {self.platform}")
        except (FileNotFoundError, ProcessLookupError):
            return None
        except (OSError, ValueError, IndexError, StopIteration, ZeroDivisionError) as error:
            if isinstance(error, ProcessError):
                raise
            raise ProcessError(f"Cannot read process {pid}: {error}") from error

    def list(self, deadline=None):
        deadline = self._deadline(deadline)
        try:
            if self.platform == "darwin":
                result = self._run(["/bin/ps", "-axo", "pid=,comm="], deadline)
                if result.returncode:
                    raise ProcessError("Cannot enumerate local processes")
                candidates = []
                for row in result.stdout.splitlines():
                    pid, executable = row.strip().split(None, 1)
                    if Path(executable).name == "codex":
                        candidates.append((int(pid), executable))
            elif self.platform.startswith("linux"):
                candidates = [(int(path.name), None) for path in self.proc_root.iterdir() if path.name.isdecimal()]
            else:
                raise ProcessError(f"Unsupported process platform: {self.platform}")
            records = []
            for pid, executable in sorted(candidates):
                self._remaining(deadline)
                try:
                    record = self._read_mac(pid, deadline, executable) if self.platform == "darwin" \
                        else self.read(pid, deadline)
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except ProcessError as error:
                    if isinstance(error.__cause__, PermissionError):
                        continue
                    raise
                if record is not None:
                    records.append(record)
            self._remaining(deadline)
            return records
        except (OSError, ValueError) as error:
            if isinstance(error, ProcessError):
                raise
            raise ProcessError(f"Cannot enumerate local processes: {error}") from error
