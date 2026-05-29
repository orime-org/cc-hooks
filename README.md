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

## Plugin: watcher (0.1.1)

### What it does

| Component | When it fires | What it does |
|---|---|---|
| `UserPromptSubmit` hook (`announce-intent.sh`) | Every prompt you submit | Injects a `<system-reminder>` with 11 segments of rules |
| `Stop` hook (`suggest-watcher.sh`) | Every Claude turn ends | Blocks the turn and reminds Claude to invoke `watcher` skill (skippable per-project via `/watcher:watcher-off`) |
| `watcher` skill (audit / configure) | Triggered by Stop hook or manually | Runs 5-step audit + 7-section summary, or configures project-level `.watcher/` |
| `/watcher:watcher-off` / `/watcher:watcher-on` slash commands | Run manually | Toggle the Stop hook reminder for the current project (creates / removes `.watcher/.stop-disabled`) |

### The 11 rule segments injected per turn

`watcher` enforces 11 segments (Chinese-first, plain language):

1. Current date (UTC, second precision)
2. Segment structure — Markdown headings, numbering whitelist, no fake tables
3. 4-step intent restate — rephrase → analyze root cause → propose thorough solution → state plan
4. Output format — Markdown tables, no `field: value` lists, vertical flow diagrams
5. Conversation style — plain language, Chinese by default, no telegram-style words
6. Decision tables — 5-column Markdown, no `AskUserQuestion` tool
7. Root-cause-first, evidence-backed — every problem must trace to root cause, backed by real evidence
8. Thorough-only, zero discount — every solution must be thorough, absolutely no discount allowed
9. DD / TDD process + smoke / E2E test enforcement for coding tasks
10. PR after-care — watch CI, post the full PR url after creating it, clean up branches after merge
11. Death-penalty bottom line — fail to find root cause or use thorough solutions, and I lose my job, default on my mortgage, end up homeless and starving

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

Once installed, every prompt triggers the `UserPromptSubmit` hook. Claude sees a `<system-reminder>` containing the current date and 10 rule segments, then:

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

## Toggling the Stop reminder per project

The `Stop` hook reminder can be silenced for a specific project without uninstalling the plugin or disabling the global `UserPromptSubmit` rule injection.

| Slash command | What it does | Marker file |
|---|---|---|
| `/watcher:watcher-off` | Silence the Stop reminder in the current project | Creates `<project>/.watcher/.stop-disabled` |
| `/watcher:watcher-on` | Re-enable the Stop reminder in the current project | Removes `<project>/.watcher/.stop-disabled` |

How it works:

- The Stop hook reads `cwd` from its stdin JSON and checks if `<cwd>/.watcher/.stop-disabled` exists
- If yes → `exit 0` immediately (no block, no reminder)
- If no → normal `decision:"block"` flow that nudges Claude to invoke the `watcher` skill
- The `UserPromptSubmit` announce rules keep running either way — only the turn-end audit reminder is toggled
- Each project has its own toggle file, so you can keep `watcher` chatty in important projects and quiet in throwaway sandboxes

You can also manage the toggle file by hand: `touch .watcher/.stop-disabled` / `rm .watcher/.stop-disabled`.

## Customizing announce rules

The 10 rule segments live in `watcher/hooks/announce-intent.sh` — a Bash script that emits stdout, which Claude Code wraps in `<system-reminder>` on `UserPromptSubmit`.

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
