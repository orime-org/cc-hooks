# 在 Codex 中使用 watcher

watcher 为官方 Codex 提供协作规范、提交检查和项目审计。`0.2.0` 增加三项简短任务收尾，并退役插件提供的 WezTerm 任务面板。

## 1. 安装、授权与更新

准备 Bash、Git、`jq`、Python 3，以及支持插件和 hooks 的官方 Codex CLI。

| 场景 | 在终端执行 |
|---|---|
| 从 GitHub 安装 | `codex plugin marketplace add orime-org/cc-hooks --ref main --json`，然后 `codex plugin add watcher@orime --json` |
| 更新 GitHub 市场及插件 | `codex plugin marketplace upgrade orime --json`，然后 `codex plugin add watcher@orime --json` |
| 查看安装 | `codex plugin list --marketplace orime --json` |
| 查看实际市场来源 | `codex plugin marketplace list --json` |

本地市场安装和更新见[中文 README 第 6 节](../README.zh-CN.md#6-使用本地源码)。本地市场先更新实际源码目录，再刷新安装缓存。

在新启动或恢复的 Codex 会话中打开 `/hooks`，检查并信任 watcher 的定义；更新后需要重新审核时，仍通过 `/hooks` 完成。随后消息会收到协作规范。原项目继续工作可执行 `codex resume` 并选择原会话。

安装、更新、授权及正式配置由用户执行。使用官方 Codex 的正常运行和升级方式。

## 2. 三项任务收尾

| 项目 | 正文上限 | 内容 |
|---|---:|---|
| 当前任务 | 20 字 | 正在解决什么 |
| 当前任务的阶段 | 20 字 | 当前实际执行的流程环节 |
| 工作纪律自评 | 30 字 | 按本轮事实写遵循情况；有偏离时写偏离及正确做法 |

正文合计最多 70 字，标点、数字和英文字母各计 1 字，字段名不计。

本轮实际推进设计、实现、审查、文档同步、smoke 等具体工作时，收尾补充三项。普通问答和讨论直接回答；按本轮实际工作判断。其他汇报遵循已有协作规范。

UserPromptSubmit hook 在消息提交时送达规则。Agent 在发送前自行核对格式及长度，Stop 按项目的审计开关处理。任务规划继续使用 Codex 原生 `update_plan`。

## 3. 移除已有 WezTerm 任务面板

本节供曾安装面板的用户执行。先移除终端加载入口、关闭现有面板，再更新插件。

### 3.1 找到并备份实际配置

先查原配置技能输出的绝对路径及备份记录。原安装器支持显式指定配置；默认先检查 `XDG_CONFIG_HOME/wezterm/wezterm.lua`（XDG_CONFIG_HOME 未设置时为用户主目录中的 `.config/wezterm/wezterm.lua`），该文件存在时使用它，否则使用用户主目录中的 `.wezterm.lua`。

读取实际文件并保存备份。以下是托管区段的形状，`dofile` 中的路径以本机内容为准：

```lua
-- BEGIN cc-hooks task panel
dofile("/absolute/path/to/plugin-data/task-panel-integration/loader.lua")
-- END cc-hooks task panel
```

删除从 BEGIN 到 END 的这个完整区段，保留其余配置正文。区段缺失、标记不完整或加载方式被改写时，先查证实际内容，再询问当前用户如何处理。

### 3.2 重载配置并退出旧面板

通过 WezTerm 的 ReloadConfiguration 操作重新加载配置；按键以本机设置为准。重载会重新建立 Lua 状态并清除原事件处理器，见 [WezTerm 官方说明](https://wezterm.org/config/lua/wezterm/on.html)。

分别点击现有任务面板并按 `q`，确认面板退出、原工作窗格保留。然后按第 1 节更新插件并加载新会话。

### 3.3 清理面板运行副本及缓存

面板进程退出后，在原插件数据目录中移除以下两个专用子目录：

| 目录 | 内容 |
|---|---|
| `task-panel-integration` | 原面板运行文件及 Lua loader |
| `task-panel` | 原面板计划缓存和关联记录 |

默认插件数据目录为 Codex 配置目录中的 `plugins/data/watcher-orime`。Codex 配置目录默认是用户主目录中的 `.codex`，设置 `CODEX_HOME` 时使用其实际值。原安装器支持 `--data-dir`，自定义位置以安装记录为准。

先确认实际目录及内容，再清理这两个子目录。同目录其他插件数据继续保留。

## 4. 提交检查和审计

提交检查保留原版目录解析：依据 `git -C`、提交前的 `cd` 及 hook 目录上下文定位目标仓库，普通输入以会话 cwd 为起点。仓库根目录有 `.watcher/` 时检查主分支、提交标题和署名规则。

解析器采用启发式兼容边界。有明确约定和事实就按约定处理；正常查证后仍无法确定时，Agent 询问当前用户并按答复处理。目录歧义提示后，可使用确认过的绝对 workdir 或 `git -C` 路径重试。

| 目的 | 在 Codex 中输入 |
|---|---|
| 创建或修改项目配置 | `$watcher:watcher-configure` |
| 手动审计一次 | `$watcher:watcher` |
| 关闭自动审计 | `$watcher:watcher-off` |
| 开启自动审计 | `$watcher:watcher-on` |

手动审计执行一次，自动开关保持当前状态。PR 由用户完成检查并亲自合并，AI 准备代码、提交和 PR，并跟踪 CI/review。

## 5. 验证记录与维护

本轮已验证两个客户端的规则注入、保留 hook 和提交检查，以及真实官方 Codex 的 smoke 收尾和普通问答。独立 WezTerm 窗口验证了移除托管区段、重载、q 退出及父窗格保留，见[实现验证记录](./round-summary-panel-retirement-validation.md)。

CLI 和 hook 字段变化时，依据实际报错、官方能力及验证结果适配。历史面板设计与 demo 留有退役标记，当前使用以本指南和 README 为准。
