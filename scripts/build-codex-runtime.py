#!/usr/bin/env python3
"""Build a source-stamped companion package using Codex's canonical builder."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from urllib.request import urlopen

BASE = "83086188ae0614bd882818ff1aa23f3194962012"
TARGET = "aarch64-apple-darwin"
FEATURES = ("effective_tool_context", "interactive_terminal_context",
            "session_start_on_attach", "committed_plan_callbacks")


def git(source, *args, check=True):
    return subprocess.run(["git", "-C", str(source), *args], check=check,
                          capture_output=True, text=True)


def read_source(source, *, base=BASE):
    if git(source, "status", "--porcelain", "--untracked-files=normal").stdout.strip():
        raise ValueError("The native source checkout must be clean")
    if git(source, "merge-base", "--is-ancestor", base, "HEAD", check=False).returncode:
        raise ValueError("The native source does not descend from the pinned upstream base")
    commit = git(source, "rev-parse", "HEAD").stdout.strip()
    workspace = tomllib.loads((source / "codex-rs/Cargo.toml").read_text())
    return {"commit": commit, "base_commit": base,
            "version": workspace["workspace"]["package"]["version"]}


def require_client(report, commit):
    client = report.get("client") or {}
    if type(client.get("runtime_hooks_version")) is not int or client["runtime_hooks_version"] != 1:
        raise ValueError("The binary reports an incompatible runtime hook protocol")
    features = client.get("features")
    if not isinstance(features, list) or not all(isinstance(value, str) for value in features):
        raise ValueError("The binary reports invalid runtime hook features")
    missing = sorted(set(FEATURES) - set(features))
    if missing:
        raise ValueError("The binary is missing runtime hook features: " + ", ".join(missing))
    if client.get("build_commit") != commit:
        raise ValueError("The binary source commit does not match the clean source checkout")
    return client


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_files(package):
    result = {}
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError("Package checksum inputs must not be symlinks")
        if path.is_file():
            result[path.relative_to(package).as_posix()] = checksum(path)
    return result


def verify_package(package):
    expected = json.loads((package / "build-manifest.json").read_text())["files"]
    for relative, digest in expected.items():
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("Invalid package checksum path")
        path = package / name
        if not path.is_file() or path.is_symlink() or checksum(path) != digest:
            raise ValueError("Package checksum mismatch: " + relative)
    actual = set(hash_files(package)) - {"build-manifest.json", "SHA256SUMS"}
    if actual != set(expected):
        raise ValueError("Package checksum file list does not match the package")


def prepare_rg(source, inputs, archive):
    manifest = (source / "scripts/codex_package/rg").read_text()
    artifact = json.loads("\n".join(manifest.splitlines()[1:]))["platforms"]["macos-aarch64"]
    if archive is None:
        archive = inputs / "ripgrep.tar.gz"
        with urlopen(artifact["providers"][0]["url"], timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    if archive.stat().st_size != artifact["size"] or checksum(archive) != artifact["digest"]:
        raise ValueError("ripgrep archive does not match the native source checksum pin")
    prefix = str(Path(artifact["path"]).parent)
    licenses = inputs / "licenses"
    licenses.mkdir()
    with tarfile.open(archive, "r:gz") as bundle:
        for name in ("rg", "COPYING", "LICENSE-MIT", "UNLICENSE"):
            member = bundle.getmember(prefix + "/" + name)
            if not member.isfile():
                raise ValueError("ripgrep package contains an invalid resource")
            destination = inputs / "rg" if name == "rg" else licenses / name
            destination.write_bytes(bundle.extractfile(member).read())
            destination.chmod(0o755 if name == "rg" else 0o644)
    return inputs / "rg", licenses


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def build(args):
    source, destination = args.source.resolve(), args.output.absolute()
    if not args.source.is_absolute() or not args.output.is_absolute():
        raise ValueError("Source and output must be absolute paths")
    if destination.exists():
        raise ValueError("Output already exists; choose a new installation directory")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("This companion package currently targets macOS arm64")
    identity = read_source(source)
    sys.path.insert(0, str(source / "scripts"))
    from codex_package.cli import assemble_package, create_parser
    from codex_package.targets import TARGET_SPECS
    from codex_package.v8 import resolve_codex_v8_cargo_env

    environment = dict(os.environ, STABLE_GIT_COMMIT=identity["commit"])
    environment.update(resolve_codex_v8_cargo_env(TARGET_SPECS[TARGET], environ=environment))
    target_dir = Path(environment.get("CARGO_TARGET_DIR", source / "codex-rs/target"))
    if not target_dir.is_absolute():
        target_dir = source / "codex-rs" / target_dir
    environment["CARGO_TARGET_DIR"] = str(target_dir)
    command = [args.cargo, "build", "--locked", "--target", TARGET, "--profile", args.profile,
               "--bin", "codex", "--bin", "codex-code-mode-host", "-j", str(args.jobs)]
    if args.offline:
        command.append("--offline")
    subprocess.run(command, cwd=source / "codex-rs", env=environment, check=True)
    if read_source(source) != identity:
        raise ValueError("The source commit changed during the build")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".codex-runtime-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        inputs = staging / "inputs"
        inputs.mkdir()
        rg, rg_licenses = prepare_rg(source, inputs, args.rg_archive)
        profile_directory = "debug" if args.profile == "dev" else args.profile
        binaries = target_dir / TARGET / profile_directory
        package = staging / "package"
        version = identity["version"] + "-cc-hooks.g" + identity["commit"][:12]
        options = create_parser().parse_args([
            "--target", TARGET, "--package-version", version, "--package-dir", str(package),
            "--entrypoint-bin", str(binaries / "codex"),
            "--code-mode-host-bin", str(binaries / "codex-code-mode-host"),
            "--rg-bin", str(rg), "--strip", "none"])
        assemble_package(options)
        metadata_path = package / "codex-package.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["runtime_hooks_version"] = 1
        write_json(metadata_path, metadata)
        licenses = package / "licenses"
        licenses.mkdir()
        shutil.copyfile(source / "LICENSE", licenses / "Codex-LICENSE")
        shutil.copyfile(source / "NOTICE", licenses / "Codex-NOTICE")
        shutil.copytree(rg_licenses, licenses / "ripgrep")
        executable = package / "bin/codex"
        probe_home = staging / "probe-home"
        probe_home.mkdir()
        probe = subprocess.run([str(executable), "debug", "hook-capabilities", "--json"],
                               env=dict(environment, CODEX_HOME=str(probe_home)),
                               check=True, capture_output=True, text=True, timeout=20)
        report = json.loads(probe.stdout)
        client = require_client(report, identity["commit"])
        write_json(package / "capability-build-probe.json", report)
        write_json(package / "build-manifest.json", {
            "upstream": "https://github.com/openai/codex", "source": identity,
            "target": TARGET, "profile": args.profile, "version": version,
            "runtime_hooks_version": 1, "client": client,
            "daemon_verified": False, "files": hash_files(package)})
        verify_package(package)
        hashes = hash_files(package)
        (package / "SHA256SUMS").write_text("".join(
            f"{digest}  {name}\n" for name, digest in hashes.items()))
        if destination.exists():
            raise ValueError("Output was created during the build; choose a new directory")
        package.rename(destination)
    print(str(destination))
    print(str(destination / "build-manifest.json"))
    print("Daemon capability verification is pending an actual connection.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--profile", choices=("dev", "dev-small", "release"), default="dev-small")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--rg-archive", type=Path)
    parser.add_argument("--offline", action="store_true")
    try:
        build(parser.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Companion build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
