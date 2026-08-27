# Orime — Claude Code Plugin Marketplace

> Self-monitoring + knowledge curation plugins for Claude Code.

[中文文档 / Chinese](./README.zh-CN.md)

## What is Orime?

Orime is a plugin marketplace for [Claude Code](https://claude.ai/code), focused on plugins that help Claude self-monitor its behavior and keep your project's knowledge base in sync.

It currently holds one plugin: **`watcher`**.

## Why use it?

When Claude runs autonomously over many turns:

- It can skip steps (e.g., not restate your intent before acting)
- It can drift from project conventions (formatting, language, naming)
- Documentation and memory can fall out of sync with what shipped
- It can commit straight to the main branch, or write a commit title in the wrong format

Once `watcher` is installed, four components cover these: a collaboration spec is injected at the start of every turn, a knowledge audit runs at every turn end, `git commit` passes through a tool-level gate, and output follows a Chinese engineering style.

## Repository layout (name cheat-sheet)

This project has a few names — here's the map so they don't trip you up:

| Name | What it is |
|---|---|
| `cc-hooks` | The GitHub repository |
| `orime` | The plugin marketplace inside the repo (you install with `@orime`) |
| `watcher` | The only plugin in the marketplace so far |
| `watcher` skill | The skill inside the plugin (same name as the plugin — that's why you see two `watcher` levels in the path) |

The layout:

```
cc-hooks/                          # repository
├── .claude-plugin/
│   └── marketplace.json           # marketplace manifest (named orime)
├── README.md / README.zh-CN.md
├── CHANGELOG.md
├── LICENSE
├── docs/
└── watcher/                       # the plugin (only one)
    ├── .claude-plugin/plugin.json
    ├── commands/                  # watcher-configure / watcher-off / watcher-on
    ├── hooks/                     # announce-intent.sh / bash-gate.sh / suggest-watcher.sh / hooks.json
    ├── output-styles/             # chinese-engineering.md
    ├── scripts/                   # check-size.sh + smoke tests
    ├── skills/watcher/            # skill (same name as the plugin)
    └── skills/visual-adversary/   # skill loaded by the visual review step
        ├── SKILL.md
        └── references/
```

`.watcher/` (with the dot) is per-project runtime config that watcher generates inside a *monitored* project. It's `.gitignore`d and **not in this repo** — it is a separate thing from the plugin dir `watcher/` (no dot).

## Plugin: watcher

### What it does

| Component | When it fires | What it does |
|---|---|---|
| `UserPromptSubmit` hook (`announce-intent.sh`) | Every prompt you submit | Injects a collaboration spec in four chapters: general principles, expression, general workflow, coding-task workflow |
| `PreToolUse` hook (`bash-gate.sh`) | Every Bash command Claude runs | Blocks two cases: committing on the main branch; a commit title outside the `type: summary` format or carrying `Co-Authored-By`. Applies only to projects whose repo root has `.watcher/` |
| `Stop` hook (`suggest-watcher.sh`) | Every Claude turn ends | Prompts Claude to invoke the `watcher` skill for an audit; reports the current time and context token usage each turn, warning to run `/compact` past 85%. Skips the audit while a background `subagent` / `workflow` task is still running, so it lands on the turn where that task finishes |
| `watcher` skill | Triggered by the Stop hook, or manually via `/watcher:watcher` | Runs the 5-step audit and emits a 7-section summary |
| `visual-adversary` skill | The spec's visual review step, or manually via `/watcher:visual-adversary` | Boots the real app, reads computed styles and layout metrics, and reports accessibility must-fixes separately from suggestions |
| Output style (`chinese-engineering.md`) | Active as soon as the plugin is installed | Chinese engineering mode: conclusion first, short sentences, no AI filler |
| `/watcher:watcher-configure` | Run manually | Creates or revises this project's `.watcher/` trio. This is the one way to configure |
| `/watcher:watcher-off` / `/watcher:watcher-on` | Run manually | Toggles the turn-end automatic audit per project |

### The rules injected per turn

A collaboration spec is injected at the start of every turn, in four chapters: general principles, expression, general workflow, coding-task workflow.

The text lives in [`watcher/hooks/announce-intent.sh`](./watcher/hooks/announce-intent.sh), which is the single source.

## Installation

### From GitHub

```bash
/plugin marketplace add orime-org/cc-hooks
/plugin install watcher@orime
```

### From local clone

```bash
git clone https://github.com/orime-org/cc-hooks.git
/plugin marketplace add /path/to/cc-hooks
/plugin install watcher@orime
```

After installing or pulling updates:

```
/reload-plugins
```

## Quick start

Once installed, each turn runs like this:

1. You submit a prompt and the `UserPromptSubmit` hook injects the collaboration spec
2. Claude states what it plans to do before changing anything, then acts on your request
3. When Claude runs `git commit`, the `PreToolUse` hook checks the branch and the title format
4. On turn end the `Stop` hook fires and Claude invokes the `watcher` skill
5. `watcher` runs the 5-step audit and emits a 7-section Markdown summary

You'll see structured output: consistent numbering, comparison tables, decision tables when input is needed, and a `## 6. 根因自检` section after every action.

## Project-level configuration (`.watcher/`)

For per-project rules (which docs must stay in sync, which files are off-limits), create a `.watcher/` directory at your project root with 3 files:

| File | Purpose |
|---|---|
| `project-summary.md` | One paragraph — what is this project, who uses it, what's the goal |
| `doc-inventory.md` | List of canonical docs that must stay in sync with code |
| `watchlist.md` | Per-project rules — e.g., "never modify `1.txt`", "always run tests after `src/auth/`" |

To set up `.watcher/`, run:

```
/watcher:watcher-configure
```

It interviews you about your project, shows you the drafts for confirmation, then writes the 3 files. From then on every audit runs both the general rules and your project rules.

Once `.watcher/` exists, the project also comes under `bash-gate.sh`.

## Bash command gate

In projects whose repo root has `.watcher/`, Claude's `git commit` calls pass through a check:

| Check | Blocks when |
|---|---|
| Branch | Currently on `main` or `master` |
| Commit title | Outside `type: summary`, where type is one of `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci`; summary over 72 characters; trailing period |
| Commit message | Contains `Co-Authored-By` |

When blocked, Claude is told which check failed.

The branch check reads git, so the command text cannot change its answer. The title check reads the command text, which bounds what it covers: when the message arrives through `-F`, a heredoc, command substitution, or contains a backtick, the final text is not on the command line and neither the title nor the `Co-Authored-By` check runs. Covering those writings needs a native git `commit-msg` hook — see the known boundaries in `docs/bash-gate-design.md`.

Repos without `.watcher/` pass through untouched.

## Toggling the turn-end audit per project

| Slash command | Effect |
|---|---|
| `/watcher:watcher-off` | Sets `enable-audit` to `false` in `<project>/.watcher/audit-state.json` |
| `/watcher:watcher-on` | Sets it to `true` |

While off, each turn still shows the time, token usage, and the count of unaudited rounds, with the audit itself skipped. The per-turn spec injection is unaffected.

Each project has its own `audit-state.json`, independent of the others. The file can also be edited by hand.

## Changing the rules

The collaboration spec lives in [`watcher/hooks/announce-intent.sh`](./watcher/hooks/announce-intent.sh) — a Bash script that emits stdout, which Claude Code wraps in `<system-reminder>` on `UserPromptSubmit`.

After editing, run these three:

```bash
bash watcher/tests/check-size.sh                                    # character ceiling 9500
echo '{"session_id":"test","prompt":"test"}' | bash watcher/hooks/announce-intent.sh
python3 watcher/tests/smoke-stop-hook.py
```

The 9500 in `check-size.sh` is a self-imposed ceiling. Claude Code caps a single hook's stdout at 10000 characters, past which it is truncated to a 2000-character preview; the remaining 500 covers a mismatch between what the script counts and what Claude Code counts.

After commit + push, run `/reload-plugins` in any active Claude Code session.

To change the audit flow, edit [`watcher/skills/watcher/SKILL.md`](./watcher/skills/watcher/SKILL.md). To change the Bash gate rules, edit `watcher/hooks/bash-gate.sh` and run `python3 watcher/tests/smoke-bash-gate.py`.

## Contributing

Issues and PRs welcome at https://github.com/orime-org/cc-hooks.

## License

MIT — see [LICENSE](./LICENSE).

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).
