# Orime：Claude Code 与 Codex 插件

[English](./README.md)

Orime 是本仓库的插件市场，当前提供 `watcher` 插件。它提供每轮协作规范、Git 提交检查、项目知识审计，以及 Codex 在 WezTerm 中的会话任务面板。

| 功能 | Codex | Claude Code |
|---|---|---|
| 每次提交消息注入协作规范 | 原生 UserPromptSubmit hook | UserPromptSubmit hook |
| 检查分支、提交标题和署名 | PreToolUse hook | PreToolUse hook |
| 项目审计及自动审计开关 | `$watcher:…` 技能 | `/watcher:…` 技能 |
| WezTerm 下方任务面板 | 配置后，后续会话自动创建 | 使用客户端任务显示 |

## 1. 在 Codex 中安装

### 1.1 准备环境

使用支持插件和原生 hooks 的官方 Codex CLI。协作规范和提交检查需要 Bash、Git、`jq`；任务面板另需 Python 3.11+（含 curses）和 WezTerm。本地进程读取已适配 macOS 与 Linux。

在终端检查：

```bash
codex plugin --help
git --version
jq --version
python3 -c 'import curses, sys; assert sys.version_info >= (3, 11); print(sys.version)'
```

### 1.2 安装并授权

在终端执行：

```bash
codex plugin marketplace add orime-org/cc-hooks --ref main --json
codex plugin add watcher@orime --json
```

本地源码安装见第 6 节。进入你的项目目录，执行 `codex`，在新进入的 Codex 会话中打开：

```text
/hooks
```

