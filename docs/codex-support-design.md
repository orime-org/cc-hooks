# Codex 支持设计文档

让 watcher 插件在 OpenAI Codex CLI 里也能装、也能用。

## 1. 任务目标

watcher 插件装进 Codex CLI 后，三个 hook（规范注入、bash 拦截、收尾审计）和全部 skill 都按它们在 Claude Code 里的行为工作。Claude Code 里的现有行为不变。

本仓库没有 DD、TDD、选择澄清的流程规范，建议完善；本任务按协作规范的流水线执行。smoke 体系已有，见 `.github/workflows/smoke.yml`。

## 2. 现状

### 2.1 Codex 侧（本轮实测，Codex CLI 0.163.0）

| 事实 | 出处 |
|---|---|
| 插件自带的 `hooks/hooks.json` 会执行，`UserPromptSubmit`、`PreToolUse`、`Stop` 都触发 | 探测插件装进本机 Codex 后跑 `codex exec`，hook 日志三种事件都有 |
| hook 进程里有 `PLUGIN_ROOT`、`PLUGIN_DATA`，也有 `CLAUDE_PLUGIN_ROOT`、`CLAUDE_PLUGIN_DATA` | 同上，hook 打印的环境变量 |
| `PreToolUse` 的 shell 工具 `tool_name` 是 `Bash`，`tool_input.command` 是命令文本；`exit 2` 加 stderr 能拦住 | Codex 报错原文 `Command blocked by PreToolUse hook: PROBE_GATE: blocked by exit 2` |
| `Stop` 返回 `{"decision":"block","reason":X}`，Codex 按 X 再起一轮；再起的那一轮结束时 `stop_hook_active` 为 `true` | 模型第二轮按 reason 回了指定文字；第二次 Stop 输入 `stop_hook_active: true` |
| `Stop` 返回 `continue:false` 时，`stopReason` 在 TUI 里作为 hook 输出给用户看，不进模型上下文 | openai/codex `codex-rs/hooks/src/events/stop.rs:278-288`（`HookOutputEntryKind::Stop`），`codex-rs/tui/src/history_cell/hook_cell.rs:331-338`；本机会话记录里查不到这段文字 |
| `UserPromptSubmit` 的 stdout 超过约 2,500 token 时，全文存进 `$TMPDIR/hook_outputs/<会话>/`，模型只拿到开头和结尾。announce 9,493 字符超过了这个限 | 探测时生成了 `hook_outputs` 文件，全文 9,534 字符 |
| handler 加 `"additionalContextLimit": 0` 后，announce 全文作为 developer 消息进上下文，不再生成 `hook_outputs` 文件 | 第二次探测的会话记录里，开头、中间、结尾三个标记都在 |
| `transcript_path` 指向 `~/.codex/sessions/.../rollout-*.jsonl`；`codex exec --ephemeral` 时为 `null` | 两次探测的 hook 输入 |
| rollout 里 `{"type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":N},"model_context_window":W}}}` 记录上下文用量；`input_tokens` 已含缓存命中部分 | `~/.codex/sessions/2026/10/21/rollout-…jsonl` 的 `token_count` 行（`input_tokens` 24173 中含 `cached_input_tokens` 12032） |
| 插件的 skill 以 `插件名:skill名` 出现在模型的 skill 列表里，带 `SKILL.md` 绝对路径，例如 `documents:documents`、`browser-use:browser` | 探测时让模型列出 skill 列表 |
| `agents/openai.yaml` 设 `allow_implicit_invocation: false` 的 skill 不进模型的 skill 列表 | 同上，探测 skill 没出现在列表里 |
| Codex 的任务清单工具是 `update_plan`，派子代理是 `spawn_agent`，向用户提问是 `request_user_input`；联网搜索只能经 `functions.exec` 调 `web__run` | 探测时让模型列出工具名 |
| Codex 读仓库根的 `.claude-plugin/marketplace.json`，`codex plugin list` 列出 `watcher@orime` | `codex plugin marketplace add <本仓>` 后的 `codex plugin list` |
| 插件清单读 `.codex-plugin/plugin.json`；其中的 `hooks` 字段设了之后替代默认的 `hooks/hooks.json` | [插件构建文档](https://developers.openai.com/plugins/build/plugins) |
| 插件 hook 装上后默认不受信任，要用户在 `/hooks` 里点信任；信任绑定 hook 的 hash，改了要重新信任 | [Hooks 文档](https://learn.chatgpt.com/docs/hooks) |
| SKILL.md 必须有 `name`、`description`；用户在 Codex 里用 `$` 或 `/skills` 显式调用 skill | [Skills 文档](https://learn.chatgpt.com/docs/build-skills.md) |

### 2.2 插件里 Claude Code 专有的地方（本轮逐文件检索）

| 位置 | 内容 | 在 Codex 里的问题 |
|---|---|---|
| `watcher/hooks/announce-intent.sh:40,123,125,126` | `workflow` | Codex 没有 workflow 工具 |
| `watcher/hooks/announce-intent.sh:124` | `TaskCreate/TaskUpdate` | Codex 是 `update_plan` |
| `watcher/hooks/announce-intent.sh:94,116,117` | `WebSearch` | Codex 没有这个工具名 |
| `watcher/hooks/announce-intent.sh:95` | `AskUserQuestion` | Codex 是 `request_user_input` |
| `watcher/hooks/announce-intent.sh:116` | `CLAUDE.md` | Codex 的项目规则文件是 `AGENTS.md` |
| `watcher/hooks/announce-intent.sh:128,179` | `/watcher:playbook`、`/watcher:visual-adversary` | 斜杠是 Claude Code 用户命令的写法 |
| `watcher/hooks/suggest-watcher.sh:145,154` | 上下文窗口写死 1M；只认 Claude Code 的 `.message.usage` | Codex rollout 格式不同，窗口因模型而异 |
| `watcher/hooks/suggest-watcher.sh:277` | 「调用 Skill 工具 `skill='watcher'`」 | Codex 没有 Skill 工具 |
| `watcher/hooks/suggest-watcher.sh:248,264,285,288` | `/watcher:watcher-configure`、`/watcher:watcher-on`、`/watcher:watcher-off` | 斜杠写法 |
| `watcher/commands/watcher-on.md`、`watcher-off.md`、`watcher-configure.md` | 插件命令 | Codex 插件不支持命令 |
| `watcher/output-styles/chinese-engineering.md` | 输出风格 | Codex 没有输出风格 |
| `watcher/skills/visual-adversary/SKILL.md:39` | `${CLAUDE_SKILL_DIR}` | 这是 Claude Code 在 SKILL.md 里做的文字替换，Codex 不替换 |
| `watcher/skills/visual-adversary/SKILL.md:34,52`、`playbook/SKILL.md:31`、`playbook/references/adversary-review.md:3,7` | `workflow` | 同上 |
| `watcher/skills/playbook/references/git-pr.md:29,31` | `Monitor` | Codex 没有 Monitor 工具 |
| `watcher/skills/playbook/SKILL.md:20` | 「项目的规则文件（`CLAUDE.md` 或它导入的 `AGENTS.md`）」「Claude Code 自带工具」 | 只写了 Claude Code |
| `watcher/skills/watcher/SKILL.md:8` | 「Stop hook 的 reason 明确要求"调用 Skill 工具 watcher"」 | Codex 的 reason 不会这么写 |
| `watcher/skills/watcher/SKILL.md:9,12,20,65,97,117,196,250,325,340`、`references/setup-flow.md:1,3,9,110` | `/watcher`、`/watcher:watcher-configure` | 斜杠写法 |
| `watcher/skills/watcher/references/agent-paths.md:19-28` | Codex 段：skill 目录写 `~/.codex/skills`，「Codex 没有记忆文件机制」 | 和 2.1 查到的不一致：用户 skill 目录是 `~/.agents/skills`，插件 skill 在插件缓存里；本机有 `~/.codex/memories/` |
| `watcher/hooks/bash-gate.sh` | 读 `tool_input.command`、`cwd`，`exit 2` 拦截 | 无问题，2.1 已实测 |

## 3. 验收清单

产出物按 1.2 术语表判定：hook 脚本、清单文件、skill 都是**生产代码**。级别按 3.1.2 判为**开发级**：插件只在 Claude Code 或 Codex 干活的过程中起作用。同类判定见 `docs/bash-gate-design.md:15`（决策者裁定 bash-gate 为开发级）。开发级不进三类。

| # | 做什么 | 产出物·级别 | 场景／目标／结果 | 对应目标哪部分 |
|---|---|---|---|---|
| 1 | 加 Codex 插件清单 | 生产代码·开发级 | 场景：用户把本仓加成 Codex marketplace 后装 `watcher@orime`。目标：Codex 用 Codex 专用的 hook 配置。结果：`watcher/.codex-plugin/plugin.json` 的 `hooks` 指向 `./hooks/codex-hooks.json`，版本号和 `.claude-plugin/plugin.json` 一致 | 能装 |
| 2 | 加 Codex hook 配置 | 生产代码·开发级 | 场景：Codex 加载插件 hook。目标：三个脚本都挂上，并知道当前平台。结果：`codex-hooks.json` 的三个 command 都带参数 `codex`；`UserPromptSubmit` 的 handler 带 `"additionalContextLimit": 0` | 三个 hook |
| 3 | 规范在 Codex 里全文注入 | 生产代码·开发级 | 场景：Codex 用户每次提交 prompt。目标：模型拿到完整规范，工具名是 Codex 的。结果：模型上下文里有全文；Codex 版里没有 `workflow`、`TaskCreate`、`TaskUpdate`、`WebSearch`、`AskUserQuestion`、`CLAUDE.md`、`/watcher:`，换成 2.2 对应的 Codex 说法 | 规范注入 |
| 4 | Claude Code 版规范不变 | 生产代码·开发级 | 场景：Claude Code 用户每次提交 prompt。目标：现有行为不变。结果：不带参数时输出和改动前逐字节相同，仍 ≤ 9,500 | 不变 |
| 5 | bash 拦截在 Codex 里生效 | 生产代码·开发级 | 场景：Codex 在配了 `.watcher/` 的仓库主分支上 `git commit`，或标题不合规。目标：和 Claude Code 一样拦下。结果：调用被拦，模型收到原因 | bash 拦截 |
| 6 | Stop hook 在 Codex 里读对上下文用量 | 生产代码·开发级 | 场景：Codex 一轮结束。目标：状态行显示真实用量。结果：从 rollout 最后一条 `token_count` 取 `input_tokens` 和 `model_context_window`，按实际窗口算百分比，状态行写实际窗口大小；取不到就省掉上下文那一段，其余照显 | 收尾审计 |
| 7 | Stop hook 在 Codex 里的提示文字 | 生产代码·开发级 | 场景：三条出口（没配、OFF、ON）。目标：模型和用户按 Codex 的方式去调 skill。结果：ON 的 reason 指名 `watcher:watcher` skill 和它的 `SKILL.md` 绝对路径；用户命令写成 Codex 的显式调用写法；三条出口的判定和状态读写和 Claude Code 完全一样 | 收尾审计 |
| 8 | 三个开关命令改成 skill | 生产代码·开发级 | 场景：用户在两个平台开关审计、建配置。目标：两个平台用同一份内容。结果：`commands/*.md` 移到 `skills/watcher-on/SKILL.md` 等三处，名字不变；Claude Code 里 `/watcher:watcher-on` 等照常能用；Codex 里能显式调用 | 两平台 skill |
| 9 | skill 正文两个平台都能照做 | 生产代码·开发级 | 场景：模型在 Codex 里读 watcher、playbook、visual-adversary 和三个开关 skill。目标：里面提到的工具、变量、命令写法在 Codex 里有对应。结果：2.2 列出的 skill 正文位置都写明 Codex 的对应说法；`${CLAUDE_SKILL_DIR}` 写明 Codex 下用本 SKILL.md 所在目录 | 全部 skill |
| 10 | `agent-paths.md` Codex 段改对 | 文案 | 生效目标：audit 时找对 Codex 的规则文件、skill 目录和记忆位置 | 收尾审计 |
| 11 | README 加 Codex 安装 | 文案 | 生效目标：Codex 用户能照着装上、信任 hook，并把输出风格放进 `~/.codex/AGENTS.md` | 能装 |
| 12 | smoke 覆盖 Codex | 测试代码 | 验证：`check-size.sh` 量两个版本；新增 announce 用例断言 4、3 的结果；`smoke-stop-hook.py` 加 Codex rollout 读数、`null` transcript、Codex 文字；`smoke-bash-gate.py` 加 Codex 输入形状；新增清单用例断言 1、2；CI 跑全部 | 4.2.6 |

## 4. 设计

### 4.1 目录

```
watcher/
├── .claude-plugin/plugin.json   # 已有，Claude Code 读
├── .codex-plugin/plugin.json    # 新增，Codex 读
├── hooks/
│   ├── hooks.json               # 已有，Claude Code 的 hook 配置，不改
│   ├── codex-hooks.json         # 新增，Codex 的 hook 配置
│   └── *.sh                     # 两个平台共用
├── skills/
│   ├── watcher/  playbook/  visual-adversary/   # 已有
│   └── watcher-on/  watcher-off/  watcher-configure/   # 从 commands/ 移来
└── output-styles/               # 只有 Claude Code 用
```

仓库根的 `.claude-plugin/marketplace.json` 两个平台都读，不另加。

### 4.2 平台怎么传给脚本

`codex-hooks.json` 的每条 command 末尾加参数 `codex`，例如：

```json
{"type": "command", "command": "bash \"${PLUGIN_ROOT}/hooks/announce-intent.sh\" codex", "timeout": 5, "additionalContextLimit": 0}
```

脚本读 `$1`：等于 `codex` 走 Codex 分支，其余一律走现在的 Claude Code 分支。`hooks.json` 不改，所以 Claude Code 的调用和现在完全一样。

### 4.3 announce-intent.sh

规范正文仍是一份 heredoc。Codex 分支把它过一遍固定的替换表再输出：

| Claude Code 原文 | Codex 输出 |
|---|---|
| `workflow` | `spawn_agent` |
| `TaskCreate/TaskUpdate` | `update_plan` |
| `WebSearch` | `联网搜索` |
| `AskUserQuestion` | `request_user_input` |
| `CLAUDE.md` | `AGENTS.md` |
| `` `/watcher:playbook` `` | `` `watcher:playbook` skill `` |
| `` `/watcher:visual-adversary` `` | `` `watcher:visual-adversary` skill `` |

`WebSearch` 对应「联网搜索」：Codex 的联网搜索经 `functions.exec` 调 `web__run`（2.1），没有固定的顶层工具名。

替换表写在脚本里，用 `sed` 一次做完。Claude Code 分支不经过替换，输出逐字节不变。

### 4.4 suggest-watcher.sh

三条出口（没配 `.watcher/`、OFF、ON）的判定、`audit-state.json` 的读写、`stop_hook_active` 防递归，两个平台完全一样，不新增状态。平台只影响两件事。

**一、上下文读数。**

| 平台 | 读哪一行 | tokens | 窗口 |
|---|---|---|---|
| Claude Code（不变） | 从末尾往前第一条带 `.message.usage.input_tokens` 的行 | `input + cache_read + cache_creation` | 1M |
| Codex | 从末尾往前第一条 `.type=="event_msg" and .payload.type=="token_count" and .payload.info != null` 的行 | `.payload.info.last_token_usage.input_tokens` | `.payload.info.model_context_window` |

两个平台取不到时都一样：省掉上下文那一段，时间、CPU、内存照显。`transcript_path` 为 `null` 也走这条。Codex 状态行里的「窗口 1M」换成实际窗口，比如「窗口 475K」；85% 告警阈值和 `/compact` 提示不变，Codex 也有 `/compact`。

**二、提示文字。**

| 位置 | Claude Code（不变） | Codex |
|---|---|---|
| ON 的 reason 第一行 | 调用 Skill 工具 `skill='watcher'` | 用 `watcher:watcher` skill 跑本轮收尾，先读 `${PLUGIN_ROOT}/skills/watcher/SKILL.md`（展开成绝对路径） |
| 用户命令 | `/watcher:watcher-on` 等 | Codex 的显式调用写法，见 4.7 |

Codex 里 OFF 和没配两条出口的 `stopReason` 只给用户看（2.1）。文字和 Claude Code 版保持一致，只换命令写法。

### 4.5 bash-gate.sh

不改。Codex 的输入形状和退出码语义在 2.1 实测过，和 Claude Code 一样。`codex-hooks.json` 里照样挂在 `PreToolUse`、`matcher: "Bash"` 上。

### 4.6 三个命令改成 skill

`commands/watcher-on.md` 移到 `skills/watcher-on/SKILL.md`，另外两个同样处理。frontmatter 留 `name`、`description`，去掉 `command: true`，正文不变。

| 平台 | 名字 | 用户怎么调 | 模型能不能自己调 |
|---|---|---|---|
| Claude Code | `watcher:watcher-on`，和现在一样 | `/watcher:watcher-on`，和现在一样 | 能，和现在一样（现在这三个命令就在模型的 skill 列表里） |
| Codex | `watcher:watcher-on` | 显式调用，见 4.7 | 能，默认 `allow_implicit_invocation` 为 `true` |

两个平台的能力一致。模型不要自己去关审计，这条约束仍由 Stop hook reason 里的那句「这是留给用户的开关，Claude 别自作主张去关」管，这句不变。

### 4.7 Codex 里用户怎么显式调 skill

文档写的是 `$` 加 skill 名（2.1）。插件 skill 在列表里的名字是 `watcher:watcher-on`，所以写法应是 `$watcher:watcher-on`。这一点没有直接证据，是推断：实现前先在 Codex TUI 里试一次，再写进 hook 文字和 skill 正文。试出来不一样就按实际写法改。

### 4.8 skill 正文

每个 skill 正文提到 Claude Code 专有写法的地方，原文不动，就地补上 Codex 的对应说法：

| 原文 | 补充 |
|---|---|
| `workflow` | Codex 用 `spawn_agent` |
| `Monitor` | Codex 用 `gh pr checks <N> --watch` 起一个后台命令盯着 |
| `${CLAUDE_SKILL_DIR}` | Codex 下换成本 SKILL.md 所在目录的绝对路径 |
| `/watcher:…`、`/watcher` | Codex 写法见 4.7，每个 skill 开头说一次 |
| 「调用 Skill 工具 watcher」 | 改成「要求调用 watcher skill」，两个平台通用 |
| 「`CLAUDE.md` 或它导入的 `AGENTS.md`」「Claude Code 自带工具」 | 加上 Codex 的 `AGENTS.md` 和自带工具 |

`agent-paths.md` 的 Codex 段按 2.1 改：skill 目录、插件 skill 的位置和名字、`~/.codex/memories/`。`~/.codex/memories/` 的用途先查官方文档再写；查不到就只写「目录存在、用途没查到出处」。

### 4.9 输出风格

Codex 没有输出风格。README 写明：Codex 用户把 `output-styles/chinese-engineering.md` 正文（frontmatter 以下）放进 `~/.codex/AGENTS.md`。插件不改用户的全局配置。

### 4.10 不新增状态流转

`audit-state.json` 的状态和转移（`enable-audit` 开关、`unaudited-rounds` 计数、skill 进入即清零）不变，平台只换读数来源和提示文字。4.4 的表已列出平台差异，状态流转 demo 不需要。

## 5. 依赖和选择

不引入新依赖：仍是 bash、jq、sed。

| 选择 | 依据 |
|---|---|
| 一个插件目录、两份清单、脚本共用 | Codex 文档写明 `.codex-plugin/plugin.json` 是 Claude 兼容插件的位置，并为兼容设 `CLAUDE_PLUGIN_ROOT`（2.1）；共用脚本只有一份实现 |
| 平台由 hook 配置传参数 | 两份 hook 配置本来就分开写，参数随各自的配置传入，脚本只读 `$1` |
| announce 用替换表生成 Codex 版 | 规范正文只有一份，Claude Code 版逐字节不变（验收 4） |

## 6. 验证

| 层 | 做什么 |
|---|---|
| smoke（CI） | 验收 12 列的全部用例 |
| Codex 真机 | 从本 worktree 加 marketplace、装 `watcher@orime`，在一个配了 `.watcher/` 的临时 git 仓用 `codex exec --dangerously-bypass-hook-trust` 跑：announce 全文进上下文且没有 `hook_outputs` 文件；主分支 `git commit` 被拦；ON 时模型读了 `skills/watcher/SKILL.md`；OFF 时 `stopReason` 是 Codex 文字；rollout 读数正确。再在 TUI 里试 4.7 的显式调用写法和 `/hooks` 信任流程。跑完卸载、删 marketplace、删会话，`~/.codex/config.toml` 和跑之前逐字一致 |
| Claude Code 真机 | `claude -p --plugin-dir <worktree>/watcher`：三个开关 skill 能用 `/watcher:watcher-on` 等调用；announce、bash 拦截、Stop 输出和 main 上逐字相同 |
