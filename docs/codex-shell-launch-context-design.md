# Codex shell 启动目录上下文修正设计

本文状态为历史研究稿。现行验收基线为保留原版跨目录能力并补齐实际 Codex 目录输入差异，见 codex-runtime-integration-design.md 第 3 节 R1、R2 及第 4 节。本稿的目录 RPC 与完整 shell 上下文方案保留为研究和审查记录，具体必要性按现行功能基线核定。

## 1. 目标、状态与证据

本设计处理第四轮实现审查的 B1、B2：Bash 的 `cd -P ""` 失败被误当成功，以及符号链接 workdir 被误当 shell 的逻辑 PWD。当前是待独立审查的设计稿，生产实现尚未修改。它延续运行集成设计 R1、R2 的本地执行目录目标，不改变 hook 顶层 cwd、远端策略边界或任务面板交互。

| 本轮读取或执行 | 直接事实 | 设计约束 |
|---|---|---|
| `watcher/hooks/codex_gate_context.py:227`、`:295`、`:325` | 通用路径拼接消去空字符串；初始目录直接采用 context.cwd；cd 与 Git -C 共用目录计算 | 操作结果必须带成功状态，初始 shell 状态须另有事实来源 |
| 原生 `core/src/tools/handlers/unified_exec/exec_command.rs:121`、`:249`、`:529` | workdir 解析共用；实际 shell 在 handler 中选择；hook 当前只有 environment_id、is_remote、cwd | 准备入口同时选定 shell、cwd、环境，不能只在插件中 realpath |
| 原生 `core/src/tools/handlers/unified_exec.rs:97` | get_command 处理默认 shell、显式 shell fallback、login 默认值及禁用条件 | 准备与执行复用 ShellInvocation，不能把 args.shell 当实际 shell |
| `round4-shell-start-context.json`，20 次真实 Bash/zsh 执行 | Bash 的物理空 cd 失败，zsh 成功；Git -C 空参数保持目录。有效逻辑 PWD 可被保留；PWD 缺省或无效时采用物理目录；含 /. 的有效 PWD 在两种 shell 中不同 | cwd、launch PWD 和 shell 类型须共同解释；不能统一成 realpath |
| 原生 `exec-server/src/local_process.rs:743`、`protocol/src/shell_environment.rs:135` | 执行器自身环境按策略合并，再叠加明确 env；policy.set 在 exclude 后应用 | hook 进程环境不能代替工具环境；冻结缺省值同时处理继承与 set |
| `round4-prepared-launch-env-probe.json`，30 次真实 process/start | PWD/OLDPWD 的存在性和值可通过现有 envPolicy/env 冻结；login 与实际 snapshot 的覆盖矩阵通过。不存在 process/prepare RPC | 新增只读查询，复用 child_env；不得调用虚构的 prepare 接口 |
| 原生 `exec-server/src/process_sandbox.rs:47`、`:127` | 完整 PreparedExecRequest 持有网络代理等资源，位于权限协调后的启动阶段 | 不把完整启动准备移到 PreToolUse 前 |
| 原生 `exec-server/src/shell_snapshot.rs:272`、`shell-command/src/shell_snapshot_capture.rs:340` | snapshot 不捕获 PWD/OLDPWD，显式请求环境在 snapshot 环境后恢复；snapshot 仍保存函数及选项 | 字段命名为 launch 值，不能声称描述任意启动脚本运行后的状态 |

上表原生相对路径均以 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-integration-wt/codex-rs` 为根；实验记录均在 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22`。实验不是新增准备接口已经实现的证明。

## 2. 修复后的可观测结果

| 输入条件 | 要求的结果 |
|---|---|
| Bash，`cd -P "" || git commit`，当前为受管 main | cd 失败，检查实际可达的 commit，按已有 main 规则拦截 |
| Bash 默认或 -L 空 cd、zsh 三种空 cd | cd 成功，后续 &&/|| 按成功推进 |
| Git `-C ""`，含连续 -C | 保留当前物理目录，后续相对 -C 从该目录继续 |
| workdir 是指向 main/subdir 的链接，launch PWD 缺省、陈旧或相对 | shell 从物理 main/subdir 起步；cd .. 后按 main 拦截 |
| workdir 是指向 feature/subdir 的反向链接，launch PWD 无效 | cd .. 后按 feature 放行合规提交 |
| launch PWD 是有效逻辑目录名 | 按选定 shell 的启动规则保留逻辑名；后续 cd .. 可以进入逻辑父目录 |
| 有效逻辑 PWD 含 /. | Bash 与 zsh 按真实启动矩阵分别解释，不共用未经验证的字符串规范化 |
| 首次 cd -、连续多次 cd 和混合 Git -C | 前目录来自 launch OLDPWD；操作依次返回成功状态、新逻辑目录、物理目录和前目录 |
| Claude Code、旧 Codex payload、动态词法、管道或分组 | 维持既有兼容入口；不把旧输入伪装成具有新能力的输入 |

