#!/usr/bin/env python3
"""Static checks on the plugin layout for Claude Code and Codex.

Run: python3 tests/smoke-manifests.py

Covers the Codex manifest and hook config, the Claude Code hook config staying as
on origin/main, the switch commands living as skills, and the platform section
every SKILL.md opens with.
"""
import json
import os
import re
import subprocess

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PLUGIN = os.path.join(ROOT, "watcher")
SKILLS = os.path.join(PLUGIN, "skills")
SECTION_HEADING = "## 平台对照"
SKILL_NAMES = ("watcher", "playbook", "visual-adversary", "watcher-on", "watcher-off", "watcher-configure")
SWITCHES = ("watcher-on", "watcher-off", "watcher-configure")

failures = []
checks = 0


def check(name, ok, detail=""):
    global checks
    checks += 1
    if not ok:
        failures.append(f"{name}: {detail}")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        failures.append(f"{os.path.relpath(path, ROOT)}: {e}")
        return {}


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


def section(text):
    """The platform section: its heading, intro and mapping table, up to the end of the table."""
    i = text.find(SECTION_HEADING + "\n")
    if i < 0:
        return None
    lines = text[i:].split("\n")
    end = next((k for k in range(1, len(lines)) if lines[k - 1].startswith("|") and not lines[k].startswith("|")), None)
    return "\n".join(lines[:end]) if end else None


