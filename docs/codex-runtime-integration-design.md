# Codex 运行集成补充设计

## 1. 目标与状态

完成 CC hooks 的 Codex 适配，并在 Codex 的交互终端是 WezTerm 时自动显示、恢复和同步下方任务面板。

2026-10-24 用户明确保留原版跨目录提交检查能力。目录适配的验收基线是原版已有的 git -C、提交前 cd、会话 cwd 定位及目标仓库 .watcher/ 作用域，同时补齐 Codex workdir 与 hook 输入之间的实际差异。第 3 节 R1、R2 和第 4 节按本次要求执行。

本文是第二轮独立设计审查后的修订稿。2026-10-22 用户已确认第一轮四项审查结论、第二轮统一启动协调方案和演示结构；修订对应关系见 `codex-runtime-integration-review.md`。本文第 4 至 10 节描述拟实现行为，运行验证状态见第 11 节。原适配设计第 4.5 节的工作目录结论随确认结果修订。

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
| R1 | Codex 执行上下文、hook schema，生产代码·开发级 | Codex 为命令指定本地 workdir；hook 取得对应执行目录，受管 main 提交被拦、功能分支合规提交通过；hook 自身 cwd 保持兼容 | 补齐 Codex 目录传递差异 |
| R2 | 插件 gate 及测试，生产代码·开发级、测试代码 | 保留原版跨目录提交检查：git -C、提交前 cd、会话 cwd 定位目标仓库，目标根存在 .watcher/ 时执行已有分支和提交信息规则；测试对照原版能力及 Codex workdir 差异 | 保持原版功能兼容 |
| R3 | Codex 当前客户端上下文，生产代码·开发级 | 两个 TUI 共享 daemon，分别在不同 WezTerm pane；启动输入对应各自当前 pane；exec 与子代理的启动保持自身身份 | 自动绑定对应终端 |
| R4 | 插件启动 hook，生产代码·用户级·承诺内 | 已信任插件，在 WezTerm 启动或恢复 Codex；首条用户输入前出现下方任务面板，输入焦点回到上方 Codex；重复触发后对应父 pane 保持一个面板 | 自动启动 |
| R5 | 同步 PostToolUse 缓存，生产代码·用户级·承诺内 | 根线程已生效的 update_plan，其名称、顺序、状态和清空操作在缓存写入后的下一次 1 秒刷新内显示；用户取消后，已提交计划的同步回调按配置时限完成；其他会话及子代理保持各自状态 | 同步真实计划 |
| R6 | 会话与面板绑定文件，生产代码·用户级·承诺内 | 重开或切换根会话后复用面板，显示目标会话保存的计划；新会话及没有保存快照的历史会话显示等待；旧会话更新保持写入自己的缓存 | 恢复与隔离 |
| R7 | 面板显示及生命周期，生产代码·用户级·承诺内 | 中文、空列表、长文本、多任务、缩放、错误均可辨认；上下键和 PageUp/PageDown 可浏览任务；q 关闭，当前 attach 保持关闭，新 attach 可重开 | 固定显示并可操作 |
| R8 | 插件及配套 Codex 构建产物、许可与安装说明，生产代码·开发级、文案 | 插件包含脚本与源许可；配套客户端和 daemon 提供第 10 节的运行能力；安装说明记录来源提交、平台、校验值和启动命令；脚本依赖为既有 bash/jq 及 Python 3.11+ 标准库，插件路径从 PLUGIN_ROOT/PLUGIN_DATA 得到 | 可独立安装 |
| R9 | 故障说明、smoke 和真实运行记录，测试代码、文案 | 缺依赖、能力缺失或不匹配、IPC 失败、非法输入、并发启动、starting 写入后进程中断、晚到响应、计划回调故障均有明确结果及恢复路径；期限内重开后保持空闲，启动协调仍自行推进到可见面板或含操作说明的故障诊断；Codex 可继续工作；已有三个 hook 及 Claude Code 回归符合原验收 | 完整交付 |

## 4. 原生工作目录修复

从 `ExecCommandHandler::handle_call` 提取 `resolve_exec_environment_and_cwd`。执行器与 hook 元数据生成共同调用，输入是同一 StepContext 和 ExecCommandEnvironmentArgs。空 workdir 使用选定环境 cwd，相对路径以该环境 cwd 解析，非法环境或路径沿用执行器错误。