本次静态目录解释继续针对解析器已有的字面路径及顺序连接符。变量展开、命令替换、未知命令影响条件可达性等已有路径仍回到 legacy_context。启动文件主动 cd、替换 cd 函数，或 snapshot 改变 shell 目录选项，不由 launch 元数据静态证明。这是需要独立审查重点核对的现有兼容边界：不得把 B1/B2 的通过写成任意 shell 程序的执行等价性，也不得悄然缩减 R1/R2 的已确认范围。

## 3. 调用内一次准备

新增内部不可变 `PreparedExecContext`，只属于一个 ToolInvocation；克隆 invocation 时共享该对象，不在 Session、进程管理器或全局表中按 call_id 缓存。内容为选定执行环境、请求 cwd、物理 cwd、ShellInvocation，以及 launch PWD/OLDPWD 的 Option<String>。None 为缺省，Some("") 为空字符串。实际命令 argv 不缓存，以允许现有 hook 改写 cmd。

| 阶段 | 唯一入口与消费方 |
|---|---|
| 参数与环境解析 | exec_command 的异步准备入口调用现有目录解析器和 get_command；interactive 与 one-shot 共用该入口，其他 handler 默认无准备结果 |
| 直接本地环境 | 从 open_session_with_sandbox 提取无副作用的基础环境构造；同一份基础 env 的 PWD/OLDPWD 投影用于 hook 与执行 |
| 执行器环境 | 新增只读 `process/directoryContext` RPC，输入 cwd、envPolicy、env，返回执行器解析的物理 cwd 和 child_env 的 PWD/OLDPWD 投影；不启动 shell、命令、网络代理或 snapshot 捕获 |
| hook 输入 | 从 PreparedExecContext 投影新增 launch_shell 字段；顶层 cwd 和既有 tool_execution_context.cwd 的含义不变 |
| 执行 | handler 消费同一准备对象；按当前 cmd 和固定 ShellInvocation 生成 argv；既有审批、sandbox、snapshot、网络代理及 spawn 仍在原阶段 |
| 冻结环境 | 直接路径在最终 env 中恢复准备的 PWD/OLDPWD。执行器路径先从 envPolicy 继承与 set 排除这两项，再在 env 中写入存在值；None 删除明确覆盖。实际 snapshot 已过滤这两项，不会重新加入缺省值 |

准备对象不冻结 HOME、CDPATH 或完整 shell 状态，也不改写这些环境的现有启动语义。现有 tilde 展开依赖 hook 的 HOME，存在环境不一致风险；CDPATH、启动选项也可能影响字面 cd。这些同类影响必须在独立设计审查中核定，若 R1/R2 要求覆盖它们，需补足同源信息或更换准备边界，不能靠把它们叫作动态输入来宣称已经解决。

registry 先异步准备并响应 cancellation，再发送 PreToolUse。拒绝时释放调用内值，不启动目标命令。没有 PreToolUse 配置的调用也使用同一准备入口，handler 不另选 shell 或目录。RPC 使用现有执行器请求的截止与取消机制；具体 API 接入及重连路径须由实现前的失败测试锁定，不另建后台协调器。

## 4. 公开协议与兼容

`tool_execution_context.launch_shell` 是可选 typed 对象，字段为 `kind`、`path`、`login`、`physical_cwd`、`pwd`、`oldpwd`。kind/path 表示实际选定值；pwd/oldpwd 明确序列化为字符串或 null。目录和字符串继续沿用原有合法性校验，拒绝 NUL；插件不读取自己的 PWD 补缺。

运行能力新增 `launch_shell_context`，客户端与 daemon 按现有交集协商；runtime_hooks_version 保持 1，因为既有字段含义及 hook 时序契约不变。执行器 EnvironmentCapabilities 独立增加缺省为 false 的 `directory_context`，只有报告支持的执行器接收新 RPC。本地配套制品须具备此能力；旧执行器不发送未知方法，也不声称完成新语义。远端继续沿既有明确支持边界处理，不要求本地 gate 解释外部 shell。

