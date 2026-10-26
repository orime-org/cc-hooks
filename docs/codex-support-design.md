# Codex 支持设计文档

> 历史材料：本文中的任务面板及配套构建方案已于 0.2.0 退役。当前功能及已有面板移除步骤见 [Codex 使用指南](./codex-usage.zh-CN.md)。

让 watcher 插件在 OpenAI Codex CLI 里也能装、也能用。

## 1. 任务目标

watcher 插件装进 Codex CLI 后，三个 hook（规范注入、bash 拦截、收尾审计）和全部 skill 都按它们在 Claude Code 里的行为工作。Claude Code 里的现有行为不变。

本仓库没有 DD、TDD、选择澄清的流程规范，建议完善；本任务按协作规范的流水线执行。smoke 体系已有，见 `.github/workflows/smoke.yml`。

## 2. 现状

### 2.1 Codex 侧（Codex CLI 0.163.0，本机探测和 openai/codex `rust-v0.163.0` 源码）

| 事实 | 出处 |
|---|---|
| 插件自带的 hook 会执行，`UserPromptSubmit`、`PreToolUse`、`Stop` 都触发 | 探测插件装进本机 Codex 后跑 `codex exec`，hook 日志三种事件都有 |
| hook 进程里有 `PLUGIN_ROOT`、`PLUGIN_DATA`，也有 `CLAUDE_PLUGIN_ROOT`、`CLAUDE_PLUGIN_DATA`；`PLUGIN_DATA` 是插件可写的数据目录，例如 `~/.codex/plugins/data/watcher-probe-probe-market` | 同上，hook 打印的环境变量 |
| `PreToolUse` 的 shell 工具 `tool_name` 是 `Bash`，`tool_input.command` 是命令文本；`exit 2` 加 stderr 能拦住 | Codex 报错原文 `Command blocked by PreToolUse hook: PROBE_GATE: blocked by exit 2` |
| `Stop` 返回 `{"decision":"block","reason":X}`，Codex 把 X 写进会话、再起一轮；再起的那一轮结束时 `stop_hook_active` 为 `true` | `core/src/session/turn.rs:737-755`；探测时模型第二轮按 reason 回了指定文字 |
| `Stop` 返回 `continue:false` 时，`stopReason` 只作为 hook 输出显示在 TUI，不进模型上下文；随后循环直接 `break`，跳过用户配置的 `notify`（`run_legacy_after_agent_hook`）和轮末自动压缩 | `hooks/src/events/stop.rs:296-305`，`core/src/session/turn.rs:765-775`，`tui/src/history_cell/hook_cell.rs:331-338`；本机会话记录里查不到 `stopReason` 文字 |
| `Stop` 返回的 `systemMessage` 在 TUI 里显示成 `↳ Hook · <第一行>` 加后续各行，不改变本轮流程，也不进模型上下文；`codex exec` 只打印 `hook: Stop Completed`，不打印这段文字，会话记录也不存 | `hooks/src/events/stop.rs:288-293`，`tui/src/history_cell/hook_cell.rs:281-295`，`exec/src/event_processor_with_human_output.rs:280-287`，`rollout/src/policy.rs:213-214` |
| 子代理和根会话共用同一个 `session_id`；新开的 `codex exec` 拿新的 `session_id`，`codex exec resume` 沿用原来的 | `core/src/session/session.rs:668-671,932-953` |
| `Stop` 只有 `decision:block` 一条通路能把文字送进模型 | `hooks/src/events/stop.rs:252-330` 只解析 `systemMessage`、`continue`/`stopReason`、`decision`/`reason` |
| 根会话跑 `Stop`，`spawn_agent` 派出的子代理跑 `SubagentStop` | `core/src/hook_runtime.rs:400` |
| 子代理收到任务时也触发 `UserPromptSubmit`，输入里带 `agent_id`、`agent_type` | `core/src/hook_runtime.rs:684-688,1042-1061`，`hooks/src/events/user_prompt_submit.rs:82-87`，`core/src/tools/handlers/multi_agents/spawn.rs:119` |
| `UserPromptSubmit` 的 stdout 超过约 2,500 token 时，全文存进 `$TMPDIR/hook_outputs/<会话>/`，模型只拿到开头和结尾；announce 9,493 字符超过了这个限 | 探测时生成了 `hook_outputs` 文件，全文 9,534 字符 |
| handler 加 `"additionalContextLimit": 0` 后，announce 全文作为 developer 消息进上下文 | 第二次探测的会话记录里开头、中间、结尾三个标记都在，没有 `hook_outputs` 文件 |
| `transcript_path` 指向 `~/.codex/sessions/.../rollout-*.jsonl`；`codex exec --ephemeral` 时为 `null` | 两次探测的 hook 输入 |
| rollout 的 `token_count` 事件里有 `last_token_usage` 和 `model_context_window`；Codex 自己算上下文用量用的是 `last_token_usage.total_tokens` | 本机 rollout；`protocol/src/protocol.rs:2561-2563`（`tokens_in_context_window` 返回 `total_tokens`） |
| Codex 在 `Stop` 之前不刷 rollout，在 `SessionEnd`、`Interrupt` 之前刷 | `core/src/hook_runtime.rs:493,535` |
| Codex 默认开自动压缩，阈值是模型窗口的 90% | `core/src/session/turn.rs:174-180`，`protocol/src/openai_models.rs` 的 `auto_compact_token_limit` |
| 插件的 skill 以 `插件名:skill名` 出现在模型的 skill 列表里，带 `SKILL.md` 绝对路径 | 探测时模型列出的 `documents:documents`、`browser-use:browser` |
| `agents/openai.yaml` 设 `allow_implicit_invocation: false` 的 skill 不进模型的 skill 列表 | 探测 skill 没出现在列表里 |
| 安装插件时，`commands/*.md` 会被转成名为 `source-command-<名字>` 的 skill | `core-plugins/src/store.rs:644`，`core-plugins/src/command_migration.rs:14,340` |
| Codex 的任务清单工具是 `update_plan`，派子代理是 `spawn_agent`，向用户提问是 `request_user_input`，改文件是 `apply_patch`，跑命令是 `exec_command`；联网搜索经 `functions.exec` 调 `web__run` | 探测时模型列出的工具名 |
| Codex 读仓库根的 `.claude-plugin/marketplace.json` | `codex plugin marketplace add <本仓>` 后 `codex plugin list` 列出 `watcher@orime` |
| 插件清单读 `.codex-plugin/plugin.json`；其中 `hooks` 字段设了之后替代默认的 `hooks/hooks.json` | [插件构建文档](https://developers.openai.com/plugins/build/plugins) |
| 插件 hook 装上后默认不受信任，要在 `/hooks` 里信任；信任绑定 hook 的 hash | [Hooks 文档](https://learn.chatgpt.com/docs/hooks) |
| SKILL.md 必须有 `name`、`description`；用户用 `$` 或 `/skills` 显式调用 skill | [Skills 文档](https://learn.chatgpt.com/docs/build-skills.md) |

### 2.2 插件里 Claude Code 专有的地方（逐文件检索）

| 位置 | 内容 | 在 Codex 里的问题 |
|---|---|---|
| `watcher/hooks/announce-intent.sh:40,123,125,126` | `workflow` | Codex 没有 workflow 工具 |
| `watcher/hooks/announce-intent.sh:124` | `TaskCreate/TaskUpdate` | Codex 是 `update_plan` |
| `watcher/hooks/announce-intent.sh:94,116,117` | `WebSearch` | Codex 没有这个工具名 |
| `watcher/hooks/announce-intent.sh:95` | `AskUserQuestion` | Codex 是 `request_user_input` |
| `watcher/hooks/announce-intent.sh:116` | `CLAUDE.md` | Codex 的项目规则文件是 `AGENTS.md` |
| `watcher/hooks/announce-intent.sh:128,179` | `/watcher:playbook`、`/watcher:visual-adversary` | 斜杠是 Claude Code 用户命令的写法 |
| `watcher/hooks/suggest-watcher.sh:145,154,162` | 窗口写死 1M；只认 `.message.usage`；85% 时建议手动 `/compact` | Codex rollout 格式不同，窗口因模型而异，Codex 默认自动压缩 |
| `watcher/hooks/suggest-watcher.sh:246-250,261-266` | OFF 和没配两条出口用 `continue:false` | Codex 上会跳过 `notify` 和轮末压缩，文字也到不了模型 |
| `watcher/hooks/suggest-watcher.sh:277` | 「调用 Skill 工具 `skill='watcher'`」 | Codex 没有 Skill 工具 |
| `watcher/hooks/suggest-watcher.sh:248,264,285,288` | `/watcher:watcher-configure`、`/watcher:watcher-on`、`/watcher:watcher-off` | 斜杠写法 |
| `watcher/commands/watcher-on.md`、`watcher-off.md`、`watcher-configure.md` | 插件命令 | Codex 安装时转成 `watcher:source-command-watcher-on` 等，名字和 Claude Code 对不上 |
| `watcher/commands/watcher-configure.md:9` | `skills/watcher/references/setup-flow.md`（相对插件根） | 移进 skill 目录后按 skill 目录解析会指错 |
| `watcher/commands/watcher-configure.md:15,17,31-33`，`watcher-on.md:11`，`watcher-off.md:11,23,28-29` | Write 工具、Bash 工具、`/watcher:…` | Codex 工具名和调用写法不同 |
| `watcher/output-styles/chinese-engineering.md` | 输出风格 | Codex 没有输出风格 |
| `watcher/skills/watcher/SKILL.md:72,92,95,122,205,297`，`references/setup-flow.md:47,92,94,103,125,132` | Read、Edit、Write 工具名 | Codex 是 `exec_command`、`apply_patch` |
| `watcher/skills/watcher/SKILL.md:206,211,287` | WebSearch、WebFetch | Codex 没有这两个工具名 |
| `watcher/skills/watcher/SKILL.md:105,122,174,210` | `CLAUDE.md` | Codex 的规则文件是 `AGENTS.md` |
| `watcher/skills/watcher/SKILL.md:8` | 「Stop hook 的 reason 明确要求"调用 Skill 工具 watcher"」 | Codex 的 reason 不会这么写 |
| `watcher/skills/watcher/SKILL.md:9,12,20,65,97,117,196,250,325,340`，`references/setup-flow.md:1,3,9,110` | `/watcher`、`/watcher:watcher-configure` | 斜杠写法 |
| `watcher/skills/watcher/SKILL.md:88` | 「一个 CC 会话」 | 只写了 Claude Code |
| `watcher/skills/visual-adversary/SKILL.md:39` | `${CLAUDE_SKILL_DIR}` | Claude Code 在 SKILL.md 里做的文字替换，Codex 不替换 |
| `watcher/skills/visual-adversary/SKILL.md:34,52`，`playbook/SKILL.md:31`，`playbook/references/adversary-review.md:3,7` | `workflow`，以及 `agents_error`、`agents_done`、`agent_count` 统计 | Codex 是 `spawn_agent`，没有这几个统计字段 |
| `watcher/skills/playbook/references/git-pr.md:29,31` | `Monitor` | Codex 没有 Monitor 工具 |
| `watcher/skills/playbook/SKILL.md:20` | 「`CLAUDE.md` 或它导入的 `AGENTS.md`」「Claude Code 自带工具」 | 只写了 Claude Code |
| `watcher/skills/watcher/references/agent-paths.md:19-28` | Codex 段：skill 目录写 `~/.codex/skills`，「Codex 没有记忆文件机制」 | 用户 skill 目录是 `~/.agents/skills`，插件 skill 在插件缓存里；本机有 `~/.codex/memories/` |
| `watcher/hooks/bash-gate.sh` | 读 `tool_input.command`、`cwd`，`exit 2` 拦截 | 本地跨目录调用需取得原生有效执行目录，见 `codex-runtime-integration-design.md` 第 4 节及原生复现记录 |

## 3. 验收清单

产出物按 1.2 术语表判定：hook 脚本、清单文件、skill 都是**生产代码**。级别按 3.1.2 判为**开发级**：插件只在 Claude Code 或 Codex 干活的过程中起作用。同类判定见 `docs/bash-gate-design.md:15`。开发级不进三类。

| # | 做什么 | 产出物·级别 | 场景／目标／结果 | 对应目标哪部分 |
|---|---|---|---|---|
| 1 | 加 Codex 插件清单 | 生产代码·开发级 | 场景：用户把本仓加成 Codex marketplace 后装 `watcher@orime`。目标：Codex 用 Codex 专用的 hook 配置。结果：`watcher/.codex-plugin/plugin.json` 的 `hooks` 指向 `./hooks/codex-hooks.json`，版本号和 `.claude-plugin/plugin.json` 一致 | 能装 |
| 2 | 加 Codex hook 配置 | 生产代码·开发级 | 场景：Codex 加载插件 hook。目标：三个脚本都挂上，并知道当前平台。结果：`codex-hooks.json` 的三个 command 都带参数 `codex`；`UserPromptSubmit` 的 handler 带 `"additionalContextLimit": 0` | 三个 hook |
| 3 | 规范在 Codex 里全文注入 | 生产代码·开发级 | 场景：Codex 用户每次提交 prompt。目标：模型拿到完整规范，工具名是 Codex 的。结果：模型上下文里有全文；Codex 版里没有 `workflow`、`TaskCreate`、`TaskUpdate`、`WebSearch`、`AskUserQuestion`、`CLAUDE.md`、`/watcher:`，换成 4.3 的 Codex 说法 | 规范注入 |
| 4 | Codex 子代理不注入规范 | 生产代码·开发级 | 场景：Codex 用 `spawn_agent` 派子代理，子代理收到任务时触发 `UserPromptSubmit`。目标：和 Claude Code 一样只给主会话注入。结果：输入带非空 `agent_id` 时 announce 不输出任何内容 | 规范注入 |
| 5 | Claude Code 版规范不变 | 生产代码·开发级 | 场景：Claude Code 用户每次提交 prompt。目标：现有行为不变。结果：不带参数时输出和改动前逐字节相同，仍 ≤ 9,500 | 不变 |
| 6 | bash 拦截在 Codex 里生效 | 生产代码·开发级 | 场景：Codex 在配了 `.watcher/` 的仓库主分支上 `git commit`，或标题不合规。目标：和 Claude Code 一样拦下。结果：调用被拦，模型收到原因 | bash 拦截 |
| 7 | Stop hook 在 Codex 里读对上下文用量 | 生产代码·开发级 | 场景：Codex 一轮结束。目标：状态行显示的用量和 Codex 自己的口径一致。结果：从 rollout 最后一条 `token_count` 取 `last_token_usage.total_tokens` 和 `model_context_window`，按实际窗口算百分比，写实际窗口大小，不带手动压缩建议；取不到就省掉上下文那一段，其余照显 | 收尾审计 |
| 8 | Codex 的 ON 出口 | 生产代码·开发级 | 场景：配了 `.watcher/` 且审计开着，一轮正常结束。目标：模型去跑 watcher skill。结果：`decision:block` 的 reason 指名 `watcher:watcher` skill 和它 `SKILL.md` 的绝对路径；用户命令写成 Codex 的显式调用写法 | 收尾审计 |
| 9 | Codex 的 OFF 和没配出口 | 生产代码·开发级 | 场景：审计关着或没配 `.watcher/`，一轮正常结束。目标：用户当场看到状态，本轮正常结束，模型在下一轮收到同样的文字，和 Claude Code 一致。结果：输出 `{"systemMessage": 状态文字}`；状态文字里的用户命令是 4.7 的写法，没有 `/watcher:`；同一段文字写进 `${PLUGIN_DATA}/pending-stop/<session_id>.txt`，同一会话后写的覆盖先写的；`PLUGIN_DATA` 为空时照常输出、不写文件；下一次根会话的 `UserPromptSubmit` 时 announce 把它完整接在规范后面输出并删掉文件；子代理的 `UserPromptSubmit` 不读也不删这个文件；7 天前的交接文件被删、新的保留；`notify` 照常触发 | 收尾审计 |
| 10 | 三条出口的判定和状态读写不变 | 生产代码·开发级 | 场景：两个平台的任意一轮。目标：Codex 只换输出和读数来源。结果：迁移、三个 skip 判定、`audit-state.json` 读写、`stop_hook_active` 防递归在两个平台上走同一段代码；带 `codex` 时三种 skip 都不输出、不留交接文件 | 收尾审计 |
| 16 | Claude Code 版 Stop 输出不变 | 生产代码·开发级 | 场景：Claude Code 一轮结束。目标：现有行为不变。结果：不带参数时，固定输入（ON、OFF、没配，各分有无 transcript）下，遮掉时间、CPU、内存那一段后，输出和 `origin/main` 上的 `suggest-watcher.sh` 逐字相同 | 不变 |
| 11 | 三个开关命令改成 skill | 生产代码·开发级 | 场景：用户在两个平台开关审计、建配置。目标：两个平台名字一致、内容同一份。结果：`commands/*.md` 移到 `skills/watcher-on/SKILL.md` 等三处；Claude Code 里 `/watcher:watcher-on` 等照常能用；Codex 里叫 `watcher:watcher-on` 等，没有 `source-command-*`；`watcher-configure` 里 setup-flow 的路径能解析到真实文件 | 两平台 skill |
| 12 | skill 正文两个平台都能照做 | 生产代码·开发级 | 场景：模型在 Codex 里读 6 个 SKILL.md 和它们的 references。目标：提到的工具、变量、命令写法在 Codex 里有对应。结果：6 个 SKILL.md 开头都有同一段「平台对照」（4.8），2.2 列出的 skill 正文位置都被它覆盖；frontmatter 和另两处直接改完：`watcher/SKILL.md:8` 不再写「调用 Skill 工具」，`watcher/SKILL.md:88` 写成两个平台通用，`playbook/SKILL.md:20` 写上 Codex 的规则文件和自带工具 | 全部 skill |
| 13 | `agent-paths.md` Codex 段改对 | 文案 | 生效目标：audit 时找对 Codex 的规则文件、skill 目录和记忆位置 | 收尾审计 |
| 14 | README 加 Codex 安装 | 文案 | 生效目标：Codex 用户能照着装上、在 `/hooks` 信任 hook、知道每次更新后要重新信任，并把输出风格放进 `~/.codex/AGENTS.md` | 能装 |
| 15 | smoke 覆盖 Codex | 测试代码 | 验证：`check-size.sh` 的 9,500 上限只管不带参数的输出，Codex 版只报长度；announce 用例断言 3、4、5 和 9 的接续（交接文字完整接在规范后、子代理不动文件、7 天清理、`PLUGIN_DATA` 为空）；`smoke-stop-hook.py` 的现有用例带参数和不带参数各跑一遍，再加 Codex 的 rollout 读数、`null` transcript、三条出口的输出形状、交接文件和命令写法，以及验收 16 的对比；`smoke-bash-gate.py` 加 Codex 输入形状；清单用例断言 1、2、11、12；CI 跑全部 | 4.2.6 |

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
│   ├── watcher/  playbook/  visual-adversary/          # 已有
│   └── watcher-on/  watcher-off/  watcher-configure/   # 从 commands/ 移来
└── output-styles/               # 只有 Claude Code 用
```

仓库根的 `.claude-plugin/marketplace.json` 两个平台都读。

### 4.2 平台怎么传给脚本

`codex-hooks.json` 的每条 command 末尾加参数 `codex`，例如：

```json
{"type": "command", "command": "bash \"${PLUGIN_ROOT}/hooks/announce-intent.sh\" codex", "timeout": 5, "additionalContextLimit": 0}
```

脚本读 `$1`：等于 `codex` 走 Codex 分支，其余走现在的 Claude Code 分支。`hooks.json` 保持原样。

### 4.3 announce-intent.sh

Codex 分支按顺序做三件事：

| 步 | 做什么 |
|---|---|
| 1 | 输入带非空 `agent_id`，直接退出，不输出。子代理和根会话共用 `session_id`（2.1），这一步必须排在第 3 步前面，交接文件才只被根会话读到 |
| 2 | 规范正文过一遍下面的替换表后输出 |
| 3 | `${PLUGIN_DATA}/pending-stop/<session_id>.txt` 存在，就在规范后面接一段「上一轮结束时 Stop hook 的输出：」加文件内容，然后删掉文件；顺手删掉同目录里 7 天前的文件 |

替换表：

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

替换表写在脚本里，用 `sed` 一次做完。Claude Code 分支不经过上面三步，输出逐字节不变。

### 4.4 suggest-watcher.sh

迁移、三个 skip 判定、`audit-state.json` 读写、`stop_hook_active` 防递归，两个平台走同一段代码（验收 10）。平台影响三件事。

**一、上下文读数。**

| 平台 | 读哪一行 | tokens | 窗口 | 告警 |
|---|---|---|---|---|
| Claude Code（不变） | 从末尾往前第一条带 `.message.usage.input_tokens` 的行 | `input + cache_read + cache_creation` | 1M | ≥85% 建议手动 `/compact` |
| Codex | 从末尾往前第一条 `.type=="event_msg" and .payload.type=="token_count" and .payload.info != null` 的行 | `.payload.info.last_token_usage.total_tokens` | `.payload.info.model_context_window` | 只显示读数；Codex 默认在 90% 自动压缩（2.1） |

两个平台的口径都对齐各自平台显示给用户的用量：Claude Code 对齐 `/context`（`suggest-watcher.sh:27`），Codex 对齐 `tokens_in_context_window`（2.1）。取不到时都省掉上下文那一段，时间、CPU、内存照显；`transcript_path` 为 `null` 也走这条。Stop 之前 Codex 不刷 rollout（2.1），读到的可能是上一次请求的数，真机验证里对比（第 6 节）。

**二、三条出口的输出。**

| 出口 | Claude Code（不变） | Codex |
|---|---|---|
| ON | `{"decision":"block","reason":状态+提醒}` | 同样用 `decision:block`；reason 第一行改成「用 `watcher:watcher` skill 跑本轮收尾，先读 `<PLUGIN_ROOT 展开后的绝对路径>/skills/watcher/SKILL.md`」 |
| OFF、没配 | `{"continue":false,"stopReason":状态文字}`：用户当场看到，模型下一轮作为 `Stop hook stopped continuation: X` 收到 | `{"systemMessage":状态文字}`：用户在 TUI 里当场看到 `↳ Hook ·` 那一行，本轮正常结束；同一段文字写进 `${PLUGIN_DATA}/pending-stop/<session_id>.txt`，由下一次 announce 交给模型（4.3 第 3 步） |

`systemMessage` 不改变本轮流程（2.1），所以 `notify` 和轮末压缩照常跑。交接文件按 `session_id` 分开，同一会话后写的覆盖先写的，和 Claude Code 只带最近一次 stop 文字一致。`PLUGIN_DATA` 为空时不写交接文件，其余照常。

**三、提示文字里的用户命令。** Codex 写成显式调用写法，见 4.7。

### 4.5 bash-gate.sh

`codex-hooks.json` 将脚本挂在 `PreToolUse`、`matcher: "Bash"` 上，命令字段和退出码沿用既有协议。Codex 继续支持原版跨目录提交检查：git -C、提交前 cd 和会话 cwd 定位目标仓库，目标仓库根有 .watcher/ 时执行既有规则。Codex 的独立执行上下文补齐显式 workdir 的目录信息。目标行为和验收见 `codex-runtime-integration-design.md` 第 3 节 R1、R2 及第 4 节。

### 4.6 三个命令改成 skill

`commands/watcher-on.md` 移到 `skills/watcher-on/SKILL.md`，另外两个同样处理，`commands/` 目录删掉。frontmatter 留 `name`、`description`，去掉 `command: true`。正文加 4.8 的平台对照段；`watcher-configure` 里的 `skills/watcher/references/setup-flow.md` 改成 `../watcher/references/setup-flow.md`，这是相对 skill 自己目录的路径，两个平台都按这个目录解析（Claude Code 给 skill 正文加「Base directory for this skill」，Codex 给 SKILL.md 绝对路径）。

移动的理由是两个平台名字一致：留在 `commands/` 时 Codex 会转成 `watcher:source-command-watcher-on`（2.1）。

| 平台 | 名字 | 用户怎么调 | 模型能不能自己调 |
|---|---|---|---|
| Claude Code | `watcher:watcher-on`，和现在一样 | `/watcher:watcher-on`，和现在一样 | 能，和现在一样（现在这三个命令就在模型的 skill 列表里） |
| Codex | `watcher:watcher-on` | 显式调用，见 4.7 | 能，`allow_implicit_invocation` 默认为 `true` |

「模型不要自己去关审计」仍由 Stop hook reason 里那句「这是留给用户的开关，Claude 别自作主张去关」管。

### 4.7 Codex 里用户怎么显式调 skill

写法是 `$watcher:watcher-on`。Codex 从用户文字里取 `$` 后面的名字，名字允许 `a-z A-Z 0-9 _ - :`（`skills/src/mentions.rs:226-228`），再和 skill 列表里的名字精确匹配（`skills/src/selection.rs` 的 `select_skills_from_mentions`）；插件 skill 在列表里的名字是 `watcher:watcher-on`（2.1）。TUI 和 `codex exec` 都走这段逻辑，第 6 节的真机验证用 `codex exec` 跑一次。

### 4.8 skill 正文：平台对照段

6 个 SKILL.md（watcher、playbook、visual-adversary、watcher-on、watcher-off、watcher-configure）开头、frontmatter 之后放同一段：

| 正文里的写法 | 在 Codex 里 |
|---|---|
| Read、Edit、Write、Bash 工具 | `exec_command` 读文件和跑命令，`apply_patch` 改文件 |
| WebSearch、WebFetch | 联网搜索 |
| workflow | `spawn_agent`；判「对抗是否跑成」看每个子代理的 `wait` 结果都是 completed 且没有报错（对应 `agents_error`、`agents_done`、`agent_count`） |
| Monitor | `gh pr checks <N> --watch` 盯 CI，`gh pr view <N> --json state,mergeStateStatus,reviewDecision` 看合并和 review |
| `/watcher:…`、`/watcher` | 4.7 的写法 |
| `CLAUDE.md` | `AGENTS.md` |
| `${CLAUDE_SKILL_DIR}` | 本 SKILL.md 所在目录的绝对路径 |
| CC、Claude Code | Codex |
| Skill 工具 | 读对应 skill 的 SKILL.md |

references 文件都在读完 SKILL.md 之后才读，这一段能管到它们。smoke 断言 6 个 SKILL.md 都含这一段，并且内容相同。

另外三处直接改：`watcher/SKILL.md:8` 在 frontmatter 里，平台对照段管不到，「调用 Skill 工具 watcher」改成「要求调用 watcher skill」；`watcher/SKILL.md:88` 的「一个 CC 会话」改成「一个会话」；`playbook/SKILL.md:20` 的规则文件和自带工具加上 Codex。

`agent-paths.md` 的 Codex 段按 2.1 改：skill 目录、插件 skill 的位置和名字、`~/.codex/memories/`。`~/.codex/memories/` 的用途先查官方文档再写，查不到就只写「目录存在、用途没查到出处」。

### 4.9 输出风格

README 写明：Codex 用户把 `output-styles/chinese-engineering.md` 正文（frontmatter 以下）放进 `~/.codex/AGENTS.md`。插件不改用户的全局配置。

### 4.10 状态和数据流转

`audit-state.json` 的状态和转移不变。Stop 输出送到谁、本轮会不会再起、Stop 之后 Codex 还跑什么，两个平台不一样，流转演示见 `docs/codex-stop-flow.html`。

## 5. 依赖和选择

基础适配依赖 bash、jq、sed。自动 WezTerm 任务面板另依赖 Python 3.11+ 标准库、WezTerm CLI 及具备运行能力协议的配套 Codex 客户端和 daemon，交付要求见 `codex-runtime-integration-design.md` 第 9、10 节。

| 选择 | 依据 |
|---|---|
| 一个插件目录、两份清单、脚本共用 | Codex 读 `.codex-plugin/plugin.json`，并为兼容设 `CLAUDE_PLUGIN_ROOT`（2.1）；共用脚本只有一份实现 |
| 平台由 hook 配置传参数 | 两份 hook 配置本来就分开写，参数随各自的配置传入，脚本只读 `$1` |
| announce 用替换表生成 Codex 版 | 规范正文只有一份，Claude Code 版逐字节不变（验收 5） |
| OFF、没配在 Codex 上用 `systemMessage` 加交接文件 | Codex 的 Stop 只有 block 能进模型，block 会再起一轮；`continue:false` 会跳过 `notify` 和轮末压缩（2.1）。交接给下一次 `UserPromptSubmit` 和 Claude Code 的送达时机一样：下一次用户发言时进上下文（`suggest-watcher.sh:24-25`） |

## 6. 验证

| 层 | 做什么 |
|---|---|
| smoke（CI） | 验收 15 列的全部用例 |
| Codex 真机 | 从本 worktree 加 marketplace、装 `watcher@orime`，在一个配了 `.watcher/` 的临时 git 仓用 `codex exec --dangerously-bypass-hook-trust` 跑：announce 全文进上下文且没有 `hook_outputs` 文件；主分支 `git commit` 被拦；ON 时模型读了 `skills/watcher/SKILL.md`；OFF 时本轮正常结束，交接文件名等于 Stop 输入里的 `session_id`；用 `codex exec resume <session_id>` 跑下一轮，developer 消息里有交接文字、交接文件被删；配一个临时 `notify` 程序，OFF 和没配两种出口后它都被调到；派一个子代理，子代理的 rollout 里没有规范；hook 在 Stop 时读到的用量和这一轮结束后 rollout 最后一条 `token_count` 对比；skill 列表里有 `watcher:watcher-on` 等、没有 `source-command-*`。再在 TUI 里试：4.7 的写法、`/hooks` 信任流程、OFF 和没配出口时出现 `↳ Hook ·` 那一行状态文字。跑完卸载、删 marketplace、删会话，`~/.codex/config.toml` 和跑之前逐字一致 |
| Claude Code 真机 | `claude -p --plugin-dir <worktree>/watcher`：三个开关 skill 能用 `/watcher:watcher-on` 等调用，`watcher-configure` 读到了 setup-flow；announce 和 main 上逐字相同；Stop 输出遮掉时间、CPU、内存后和 main 上逐字相同；bash 拦截行为不变 |
