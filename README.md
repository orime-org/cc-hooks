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
| `Stop` hook (`suggest-watcher.sh`) | Every Claude turn ends | Blocks the turn and reminds Claude to invoke `watcher` skill; skips entirely while a background `subagent`/`workflow` task is still running/pending (reads `background_tasks`) or the turn had no final text, so the audit lands on the wake-up turn instead; each real turn-end also reports the current time + context token usage (K + %) and warns to run `/compact` past 85%. `/watcher:watcher-off` turns off the audit for the project **but still shows the time + token + rounds-since-last-audit status each turn** (audit-off ≠ status-off); `/watcher:watcher-on` re-enables the audit |
| `watcher` skill (audit only) | Triggered by Stop hook or manually via `/watcher:watcher` | Runs the 5-step audit + 7-section summary. **Never creates configs** — that belongs to the command below |
| `/watcher:watcher-configure` slash command | Run manually | **The one way to configure**: create or revise this project's `.watcher/` trio (interviews you → shows drafts for confirmation → only then writes) |
| `/watcher:watcher-off` / `/watcher:watcher-on` slash commands | Run manually | Toggle the per-turn automatic `watcher` audit for the current project (flips `enable-audit` in `.watcher/audit-state.json`) |

### The 13 rule segments injected per turn

`watcher` enforces 13 segments (Chinese-first, plain language):

