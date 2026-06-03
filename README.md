# Orime — Claude Code Plugin Marketplace

> Self-monitoring + knowledge curation plugins for Claude Code.

[中文文档 / Chinese](./README.zh-CN.md)

## What is Orime?

Orime is a plugin marketplace for [Claude Code](https://claude.ai/code), focused on plugins that help Claude self-monitor its behavior and keep your project's knowledge base in sync.

The flagship plugin is **`watcher`** — a turn-by-turn intent guard plus a Stop-time knowledge audit that keeps Claude accountable.

## Why use it?

When Claude runs autonomously over many turns:

- It can skip steps (e.g., not restate your intent before acting)
- It can drift from project conventions (formatting, language, naming)
- Documentation and memory can fall out of sync with what shipped

`watcher` injects rules at every turn (via `UserPromptSubmit` hook) and runs a 5-step knowledge audit at every Stop (via the `watcher` skill). The result: Claude follows your output style and your knowledge base stays current.

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
cc-hooks/                      # repository
├── .claude-plugin/
│   └── marketplace.json       # marketplace manifest (named orime)
├── README.md / README.zh-CN.md
├── CHANGELOG.md
├── LICENSE
└── watcher/                   # the plugin (only one)
    ├── .claude-plugin/plugin.json
    ├── commands/              # watcher-off / watcher-on
    ├── hooks/                 # announce-intent.sh / suggest-watcher.sh / hooks.json
    └── skills/watcher/        # skill (same name as the plugin)
        ├── SKILL.md
        └── references/
```

> Note: `.watcher/` (with the dot) is per-project runtime config that watcher generates inside a *monitored* project. It's `.gitignore`d and **not in this repo** — don't confuse it with the plugin dir `watcher/` (no dot).

## Plugin: watcher

### What it does

| Component | When it fires | What it does |
|---|---|---|
| `UserPromptSubmit` hook (`announce-intent.sh`) | Every prompt you submit | Injects a `<system-reminder>` with 13 segments of rules |
| `Stop` hook (`suggest-watcher.sh`) | Every Claude turn ends | Blocks the turn and reminds Claude to invoke `watcher` skill; also reports context token usage (K + %) and warns to run `/compact` past 85% (skippable per-project via `/watcher:watcher-off`) |
| `watcher` skill (audit / configure) | Triggered by Stop hook or manually | Runs 5-step audit + 7-section summary, or configures project-level `.watcher/` |
| `/watcher:watcher-off` / `/watcher:watcher-on` slash commands | Run manually | Toggle the per-turn automatic `watcher` audit for the current project (creates / removes `.watcher/.stop-disabled`) |

### The 13 rule segments injected per turn

`watcher` enforces 13 segments (Chinese-first, plain language):

1. Current date (UTC, second precision)
2. Segment structure — Markdown headings, numbering whitelist, no fake tables
3. 4-step intent restate — rephrase → analyze root cause → propose thorough solution → state plan
4. Output format — Markdown tables, no `field: value` lists, vertical flow diagrams (any 2+ similar items — reports / explanations / self-checks too, no scenario exception)
5. Conversation style — plain language, Chinese by default, no telegram-style words
6. Decision tables — 3-column Markdown (option / what / why-incl-consequence), recommendation tagged inline as `A（推荐）` (no separate column), no `AskUserQuestion` tool
7. Root-cause-first, evidence-backed — survey the whole picture before tunneling into one direction; check local first, then search the web (WebSearch); don't flail, after 2 failed attempts stop and search for an existing solution; surface unplanned problems to me first (no self-patching) — blocking ones stop & diagnose, side ones go to the todo list for me to decide (this todo/confirm flow is for runnable code only; pure doc/note/memory mismatches are zero-cost — fix on sight per segment 12)
8. Thorough-only, zero discount — every solution must be thorough, absolutely no discount allowed
9. Strict coding-task rules — spec gate (confirm DD / TDD + smoke / E2E specs exist before coding, gate one, don't skip), then a fixed order: 9.1 docs-first → 9.2 tests-first (TDD red, test before implementation) → 9.3 implement + refactor (green; incl. modularize/extract-shared, surface pre-existing bad code, doc/note/memory mismatches fixed directly per segment 12.1) → 9.4 full verify (smoke / E2E, must all pass before PR) → 9.5 sync docs → 9.6 open PR
10. PR after-care — watch CI, post the full PR url after creating it, clean up branches after merge
11. Subagent usage — parallelize independent multi-folder/module work, offload big searches to keep the main context clean, run multi-angle reviews; never spawn for sequential context-sharing work or trivial single-point tasks
12. Honesty + verify capstone — faking it is the only red line (false confidence, workaround-as-fix, claiming unverified, too lazy to search); "I don't know" isn't the end — go WebSearch / check docs / run a minimal test, then conclude; found an error → fix it on the spot (new or old mistake, don't defer), split by fix cost: doc/note/memory mismatches (zero-cost) fixed on sight with no todo/no asking, pre-existing code (risky) goes through report+confirm first
13. Death bottom line — fail to find root cause or use thorough solutions, and I lose my job, default on my mortgage, end up homeless and starving

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

Once installed, every prompt triggers the `UserPromptSubmit` hook. Claude sees a `<system-reminder>` containing 13 rule segments (the first is the current date), then:

1. Restates your intent (`## 1. 复述意图` with 4 sub-items)
2. Acts according to your request
3. On turn end, the `Stop` hook fires and Claude invokes `watcher` skill
4. `watcher` runs a 5-step audit and emits a 7-section Markdown summary

You'll see structured output with consistent numbering, comparison tables, decision tables when input is needed, and a `## 6. 根因自检` section after every action.

## Project-level configuration (`.watcher/`)

For per-project rules, create a `.watcher/` directory at your project root with 3 files:

| File | Purpose |
|---|---|
| `project-summary.md` | One paragraph — what is this project, who uses it, what's the goal |
| `doc-inventory.md` | List of canonical docs that must stay in sync with code |
| `watchlist.md` | Per-project rules — e.g., "never modify `1.txt`", "always run tests after `src/auth/`" |

To set up `.watcher/`, run:

```
/watcher configure
```

`watcher` enters configure mode, interviews you about your project, and writes the 3 files. After that, every audit runs both global rules and your project-specific rules.

## Toggling the per-turn watcher audit per project

The per-turn automatic `watcher` audit can be silenced for a specific project without uninstalling the plugin or disabling the global `UserPromptSubmit` rule injection.

| Slash command | What it does | Marker file |
|---|---|---|
| `/watcher:watcher-off` | Silence the per-turn watcher audit in the current project | Creates `<project>/.watcher/.stop-disabled` |
| `/watcher:watcher-on` | Re-enable the per-turn watcher audit in the current project | Removes `<project>/.watcher/.stop-disabled` |

How it works:

- The Stop hook reads `cwd` from its stdin JSON and checks if `<cwd>/.watcher/.stop-disabled` exists
- If yes → `exit 0` immediately (no block, no reminder)
- If no → normal `decision:"block"` flow that nudges Claude to invoke the `watcher` skill
- The `UserPromptSubmit` announce rules keep running either way — only the turn-end audit reminder is toggled
- Each project has its own toggle file, so you can keep `watcher` chatty in important projects and quiet in throwaway sandboxes

You can also manage the toggle file by hand: `touch .watcher/.stop-disabled` / `rm .watcher/.stop-disabled`.

## Customizing announce rules

The 13 rule segments live in `watcher/hooks/announce-intent.sh` — a Bash script that emits stdout, which Claude Code wraps in `<system-reminder>` on `UserPromptSubmit`.

To change a rule:

1. Edit `watcher/hooks/announce-intent.sh`
2. Smoke test: `echo '{"session_id":"test","prompt":"test"}' | bash watcher/hooks/announce-intent.sh`
3. Commit + push
4. Run `/reload-plugins` in any active Claude Code session

To change the audit flow, edit `watcher/skills/watcher/SKILL.md`.

## Contributing

Issues and PRs welcome at https://github.com/orime-org/cc-hooks.

## License

MIT — see [LICENSE](./LICENSE).

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).