# A. Codex manifest
cc_manifest = load_json(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"))
cx_manifest = load_json(os.path.join(PLUGIN, ".codex-plugin", "plugin.json"))
check("A1 Codex manifest names the plugin watcher", cx_manifest.get("name") == "watcher", repr(cx_manifest.get("name")))
check("A2 both manifests carry the same version", cx_manifest.get("version") == cc_manifest.get("version"),
      f"{cx_manifest.get('version')!r} vs {cc_manifest.get('version')!r}")
check("A3 Codex manifest points at the Codex hook config", cx_manifest.get("hooks") == "./hooks/codex-hooks.json",
      repr(cx_manifest.get("hooks")))
check("A4 Codex manifest points at the skills dir", cx_manifest.get("skills") == "./skills/", repr(cx_manifest.get("skills")))
check("A5 no root plugin.json in the plugin", not os.path.exists(os.path.join(PLUGIN, "plugin.json")))

# B. Codex hook config
cc_hooks = load_json(os.path.join(PLUGIN, "hooks", "hooks.json")).get("hooks", {})
cx_hooks = load_json(os.path.join(PLUGIN, "hooks", "codex-hooks.json")).get("hooks", {})
check("B1 Codex config wires the shared events", set(cx_hooks) == set(cc_hooks),
      repr(sorted(cx_hooks)))
for event, groups in cx_hooks.items():
    check(f"B8 {event} has the same handler groups as Claude Code",
          len(groups) == len(cc_hooks.get(event, [])))
    for g, group in enumerate(groups):
        cc_group = (cc_hooks.get(event) or [{}])[g] if g < len(cc_hooks.get(event) or []) else {}
        check(f"B9 {event} has the same handlers as Claude Code",
              len(group.get("hooks", [])) == len(cc_group.get("hooks", [])))
        if event == "PreToolUse":
            check(f"B2 {event} matcher is Bash", group.get("matcher") == "Bash", repr(group.get("matcher")))
        cc_handlers = cc_group.get("hooks") or []
        for h, handler in enumerate(group.get("hooks", [])):
            cc_handler = cc_handlers[h] if h < len(cc_handlers) else {}
            cmd = handler.get("command", "")
            m = re.fullmatch(r'bash "\$\{PLUGIN_ROOT\}/hooks/([a-z-]+\.sh)" codex', cmd)
            check(f"B3 {event} command runs a hook script with `codex`", bool(m), repr(cmd))
            if m:
                check(f"B4 {event} script exists", os.path.isfile(os.path.join(PLUGIN, "hooks", m.group(1))), m.group(1))
                cc_cmd = cc_handler.get("command", "")
                check(f"B5 {event} runs the same script as Claude Code", m.group(1) in cc_cmd, f"{cmd!r} vs {cc_cmd!r}")
            cc_timeout = cc_handler.get("timeout")
            check(f"B6 {event} timeout matches Claude Code", handler.get("timeout") == cc_timeout,
                  f"{handler.get('timeout')!r} vs {cc_timeout!r}")
            if event == "UserPromptSubmit":
                check("B7 UserPromptSubmit passes the full spec", handler.get("additionalContextLimit") == 0,
                      repr(handler.get("additionalContextLimit")))

# C. Claude Code hook config stays as on origin/main
main_hooks = subprocess.run(["git", "show", "origin/main:watcher/hooks/hooks.json"], cwd=ROOT,
                            capture_output=True, text=True).stdout
with open(os.path.join(PLUGIN, "hooks", "hooks.json")) as f:
    check("C1 hooks.json is unchanged from origin/main", f.read() == main_hooks)

# D. Switch commands live as skills
check("D1 commands/ is gone", not os.path.exists(os.path.join(PLUGIN, "commands")))
for name in SWITCHES:
    path = os.path.join(SKILLS, name, "SKILL.md")
    text = open(path).read() if os.path.isfile(path) else ""
    fm = frontmatter(text)
    check(f"D2 {name} skill exists", bool(text), path)
    check(f"D3 {name} frontmatter name matches its dir", re.search(rf"^name: {name}$", fm, re.M) is not None, fm[:80])
    check(f"D4 {name} has a description", re.search(r"^description: \S", fm, re.M) is not None, fm[:80])
    check(f"D5 {name} drops `command: true`", "command: true" not in fm)

configure = os.path.join(SKILLS, "watcher-configure", "SKILL.md")
text = open(configure).read() if os.path.isfile(configure) else ""
ref = "../watcher/references/setup-flow.md"
check("D6 watcher-configure points at setup-flow relative to its own dir", ref in text)
check("D7 that path resolves", os.path.isfile(os.path.normpath(os.path.join(os.path.dirname(configure), ref))))
check("D8 no plugin-root-relative setup-flow path left", "`skills/watcher/references/setup-flow.md`" not in text)

packaged_skills = {name for name in os.listdir(SKILLS) if os.path.isfile(os.path.join(SKILLS, name, "SKILL.md"))}
check("D9 packaged skills match the supported skills", packaged_skills == set(SKILL_NAMES), repr(sorted(packaged_skills)))
panel_assets = [name for name in os.listdir(os.path.join(PLUGIN, "hooks"))
                if name.startswith(("task-panel", "task_panel"))]
check("D10 task panel runtime is retired", not panel_assets, repr(panel_assets))
check("D11 task panel configuration skill is retired",
      not os.path.exists(os.path.join(SKILLS, "task-panel-configure")))
check("D12 companion runtime builder is retired",
      not os.path.exists(os.path.join(ROOT, "scripts", "build-codex-runtime.py")))
with open(os.path.join(ROOT, ".github", "workflows", "smoke.yml")) as stream:
    ci = stream.read()
check("D13 CI targets the supported feature checks",
      "task-panel" not in ci and "test-runtime-package.py" not in ci)

# E. Platform section: present, identical, before any other level-2 heading
sections = {}
for name in SKILL_NAMES:
    path = os.path.join(SKILLS, name, "SKILL.md")
    text = open(path).read() if os.path.isfile(path) else ""
    sec = section(text)
    sections[name] = sec
    check(f"E1 {name} has the platform section", sec is not None)
    if sec is None:
        continue
    body = text[len(frontmatter(text)) + 8:] if frontmatter(text) else text
    first_h2 = re.search(r"^## .*$", body, re.M)
    check(f"E2 {name} opens with the platform section", first_h2 is not None and first_h2.group(0) == SECTION_HEADING,
          first_h2.group(0) if first_h2 else "no level-2 heading")
present = [s for s in sections.values() if s]
check("E3 the platform section is identical in every SKILL.md", len(set(present)) == 1, f"{len(set(present))} variants")
if present:
    for wanted in ("exec_command", "apply_patch", "spawn_agent", "wait", "gh pr checks", "mergeStateStatus",
                   "$watcher:", "AGENTS.md", "${CLAUDE_SKILL_DIR}", "联网搜索", "Claude Code"):
        check(f"E4 platform section maps {wanted!r}", wanted in present[0])

# F. Direct edits outside the section
watcher_md = open(os.path.join(SKILLS, "watcher", "SKILL.md")).read()
check("F1 watcher/SKILL.md no longer says 调用 Skill 工具", "调用 Skill 工具" not in watcher_md)
check("F2 watcher/SKILL.md no longer says CC 会话", "CC 会话" not in watcher_md)
playbook_md = open(os.path.join(SKILLS, "playbook", "SKILL.md")).read()
rule_line = next((l for l in playbook_md.splitlines() if l.startswith("只写流程和决策逻辑")), "")
check("F3 playbook names Codex rule files and tools", "Codex" in rule_line, rule_line[:120])

if failures:
    print(f"❌ {len(failures)}/{checks} checks failed:\n")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print(f"✅ all {checks} checks passed")
