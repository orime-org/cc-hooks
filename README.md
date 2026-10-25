# Orime: Claude Code and Codex plugins

[中文安装与使用说明](./README.zh-CN.md)

Orime is this repository's plugin marketplace. Its `watcher` plugin provides per-turn collaboration rules, Git commit checks, project knowledge audits, and a session task pane for Codex in WezTerm.

| Capability | Codex | Claude Code |
|---|---|---|
| Collaboration rules on each prompt | Native UserPromptSubmit hook | UserPromptSubmit hook |
| Branch, commit-title and attribution checks | PreToolUse hook | PreToolUse hook |
| Project audits and automatic-audit switch | `$watcher:…` skills | `/watcher:…` skills |
| Bottom task pane in WezTerm | Configure once; subsequent sessions attach automatically | Uses the client's task display |

## 1. Install in Codex

### 1.1 Prerequisites

Use the official Codex CLI with plugin and native hook support. Shared hooks require Bash, Git and `jq`. The task pane additionally needs WezTerm and Python 3.11+ with curses. Local process discovery supports macOS and Linux.

Run in your terminal:

```bash
codex plugin --help
git --version
jq --version
python3 -c 'import curses, sys; assert sys.version_info >= (3, 11); print(sys.version)'
```

### 1.2 Install and authorize

Run in your terminal:

```bash
codex plugin marketplace add orime-org/cc-hooks --ref main --json
codex plugin add watcher@orime --json
```

For a source checkout, use section 6. Enter your project directory and start `codex`. In that newly entered session, open:

```text
/hooks
```

Review and trust watcher's hooks. Codex manages plugin installation and hook trust separately; see the [official bundled-hook documentation](https://developers.openai.com/plugins/build/plugins#bundled-hooks). Revisit `/hooks` when updated definitions require review.

Check the installation from your terminal:

```bash
codex plugin list --marketplace orime --json
```

## 2. Configure the Codex task pane

### 2.1 First-time setup

In a Codex session running inside WezTerm, invoke:

```text
$watcher:task-panel-configure
```

The skill checks prerequisites, installs the local pane runtime and adds its WezTerm loader. Changes to an existing WezTerm configuration produce a backup and a report of the full paths. Codex titles and status lines follow your own settings.

Follow the skill's instructions to reload WezTerm configuration. Default shortcuts are `Ctrl+Shift+R`, and also `Cmd+R` on macOS; custom bindings take precedence. Configuration reload preserves open terminal windows and running tasks.

The pane requires the plan tool. If the skill finds it disabled, set or update this entry in your Codex user configuration:

```toml
[tools.update_plan]
enabled = true
```

The default user configuration is `~/.codex/config.toml`; with `CODEX_HOME` set, use `config.toml` inside that directory.

### 2.2 Verify the result

Start `codex` or `codex resume` from the project directory. After setup and authorization, WezTerm creates a bottom task pane automatically.

The pane can initially show “等待当前会话信息” (waiting for session information). Submit a message so the first native hook can attach the session and load its saved tasks. To check synchronization, ask:

```text
Call update_plan with two demonstration tasks and mark the first as completed.
```

Expect two tasks and `1/2`. A resumed session loads its saved plan after its first native event. Pane contents follow that session's `update_plan` calls.

### 2.3 Controls

Click the task pane to focus it before using keys.

| Action or state | Result |
|---|---|
| Automatic height | Three to seven rows; up to four tasks and a remaining-count indicator |
| Arrow keys, PgUp/PgDn | Scroll the complete task list |
| Press m, then drag the divider | Manual height persists across plan updates |
| Press a | Restore automatic content height |
| Press q or close the bottom pane | Keep it closed for this Codex process |
| Reopen after q | Exit Codex, run `codex resume` from the same project and select the session |

The pane reads its local cache each second. Initial display, required-height changes, terminal-size changes and m/a input trigger WezTerm height handling. Failures retry with increasing delays, capped at thirty seconds.

## 3. Configure project audits and commit checks

Pane setup is local to the machine. Project auditing and commit checks use `.watcher/` in each project's root.

| Purpose | In Codex | In Claude Code |
|---|---|---|
| Create or revise project configuration | `$watcher:watcher-configure` | `/watcher:watcher-configure` |
| Run one manual audit | `$watcher:watcher` | `/watcher:watcher` |
| Disable automatic turn-end audits | `$watcher:watcher-off` | `/watcher:watcher-off` |
| Enable automatic turn-end audits | `$watcher:watcher-on` | `/watcher:watcher-on` |
| Consult step-specific work methods | `$watcher:playbook` | `/watcher:playbook` |
| Invoke a visual review manually | `$watcher:visual-adversary` | `/watcher:visual-adversary` |

The configuration skill shows drafts for approval, then writes:

| File | Contents |
|---|---|
| `.watcher/project-summary.md` | Project purpose, users and goals |
| `.watcher/doc-inventory.md` | Documents that should stay synchronized with code |
| `.watcher/watchlist.md` | Project-specific concerns and rules |