PreToolUse 顶层追加可选 `tool_execution_context`。`environment_id` 为选定环境标识，`is_remote` 表示执行环境位置，`cwd` 在本地环境中是绝对本地路径，在远端环境中是环境路径 URI。`.cwd` 继续表示本地 hook 运行目录；`tool_input.command` 及 command rewrite 的现有语义保持。

元数据解析接口返回 `Result`，错误时工具调用返回错误。默认 handler 返回空执行上下文；ExecCommandHandler 接入共用解析器。此内部接口在实现时须覆盖现有 override 和调用方。write_stdin 继续沿用已有进程路径。

提交检查根据命令定位目标仓库。目录来源延续原版已有的 git -C、提交前 cd 和会话 cwd，并接入 Codex 显式 workdir 对应的执行上下文。目标仓库根目录的 .watcher/ 是启用条件，符合原版规则的主分支与提交信息检查继续执行。

| 命令目标 | 检查结果 |
|---|---|
| 当前项目及普通子目录，仓库根有 .watcher/ | 执行已有分支和提交信息规则 |
| 另一个本地项目，仓库根有 .watcher/ | 同样执行已有规则 |
| 本地目标仓库根没有 .watcher/ | 放行 |

目录适配以原版正常能力和实际 Codex 输入差异为验收依据。其他 shell 配置与执行语义扩展须证明其对应的已支持行为或实际需求，再按问题归属处理。历史实验能证明现象存在，功能必要性另按本节目标判断。相关研究记录见 codex-shell-launch-context-design.md。

原生远端上下文继续提供标识和环境路径 URI；本地 gate 沿用已定的远端说明与放行边界。任务面板继续按已确认的显示与同步设计执行。

## 5. 当前终端与启动时机

### 5.1 连接上下文

TUI 在 initialize 时提交可选 typed `terminalContext`，内容为 `frontend`、`program`、`paneId`、`unixSocket`。交互 TUI 的 frontend 为 `tui`；exec 为 `exec`。字段从前端自身读取，按连接保存在 ConnectionSessionState。字符串长度、pane ID 和 socket 路径在边界验证；此上下文属于显示定位信息。

当前连接 start、resume、fork 时，将上下文与 attach ID 一起传给启动 hook。hook JSON 新增可选 `client_context`，包含 `frontend`、`terminal_program`、`wezterm_pane`、`wezterm_unix_socket`、`attachment_id`；同时提供第 10 节的 `hook_capabilities`。上下文按这次 attach 使用，客户端断开后失效。

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
| `watcher/hooks/task_panel_hook.py` | 校验事件，由唯一启动协调入口推进创建与恢复，执行 WezTerm CLI 并协调关闭 |
| `watcher/hooks/task_panel_store.py` | 唯一文件读写入口，处理锁、结构校验及原子重命名 |
| `watcher/hooks/task_panel.py` | curses 显示、滚动、缩放和键盘操作 |
| `watcher/third-party/multi-cc-im.LICENSE` | 复用代码的完整 MIT 声明及来源 |

数据位于 `${PLUGIN_DATA}/task-panel/`。目录权限 0700，JSON 和锁文件 0600。会话 ID 校验后作为 `plans/<session_id>.json` 的文件名。父 pane 的绑定键取 socket 路径和 pane ID 的 SHA-256，写到 `bindings/<key>.json`。

计划文件包含 `version`、`session_id`、`title`、`plan`、`updated_at`；plan 为 `{step, status}` 数组，status 使用 `pending`、`in_progress`、`completed`。空数组是有效的清空。缓存写入由同步根 PostToolUse 完成，返回前完成落盘。错误输入给出诊断，保留上次有效快照。

绑定文件包含 `version`、父 pane、面板 pane、会话 ID、attach ID、实例 nonce、状态、`starting_created_at` 和 `starting_deadline`。生命周期操作按绑定键加 `fcntl.flock`；计划操作按会话加独立锁。所有写入经 store 模块校验与原子替换；显示端只读完整快照。

为保证跨 Code Mode runtime 的顺序，在 Codex registry 的 PlanHandler dispatch 外层取得 Session 所属的计划锁，持有到同步 PostToolUse 完成。锁覆盖同一根线程的计划生效及缓存回调；由已注册 PlanHandler 提供提交阶段标记，其他 handler 沿用既有调度。这是内部集成设计，取消语义如下。