1. Current date (UTC, second precision)
2. Segment structure — Markdown headings, numbering whitelist, no fake tables
3. 4-step intent restate — rephrase → analyze root cause → propose thorough solution → state plan
4. Output format — Markdown tables; never fake one with bullets / `field: value` lists / `────` rules / A. B. C. lists, vertical flow diagrams (any 2+ similar items — reports / explanations / self-checks too, no scenario exception)
5. Conversation style — plain language, Chinese by default, **written as ordinary Chinese sentences** (complete clauses punctuated with commas, periods and semicolons; em dashes are not commas, parentheses hold asides rather than the main clause, arrows and slashes are not punctuation), no telegram-style words; you're a teammate (say "our" product/project/company, not "your")
6. Decision tables — **state the exact question on the line above the table** ("what we're deciding: xxx"; the bar is that I can decide from that line plus the table alone, without scrolling back); 3-column Markdown (option / what / why-incl-consequence), recommendation tagged inline as `A（推荐）` (no separate column), no `AskUserQuestion` tool; **options must not be invented**: when mature outside practice exists to look at (product behaviour / interaction / architecture / protocol / format / security), WebSearch 2-3 industrial-grade products or mainstream OSS first, then draft the options; **every option must trace back to a basis** — outside practice (with the source) / an existing fact in our project / an explicit "this is my guess, found no precedent" — claiming "the industry does X" without actually checking is the segment-12 bluffing capital offence; purely internal trade-offs skip the outside research but still state their basis, and when unsure which kind it is, treat it as "outside practice exists" and go check
7. Root-cause-first, evidence-backed — survey the whole picture before tunneling into one direction; check local first, then search the web (WebSearch); don't flail, after 2 failed attempts stop and search for an existing solution; when a conclusion leans on an established rule / approved decision / prior evidence, cite the rule's text + source before concluding (re-check the source, don't recall from memory); surface unplanned problems to me first (no self-patching) — blocking ones stop & diagnose, side ones go to the todo list for me to decide (this todo/confirm flow is for runnable code only; pure doc/note/memory mismatches are zero-cost — fix on sight per segment 12.1)
8. Thorough-only, zero discount — every solution must be thorough, absolutely no discount allowed
9. Strict coding-task rules — spec gate (confirm docs / TDD + smoke / E2E + fork-clarification specs exist before coding, gate one, don't skip). **Start by writing the acceptance checklist**: which items this round covers and what user need or experience each one has to satisfy, one tickable line each. Derive it from the authoritative spec/mock where one exists, otherwise write it from what I asked for and get it confirmed. This thread runs end to end, every step must trace back to a checklist item, and nothing may be built from memory or drift from it: 9.1 write the checklist as the binding source → 9.2 MUST encode its key constraints as runnable tests (visual regression / contract / schema — mandatory, not optional) and keep the checklist in view while implementing → 9.3 before submitting, check the build against the checklist item by item; anything unmatched or undone counts as incomplete and blocks the PR (smoke covers "does it run", this covers "does it match the spec") → approved deviations fold back into the checklist the moment they are approved, and 9.5 brings the spec along. **Logic forks are always brought to me** (9.1 asks them as a table before the doc is written; 9.2 stops and asks when a fork the doc never covered surfaces mid-implementation — never decide alone, never assume on my behalf; only ask when there are multiple options AND getting it wrong is costly, otherwise use a sensible default and flag it). Then a fixed order: **9.1 docs-first** (reuse-first gate: before writing your own code, search for a battle-tested OSS library — esp. frontend — and adopt it rather than reinventing the wheel; any adopted library MUST be free for commercial use — permissive license only (MIT / Apache-2.0 / BSD / ISC), no viral copyleft (GPL / AGPL), no non-commercial (CC-BY-NC), no source-available-restricted (BSL / SSPL / Elastic / Redis RSAL); read the actual LICENSE / package.json license field, ask me when unsure (incl. MPL / LGPL); then write the doc; for UI work the design must also cover the visual side — layout / states / motion / consistency — and new-or-heavily-reworked visuals get a viewable demo for sign-off before implementation, while changes to already-runnable UI are dogfooded in the real app; after the doc, before code, run the Gate 1 design adversarial — see 9.4) → **9.2 red then green** (red: write tests from the doc and run them to confirm they fail as expected — E2E is not forced red here, deferred to 9.3; green: minimal implementation to pass, then refactor. Three things hold in this step — modularize / extract-shared, stop and ask on forks the doc never covered, surface pre-existing bad code and confirm the fix with me first) → **9.3 full verify** (smoke / E2E; UI/app smoke MUST really launch the app + drive a real browser over http via MCP tools, not the bash sandbox, no mock-faking; must all pass before a code PR) → **9.4 adversarial verify** — ten single-purpose rules: **how to attack** — an independent adversary, never self-review; **a verify/judge layer IS nested inside the run** (once a hole is found, a separate layer inside that same run refutes it item by item, and only what survives comes back); Gate 1 runs in the design phase before code, then a docs-only PR; Gate 2 when a code PR is due and only after smoke/dogfood really passes; pure styling / copy / config-value / comment changes with no attack surface waive both gates; each adversary caps its own finding pass at five items and hands back however many of its own survive refutation; attack → fix → re-attack until a round turns up no behavioural holes and the round-count tier is met, cap 3 for ordinary changes and 5 for high-risk ones, every confirmed behavioural hole gets frozen into a permanent test; **how holes are classified** — **behavioural** = crashes / wrong logic / root cause untreated / names contradicting code / duplicated logic / missing error paths / giant functions / same thing written differently in many places, criterion = enumerable and freezable into a check; **descriptive** = wording / comments / naming / style where the semantics are fine and it's purely taste — never re-enters the loop and never blocks convergence, still goes on tables 1 and 2 for me to rule on; **what Gate 1 attacks / what Gate 2 attacks** (four lenses: requirement-delivery, checking the 9.1 checklist item by item with no per-adversary cap for whether what I asked for is actually there / does it crash / code quality read-only / root-cause-vs-band-aid); **the round table comes first** — cumulative rounds 1–N, one row per round, three columns (round | behavioural holes | descriptive holes), counts only, never restate the holes; **how to verify** — **everything that comes back starts as not-established; the burden of proof is on me**, established only if I can prove it. First confirm the attack actually ran (no trace means not verified, send it back), then each item clears two layers — **does it reproduce** (run it, or re-read file:line) and **does it count** (is it in scope for this PR/task? does it clash with our UX stance? does it match what the doc says this task is?) — one miss means not established; no repro but a stateable trigger = pending, listed for me to decide; **table 1 before any fix, nothing moves until I approve** (a hard stop: one row per item, none dropped or merged, not-established and pending listed too, exactly four columns — hole: id + adversary's own words | established-or-not and on what evidence | root cause | thorough fix and whether it's fixed this round); **how to fix** — work from the fixes approved in table 1, cluster by root cause or pattern, one pass per group, factor out shared code, never patch item by item; **fixing a hole also follows segment 7 root-cause and segment 8 thorough-solution**; anything reported as "fixed" is verified per item too; **table 2 after fixing** — one row per group, four columns (group | the holes in it: table-1 ids + what happened to each | what changed | how it was verified), with pending-nonblocking items explained in their own paragraph; **what counts as passing** — **convergence tracks behavioural holes only** (this round turns up zero behavioural holes AND everything ruled to-fix actually fixed AND the round-count tier is met; leftover descriptive holes do not block it); hitting the round cap with behavioural holes left, judging a fix a band-aid, or anything left unfixed all mean stop and report to me, and a blocker gets reported the moment it surfaces → **9.5 wrap up** (sweep all affected docs once verification passes and the code is stable, while any single mismatch you stumble on is fixed on the spot per 12.1; open the PR only when docs / code / tests are all in place and smoke / E2E fully pass — commit + PR description all in English, Conventional Commits format, no attribution trailer)
10. PR after-care (any PR) — watch CI, post the full PR url after creating it, clean up branches after merge
11. Delegation (workflow) — before starting, ask "can this be split to run in parallel / orchestrated"; judge only by more-efficient + higher-quality. Two tiers: 11.1 do it yourself (sequential / trivial), 11.2 run a workflow — everything that gets delegated goes through one (parallel multi-folder work, big searches, multi-angle reviews, fan-out that needs collect/verify/synthesize, loops, large-scale jobs); decide on your own when it is warranted, no opt-in needed; never spawn just to spawn. Closing rule: what a workflow hands back is INPUT, not a verdict — never rubber-stamp "clean / 0 holes / all green"; you own the final call. Confirm it actually ran (process trace, not an empty / cached / crashed false-green), then **split by type** — adversarial (the holes and "fixed" claims coming back from Gate 1 / Gate 2) is adjudicated item by item on evidence, never sampled (see 9.4); every other delegation (search / research / retrieval) gets the key conclusions spot-checked, risk-scaled (not a full re-run). Hard anti-regress: once it is handed back, that check is yours to do — never delegate it out again.
12. Honesty + verify capstone — faking it is the only red line (false confidence, workaround-as-fix, claiming unverified, too lazy to search); "I don't know" isn't the end — go check (per segment 7: local first, then remote, then experiment), then conclude; found an error → fix it on the spot (new or old mistake, don't defer), split by fix cost: 12.1 doc/note/memory mismatches (zero-cost) fixed on sight with no todo/no asking, 12.2 pre-existing code (risky) goes through report+confirm first
13. What it comes down to — these rules are what lets us do the job well; finding the real root cause and shipping thorough solutions are the two that matter most

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
