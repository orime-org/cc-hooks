---
name: task-panel-configure
description: 配置官方 Codex 的 WezTerm 任务面板。用于首次安装面板、重新配置或修复面板加载配置。
---

# 配置 Codex 任务面板

## 平台对照

本 skill 在 Claude Code 和 Codex 里都会用到。正文按 Claude Code 的说法写，在 Codex 里按下表换成对应的东西：

| 正文里的写法 | 在 Codex 里 |
|---|---|
| Claude Code、CC | Codex |
| Read、Edit、Write、Bash 工具 | 用 `exec_command` 读文件和跑命令，用 `apply_patch` 改文件 |
| WebSearch、WebFetch | 联网搜索 |
| workflow | 用 `spawn_agent` 派子代理；判对抗是否跑成，看每个子代理的 `wait` 结果都是 completed、没有报错（对应 `agents_error`、`agents_done`、`agent_count`） |
| Monitor | 用 `gh pr checks <N> --watch` 盯 CI，用 `gh pr view <N> --json state,mergeStateStatus,reviewDecision` 看合并和 review |
| `/watcher:xxx`、`/watcher` | `$watcher:xxx`、`$watcher:watcher` |
| `CLAUDE.md` | `AGENTS.md` |
| `${CLAUDE_SKILL_DIR}` | 本 SKILL.md 所在目录的绝对路径 |
| Skill 工具 | 读对应 skill 的 SKILL.md |

## 配置范围

将当前本机的官方 Codex 与 WezTerm 接入任务面板。用户调用本技能后，执行插件已有的配置脚本，保留现有设置和运行中的终端任务。面板配置保存在本机；后续会话自动显示各自的任务。

## 执行配置

以本 SKILL.md 的实际所在目录解析 `../../hooks/task_panel_setup.py`，取得脚本的完整绝对路径。复用这份脚本完成配置。插件安装位置随机器和版本变化，命令使用本机解析出的路径。

先核对 Python 3.11+（含 curses）与 WezTerm 是否可用，以及当前 Codex 配置目录。系统进程读取在 macOS 使用 `ps`、`lsof` 与系统参数接口，在 Linux 使用 `/proc`；缺少对应系统入口时报告具体缺项。脚本默认采用 `CODEX_HOME`，未设置时采用用户的 `.codex` 目录；默认插件数据目录为其中的 `plugins/data/watcher-orime`。

任务面板支持在项目当前目录执行 `codex` 或 `codex resume`。用户先进入目标项目目录，再启动或恢复会话；配置完成后的验证沿用这个入口。

核对当前 WezTerm 的配置位置。设置了 `XDG_CONFIG_HOME` 时先检查 `$XDG_CONFIG_HOME/wezterm/wezterm.lua`，未设置时先检查 `~/.config/wezterm/wezterm.lua`；该文件存在则采用，否则采用 `~/.wezterm.lua`。发现运行中的 WezTerm 使用 `--config-file` 或明确设置了其他配置路径时，将该完整路径传给脚本的 `--wezterm-config`。实际路径仍不明确时询问当前用户。

用 `python3` 执行脚本并带上 `--check`，检查目标路径与 WezTerm 配置入口；成功后使用相同参数去掉 `--check` 执行配置。脚本会备份已有 WezTerm 配置，安装面板运行文件并加入加载区段。Codex 配置保持用户当前内容，标题和状态栏由用户原生设置管理。自定义 `--codex-home`、`--data-dir` 时保持与实际插件安装环境一致。

核对输出的配置文件和运行文件已写入，同时检查计划工具可用性与 watcher hooks 的信任状态。hooks 需要审核时，说明 Codex 原生 `/hooks` 授权入口，由用户完成信任；已有授权按当前状态继续。配置失败时报告具体错误与下一步，保留可恢复的备份。

## 让配置生效

WezTerm 使用原生“重新加载配置”操作，保留现有窗口、pane 和运行中的任务。先核对本机该操作的快捷键，默认是 `Ctrl+Shift+R`，macOS 也默认支持 `Cmd+R`。环境已有可用且获授权的重载方式时可直接使用；否则告诉用户在方便时按该快捷键。

WezTerm 重载后，当前运行的 Codex 可以出现等待面板。下一次提交消息触发原生 hook 后，面板加载当前会话已有任务，并跟随 `update_plan` 更新。后续在 WezTerm 中运行 `codex` 或 `codex resume`，面板自动创建；恢复会话的任务在首次原生事件到达后加载。

## 汇报结果

区分“配置已写入”“WezTerm 已重载”“面板已实际显示”“当前会话任务已加载”。仅在真实窗口观察到对应结果后报告。说明当前还需完成的授权、重载或首次消息触发。

给用户的配置文件、备份和脚本路径使用完整绝对路径。说明后续正常使用 Codex 即可自动显示面板；本技能可用于再次检查和配置。