### 6.1 计划提交与取消

计划在等待锁、PreToolUse 和参数验证期间响应取消。参数验证结束后，在发出 PlanUpdate 前进行最后一次取消检查；随后将该 dispatch 标记为 committed。该标记是提交点，进入已生效计划的发布与同步阶段。

PlanHandler 沿用原生 `finishes_on_cancellation` 的完成机制。外层 parallel 调度对该类调用等待内部取消检查或提交后的完成；registry 在 committed 之后使用独立完成令牌等待 PostToolUse。Session 持有已提交 dispatch 的完成任务，直到回调完成或到达配置时限；调用方离开和 Code Mode worker 取消均由同一提交标记处理。计划锁由完成任务持有，终态释放一次。所有权、外层 abort、内部 `or_cancel_tool` 及退出清理须在同一组原生集成测试覆盖。

插件保存回调使用同步 command hook，timeout 为 5 秒。正常缓存写入在回调返回前完成。回调失败或超时通过 Codex hook 诊断报告；显示端保留带保存时间的最近有效快照。后续成功的 update_plan 重新建立同步状态；恢复会话展示已保存的快照。用户看到失败诊断时，该次同步状态为失败。

| 计划阶段 | 用户取消或调用方离开 | 推进执行（获锁或验证完成） | 回调成功 | 回调失败或超时 |
|---|---|---|---|---|
| waiting | cancelled，释放等待，推断 | 取得锁后进入 validating，推断 | 无回调，保持，推断 | 无回调，保持，推断 |
| validating | cancelled，释放锁，推断 | 最后检查后进入 committed，推断 | 无回调，保持，推断 | 无回调，保持，推断 |
| committed | 完成任务继续等待有界回调，保持，推断 | 保持，提交标记只写一次，推断 | completed，释放锁，推断 | failed，报告同步诊断并释放锁，推断 |
| completed | 保持，推断 | 保持，推断 | 保持，推断 | 保持，推断 |
| failed | 保持，推断 | 保持，推断 | 保持，推断 | 保持，推断 |
| cancelled | 保持，推断 | 保持，推断 | 保持，推断 | 保持，推断 |

状态由 dispatch 完成任务的阶段更新函数唯一写入。waiting 和 validating 阶段的取消与 committed 之后的完成共用该入口。表内转移为本次内部设计推断，现有机制出处是 `parallel.rs:247` 及 `registry.rs:767`。

### 6.2 面板创建与复用

SessionStart 的 attach 与 duplicate 进入同一 `coordinate_panel` 函数。该函数在当前 hook 进程内同步完成创建协调，覆盖绑定锁等待、父 pane 和已有实例核对、等待旧尝试、到期重建、ready 确认和焦点恢复。`starting` 表示协调中的中间状态。调用的正常返回结果为面板可见；故障返回包含具体原因和恢复操作。用户关闭、父 pane 消失及被较新 attach 接管分别返回对应终止结果。

| 配置 | 数值及用途 | 预算归属 |
|---|---|---|
| 创建尝试期限 | 4 秒，落盘为 `starting_created_at` 和 `starting_deadline` | 每次尝试独立计算，含 CLI 操作及 viewer 确认 |
| CLI 操作预算 | 每次尝试累计最多 3 秒；子程序使用参数数组 | 每次调用同时受剩余尝试时间和协调时间约束 |
| viewer 确认预算 | 创建尝试内预留 1 秒 | viewer 读取自身 pane ID，设置 nonce 标题，持锁确认最新绑定 |
| 整次协调预算 | 10 秒，使用单调时钟，从进入函数起计算 | 锁等待、核对、轮询、旧尝试等待、重建、焦点恢复共同消耗 |
| SessionStart hook timeout | 12 秒 | 包含前提检查、启动协调及返回诊断 |

持久创建期限来自独立的 4 秒配置。每次核对取得绑定锁，检查父 pane、attach ID、closed 状态及 nonce。CLI list 找到对应 nonce 的有效 pane 且 ready 已确认时复用；新实例通过 `split-pane --pane-id <parent> --bottom --cells 10 -- ...` 启动。创建前原子写入 starting、nonce 和创建期限。

