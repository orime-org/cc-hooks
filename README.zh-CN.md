# Orime：Claude Code 与 Codex 插件

[English](./README.md)

Orime 是本仓库的插件市场，当前提供 `watcher` 插件。它提供每轮协作规范、Git 提交检查、项目知识审计和简短任务收尾。

| 功能 | Codex | Claude Code |
|---|---|---|
| 每次提交消息注入协作规范 | UserPromptSubmit hook | UserPromptSubmit hook |
| 检查分支、提交标题和署名 | PreToolUse hook | PreToolUse hook |
| 项目审计及开关 | `$watcher:…` 技能 | `/watcher:…` 技能 |
| 具体工作收尾 | 三项简短信息 | 三项简短信息 |

## 1. 在 Codex 中安装

使用支持插件和 hooks 的官方 Codex CLI。需要 Bash、Git、`jq` 和 Python 3.11+。先在终端检查：

```bash
codex plugin --help
git --version
jq --version
python3 --version
```

在终端注册市场并安装插件：

```bash
codex plugin marketplace add orime-org/cc-hooks --ref main --json
codex plugin add watcher@orime --json
codex plugin list --marketplace orime --json
```

进入项目目录并执行 `codex`，在会话中打开 `/hooks`，检查并信任 watcher 的 hook。安装和授权完成后，后续消息会按规范处理。安装、更新及 hook 授权由用户执行。

## 2. 任务收尾

Agent 实际推进设计、实现、审查、文档同步、smoke 等工作时，收尾补充以下三项。

| 项目 | 正文上限 |
|---|---:|
| 当前任务 | 20 字 |
| 当前任务的阶段 | 20 字 |
| 工作纪律自评 | 30 字 |

三项正文合计最多 70 字，标点、数字和英文字母各计 1 字，字段名不计。自评按本轮事实说明遵循情况；有偏离时写具体偏离及正确做法。普通问答和讨论直接回答，其余汇报按既有规范执行。

格式由 Agent 在发送前自查。Stop 沿用项目的自动审计开关和手动审计约定。

`0.2.0` 起任务面板已退役。此前安装过 WezTerm 面板的用户，先按[旧面板移除步骤](./docs/codex-usage.zh-CN.md#3-移除已有-wezterm-任务面板)移除终端加载区段并关闭面板，再更新插件。

## 3. 配置项目审计和提交检查

在需要审计和提交检查的项目中调用配置技能。

| 目的 | Codex 中输入 | Claude Code 中输入 |
|---|---|---|
| 创建或修改项目配置 | `$watcher:watcher-configure` | `/watcher:watcher-configure` |
| 手动审计一次 | `$watcher:watcher` | `/watcher:watcher` |
| 关闭自动审计 | `$watcher:watcher-off` | `/watcher:watcher-off` |
| 开启自动审计 | `$watcher:watcher-on` | `/watcher:watcher-on` |
| 查看分步工作方法 | `$watcher:playbook` | `/watcher:playbook` |
| 手动调用视觉审查 | `$watcher:visual-adversary` | `/watcher:visual-adversary` |

配置技能经用户确认后写入项目根目录的 `.watcher/` 配置。每个项目独立维护审计规则和开关。自动审计关闭后，显式调用审计技能仍执行一次，自动开关保持关闭。

提交检查根据命令目录和 hook 上下文定位目标仓库。目标仓库根目录有 `.watcher/` 时，检查主分支提交、提交标题及署名。目录解析沿用启发式规则；Agent 正常查证后仍无法确定时，询问当前用户并按答复处理。详细边界见 [Codex 使用指南](./docs/codex-usage.zh-CN.md#4-提交检查和审计)。

PR 必须由用户检查并亲自合并。AI 负责准备代码、提交和 PR，并跟踪 CI/review。

## 4. 更新 Codex 插件

GitHub 市场安装在终端执行：

```bash
codex plugin marketplace upgrade orime --json
codex plugin add watcher@orime --json
codex plugin list --marketplace orime --json
```

在新启动或恢复的 Codex 会话中加载更新后的插件，通过 `/hooks` 检查并信任更新后的定义。需要继续原工作时，在原项目目录执行：

```bash
codex resume
```

选择原会话。本地市场先按第 6 节更新实际源码目录，再刷新插件安装。

## 5. 在 Claude Code 中安装和更新

在 Claude Code 内执行：

```text
/plugin marketplace add orime-org/cc-hooks
/plugin install watcher@orime
```

按客户端提示检查插件和 hook 授权。项目配置使用 `/watcher:watcher-configure`。

更新时执行：

```text
/plugin marketplace update orime
/plugin update watcher@orime
/reload-plugins
```

## 6. 使用本地源码

将示例中的 `/absolute/path/to/cc-hooks` 替换为本机实际绝对路径：

```bash
codex plugin marketplace add /absolute/path/to/cc-hooks --json
codex plugin add watcher@orime --json
```

更新前查看实际登记的源码目录：

```bash
codex plugin marketplace list --json
git -C /absolute/path/to/cc-hooks pull --ff-only origin main
codex plugin add watcher@orime --json
```

本地市场读取该目录，GitHub 市场读取其下载的快照。检查实际登记来源后更新对应目录。Claude Code 本地市场可用 `/plugin marketplace add /absolute/path/to/cc-hooks`。

## 7. 维护与验证

协作规范的唯一真源为 [announce-intent.sh](./watcher/hooks/announce-intent.sh)。两个客户端共用规范及提交检查、Stop 实现；Codex 入口位于 [codex-hooks.json](./watcher/hooks/codex-hooks.json)。

| 目录 | 内容 |
|---|---|
| `watcher/hooks/` | 协作规范注入、提交检查、Stop 及平台配置 |
| `watcher/skills/` | 审计、配置、开关、playbook 和视觉审查技能 |
| `watcher/output-styles/` | Claude Code 中文输出风格 |
| `tests/` | 长度检查及保留功能的 smoke/解析测试 |
| `docs/` | 使用指南、设计和验证记录；旧面板资料带历史标记 |

修改后运行 [.github/workflows/smoke.yml](./.github/workflows/smoke.yml) 中的检查。快速核对：

```bash
bash tests/check-size.sh
python3 tests/smoke-announce.py
python3 tests/smoke-manifests.py
```

项目注入门槛为 9500 UTF-16 单元，测量完整 stdout，保留距 Claude Code 单份输出 10000 字符限制的余量。执行失败时检查返回失败。视觉审查脚本改动另运行 `python3 tests/smoke-visual-adversary.py`。

[更新记录](./CHANGELOG.md) · [Codex 使用指南](./docs/codex-usage.zh-CN.md) · [MIT 许可证](./LICENSE)
