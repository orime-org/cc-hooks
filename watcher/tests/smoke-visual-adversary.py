#!/usr/bin/env python3
"""Smoke test for the visual-adversary extraction scripts.

extract-tokens.js runs under node and is asserted here.

inject-collect.js resolves values through a live CSS engine, so its assertions
run against a real page in a real browser — va-browser-check.js serves a fixture
over HTTP, drives chromium through playwright, and checks the returned data.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
EXTRACT = os.path.join(PLUGIN, "skills", "visual-adversary", "scripts", "extract-tokens.js")
BROWSER_CHECK = os.path.join(HERE, "va-browser-check.js")

FIXTURE_CSS = """
:root {
  --color-primary: #2563eb;
  --color-text: hsl(220 13% 18%);
  --spacing-4: 1rem;
  --radius-md: 6px;
  --btn-bg: var(--color-primary);
}
.card { padding: var(--spacing-4); }
.other { color: var(--color-text); }
"""

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def run_extract(root):
    out = subprocess.run(
        ["node", EXTRACT, root], capture_output=True, text=True, timeout=30
    )
    if out.returncode != 0:
        raise RuntimeError(f"extract-tokens.js exited {out.returncode}: {out.stderr}")
    return json.loads(out.stdout)


def test_extract_finds_declarations():
    with tempfile.TemporaryDirectory() as d:
        styles = os.path.join(d, "src", "styles")
        os.makedirs(styles)
        with open(os.path.join(styles, "tokens.css"), "w") as f:
            f.write(FIXTURE_CSS)

        data = run_extract(d)
        names = [t["name"] for t in data["tokens"]]

        check("finds every declared token", names == [
            "--btn-bg", "--color-primary", "--color-text", "--radius-md", "--spacing-4"
        ], names)
        check("var() usage is not mistaken for a declaration",
              names.count("--spacing-4") == 1, names)
        check("records the source file",
              data["tokens"][0]["sources"] == ["src/styles/tokens.css"],
              data["tokens"][0]["sources"])
        check("no tailwind config detected", data["tailwindConfig"] is None)
        check("no note when tokens exist", data["note"] is None, data["note"])


def test_extract_reports_missing_tokens():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "plain.css"), "w") as f:
            f.write(".a { color: red; }\n")

        data = run_extract(d)
        check("empty token list when nothing is declared", data["tokenCount"] == 0)
        check("note tells the caller to report a missing definition",
              data["note"] is not None and "lacking a token" in data["note"],
              data["note"])


def test_extract_detects_tailwind():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "tailwind.config.js"), "w") as f:
            f.write("module.exports = {}\n")

        data = run_extract(d)
        check("tailwind config is detected",
              data["tailwindConfig"] == ["tailwind.config.js"],
              data["tailwindConfig"])
        check("note asks for the theme scale",
              data["note"] is not None and "Tailwind" in data["note"],
              data["note"])


def test_extract_skips_vendor_dirs():
    with tempfile.TemporaryDirectory() as d:
        nm = os.path.join(d, "node_modules", "pkg")
        os.makedirs(nm)
        with open(os.path.join(nm, "vendor.css"), "w") as f:
            f.write(":root { --vendor-token: red; }\n")

        data = run_extract(d)
        names = [t["name"] for t in data["tokens"]]
        check("node_modules is not scanned", "--vendor-token" not in names, names)


def test_extract_reads_non_stylesheet_sources():
    """A Vue SFC, a CSS-in-JS template and an inline <style> all hold tokens."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src")
        os.makedirs(src)
        with open(os.path.join(src, "App.vue"), "w") as f:
            f.write("<template><div/></template>\n<style>:root { --sfc-color: #2563eb; }</style>\n")
        with open(os.path.join(src, "theme.ts"), "w") as f:
            f.write("export const G = createGlobalStyle`:root { --cssinjs-radius: 6px; }`\n")
        with open(os.path.join(d, "index.html"), "w") as f:
            f.write("<style>:root { --inline-gap: 8px; }</style>\n")

        data = run_extract(d)
        names = [t["name"] for t in data["tokens"]]
        check("token in a Vue SFC style block is found", "--sfc-color" in names, names)
        check("token in a CSS-in-JS template is found", "--cssinjs-radius" in names, names)
        check("token in an inline style block is found", "--inline-gap" in names, names)
        check("a project with tokens outside stylesheets is not reported as lacking them",
              data["note"] is None, data["note"])


def test_extract_reports_depth_truncation():
    """A deep tree stops the scan; the empty result must not read as 'no tokens'."""
    with tempfile.TemporaryDirectory() as d:
        deep = d
        for i in range(16):
            deep = os.path.join(deep, f"lvl{i}")
        os.makedirs(deep)
        with open(os.path.join(deep, "buried.css"), "w") as f:
            f.write(":root { --buried: red; }\n")

        data = run_extract(d)
        check("depth limit is reported", data["truncated"] is True, data)
        check("depth is named as the limit that was hit",
              data["truncatedBy"] is not None and data["truncatedBy"]["depth"] is True,
              data["truncatedBy"])
        check("a truncated scan does not claim the project lacks tokens",
              data["note"] is not None and "narrower root" in data["note"], data["note"])


def test_extract_reports_file_limit():
    """More files than the scanner takes; the cap is reported, not silent."""
    with tempfile.TemporaryDirectory() as d:
        for i in range(2100):
            with open(os.path.join(d, f"f{i}.css"), "w") as f:
                f.write(f":root {{ --t{i}: red; }}\n")

        data = run_extract(d)
        check("file limit is reported", data["truncated"] is True, data["scannedFiles"])
        check("files is named as the limit that was hit",
              data["truncatedBy"] is not None and data["truncatedBy"]["files"] is True,
              data["truncatedBy"])


def run_browser_checks():
    """Delegates to va-browser-check.js, which needs node and playwright."""
    out = subprocess.run(
        ["node", BROWSER_CHECK], capture_output=True, text=True, timeout=300
    )
    sys.stdout.write(out.stdout)
    if out.returncode == 2:
        # Exit 2 means playwright is unavailable. Reporting that as a pass would
        # claim verification that never ran.
        failures.append("browser checks could not run")
        return
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        failures.append("browser checks")


def main():
    if not os.path.exists(EXTRACT):
        print(f"missing {EXTRACT}")
        return 2

    print("extract-tokens.js")
    test_extract_finds_declarations()
    test_extract_reports_missing_tokens()
    test_extract_detects_tailwind()
    test_extract_skips_vendor_dirs()
    test_extract_reads_non_stylesheet_sources()
    test_extract_reports_depth_truncation()
    test_extract_reports_file_limit()

    print("inject-collect.js (real browser)")
    run_browser_checks()

    print()
    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