没有有效实例且旧尝试期限仍有效时，当前协调函数释放绑定锁并有界等待，每次等待受剩余创建期限和协调预算约束。醒来后重新加锁核对最新状态。期限到达且查询成功、仍无实例时，同一协调函数原子替换 nonce 和期限，执行重建。协调过程由当前 hook 进程推进；viewer 负责 ready 确认、显示及自身退出。CLI 查询失败进入 error，保留待核对的 nonce，并返回操作说明。wall clock 回拨导致持久期限超出当前时刻加 4 秒时，将旧尝试按过期处理；当前进程的等待上限仍取单调时钟预算。

启动协调在有效 viewer 确认后执行 `activate-pane`，恢复上方焦点并返回。协调预算耗尽时，以当前绑定身份记录 error、保留 nonce，并输出“任务面板启动超时，请检查 WezTerm 后重新打开或恢复 Codex”的 systemMessage。已有较新 attach 或 closed 状态时，当前协调按对应终止结果退出。锁等待本身耗尽预算时输出锁等待超时及重开操作；绑定写入继续遵循持锁约束。

协调进程在 starting 落盘后意外终止时，持久记录保持。下一次 attach 启动自己的协调函数，即使处于旧期限内，也会等待并自行推进到结果。新 attach 更新目标会话和 attach ID；既有协调每次继续执行及发布结果前核对身份，较新 attach 接管后旧协调结束。viewer 的 ready 回调持锁读取最新目标绑定。晚到的旧 nonce viewer 核对当前记录后关闭自身。相同 attach 的并发调用核对同一 nonce 和创建期限，使用绑定锁串行决定创建。正常启动最终保留一个有效面板。

统一启动协调为本次纯内部设计推断，判断依据是同步 SessionStart 的进程生命周期、已有绑定锁与 nonce，以及 R4、R9 的启动恢复结果。确定性测试覆盖写入 starting 后终止 hook、期限内重开后保持空闲、并发接管、到期重建、协调预算耗尽、时钟回拨、用户关闭及晚到实例。

用户 q 关闭时，为当前 attach 记录 closed。计划更新继续保存；当前 attach 的重复事件保持 closed。新的 attach 可重新创建。父 pane 消失时 viewer 结束并清理自己的绑定；SessionEnd 标记对应会话结束，显示最后计划与 ended 状态，直到新 attach 或用户关闭。

### 6.3 空、错误及退出

没有有效快照显示“等待首次计划更新”。安装插件前的历史计划需要后续成功的 update_plan 建立插件快照。缺 Python、wezterm、curses、PLUGIN_DATA 或 IPC 访问能力时，启动 hook 返回一条含下一步操作的 systemMessage，并正常结束。原生能力缺失及不匹配按第 10 节处理。故障状态保留在绑定记录以便下一次 attach 重试。

已有快照读取失败时面板显示“无法读取已保存的任务”，恢复有效文件后自动刷新。正常状态显示“已保存计划”及保存时间；SessionEnd 显示“会话已结束”。终端太小时保留标题和可见范围提示。关闭范围由当前父 pane 绑定及实例 nonce 确认。面向用户的演示及任务面板使用中文，工具名、字段和内部标识符保留原名。

## 7. 状态流转

生命周期状态全集为 `absent`、`starting`、`visible`、`closed`、`error`、`ended`。计划缓存与生命周期分开；每个状态的写入入口为 store 的绑定更新函数，调用方必须持有对应绑定锁。

事件全集如下。`attach` 包括 root startup/resume/fork/clear；`duplicate` 是同 attach 重复触发；`ready` 是 viewer 的 nonce 确认；`fail` 是 CLI 或创建操作失败；`plan` 是根线程成功更新；`foreign` 是其他会话或子代理事件；`close` 是 q 或用户关闭；`gone` 是父 pane 消失；`end` 是 SessionEnd；`resize` 是终端尺寸变化；`deadline` 是创建尝试期限到达；`budget` 是整次协调预算耗尽；`interrupt` 是协调进程意外终止。下列两表覆盖六种状态与这十三种事件。每个单元格的“推断”表示本次拟定行为，原生事件来源见第 2 节。

