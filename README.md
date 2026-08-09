# Orime — Claude Code Plugin Marketplace

> Self-monitoring + knowledge curation plugins for Claude Code.

[中文文档 / Chinese](./README.zh-CN.md)

## What is Orime?

Orime is a plugin marketplace for [Claude Code](https://claude.ai/code), focused on plugins that help Claude self-monitor its behavior and keep your project's knowledge base in sync.

The flagship plugin is **`watcher`** — a turn-by-turn intent guard plus a Stop-time knowledge audit that keeps Claude accountable.

### Segment structure (4 segments as of v0.1.100)

| Segment | Covers | Sub-sections |
|---|---|---|
| 1 | How to talk to me | 1.1 segments and numbering, 1.2 output format, 1.3 wording and tone, 1.4 bringing me decisions |
| 2 | How to work | 2.1 classify before acting (three deliverable kinds, three tiers, three classes under the user tier), 2.2 root-cause-first, 2.3 thorough-only, 2.4 do it yourself or delegate, 2.5 a PR is not done when opened, 2.6 surface unplanned problems |
| 3 | Coding-task rules | 3.1 three foundations up front, 3.2 rules shared by all three gates, 3.3 docs-first (Gate 1 at the end), 3.4 failing test first then implementation, 3.5 full verify (Gate 2 at the end), 3.6 wrap up (Gate 3 and submit) |
| 4 | What it comes down to | none |

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
| `UserPromptSubmit` hook (`announce-intent.sh`) | Every prompt you submit | Injects a `<system-reminder>` with 4 segments of rules |
| `Stop` hook (`suggest-watcher.sh`) | Every Claude turn ends | Blocks the turn and reminds Claude to invoke `watcher` skill; skips entirely while a background `subagent`/`workflow` task is still running/pending (reads `background_tasks`) or the turn had no final text, so the audit lands on the wake-up turn instead; each real turn-end also reports the current time + context token usage (K + %) and warns to run `/compact` past 85%. `/watcher:watcher-off` turns off the audit for the project **but still shows the time + token + rounds-since-last-audit status each turn** (audit-off ≠ status-off); `/watcher:watcher-on` re-enables the audit |
| `watcher` skill (audit only) | Triggered by Stop hook or manually via `/watcher:watcher` | Runs the 5-step audit + 7-section summary. **Never creates configs** — that belongs to the command below |
| `/watcher:watcher-configure` slash command | Run manually | **The one way to configure**: create or revise this project's `.watcher/` trio (interviews you → shows drafts for confirmation → only then writes) |
| `/watcher:watcher-off` / `/watcher:watcher-on` slash commands | Run manually | Toggle the per-turn automatic `watcher` audit for the current project (flips `enable-audit` in `.watcher/audit-state.json`) |

### The 4 rule segments injected per turn

`watcher` injects 4 segments per turn (Chinese-first). Below is what each segment covers; **the authoritative text is [`watcher/hooks/announce-intent.sh`](./watcher/hooks/announce-intent.sh)** — that file is the single source, and the full text is deliberately not duplicated here so the two cannot drift apart.

1. **How to talk to me** — segments and numbering (heading levels, numbering whitelist, never fake a table with bullets or rules); output format (any 2+ structurally similar items must be a Markdown table, no scenario exception); wording and tone (state things clearly and precisely, Chinese by default, written as ordinary Chinese sentences, name things by their actual names, you are a teammate rather than an outside vendor); how to bring me decisions (state the question and the facts before the table, 3-column table, options must trace to a basis and never be invented, no `AskUserQuestion`)
2. **How to work** — classify before acting, narrowing down three levels. First the deliverable kind: running code goes on to the next step, test code is written failing-test-first, and existing tests only change when the contract really changed, prose (comments, docs, memory) gets fixed on the spot. Then running code gets a tier: user tier is what legitimate users reach, dev tier is what only we touch while writing code (CI checks, build scripts), ops tier is what deployment and production upkeep reach. Only the user tier gets a class: in-scope must be polished until smooth, out-of-scope is a normal person hitting a state we never promised and only needs a clear message plus a clear next step, illegitimate-use needs one hard gate at the entrance plus an audit trail. Dev and ops tiers get no class. Code quality is a separate yardstick, outside both tier and class. Anything whose fallout lands on legitimate users or on us, and any tier or class you are unsure about, must be asked rather than decided alone; root-cause-first and evidence-backed (survey the whole picture, local before remote, stop and search after two failed attempts, quote a rule's text and source before leaning on it); thorough-only with zero discount; do it yourself or delegate (never spawn just to spawn; what a workflow hands back is input, not a verdict, and the closing check is never delegated again); a PR is not done when it is opened; surface unplanned problems instead of absorbing them
3. **Coding-task rules** — first lay down three foundations (spec gate, acceptance checklist, how forks get raised); 3.2 holds the rules shared by all three gates; then a fixed order: 3.3 docs-first (reuse-first plus a commercial-license gate, UI designs must cover the visual side, Gate 1 finds problems in the plan at the end) → 3.4 failing test first, then implementation → 3.5 full verify (smoke/E2E on a really launched app, Gate 2 looks for problems in the build along four lines at the end) → 3.6 wrap up (sync the prose, run Gate 3 to find problems in comments and docs, then submit; commit and PR text in English, no attribution trailer). Problem classification does not live in this segment — it is all in 2.1
4. **What it comes down to** — restates a few of the rules above: faking it is the only red line; not being sure is the signal to go check; fix errors on sight regardless of age; a problem brought for a decision must itself hold up, and the options must address the root cause. It closes on the two that matter most: find the real root cause, ship the thorough solution

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

Once installed, every prompt triggers the `UserPromptSubmit` hook. Claude sees a `<system-reminder>` containing 4 rule segments, then:

1. States what it plans to do before changing anything
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
/watcher:watcher-configure
```

This command interviews you about your project, shows you the drafts for confirmation, and writes the 3 files (**it is the only way to configure** — the `watcher` skill only audits, it never creates configs). After that, every audit runs both global rules and your project-specific rules.

## Toggling the per-turn watcher audit per project

The per-turn automatic `watcher` audit can be silenced for a specific project without uninstalling the plugin or disabling the global `UserPromptSubmit` rule injection.

| Slash command | What it does | Effect |
|---|---|---|
| `/watcher:watcher-off` | Silence the per-turn watcher audit in the current project | Sets `enable-audit: false` in `<project>/.watcher/audit-state.json` |
| `/watcher:watcher-on` | Re-enable the per-turn watcher audit in the current project | Sets `enable-audit: true` in `<project>/.watcher/audit-state.json` |

How it works — state lives in one file, `<project>/.watcher/audit-state.json` (`{ "enable-audit": true/false, "unaudited-rounds": N }`); on/off only flip the field, never delete the file:

- The Stop hook reads `<cwd>/.watcher/audit-state.json` and branches:
  - **file missing** — project not configured, or CC handed the hook a `cwd` that isn't the project root (happens on the wake-up turn after a background task finishes) → **no audit, but still shows the time + token status plus a one-line "no `.watcher/` here" note** (so you never lose the time/token readout in an unconfigured dir). Emitted through the `{"continue":false,"stopReason":…}` **stop path**: once shown, CC really stops instead of being woken by the notice to carry on working
  - **`enable-audit: false`** → status only (time / token / unaudited-round count), no audit; same `continue:false` stop path
  - **`enable-audit: true`** (the default once `.watcher/` exists) → normal `decision:"block"` flow that nudges Claude to invoke the `watcher` skill

  Don't mix the two paths: `decision:"block"` means "don't stop, keep going" — Claude sees the reason and CC starts another turn (exactly what the ON branch wants); `continue:false` means "stop" — Claude never sees the stopReason, but **you do**, as `Operation stopped by hook: …` in the terminal, and CC starts no further turn (what the two status-only branches want).
- Keeping the file present and flipping a field (instead of relying on a marker file's existence) is exactly what lets "wrong cwd → file not found" be told apart from "user turned it off"
- The `UserPromptSubmit` announce rules keep running either way — only the turn-end audit reminder is toggled
- Each project has its own file, so you can keep `watcher` chatty in important projects and quiet in throwaway sandboxes

You can also edit `.watcher/audit-state.json` by hand (`enable-audit`: true/false). Legacy `.stop-disabled` / `.skip-count` files are auto-migrated to it on the next turn.

## Customizing announce rules

The 4 rule segments live in `watcher/hooks/announce-intent.sh` — a Bash script that emits stdout, which Claude Code wraps in `<system-reminder>` on `UserPromptSubmit`.

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
