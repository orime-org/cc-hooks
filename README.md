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

## Plugin: watcher (0.1.0)

### What it does

| Component | When it fires | What it does |
|---|---|---|
| `UserPromptSubmit` hook (`announce-intent.sh`) | Every prompt you submit | Injects a `<system-reminder>` with 10 segments of rules |
| `Stop` hook (`suggest-watcher.sh`) | Every Claude turn ends | Blocks the turn and reminds Claude to invoke `watcher` skill |
| `watcher` skill (audit / configure) | Triggered by Stop hook or manually | Runs 5-step audit + 7-section summary, or configures project-level `.watcher/` |

### The 10 rule segments injected per turn

`watcher` enforces 10 segments (Chinese-first, plain language):

1. Current date (UTC, second precision)
2. Segment structure — Markdown headings, numbering whitelist, no fake tables
3. 4-step intent restate — rephrase → analyze root cause → propose thorough solution → state plan
4. Output format — Markdown tables, no `field: value` lists, vertical flow diagrams
5. Conversation style — plain language, Chinese by default, no telegram-style words
6. Decision tables — 5-column Markdown, no `AskUserQuestion` tool
7. Root-cause investigation — real evidence, local first, then remote
8. No-discount thorough solutions — don't split scope to avoid hard work
9. PR after-care — watch CI, clean up branches after merge
10. DD + TDD enforcement for coding tasks

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