| 当前状态 | attach（新 ID） | duplicate | ready | fail | plan | foreign | close | gone | end | resize |
|---|---|---|---|---|---|---|---|---|---|---|
| absent | 进入协调，创建中为 starting，推断 | 进入协调，创建中为 starting，推断 | 核 nonce，失效退出，推断 | error，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | 保持，推断 | 保持，推断 | 保持，推断 |
| starting | 更新目标绑定并进入协调，等待或重建至结果，推断 | 进入同一协调入口，核对当前尝试至结果，推断 | 有效 nonce 转 visible，协调恢复焦点后返回；旧 nonce 结束自身，推断 | error 并保留 nonce，协调报告故障，推断 | 保存，保持，由既有协调推进，推断 | 保持，推断 | closed，协调确认后退出，推断 | absent，协调结束，推断 | ended，未确认尝试由协调继续完成，推断 | 有 viewer 时重绘，协调继续，推断 |
| visible | 更新绑定，保持，推断 | 核所有权，保持，推断 | 同 nonce 保持，推断 | error，推断 | 保存并刷新，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | ended，推断 | 重绘，保持，推断 |
| closed | starting，推断 | 保持，推断 | 失效实例退出，保持，推断 | 保持，推断 | 保存，保持，推断 | 保持，推断 | 保持，推断 | absent，推断 | 保持，推断 | 保持，推断 |
| error | 能力或依赖不符时保持并诊断；符合后按 6.2 接管或创建，推断 | 能力或依赖不符时保持并诊断；恢复后按 6.2 接管或创建，推断 | 有效 nonce 则 visible，推断 | 保持，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | ended，推断 | 保持，推断 |
| ended | 复用或 starting，推断 | 保持，推断 | 有效实例显示 ended，推断 | error，推断 | 保存，保持，推断 | 保持，推断 | closed，推断 | absent，推断 | 保持，推断 | 重绘，保持，推断 |

| 当前状态 | deadline | budget | interrupt |
|---|---|---|---|
| absent | 无当前尝试，保持，推断 | 当前调用报告协调超时；可持锁时记 error，推断 | 持久状态保持，当前协调进程终止，推断 |
| starting | 当前协调核对实例；找到则接管，否则换 nonce 重建并等待结果，推断 | 当前身份转 error、保留 nonce 并报告；较新身份保持，推断 | 持久 starting 保持，下一次 attach 的协调接管，推断 |
| visible | 已确认实例的旧期限事件保持，推断 | 已完成协调的旧事件保持，推断 | 持久状态保持，推断 |
| closed | 用户关闭优先，保持，推断 | 用户关闭优先，保持，推断 | 持久状态保持，推断 |
| error | 故障已返回；下次 attach 进入协调，保持，推断 | 保持并完成本次故障告知，推断 | 持久状态保持，推断 |
| ended | 存在未确认尝试时由当前协调核对或重建，ready 后显示 ended；其余保持，推断 | 未确认尝试转 error 并报告；已完成协调的旧事件保持，推断 | 持久状态保持，下一次 attach 按目标会话协调，推断 |

deadline 和 budget 由当前协调函数的等待循环产生；事件处理前核对 attach 与 nonce。interrupt 表示进程终止这一事实，进程终止后的持久状态由下次 attach 读取。协调返回时已具有可见实例、已告知故障或明确的关闭、父 pane 消失、较新 attach 接管结果。

不变量是每个父 pane 最终对应一个有效实例，计划按根会话隔离，子代理保持其独立状态，用户关闭在当前 attach 内生效，故障保留有效计划。启动协调负责推进创建至结果，store 的绑定更新函数负责持锁及身份核对。原生 plan dispatch 锁约束成功更新及同步回调的次序；文件锁约束完整写入。

## 8. 界面与演示

演示为 `codex-runtime-integration-demo.html`，页面文字使用中文。第一页显示 Codex 在上、任务在下的固定结构，可操作启动、创建计划、推进状态、重复启动、切换会话、恢复、关闭、故障和结束，并展示启动中断、自动等待到期恢复、协调预算耗尽、提交后取消和能力不匹配。模拟启动中断后点击启动/恢复，由演示定时任务推进协调；用户保持空闲时也会恢复，推进时间按钮可加速观察。第二页按自上而下显示启动、创建中断恢复、计划更新、取消完成和目录校验的数据流转。

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
| 配套 Codex 客户端及 daemon | 含第 4、5、6.1、10 节能力的同源构建；实际来源提交写入构建清单 | 本任务交付原生集成源码、构建产物、构建与校验记录；源许可随产物分发 |
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

