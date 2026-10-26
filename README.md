# Orime: Claude Code and Codex plugins

[简体中文](./README.zh-CN.md)

Orime is the plugin marketplace in this repository. Its `watcher` plugin provides collaboration rules, Git commit checks, project knowledge audits, and concise task summaries.

| Feature | Codex | Claude Code |
|---|---|---|
| Inject collaboration rules on each prompt | UserPromptSubmit hook | UserPromptSubmit hook |
| Check branches, commit titles, and attribution | PreToolUse hook | PreToolUse hook |
| Configure and run project audits | `$watcher:…` skills | `/watcher:…` skills |
| Summarize concrete work | Three short fields | Three short fields |

## 1. Install in Codex

Use the official Codex CLI with plugin and hook support. Bash, Git, `jq`, and Python 3 are required.

```bash
codex plugin --help
git --version
jq --version
python3 --version
```

Register the marketplace and install the plugin:

```bash
codex plugin marketplace add orime-org/cc-hooks --ref main --json
codex plugin add watcher@orime --json
codex plugin list --marketplace orime --json
```

Enter your project directory, start `codex`, and open `/hooks`. Review and trust the watcher hooks. Subsequent prompts receive the collaboration rules. Installation, updates, and hook approval are user operations.

## 2. Task summaries

When an agent advances concrete work such as design, implementation, review, documentation, or smoke testing, its final reply includes these fields:

| Field | Content limit |
|---|---:|
| 当前任务 — current task | 20 characters |
| 当前任务的阶段 — current stage | 20 characters |
| 工作纪律自评 — discipline self-assessment | 30 characters |

The combined content limit is 70 characters. Punctuation, digits, and English letters each count as one; field labels are excluded. The self-assessment describes what happened, including any deviation and the correct procedure. Ordinary questions and discussion receive direct answers. Existing collaboration rules govern the rest of the report.

The agent checks formatting before sending its reply. Stop continues to follow the project's audit setting and manual-audit rules.

Version `0.2.0` retires the Codex WezTerm task pane. Existing installations should follow the [removal guide](./docs/codex-usage.zh-CN.md#3-移除已有-wezterm-任务面板) before updating the plugin.

## 3. Configure project audits and commit checks

| Action | Codex | Claude Code |
|---|---|---|
| Create or update project configuration | `$watcher:watcher-configure` | `/watcher:watcher-configure` |
| Run one manual audit | `$watcher:watcher` | `/watcher:watcher` |
| Disable automatic audits | `$watcher:watcher-off` | `/watcher:watcher-off` |
| Enable automatic audits | `$watcher:watcher-on` | `/watcher:watcher-on` |
| Read step-specific working methods | `$watcher:playbook` | `/watcher:playbook` |
| Invoke visual review manually | `$watcher:visual-adversary` | `/watcher:visual-adversary` |

After user confirmation, the configuration skill writes the project's `.watcher/` configuration. Each project maintains its own audit rules and switch. An explicit manual audit runs once while preserving the automatic-audit setting.

Commit checks resolve the target repository from command directories and hook context. Repositories with `.watcher/` receive branch, title, and attribution checks. Resolution follows the existing heuristics; an agent that remains uncertain after normal investigation asks its current user. The [Codex guide](./docs/codex-usage.zh-CN.md#4-提交检查和审计) documents the boundaries.

The user checks and merges PRs. AI prepares changes and PRs, then follows CI and review.

## 4. Update the Codex plugin

For a GitHub marketplace installation:

```bash
codex plugin marketplace upgrade orime --json
codex plugin add watcher@orime --json
codex plugin list --marketplace orime --json
```

Load the updated plugin in a newly started or resumed Codex session, then review updated definitions in `/hooks`. To continue the original session, run `codex resume` from the original project directory and select that session. For local marketplaces, update the registered source directory as described in section 6, then refresh the installation.

## 5. Install and update in Claude Code

Run inside Claude Code:

```text
/plugin marketplace add orime-org/cc-hooks
/plugin install watcher@orime
```

Follow the client's plugin and hook approval prompts. Configure a project with `/watcher:watcher-configure`.

To update:

```text
/plugin marketplace update orime
/plugin update watcher@orime
/reload-plugins
```

## 6. Use a local checkout

Replace `/absolute/path/to/cc-hooks` with your actual absolute checkout path:

```bash
codex plugin marketplace add /absolute/path/to/cc-hooks --json
codex plugin add watcher@orime --json
```

Inspect the registered source before updating:

```bash
codex plugin marketplace list --json
git -C /absolute/path/to/cc-hooks pull --ff-only origin main
codex plugin add watcher@orime --json
```

A local marketplace reads its registered directory; a GitHub marketplace reads its downloaded snapshot. Update the source actually registered on your machine. Claude Code accepts `/plugin marketplace add /absolute/path/to/cc-hooks` for local sources.

## 7. Maintain and validate

[announce-intent.sh](./watcher/hooks/announce-intent.sh) is the collaboration-rule source. Both clients share the rules, commit guard, and Stop implementation. [codex-hooks.json](./watcher/hooks/codex-hooks.json) connects the Codex hooks.

| Directory | Contents |
|---|---|
| `watcher/hooks/` | Rules, commit guard, Stop, and platform hook configurations |
| `watcher/skills/` | Audits, configuration, switches, playbook, and visual review |
| `watcher/output-styles/` | Claude Code Chinese output style |
| `tests/` | Size checks and supported-feature smoke/parser tests |
| `docs/` | Usage, design, and validation records; retired pane materials have archive notices |

Run the checks in [.github/workflows/smoke.yml](./.github/workflows/smoke.yml) after changes. Quick checks:

```bash
bash tests/check-size.sh
python3 tests/smoke-announce.py
python3 tests/smoke-manifests.py
```

The project measures complete stdout against a 9800 UTF-16-unit gate, leaving room below Claude Code's 10000-character per-output cap. Execution failures fail the check. Changes to visual-review scripts also require `python3 tests/smoke-visual-adversary.py`.

[Changelog](./CHANGELOG.md) · [Codex guide, Chinese](./docs/codex-usage.zh-CN.md) · [MIT license](./LICENSE)
