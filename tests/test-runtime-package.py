#!/usr/bin/env python3
"""Exercise source provenance and actual package-integrity guards."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build-codex-runtime.py"
spec = importlib.util.spec_from_file_location("runtime_package", SCRIPT)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimePackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="runtime package ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def git(self, source, *args):
        return subprocess.run(["git", "-C", str(source), "-c", "core.hooksPath=/dev/null",
                               "-c", "commit.gpgsign=false",
                               "-c", "user.name=Runtime Package Test", "-c",
                               "user.email=runtime-package@example.invalid", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def source(self):
        source = self.root / "native source"
        source.mkdir()
        self.git(source, "init", "--quiet")
        (source / "codex-rs").mkdir()
        (source / "codex-rs/Cargo.toml").write_text('[workspace.package]\nversion = "0.163.0"\n')
        self.git(source, "add", "--", "codex-rs/Cargo.toml")
        self.git(source, "commit", "--quiet", "-m", "test: create source fixture")
        return source, self.git(source, "rev-parse", "HEAD")

    def client_report(self):
        return {"client": {"runtime_hooks_version": 1, "version": "0.163.0+" + "a" * 40,
                           "build_commit": "a" * 40, "features": list(runtime.FEATURES)},
                "server": None, "daemon": {"state": "unavailable"}}

    def test_clean_source_reports_its_actual_commit_and_workspace_version(self):
        source, base = self.source()
        identity = runtime.read_source(source, base=base)
        self.assertEqual(identity["commit"], base)
        self.assertEqual(identity["version"], "0.163.0")

    def test_source_changes_cannot_be_labelled_with_a_clean_commit(self):
        source, base = self.source()
        (source / "codex-rs/Cargo.toml").write_text('changed source\n')
        with self.assertRaisesRegex(ValueError, "clean"):
            runtime.read_source(source, base=base)

    def test_untracked_source_changes_are_rejected(self):
        source, base = self.source()
        (source / "untracked.rs").write_text('changed source\n')
        with self.assertRaisesRegex(ValueError, "clean"):
            runtime.read_source(source, base=base)

    def test_unrelated_source_history_is_rejected(self):
        source, base = self.source()
        self.git(source, "checkout", "--quiet", "--orphan", "unrelated")
        self.git(source, "commit", "--quiet", "-m", "test: create unrelated history")
        with self.assertRaisesRegex(ValueError, "base"):
            runtime.read_source(source, base=base)

    def test_build_probe_validates_client_without_claiming_daemon_verification(self):
        report = self.client_report()
        self.assertEqual(runtime.require_client(report, "a" * 40), report["client"])
        self.assertIsNone(report["server"])

    def test_each_required_feature_must_be_reported_by_the_binary(self):
        for feature in runtime.FEATURES:
            with self.subTest(feature=feature):
                report = self.client_report()
                report["client"]["features"].remove(feature)
                with self.assertRaisesRegex(ValueError, "feature"):
                    runtime.require_client(report, "a" * 40)

    def test_binary_source_stamp_must_match_the_source_commit(self):
        with self.assertRaisesRegex(ValueError, "commit"):
            runtime.require_client(self.client_report(), "b" * 40)

    def test_capability_protocol_requires_integer_version_one(self):
        for version in [0, 2, True, "1", 1.0, None]:
            with self.subTest(version=version):
                report = self.client_report()
                report["client"]["runtime_hooks_version"] = version
                with self.assertRaisesRegex(ValueError, "protocol"):
                    runtime.require_client(report, "a" * 40)

    def test_package_verification_detects_changed_bytes(self):
        (self.root / "payload").write_bytes(b"original executable")
        manifest = {"files": runtime.hash_files(self.root)}
        (self.root / "build-manifest.json").write_text(json.dumps(manifest))
        runtime.verify_package(self.root)
        (self.root / "payload").write_bytes(b"changed executable")
        with self.assertRaisesRegex(ValueError, "checksum"):
            runtime.verify_package(self.root)


if __name__ == "__main__":
    unittest.main()