## 10. 原生能力与安装交付

构建产物包含同源 Codex 客户端和 daemon。构建清单记录原生基础版本、实际来源提交、目标平台、文件 SHA-256、原生能力协议版本及 feature 集合。本机交付目标为 macOS arm64，其他平台的支持以实际构建验证为准。构建脚本和安装说明随 CC hooks 仓库交付；源码修复随配套原生仓库交付。

原生能力协议版本定义为 `runtime_hooks_version=1`，feature 集合为 `effective_tool_context`、`interactive_terminal_context`、`session_start_on_attach`、`committed_plan_callbacks`。客户端在 initialize 中声明其集合，daemon 返回自身集合；当前连接的有效能力取双方支持的交集。生成的协议 schema 及兼容性测试固定此结构。

hook JSON 中的 `hook_capabilities` 包含协议版本、客户端和 daemon 的来源版本以及当前连接有效 feature 集合。插件在启动入口完成能力校验：满足协议和 feature 要求后判断当前交互终端并挂载；能力不足时返回中文 systemMessage，说明缺少字段或 feature、客户端及 daemon 的版本，以及安装同源构建并重开会话的操作。该提示按当前启动身份去重。当前官方 0.163.0 的字段缺失路径进入此诊断。

配套原生构建提供 `codex debug hook-capabilities --json` 查询命令，输出客户端能力、实际连接的 daemon 能力及有效集合。安装说明要求先校验产物 SHA-256，再使用说明中展示的完整可执行文件路径运行查询。客户端启动其配套 daemon 时使用同一安装目录的原生可执行文件路径；已有 daemon 的能力不匹配时明确报告安装目录与版本，用户重开匹配的进程后重新查询。

独立安装验收包含解包到一个新的可写安装目录、配置独立 CODEX_HOME、安装 watcher 插件并信任 hooks、能力查询、启动 WezTerm 面板及恢复会话。实际安装指南中的命令使用用户可复制的完整路径。发布前产物路径、校验值、来源版本及能力查询输出必须与实物一致。

本节字段及查询命令是本次拟新增契约，当前官方 0.163.0 的接口事实见第 2 节；具体交付值以通过验证的构建清单为准。

## 11. 验证与交付限制

| 层次 | 实跑要求 |
|---|---|
| 失败测试先行 | 有效目录及 schema；命令路径组合；当前连接终端；已加载 resume；插件缓存、幂等创建、关闭与迟到实例；能力协议及版本组合；starting 写入后进程终止、期限内重开后保持空闲时恢复及协调预算耗尽；计划发出后、回调写入前取消 |
| 单元及受影响范围 | 原生 hooks、core、app-server protocol 及客户端调用方检查；插件已有六项 smoke 加面板 smoke；完整许可和发布路径校验 |
| 原生集成 | 直接 update_plan 与 Code Mode 的真实 PostToolUse 输入；成功、失败和子代理路径；共享 daemon 的两个 TUI；headless exec；冷启动与已加载 resume 在首条输入前启动 |
| 顺序与生命周期 | 同 worker 和跨 worker 计划更新；等待锁、提交前和提交后的取消及调用方离开；回调失败与超时；并发启动与协调接管；starting 创建期限、无额外事件的恢复及协调预算；锁等待与时钟回拨；split 超时晚到；q；父 pane 退出；不同会话切换；SessionEnd；插件更新路径 |
| 构建与独立安装 | 同源客户端及 daemon 构建；来源和文件 SHA-256；真实能力查询；官方 0.163.0 能力缺失；客户端与 daemon 不匹配；新目录和独立 CODEX_HOME 下安装及运行 |
| UI 实际使用 | 在真实 WezTerm 操作启动、更新、滚动、缩放和恢复，记录父/子 pane、焦点、字符布局、截图和执行结果 |
| 对抗与最终交付 | 设计对抗确认后 TDD；运行验证后实现对抗；视觉对抗；文档与文案对抗；同步最新主分支后最终验证；PR、CI、合并和清场 |

当前终端 GitHub 下载和 Git fetch 有连接或 DNS 失败，WezTerm IPC 曾返回权限错误，嵌套 Codex 启动曾返回 workspace routing discovery failed。这些外部限制仍须在对应验证步骤解决；本文中的拟实现行为尚不代表运行验证通过。
