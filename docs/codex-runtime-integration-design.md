# Codex 运行集成补充设计

## 1. 目标与状态

完成 CC hooks 的 Codex 适配，并在 Codex 的交互终端是 WezTerm 时自动显示、恢复和同步下方任务面板。

本文是待审查的补充设计。当前实现状态以 `codex-support-design.md`、任务分支代码和仓库外的原生验证记录为依据；本文第 4 至 9 节描述拟实现行为。涉及原设计第 4.5 节的工作目录结论，以本轮复现为修订依据，修订须随设计审查确认。

用户已确认将 Codex CLI 工作目录修复纳入任务，并确认面板集成到 CC hooks。现有分支为 `feat/codex-support`，基线提交为 `b019fc8`。项目已有 smoke，缺少的 DD、TDD、选择澄清流程按原设计第 1 节及本次协作规范执行。

## 2. 本轮查证

| 事实 | 证据 | 对设计的约束 |
|---|---|---|
| `exec_command` 使用选定环境解析 `workdir`，PreToolUse 输入仅保留命令 | [exec_command.rs:173](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#L173)、同文件 `pre_tool_use_payload`；`codex-support-validation-2026-10-22/native-gate.json` | 有效执行目录须通过原生接口传递 |
| hook 的 `.cwd` 同时用于启动本地 hook 子进程 | [pre_tool_use.rs:84](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/hooks/src/events/pre_tool_use.rs#L84)、`hook_runtime.rs:235` | hook 目录与工具执行目录须分别表达 |
| interactive 和 one-shot shell 共用 ExecCommandHandler | [spec_plan.rs:1181](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/spec_plan.rs#L1181) | 共用解析入口覆盖两种执行方式 |
| PlanHandler 继承默认 hook payload；成功结果后同步调用 PostToolUse | [plan.rs:94](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/handlers/plan.rs#L94)、[registry.rs:107](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/registry.rs#L107)、同文件 `759` | 计划缓存可接入现有原生 hook |
| Code Mode 的委派也进入 registry | [code_mode/mod.rs:379](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/code_mode/mod.rs#L379)、[router.rs:355](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/router.rs#L355) | 须实测直接工具和 Code Mode 两条路径 |
| 用户根线程及新 fork 根线程的 session_id 对应自身线程；子代理共用会话树身份 | [session/session.rs:892](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/session/session.rs#L892)、[hook_runtime.rs:128](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/hook_runtime.rs#L128) | 面板保存根线程；PostToolUse 过滤 agent_id |
| hook 环境来自宿主进程快照，SessionStart 输入缺少当前连接的终端信息 | [hooks/registry.rs:68](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/hooks/src/registry.rs#L68)、[command_runner.rs:397](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/hooks/src/engine/command_runner.rs#L397)、[session_start.rs:40](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/hooks/src/events/session_start.rs#L40) | 自动启动须接收当前 TUI 的连接上下文 |
| 已加载线程的 resume 路径直接附着并返回 | [thread_processor.rs:3683](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L3683) | 重新打开 TUI 的启动触发须覆盖此路径 |
| SessionStart 当前通过 pending 队列在 turn 处理中执行 | [hook_runtime.rs:128](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/hook_runtime.rs#L128) | 启动面板的交互 attach 须有及时触发点 |
| PlanUpdate 属于非持久化事件 | [rollout/policy.rs:149](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/rollout/src/policy.rs#L149) | 恢复来源为插件保存的成功计划快照 |
| 单 worker 的非并行工具锁覆盖同步 PostToolUse，锁属于 runtime 实例 | [parallel.rs:49](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/parallel.rs#L49)、同文件 `196`；[delegate.rs:112](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/code_mode/delegate.rs#L112) | 跨 runtime 的计划顺序须在根线程范围串行化 |
| 本机已有 curses 任务显示实现及 MIT 许可证 | `/Users/songxiulei/Desktop/Unit_Agent/multi-cc-im/scripts/task-panel.py:21`、`:66`、该仓 `LICENSE:3` | 复用显示与字符裁剪逻辑并保留许可 |

原生复现中，会话 cwd 是 `work_temp`，命令 workdir 是临时 Git 仓库。同一 feature 分支提交被 hook 按 `work_temp` 判定而拦截；显式 `git -C` 提交成功。记录中的临时仓库已清理。

## 3. 验收清单

原适配设计的验收清单继续适用。下表对应新增面板目标及原生工作目录缺口。

| 编号 | 产出物及级别 | 处境、目标及可核验结果 | 对应目标 |
|---|---|---|---|
| R1 | Codex 执行上下文、hook schema，生产代码·开发级 | 同一会话跨仓库执行命令；hook 收到执行器解析出的本地有效目录，main 被拦，feature 合规提交放行；hook 自身 cwd 保持兼容 | 正确执行提交规则 |
| R2 | 插件 gate 及测试，生产代码·开发级、测试代码 | 本地 `workdir`、相对 `git -C`、命令内 `cd` 组合指向真实仓库；判定及英文测试覆盖各组合 | 正确执行提交规则 |
| R3 | Codex 当前客户端上下文，生产代码·开发级 | 两个 TUI 共享 daemon，分别在不同 WezTerm pane；启动输入对应各自当前 pane；exec 与子代理的启动保持自身身份 | 自动绑定对应终端 |
| R4 | 插件启动 hook，生产代码·用户级·承诺内 | 已信任插件，在 WezTerm 启动或恢复 Codex；首条用户输入前出现下方任务面板，输入焦点回到上方 Codex；重复触发后对应父 pane 保持一个面板 | 自动启动 |
| R5 | 同步 PostToolUse 缓存，生产代码·用户级·承诺内 | 根线程成功 update_plan 后，名称、顺序、状态和清空操作在下一次 1 秒刷新内显示；其他会话及子代理保持各自状态 | 同步真实计划 |
| R6 | 会话与面板绑定文件，生产代码·用户级·承诺内 | 重开或切换根会话后复用面板，显示目标会话保存的计划；新会话及没有保存快照的历史会话显示等待；旧会话更新保持写入自己的缓存 | 恢复与隔离 |
| R7 | 面板显示及生命周期，生产代码·用户级·承诺内 | 中文、空列表、长文本、多任务、缩放、错误均可辨认；上下键和 PageUp/PageDown 可浏览任务；q 关闭，当前 attach 保持关闭，新 attach 可重开 | 固定显示并可操作 |
| R8 | 插件发布目录及许可，生产代码·开发级、文案 | 独立安装的插件包含脚本与源许可；运行依赖为既有 bash/jq 及 Python 3.11+ 标准库；运行路径从 PLUGIN_ROOT/PLUGIN_DATA 得到 | 可独立安装 |
| R9 | 故障说明、smoke 和真实运行记录，测试代码、文案 | 缺依赖、IPC 失败、非法输入、并发启动、晚到启动响应均有明确结果；Codex 可继续工作；已有三个 hook 及 Claude Code 回归符合原验收 | 完整交付 |

## 4. 原生工作目录修复

从 `ExecCommandHandler::handle_call` 提取 `resolve_exec_environment_and_cwd`。执行器与 hook 元数据生成共同调用，输入是同一 StepContext 和 ExecCommandEnvironmentArgs。空 workdir 使用选定环境 cwd，相对路径以该环境 cwd 解析，非法环境或路径沿用执行器错误。

PreToolUse 顶层追加可选 `tool_execution_context`。`environment_id` 为选定环境标识，`is_remote` 表示执行环境位置，`cwd` 在本地环境中是绝对本地路径，在远端环境中是环境路径 URI。`.cwd` 继续表示本地 hook 运行目录；`tool_input.command` 及 command rewrite 的现有语义保持。

元数据解析接口返回 `Result`，错误时工具调用返回错误。默认 handler 返回空执行上下文；ExecCommandHandler 接入共用解析器。此内部接口在实现时须覆盖现有 override 和调用方。write_stdin 继续沿用已有进程路径。

插件取得本地执行目录后，按顺序解释命令内有效 cd，再解释 commit 所在段的 `git -C`。每段相对路径以前一有效目录为基准；带空格路径保留完整参数。根目录 `.watcher/`、分支和提交标题继续由现有 gate 负责。Claude Code 输入继续使用 `.cwd`。

本次本地 Git 策略验收覆盖本机执行环境。远端执行上下文须标识准确；插件收到 remote 的 commit 时输出当前本地 gate 无法核验该执行环境的诊断并拦截。此行为属于待确认的承诺外处理，不声称完成远端 Git 策略支持。

## 5. 当前终端与启动时机

### 5.1 连接上下文

TUI 在 initialize 时提交可选 typed `terminalContext`，内容为 `frontend`、`program`、`paneId`、`unixSocket`。交互 TUI 的 frontend 为 `tui`；exec 为 `exec`。字段从前端自身读取，按连接保存在 ConnectionSessionState。字符串长度、pane ID 和 socket 路径在边界验证；此上下文属于显示定位信息。

当前连接 start、resume、fork 时，将上下文与 attach ID 一起传给启动 hook。hook JSON 新增可选 `client_context`，包含 `frontend`、`terminal_program`、`wezterm_pane`、`wezterm_unix_socket`、`attachment_id`。上下文按这次 attach 使用，客户端断开后失效。

插件启动条件为 Codex hook 配置、根线程、`frontend=tui`、`terminal_program=WezTerm`，以及有效 pane 和同用户 Unix socket。wezterm 可执行程序从 PATH 查找。调用 CLI 时显式指定 socket 和父 pane。

### 5.2 及时且幂等的触发

交互 TUI 完成根线程 attach 后，首条输入前运行一次 SessionStart。新建为 startup，恢复（包含已加载线程）为 resume，fork 为 fork，clear 为 clear。该次 attach 已执行的启动事件从 pending 队列消费，后续首轮沿用已保存的 hook context。已有非交互生命周期继续使用原有调度。

同一 attach ID 的重试保持同一启动身份。新的交互 attach 使用新的 ID。多个客户端附着同一根线程时，各自的启动输入携带各自 pane；计划缓存由根线程共享。

这部分为原生集成设计推断，需独立审查生命周期控制效果、pending 消费和已运行 turn 的上下文注入。实现必须保留 SessionStart 的停止、错误和额外上下文语义。

## 6. 插件结构与数据

| 文件 | 主要职责 |
|---|---|
| `watcher/hooks/codex-hooks.json` | 保留已有三个事件；增加 SessionStart、PostToolUse `^update_plan$`、SessionEnd |
| `watcher/hooks/task-panel.sh` | 检查 Python 前提并将事件交给 Python 入口 |
| `watcher/hooks/task_panel_hook.py` | 校验事件、执行 WezTerm CLI、协调启动与关闭 |
| `watcher/hooks/task_panel_store.py` | 唯一文件读写入口，处理锁、结构校验及原子重命名 |
| `watcher/hooks/task_panel.py` | curses 显示、滚动、缩放和键盘操作 |
| `watcher/third-party/multi-cc-im.LICENSE` | 复用代码的完整 MIT 声明及来源 |

数据位于 `${PLUGIN_DATA}/task-panel/`。目录权限 0700，JSON 和锁文件 0600。会话 ID 校验后作为 `plans/<session_id>.json` 的文件名。父 pane 的绑定键取 socket 路径和 pane ID 的 SHA-256，写到 `bindings/<key>.json`。

计划文件包含 `version`、`session_id`、`title`、`plan`、`updated_at`；plan 为 `{step, status}` 数组，status 使用 `pending`、`in_progress`、`completed`。空数组是有效的清空。缓存写入由同步根 PostToolUse 完成，返回前完成落盘。错误输入给出诊断，保留上次有效快照。

绑定文件包含 `version`、父 pane、面板 pane、会话 ID、attach ID、实例 nonce 及状态。生命周期操作按绑定键加 `fcntl.flock`；计划操作按会话加独立锁。所有写入经 store 模块校验与原子替换；显示端只读完整快照。

为保证跨 Code Mode runtime 的顺序，拟在 Codex registry 的 plan dispatch 外层取得 Session 所属的计划锁，持有到同步 PostToolUse 完成。锁覆盖同一根线程的计划发出与缓存回调，其他 handler 沿用既有调度。此为内部设计推断，需核对取消、重入和锁释放路径。

### 6.1 面板创建与复用

启动入口在绑定锁内核对 CLI list 中父 pane 和已有面板的实例标题。有效面板更新绑定；新面板通过 `split-pane --pane-id <parent> --bottom --cells 10 -- ...` 启动。viewer 从 WezTerm 获取自己的 pane ID，使用 nonce 标记标题并确认当前绑定，启动入口随后 `activate-pane` 恢复上方焦点。

子程序使用参数数组、总计 3 秒的 CLI 操作预算，hook timeout 为 5 秒。创建结果不确定时记录 starting 和 nonce；下一次重试先核对同 nonce 的 pane。晚到 viewer 核对当前绑定及 nonce，失效实例关闭自身。正常重复启动最终保留一个有效面板；测试须覆盖响应晚到和重复事件。

用户 q 关闭时，为当前 attach 记录 closed。计划更新继续保存；当前 attach 的重复事件保持 closed。新的 attach 可重新创建。父 pane 消失时 viewer 结束并清理自己的绑定；SessionEnd 标记对应会话结束，显示最后计划与 ended 状态，直到新 attach 或用户关闭。

### 6.2 空、错误及退出

没有有效快照显示 `Waiting for the first plan update`。安装插件前的历史计划需要后续成功的 update_plan 建立插件快照。缺 Python、wezterm、curses、PLUGIN_DATA 或 IPC 访问能力时，启动 hook 返回一条含下一步操作的 systemMessage，并正常结束。故障状态保留在绑定记录以便下一次 attach 重试。

已有快照读取失败时面板显示 `Unable to read saved tasks`，恢复有效文件后自动刷新。终端太小时保留标题和可见范围提示。关闭范围由当前父 pane 绑定及实例 nonce 确认。

## 7. 状态流转

生命周期状态全集为 `absent`、`starting`、`visible`、`closed`、`error`、`ended`。计划缓存与生命周期分开；每个状态的写入入口为 store 的绑定更新函数，调用方必须持有对应绑定锁。

事件全集如下。`attach` 包括 root startup/resume/fork/clear；`duplicate` 是同 attach 重复触发；`ready` 是 viewer 的 nonce 确认；`fail` 包括创建失败或超时；`plan` 是根线程成功更新；`foreign` 是其他会话或子代理事件；`close` 是 q 或用户关闭；`gone` 是父 pane 消失；`end` 是 SessionEnd；`resize` 是终端尺寸变化。每个单元格的“推断”表示本次拟定行为，原生事件来源见第 2 节。

| 当前状态 | attach（新 ID） | duplicate | ready | fail | plan | foreign | close | gone | end | resize |
|---|---|---|---|---|---|---|---|---|---|---|
| absent | starting，推断 | starting，推断 | 核 nonce，失效退出，推断 | error，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | 保持，推断 | 保持，推断 | 保持，推断 |
| starting | 更新绑定，保持，推断 | 核同 nonce，保持，推断 | visible，推断 | error 并核晚到实例，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | ended，推断 | 保持，推断 |
| visible | 更新绑定，保持，推断 | 核所有权，保持，推断 | 同 nonce 保持，推断 | error，推断 | 保存并刷新，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | ended，推断 | 重绘，保持，推断 |
| closed | starting，推断 | 保持，推断 | 失效实例退出，保持，推断 | 保持，推断 | 保存，保持，推断 | 保持，推断 | 保持，推断 | absent，推断 | 保持，推断 | 保持，推断 |
| error | 核实例后 starting，推断 | 核实例后 starting，推断 | 有效 nonce 则 visible，推断 | 保持，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | ended，推断 | 保持，推断 |
| ended | 复用或 starting，推断 | 保持，推断 | 有效实例显示 ended，推断 | error，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | 保持，推断 | 重绘，保持，推断 |

不变量是每个父 pane 最终对应一个有效实例，计划按根会话隔离，子代理保持其独立状态，用户关闭在当前 attach 内生效，故障保留有效计划。原生 plan dispatch 锁约束成功更新及同步回调的次序；文件锁约束完整写入。

## 8. 界面与演示

演示为 `codex-runtime-integration-demo.html`。第一页显示 Codex 在上、任务在下的固定结构，可操作启动、创建计划、推进状态、重复启动、切换会话、恢复、关闭、故障和结束；第二页按自上而下显示启动、计划更新和目录校验的数据流转。

任务面板默认 10 行；标题包含项目及完成数，第二行显示会话与连接状态，随后是任务列表，底行显示操作与范围。任务过多时滚动浏览，长文本按终端字符格裁剪并显示截断标识。中文宽字符及组合字符使用现有裁剪逻辑，控制字符按显示数据过滤。小尺寸先保留标题及范围提示，增大后恢复任务区域。

界面颜色继承终端；状态同时使用文字和 `[x]`、`[>]`、`[ ]`。键盘上/下和 PageUp/PageDown 滚动，q 关闭。终端界面采用键盘交互；HTML 的按钮有 hover、focus 和禁用态。刷新间隔 1 秒，无额外动画。演示包含浅色、深色和窄宽度选择。尺寸与字符格在真实 WezTerm 验证。

## 9. 复用、依赖与方案依据

| 候选 | 完整能力 | 本次匹配情况 | 处理 |
|---|---|---|---|
| multi-cc-im 完整 observer 和 viewer | App Server 连接、后续计划事件、缓存、重连、curses 显示 | 包含 ws/zod；当前终端身份及首次事件前恢复仍需集成 | 保留为已评估完整候选 |
| 原生 hook 与 Python store/viewer | 成功计划同步保存、启动恢复、固定显示 | 原生已有 hook 路径；新增上下文和调度补齐自动绑定 | 拟采用并验证 |

| 依赖 | 版本或来源 | 许可证及用途 |
|---|---|---|
| bash、jq | 既有插件依赖 | 继续沿用 |
| Python | 3.11+，标准库 json、fcntl、subprocess、curses、unicodedata | 本机运行时；发布包包含 Python 脚本 |
| curses viewer 及字符裁剪 | multi-cc-im 当前 `scripts/task-panel.py` | 已读取完整 MIT；保留版权和许可 |
| WezTerm CLI | 本机 20240203-110809-5046fc22；需验证实际 IPC | 使用用户已安装终端；[split-pane](https://wezterm.org/cli/cli/split-pane.html)、[list](https://wezterm.org/cli/cli/list.html)、[activate-pane](https://wezterm.org/cli/cli/activate-pane.html) |

任务显示查阅了五个独立产品的一手资料，其能力分别如下。这些资料证明显示与会话恢复模式；具体 hook 数据流以本项目原生源码为依据。

| 产品 | 官方材料中的行为 | 来源 |
|---|---|---|
| Claude Code | 可切换任务状态区，保存展开状态并在有任务的恢复会话中还原 | [Interactive mode / Task list](https://code.claude.com/docs/en/interactive-mode#task-list) |
| Gemini CLI | write_todos 更新输入上方进度，状态按会话保存，Ctrl+T 展开 | [Todo tool](https://geminicli.com/docs/tools/todos/) |
| Roo Code | 任务标题显示摘要，工具区显示完整任务及状态 | [Task Todo List](https://roocodeinc.github.io/Roo-Code/features/task-todo-list/) |
| Cline | Focus Chain 跟随任务更新清单 | [官方发布说明](https://cline.bot/blog/cline-v3-25) |
| Codex | 原生 plan 事件，以及 TUI 的 task-progress 摘要 | [App Server](https://learn.chatgpt.com/docs/app-server)、[status_surfaces.rs:1038](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/tui/src/chatwidget/status_surfaces.rs#L1038) |

**纯内部判断**：连接上下文字段、根线程计划串行锁、缓存目录结构和绑定状态表是本次设计推断。它们的判断依据分别是宿主环境快照、runtime 锁的作用域、插件可写目录及 WezTerm pane 生命周期。设计对抗应优先查这四项。

## 10. 验证与交付限制

| 层次 | 实跑要求 |
|---|---|
| 失败测试先行 | 有效目录及 schema；命令路径组合；当前连接终端；已加载 resume；插件缓存、幂等创建、关闭与迟到实例 |
| 单元及受影响范围 | 原生 hooks、core、app-server protocol 及客户端调用方检查；插件已有六项 smoke 加面板 smoke；完整许可和发布路径校验 |
| 原生集成 | 直接 update_plan 与 Code Mode 的真实 PostToolUse 输入；成功、失败和子代理路径；共享 daemon 的两个 TUI；headless exec；冷启动与已加载 resume 在首条输入前启动 |
| 顺序与生命周期 | 同 worker 和跨 worker 计划更新；取消；并发启动；split 超时晚到；q；父 pane 退出；不同会话切换；SessionEnd；插件更新路径 |
| UI 实际使用 | 在真实 WezTerm 操作启动、更新、滚动、缩放和恢复，记录父/子 pane、焦点、字符布局、截图和执行结果 |
| 对抗与最终交付 | 设计对抗确认后 TDD；运行验证后实现对抗；视觉对抗；文档与文案对抗；同步最新主分支后最终验证；PR、CI、合并和清场 |

当前终端 GitHub 下载和 Git fetch 有连接或 DNS 失败，WezTerm IPC 曾返回权限错误，嵌套 Codex 启动曾返回 workspace routing discovery failed。这些外部限制仍须在对应验证步骤解决；本文中的拟实现行为尚不代表运行验证通过。