Configured projects default to automatic turn-end auditing; the switch lives in that project's `.watcher/audit-state.json`. With automatic auditing off, a manual invocation runs one audit and leaves the switch off. Unconfigured projects can run manual audits; automatic audits follow configuration state.

The command gate identifies the target repository and, when its root contains `.watcher/`, checks main-branch commits, `type: summary` titles and `Co-Authored-By`. It uses `git -C`, preceding `cd` and tool working-directory context. Parsing is heuristic; agents should ask their user when the target remains unclear. See the [Codex guide](./docs/codex-usage.zh-CN.md) and [gate design](./docs/bash-gate-design.md) for rules and boundaries.

The user checks and personally merges PRs. AI may prepare changes and PRs and follow CI/review. AI is prohibited from merging, enabling auto-merge or calling a merge API on the user's behalf.

## 4. Update Codex and existing panes

### 4.1 Git-backed marketplace

Run in your terminal:

```bash
codex plugin marketplace upgrade orime --json
codex plugin add watcher@orime --json
```

### 4.2 Local checkout

Inspect the registered source:

```bash
codex plugin marketplace list --json
```

Find the local `root` for `orime` and update that checkout. These commands use the example location in section 6; substitute your installation's full path:

```bash
git -C "$HOME/src/cc-hooks" pull --ff-only origin main
codex plugin add watcher@orime --json
```

### 4.3 Apply the update

After refreshing the installation cache, newly entered Codex sessions can discover added skills. Review hooks through `/hooks` as required.

For pane updates, invoke `$watcher:task-panel-configure` to refresh runtime files, then follow its WezTerm reload instructions. Already running panes load new Python code when recreated: let that Codex finish its work, exit it, run `codex resume` from the original project directory, select the session and submit a message. Apply this to each existing pane you want to update.

Subsequent starts and resumes create panes automatically. The setup skill handles first-time configuration, reconfiguration and runtime refreshes.

## 5. Install and update in Claude Code

In a Claude Code session:

```text
/plugin marketplace add orime-org/cc-hooks
/plugin install watcher@orime
```

Complete the client's installation and trust prompts. When its installation summary requests a reload, run:

```text
/reload-plugins
```

To update, run in your terminal:

```bash
claude plugin marketplace update orime
claude plugin update watcher@orime
```

Follow the client prompt to reload plugins or reenter the session. See the official [installation guide](https://code.claude.com/docs/en/discover-plugins) and [command reference](https://code.claude.com/docs/en/commands). Project configuration and audits use section 3.

## 6. Troubleshooting and local source

### 6.1 Troubleshooting

| Symptom | Check or action |
|---|---|
| Added skill is missing from `$` | Check `codex plugin list --marketplace orime --json`, refresh installation and reenter Codex |
| Installed plugin hooks do not run | Check enabled/trusted watcher definitions in that session's `/hooks` |
| WezTerm has no task pane | Run the setup skill; check Python/curses, WezTerm CLI, the actual config path and reload state |
| Waiting for session information | Submit a message and inspect the first native hook result |
| Waiting for the first plan update | Ask the current agent to call `update_plan` |
| Keys have no effect | Click the task pane first |
| A pane stays closed after q | Resume the session in a new Codex process to recreate it |
| Old connection warning or continuous Broken pipe after updating | Check source, installed plugin and pane runtime updates, then recreate the affected old pane |
| Using another terminal | Shared rules, command checks and audit skills follow their configuration; the task pane is created in WezTerm |

### 6.2 Install from a local checkout

Run in your terminal; this example stores the source under your home directory:

```bash
mkdir -p "$HOME/src"
git clone https://github.com/orime-org/cc-hooks.git "$HOME/src/cc-hooks"
codex plugin marketplace add "$HOME/src/cc-hooks" --json
codex plugin add watcher@orime --json
```

Continue with authorization in section 1 and pane setup in section 2. After editing the source, refresh installation and runtime files as described in section 4.

| Name or path | Meaning |
|---|---|
| `cc-hooks` | GitHub repository |
| `orime` | Marketplace; install selector is `watcher@orime` |
| `watcher/` | Plugin source, including both host manifests, hooks and skills |
| `.watcher/` | Configuration in a project using the plugin |
| `watcher/hooks/announce-intent.sh` | Source of the per-turn collaboration rules |
| `watcher/hooks/codex-hooks.json` | Native Codex hook entrypoints |
| `watcher/skills/` | Pane setup, auditing, switches, work methods and visual review |

## 7. Development and further reading

The [detailed Codex guide](./docs/codex-usage.zh-CN.md) covers paths, session association and commit-check boundaries. [Pane validation](./docs/codex-panel-refresh-validation.md) records twelve-pane idle-traffic and control checks.

Run the checks relevant to your changes. The [smoke workflow](./.github/workflows/smoke.yml) contains the full CI commands for rule size, both hosts' hooks, commit checks, task storage, session binding, pane display and manifests.

```bash
bash tests/check-size.sh
python3 tests/smoke-manifests.py
```

Validate visual-review scripts manually as their skill describes.

Licensed under [MIT](./LICENSE). See [CHANGELOG](./CHANGELOG.md) for version history.