| 能力形态 | 实际行为 |
|---|---|
| 配套新客户端、daemon、本地执行器 | 输出新上下文，使用共用准备结果执行 |
| 本地执行器不具备新能力或查询失败 | 依现有 tool error 路径返回明确的配套版本或准备错误；目标命令不启动。不能回填 hook 环境后继续 |
| 插件收到无 launch_shell 的旧 payload | 保留现有旧版本路径；安装说明明确旧版本不具备本轮修复能力 |
| 新字段结构非法 | gate 给出既有解析错误，返回 2 |
| 非本地执行环境 | 保留 environment_id、is_remote、cwd URI 和既有远端说明，不做本机路径解析 |

hook 的 updatedInput 当前只改 cmd，准备结果继续有效，argv 必须重新生成。launch 输入来自解析后的 shell、cwd、环境策略和覆盖；若接口未来允许改这些输入，必须先使准备失效并重新完成相应检查。执行环境路由变化不能消费另一环境的准备对象；执行器连接恢复如何验证仍是审查及失败测试重点。

## 5. 状态与事件

生命周期由 registry 单一调用栈拥有，状态为未准备、准备中、已准备、已检查、执行中、结束。事件为准备、准备成功、准备失败、hook 允许/只改 cmd、hook 拒绝、取消、启动、执行结束。下表格中“错误”表示内部调用顺序错误，不能通过重新解析绕过；“忽略”表示晚到响应不再写入。转移方案为内部设计推断，审查须重点核对取消和连接恢复。

| 状态 | 准备 | 准备成功 | 准备失败 | 允许/改 cmd | 拒绝 | 取消 | 启动 | 执行结束 |
|---|---|---|---|---|---|---|---|---|
| 未准备 | 准备中 | 错误 | 错误 | 错误 | 错误 | 结束 | 错误 | 错误 |
| 准备中 | 错误 | 已准备 | 结束 | 错误 | 错误 | 结束 | 错误 | 错误 |
| 已准备 | 错误 | 错误 | 错误 | 已检查 | 结束 | 结束 | 错误 | 错误 |
| 已检查 | 错误 | 错误 | 错误 | 错误 | 错误 | 结束 | 执行中 | 错误 |
| 执行中 | 错误 | 错误 | 错误 | 错误 | 错误 | 按现有执行取消规则 | 错误 | 结束 |
| 结束 | 错误 | 忽略 | 忽略 | 忽略 | 忽略 | 保持 | 错误 | 保持 |

没有 hook 的调用在已准备后由 registry 的无 hook 分支进入已检查。同步拒绝不会与 spawn 并行。准备成功且取消同时就绪时，启动前仍检查 cancellation。执行开始后的取消沿用当前进程所有权规则，不在本设计另建守护任务。

目录模型输入为 ShellState 与操作；ShellState 含 shell 类型、逻辑 cwd、物理 cwd、previous。操作全集为逻辑 cd、物理 cd、Git -C；输出为明确 success 与新的 ShellState。失败保留目录及 previous，成功 cd 以前一逻辑 cwd 更新 previous；Git -C 仅影响该 Git 子进程，不写 shell 状态。空参数在操作入口解释，不进入通用 join 后再猜原始参数。连接符只消费 success；未知命令结果维持现有 uncertain 分支。

## 6. 验证与交付门槛

先补失败测试，覆盖 Bash/zsh 空参数、有效/缺省/无效/含 /. PWD、正反链接、首次和连续 cd -、连续 cd 与 Git -C、hook cmd 改写。原生另测准备与执行同源、默认/显式/fallback shell、login 禁用、直接与执行器环境、取消/拒绝/故障无目标命令、旧能力协商与连接恢复。

随后按当前原生安装包的真实复现脚本跑受管 main/feature 正反路径，并跑 login/snapshot 矩阵；启动制品须重新构建匹配 CLI 和 daemon，记录源码与文件校验。面板不受目录模型影响，但最终集成交付仍要核一次真实 WezTerm 启动及计划同步。测试通过只能证明列出的执行条件，不代替第 2、3 节待核的同类范围。

中文演示见 `codex-shell-launch-context-demo.html`。演示展示调用所有权与 B1/B2 条件结果，不执行 shell，也不把浏览器模型计入原生通过数。
