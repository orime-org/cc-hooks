#!/usr/bin/env python3
"""Exercise local Codex process identity and bounded platform readers."""

import errno
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "watcher/hooks"))
import task_panel_process as process
from task_panel_binding import SessionRouter
from task_panel_launch import prepare
from task_panel_store import Store


class ProcessReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cwd = self.root / "项目 with spaces"
        self.cwd.mkdir()
        self.proc = self.root / "proc"
        self.proc.mkdir()
        (self.proc / "stat").write_text("cpu 1 2 3\nbtime 1000\n")

    def linux_process(self, pid=42, executable="/opt/codex", argv=None, ticks=250):
        directory = self.proc / str(pid)
        directory.mkdir()
        (directory / "exe").symlink_to(executable)
        (directory / "cwd").symlink_to(self.cwd)
        arguments = argv if argv is not None else [executable, "--cd", str(self.cwd)]
        (directory / "cmdline").write_bytes(b"\0".join(os.fsencode(value) for value in arguments) + b"\0")
        fields = ["S"] + ["0"] * 19
        fields[19] = str(ticks)
        (directory / "stat").write_text(f"{pid} (codex (worker)) " + " ".join(fields))
        return directory

    def linux(self):
        return process.ProcessReader(platform="linux", proc_root=self.proc, ticks_per_second=100)

    def mac(self, outputs=None, argv=None, clock=None):
        outputs = dict(outputs or {})
        defaults = {
            ("/bin/ps", "-p", "42", "-o", "comm="): "/opt/Codex App/codex\n",
            ("/bin/ps", "-p", "42", "-o", "lstart="): "Sat Oct 24 20:00:00 2026\n",
            ("/usr/sbin/lsof", "-a", "-p", "42", "-d", "cwd", "-Fn"): f"p42\nfcwd\nn{self.cwd}\n",
        }
        defaults.update(outputs)
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            value = defaults[tuple(command)]
            if isinstance(value, BaseException):
                raise value
            if isinstance(value, subprocess.CompletedProcess):
                return value
            return subprocess.CompletedProcess(command, 0, value, "")

        reader = process.ProcessReader(platform="darwin", runner=runner,
                                       argv_reader=lambda pid: argv if argv is not None else ["/opt/Codex App/codex"],
                                       clock=clock)
        return reader, calls

    def test_linux_reads_actual_directory_and_start_time_with_parenthesized_comm(self):
        self.linux_process()
        self.assertEqual(self.linux().read(42), dict(pid=42, cwd=str(self.cwd), started_at=1002.5))

    def test_linux_handles_removed_executable_path(self):
        self.linux_process(executable="/opt/codex (deleted)")
        self.assertEqual(self.linux().read(42)["pid"], 42)

    def test_linux_skips_other_executables_and_headless_modes(self):
        for index, mode in enumerate(("exec", "app-server", "mcp-server"), 42):
            self.linux_process(index, argv=["codex", mode])
            self.assertIsNone(self.linux().read(index))
        self.linux_process(45, executable="/usr/bin/python3")
        self.assertIsNone(self.linux().read(45))

    def test_linux_preserves_argument_boundaries_in_prompt(self):
        self.linux_process(argv=["codex", "Explain app-server and exec"])
        self.assertIsNotNone(self.linux().read(42))

    def test_linux_disappeared_process_returns_none(self):
        self.assertIsNone(self.linux().read(42))
        directory = self.linux_process()
        (directory / "cmdline").unlink()
        self.assertIsNone(self.linux().read(42))

    def test_linux_empty_cmdline_is_not_interactive(self):
        directory = self.linux_process()
        (directory / "cmdline").write_bytes(b"")
        self.assertIsNone(self.linux().read(42))

    def test_linux_list_filters_non_process_entries(self):
        self.linux_process()
        self.linux_process(43, argv=["codex", "app-server"])
        (self.proc / "self").symlink_to(self.proc / "42")
        self.assertEqual(self.linux().list(), [dict(pid=42, cwd=str(self.cwd), started_at=1002.5)])

    def test_linux_invalid_start_metadata_reports_error(self):
        directory = self.linux_process()
        for text in ("42 (codex) S 0", "42 (codex) " + " ".join(["S"] + ["0"] * 18 + ["invalid"])):
            with self.subTest(text=text):
                (directory / "stat").write_text(text)
                with self.assertRaises(process.ProcessError):
                    self.linux().read(42)

    def test_linux_permission_failure_reports_error(self):
        self.linux_process()
        original = Path.read_bytes

        def denied(path):
            if path.name == "cmdline":
                raise PermissionError(errno.EACCES, "denied")
            return original(path)

        with patch.object(Path, "read_bytes", denied), self.assertRaises(process.ProcessError):
            self.linux().read(42)

    def test_linux_global_directory_failure_reports_error(self):
        with patch.object(Path, "iterdir", side_effect=PermissionError(errno.EACCES, "denied")), \
                self.assertRaises(process.ProcessError):
            self.linux().list()

    def test_mac_reads_unicode_directory_and_system_start(self):
        reader, calls = self.mac()
        result = reader.read(42)
        self.assertEqual(result["pid"], 42)
        self.assertEqual(result["cwd"], str(self.cwd))
        self.assertEqual(result["started_at"], time.mktime(time.strptime("Sat Oct 24 20:00:00 2026", "%a %b %d %H:%M:%S %Y")))
        for command, kwargs in calls:
            self.assertEqual(kwargs["env"]["LC_ALL"], "C")
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], 2)

    def test_mac_preserves_native_argument_boundaries(self):
        reader, _ = self.mac(argv=["/opt/Codex App/codex", "Explain app-server and exec"])
        self.assertIsNotNone(reader.read(42))

    def test_both_platforms_resolve_session_directory_arguments(self):
        target = self.cwd / "other project"
        target.mkdir()
        relative = target.name
        variants = [
            ["--cd", str(target)], ["-C", str(target)],
            ["--cd=" + str(target)], ["-C" + str(target)], ["-C=" + str(target)],
            ["--cd", relative], ["-C", relative],
            ["--cd=" + relative], ["-C" + relative], ["-C=" + relative],
            ["resume", "session-A", "--cd", relative],
            ["--cd", relative, "resume", "--last"],
            ["-c", 'tui.status_line=[]', "-C", relative],
        ]
        for platform in ("linux", "darwin"):
            for index, options in enumerate(variants):
                with self.subTest(platform=platform, options=options):
                    argv = ["codex", *options]
                    pid = 100 + index
                    if platform == "linux":
                        self.linux_process(pid, argv=argv)
                        record = self.linux().read(pid)
                    else:
                        reader, _ = self.mac(argv=argv)
                        record = reader.read(42)
                    self.assertEqual(record["cwd"], str(target))

    def test_both_platforms_keep_directory_options_inside_prompt_literal(self):
        variants = [["--", "--cd", "ignored"], ["--", "-Cignored"],
                    ["Explain --cd and -C options"], ["-c", 'instructions="--cd=ignored"']]
        for platform in ("linux", "darwin"):
            for index, options in enumerate(variants):
                with self.subTest(platform=platform, options=options):
                    argv = ["codex", *options]
                    if platform == "linux":
                        self.linux_process(200 + index, argv=argv)
                        record = self.linux().read(200 + index)
                    else:
                        reader, _ = self.mac(argv=argv)
                        record = reader.read(42)
                    self.assertEqual(record["cwd"], str(self.cwd))

    def test_missing_directory_argument_reports_explicit_error(self):
        for platform in ("linux", "darwin"):
            for index, option in enumerate(("--cd", "-C")):
                with self.subTest(platform=platform, option=option):
                    argv = ["codex", option]
                    if platform == "linux":
                        self.linux_process(300 + index, argv=argv)
                        reader, pid = self.linux(), 300 + index
                    else:
                        reader, _ = self.mac(argv=argv)
                        pid = 42
                    with self.assertRaisesRegex(process.ProcessError, "Missing Codex working directory"):
                        reader.read(pid)

    def test_cross_directory_native_event_routes_in_both_registration_orders(self):
        target = self.cwd / "other project"
        target.mkdir()
        for early_event in (True, False):
            with self.subTest(early_event=early_event):
                reader, _ = self.mac(argv=["codex", "--cd", target.name])
                listing = ("/bin/ps", "-axo", "pid=,comm=")
                original = reader.runner
                reader.runner = lambda command, **kwargs: subprocess.CompletedProcess(
                    command, 0, "42 /opt/codex\n", "") if tuple(command) == listing else original(command, **kwargs)
                store = Store(self.root / ("early" if early_event else "late"))
                router = SessionRouter(store, reader)
                event = dict(session_id="session-A", cwd=str(target), hook_event_name="SessionStart")
                if early_event:
                    router.observe(event)
                key, _ = prepare(store, reader.read(42), "1", "/tmp/audit.sock", "2", "")
                if early_event:
                    router.attach(key)
                else:
                    router.observe(event)
                record = store.read_binding(key)
                self.assertEqual(record["session_id"], "session-A")
                self.assertEqual(record["owner_cwd"], str(target))
                self.assertEqual(record["project_title"], target.name)

    def test_mac_skips_headless_modes(self):
        for mode in ("exec", "app-server", "mcp-server"):
            with self.subTest(mode=mode):
                reader, _ = self.mac(argv=["codex", mode])
                self.assertIsNone(reader.read(42))

    def test_mac_missing_process_returns_none(self):
        command = ("/bin/ps", "-p", "42", "-o", "comm=")
        reader, _ = self.mac({command: subprocess.CompletedProcess(command, 1, "", "")})
        self.assertIsNone(reader.read(42))

    def test_mac_other_executable_and_empty_arguments_return_none(self):
        command = ("/bin/ps", "-p", "42", "-o", "comm=")
        reader, _ = self.mac({command: "/usr/bin/python3\n"})
        self.assertIsNone(reader.read(42))
        reader, _ = self.mac(argv=[])
        self.assertIsNone(reader.read(42))

    def test_mac_argument_permission_failure_reports_error(self):
        reader, _ = self.mac()
        reader.argv_reader = lambda pid: (_ for _ in ()).throw(PermissionError(errno.EPERM, "denied"))
        with self.assertRaises(process.ProcessError):
            reader.read(42)

    def test_mac_process_exit_during_argument_read_returns_none(self):
        reader, _ = self.mac()
        reader.argv_reader = lambda pid: (_ for _ in ()).throw(ProcessLookupError(errno.ESRCH, "gone"))
        self.assertIsNone(reader.read(42))

    def test_mac_list_reads_interactive_codex_candidates(self):
        listing = ("/bin/ps", "-axo", "pid=,comm=")
        reader, calls = self.mac({listing: "42 /opt/Codex App/codex\n43 /usr/bin/python3\n"})
        rows = reader.list()
        self.assertEqual([row["pid"] for row in rows], [42])
        self.assertFalse(any("43" in command for command, _ in calls))

    def test_mac_list_skips_inaccessible_foreign_process(self):
        listing = ("/bin/ps", "-axo", "pid=,comm=")
        reader, _ = self.mac({listing: "42 /opt/codex\n"})
        reader.argv_reader = lambda pid: (_ for _ in ()).throw(PermissionError(errno.EPERM, "denied"))
        self.assertEqual(reader.list(), [])

    def test_mac_invalid_start_and_missing_directory_are_explicit(self):
        command = ("/bin/ps", "-p", "42", "-o", "lstart=")
        reader, _ = self.mac({command: "invalid\n"})
        with self.assertRaises(process.ProcessError):
            reader.read(42)
        command = ("/usr/sbin/lsof", "-a", "-p", "42", "-d", "cwd", "-Fn")
        reader, _ = self.mac({command: "p42\n"})
        with self.assertRaises(process.ProcessError):
            reader.read(42)

    def test_mac_global_enumeration_error_is_explicit(self):
        listing = ("/bin/ps", "-axo", "pid=,comm=")
        reader, _ = self.mac({listing: subprocess.CompletedProcess(listing, 2, "", "query failed")})
        with self.assertRaises(process.ProcessError):
            reader.list()

    def test_mac_missing_dependency_and_permission_errors_are_explicit(self):
        command = ("/bin/ps", "-p", "42", "-o", "comm=")
        for error in (FileNotFoundError("ps missing"), PermissionError("denied")):
            with self.subTest(error=error):
                reader, _ = self.mac({command: error})
                with self.assertRaises(process.ProcessError):
                    reader.read(42)

    def test_mac_command_timeout_reports_error(self):
        command = ("/bin/ps", "-p", "42", "-o", "comm=")
        reader, _ = self.mac({command: subprocess.TimeoutExpired(command, 1)})
        with self.assertRaises(process.ProcessError):
            reader.read(42)

    def test_one_deadline_is_shared_across_subprocess_calls(self):
        values = iter((10, 10.1, 10.2, 10.5, 11.0, 11.5, 11.9, 12.1))
        reader, calls = self.mac(clock=lambda: next(values))
        with self.assertRaises(process.ProcessError):
            reader.read(42, deadline=12)
        timeouts = [kwargs["timeout"] for _, kwargs in calls]
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
        self.assertTrue(all(timeout <= 2 for timeout in timeouts))

    def test_expired_deadline_never_starts_a_command(self):
        reader, calls = self.mac(clock=lambda: 10)
        with self.assertRaises(process.ProcessError):
            reader.read(42, deadline=10)
        self.assertEqual(calls, [])

    def test_unsupported_platform_and_invalid_pid_are_explicit(self):
        with self.assertRaises(process.ProcessError):
            process.ProcessReader(platform="win32").list()
        reader = self.linux()
        for pid in (0, -1, True, "42", 1.5):
            with self.subTest(pid=pid), self.assertRaises(process.ProcessError):
                reader.read(pid)

    def test_native_mac_arguments_decode_empty_and_spaced_values(self):
        blob = struct.pack("=i", 4) + b"/opt/Codex App/codex\0\0" + \
            b"codex\0\0Explain app-server\0--search\0ENV=value\0"
        self.assertEqual(process.decode_mac_argv(blob), ["codex", "", "Explain app-server", "--search"])

    def test_native_mac_argument_errors_are_explicit(self):
        for blob in (b"", struct.pack("=i", -1) + b"codex\0", struct.pack("=i", 4) + b"codex\0\0arg\0"):
            with self.subTest(blob=blob), self.assertRaises(process.ProcessError):
                process.decode_mac_argv(blob)

    def test_native_mac_argument_syscall_uses_process_mib(self):
        blob = struct.pack("=i", 2) + b"/opt/codex\0\0codex\0Explain exec\0"
        captured = []

        class Sysctl:
            def __call__(self, mib, count, buffer, size, value, value_size):
                captured.append(list(mib))
                process.ctypes.memmove(buffer, blob, len(blob))
                size._obj.value = len(blob)
                return 0

        with patch.object(process.ctypes, "CDLL", return_value=SimpleNamespace(sysctl=Sysctl())), \
                patch.object(process.os, "sysconf", return_value=1024):
            self.assertEqual(process._mac_argv(42), ["codex", "Explain exec"])
        self.assertEqual(captured, [[1, 49, 42]])

    def test_native_mac_syscall_distinguishes_exit_and_permission(self):
        class Sysctl:
            def __call__(self, *args):
                return -1

        for code in (errno.ESRCH, errno.ENOENT, errno.EINVAL, errno.EPERM):
            expected = ProcessLookupError if code in (errno.ESRCH, errno.ENOENT, errno.EINVAL) else PermissionError
            with self.subTest(code=code), \
                    patch.object(process.ctypes, "CDLL", return_value=SimpleNamespace(sysctl=Sysctl())), \
                    patch.object(process.ctypes, "get_errno", return_value=code), \
                    patch.object(process.os, "sysconf", return_value=1024), \
                    self.assertRaises(expected):
                process._mac_argv(42)


if __name__ == "__main__":
    unittest.main()