检查并信任 watcher 的 hook。插件安装和 hook 信任分别由 Codex 管理，见 [OpenAI 官方插件文档](https://developers.openai.com/plugins/build/plugins#bundled-hooks)。更新后若 hook 定义需要重新审核，再通过 `/hooks` 完成。

在终端检查安装结果：

```bash
codex plugin list --marketplace orime --json
```

## 2. 配置 Codex 的 WezTerm 任务面板

### 2.1 首次配置

在 WezTerm 中运行的 Codex 会话里，调用：

```text
$watcher:task-panel-configure
```

技能检查环境、安装本机面板运行文件、配置 WezTerm 加载入口。修改已有 WezTerm 配置时保存备份并报告完整路径。Codex 标题与状态栏使用用户自己的设置。

按技能提示让 WezTerm 重新加载配置。默认快捷键为 `Ctrl+Shift+R`，macOS 也支持 `Cmd+R`；自定义按键以本机配置为准。重载配置会保留现有终端窗口和运行任务。

面板依赖计划工具。如果配置技能发现该工具被关闭，在 Codex 用户配置中设置或修改现有项：

```toml
[tools.update_plan]
enabled = true
```

用户配置默认位于 `~/.codex/config.toml`；设置了 `CODEX_HOME` 时使用该目录中的 `config.toml`。

### 2.2 确认生效

日常使用先进入项目目录，再执行 `codex` 或 `codex resume`。配置和授权完成后，WezTerm 自动创建下方任务面板。

启动时可能先显示“等待当前会话信息”。在该会话提交一条消息，首次原生 hook 事件会关联会话并加载已有任务。可用这条消息检查计划同步：

```text
请调用 update_plan 创建两条演示任务，并将第一条标记为已完成。
```

应看到两条任务和 `1/2`。恢复会话时，首次事件会加载该会话已保存的计划。任务内容跟随当前会话的 `update_plan`。

### 2.3 面板操作

先点击下方任务面板取得焦点，再使用按键。

| 操作或状态 | 结果 |
|---|---|
| 自动高度 | 三至七行，最多显示四条任务；更多任务显示剩余数量 |
| 上下方向键、PgUp/PgDn | 滚动查看完整列表 |
| 按 m，再拖动分隔线 | 手动高度，后续计划更新保留该高度 |
| 按 a | 恢复按任务数量调整高度 |
| 按 q 或关闭底部窗格 | 本次 Codex 运行期间保持关闭 |
| q 关闭后重新打开 | 在原项目目录退出并重新运行 `codex resume`，选择原会话 |

面板每秒读取本地缓存；首次显示、所需高度、窗口尺寸或 m/a 模式变化时处理 WezTerm 高度。失败后按递增间隔重试，最长间隔三十秒。

## 3. 配置项目审计与提交检查

任务面板的配置保存在本机。项目审计与提交检查使用各项目根目录的 `.watcher/`。

| 目的 | Codex 中输入 | Claude Code 中输入 |
|---|---|---|
| 创建或修改项目审计配置 | `$watcher:watcher-configure` | `/watcher:watcher-configure` |
| 手动审计一次 | `$watcher:watcher` | `/watcher:watcher` |
| 关闭每轮自动审计 | `$watcher:watcher-off` | `/watcher:watcher-off` |
| 开启每轮自动审计 | `$watcher:watcher-on` | `/watcher:watcher-on` |
| 查看分步工作方法 | `$watcher:playbook` | `/watcher:playbook` |
| 手动调用视觉审查 | `$watcher:visual-adversary` | `/watcher:visual-adversary` |

配置技能展示草稿，用户确认后写入：

| 文件 | 内容 |
|---|---|
| `.watcher/project-summary.md` | 项目用途、用户和目标 |
| `.watcher/doc-inventory.md` | 应与代码保持同步的文档 |
| `.watcher/watchlist.md` | 项目关注点和规则 |

已配置项目默认开启收尾自动审计，状态保存在该项目的 `.watcher/audit-state.json`。关闭自动审计后，手动调用仍执行一次审计并保持开关关闭。未配置项目可手动审计，自动审计由配置状态控制。

提交检查定位实际目标仓库；根目录有 `.watcher/` 时，检查主分支提交、`type: summary` 标题和 `Co-Authored-By`。支持按命令中的 `git -C`、`cd` 与工具目录上下文定位仓库；解析采用启发式规则，目录仍不明确时应询问用户。完整规则和边界见 [Codex 使用说明](./docs/codex-usage.zh-CN.md#提交检查及需要问用户的情况)及[提交检查设计](./docs/bash-gate-design.md)。

PR 由用户检查并亲自合并。AI 可以准备代码和 PR、跟踪 CI 与 review；禁止 AI 合并、启用自动合并或代为调用合并 API。

## 4. 更新 Codex 插件和已有面板

### 4.1 从 GitHub 市场更新

在终端执行：

```bash
codex plugin marketplace upgrade orime --json
codex plugin add watcher@orime --json
```

### 4.2 从本地源码更新

先查看登记的市场来源：

```bash
codex plugin marketplace list --json
```

找到 `orime` 的本地 `root`，更新该目录。下面对应第 6 节的示例安装位置，已有安装使用其实际完整路径：

```bash
git -C "$HOME/src/cc-hooks" pull --ff-only origin main
codex plugin add watcher@orime --json
```

### 4.3 让更新生效

更新安装缓存后，新进入的 Codex 会话可以发现新增技能。在 `/hooks` 完成需要的授权。

涉及任务面板更新时，调用 `$watcher:task-panel-configure` 刷新本机运行文件，并按提示重载 WezTerm。已经运行的面板在重新创建后加载新 Python 代码：等该 Codex 的工作结束，退出它，在原项目目录执行 `codex resume`，选择原会话并提交一条消息。每个正在运行的旧面板分别按此处理。

后续正常启动和恢复会话时，面板自动创建；配置技能用于首次配置、重新配置和刷新运行文件。

## 5. 在 Claude Code 中安装和更新

在 Claude Code 会话中执行：

```text
/plugin marketplace add orime-org/cc-hooks
/plugin install watcher@orime
```

按客户端显示的安装和信任提示完成操作。安装结果要求重载时执行：

```text
/reload-plugins
```

更新时，在终端执行：

```bash
claude plugin marketplace update orime
claude plugin update watcher@orime
```

随后按客户端提示重载插件或重新进入会话。入口见[官方安装说明](https://code.claude.com/docs/en/discover-plugins)和[命令说明](https://code.claude.com/docs/en/commands)。项目配置与审计命令见第 3 节。

## 6. 常见问题与本地源码

### 6.1 排查入口

| 现象 | 检查与处理 |
|---|---|
| `$` 列表找不到新增技能 | 核对 `codex plugin list --marketplace orime --json`；刷新安装缓存后重新进入 Codex |
| 安装了插件，hook 没执行 | 在该 Codex 会话的 `/hooks` 检查 watcher 是否已启用并信任 |
| WezTerm 没出现面板 | 调用配置技能，检查 Python/curses、WezTerm CLI、实际配置文件路径及重载状态 |
| 显示“等待当前会话信息” | 提交一条消息，检查首次原生 hook 的执行结果 |
| 显示“等待首次计划更新” | 请当前 Agent 调用 `update_plan`；任务面板显示其计划 |
| 按键没有反应 | 先点击下方任务面板取得焦点 |
| q 关闭后没有自动回来 | 当前 Codex 运行期间保持关闭；恢复原会话会创建新面板 |
| 更新后仍显示旧连接错误或持续 Broken pipe | 确认源码、安装缓存和面板运行文件均已更新，再重新创建对应旧面板 |
| 使用其他终端 | 协作规范、提交检查及审计技能按各自配置运行；任务面板在 WezTerm 中创建 |

### 6.2 本地源码安装

在终端执行，示例将源码放入自己的主目录：

```bash
mkdir -p "$HOME/src"
git clone https://github.com/orime-org/cc-hooks.git "$HOME/src/cc-hooks"
codex plugin marketplace add "$HOME/src/cc-hooks" --json
codex plugin add watcher@orime --json
```

然后继续第 1 节的 hook 授权和第 2 节的面板配置。修改源码后，按第 4 节更新安装缓存和运行文件。

| 名称或目录 | 用途 |
|---|---|
| `cc-hooks` | GitHub 仓库名 |
| `orime` | 市场名，安装选择器为 `watcher@orime` |
| `watcher/` | 插件源码；含两种宿主的清单、hooks 和技能 |
| `.watcher/` | 使用插件的项目配置 |
| `watcher/hooks/announce-intent.sh` | 每轮协作规范的源文件 |
| `watcher/hooks/codex-hooks.json` | Codex 原生事件入口 |
| `watcher/skills/` | 面板配置、审计、开关、分步方法及视觉审查技能 |

## 7. 开发与更多说明

[Codex 详细说明](./docs/codex-usage.zh-CN.md)包含配置位置、会话关联与提交检查边界。[任务面板验证记录](./docs/codex-panel-refresh-validation.md)记录十二个面板的空闲查询与真实操作验证。

开发时按改动运行对应检查。完整 CI 命令在 [smoke 工作流](./.github/workflows/smoke.yml)，包含协作规范体积、两个宿主的 hooks、提交检查、任务存储、会话绑定、面板显示和插件清单检查。

```bash
bash tests/check-size.sh
python3 tests/smoke-manifests.py
```

视觉审查脚本另按其技能说明手动验证。

许可证为 [MIT](./LICENSE)。版本记录见 [CHANGELOG](./CHANGELOG.md)。
