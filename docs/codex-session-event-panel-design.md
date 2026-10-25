# Codex 任务面板的原生会话事件绑定

## 1. 目标与确认

唯一目标：让任务面板使用当前 Codex 会话的原生事件关联和更新任务，独立于用户的标题与状态栏设置运行。

2026-10-25 用户明确支持范围为在项目当前目录工作。验收入口为先进入项目目录，再执行 `codex` 或在该目录执行 `codex resume`；进程工作目录与当前会话项目目录一致。跨目录启动归承诺外，用户可先进入目标项目目录后启动或恢复。此范围适用于下列验收项和后续审查。

2026-10-24，用户要求会话编号从 hook 直接取得，标题和 status_line 由用户自定义；任务面板默认显示任务内容。用户随后接受恢复时机调整：启动先显示等待，首次原生事件到达后加载当前会话的历史任务。第一轮设计审查确认两项启动顺序缺口后，用户确认采用实际 Codex 进程关联事件与面板的共同修订方案。本补充设计覆盖 `codex-official-hooks-design.md` 中关于身份显示、关联入口和恢复时机的段落，其余紧凑显示约定继续生效。

## 2. 当前事实与依据

| 事实 | 本轮读取或执行记录 |
|---|---|
| 当前观察器把标题与屏幕文本组合成会话编号 | `watcher/hooks/task-panel-wezterm.lua:6` 的 session_id 读取 get_title 和 get_lines_as_text；`:56` 用结果决定挂载 |
| 当前配置脚本写入两处编号显示设置 | `watcher/hooks/task_panel_setup.py:39` 的 configure_codex 修改 tui.status_line 与 tui.terminal_title；main 将结果写回配置文件 |
| 当前 viewer 显示编号前八位 | `watcher/hooks/task_panel.py:97` 将 session_id 加入第二行 |
| 原生 hook 提供当前主会话编号和完整计划 | 本轮官方 Codex 0.164.0 的 SessionStart、PostToolUse 实测；记录目录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-194019` 中的 hooks.jsonl |
| SessionStart 在首次提交消息时执行 | 官方源码 `codex-runtime-src/codex-rs/core/src/session/turn.rs` 的 run_pending_session_start_hooks；既有隔离 TUI 记录 `official-hooks-20261024-144803/tui-report.json`；本轮用户已接受对应恢复时机 |
| 共享后台的 hook 终端环境可能来自首个客户端 | 两客户端实测 `official-hooks-20261024-144803/tui-report.json`；上游问题 [openai/codex#48500](https://github.com/openai/codex/issues/48500) |
| WezTerm 提供当前 pane 的本地进程信息 | 当前观察器已使用 get_foreground_process_info；[官方接口](https://wezterm.org/config/lua/pane/get_foreground_process_info.html) 提供 pid、cwd 和 argv |
| 现有 viewer 可以跟随内部绑定变化 | `watcher/hooks/task_panel.py:284` 按 session_id 与 attachment_id 切换读取目标；本轮 hook 修改绑定后，两个按顺序启动的同目录会话显示各自计划，见上述目录 session-event-binding-report.json |
| Store 已提供事务与完整计划缓存 | `watcher/hooks/task_panel_store.py:166` 的事务入口、binding_transaction、save_plan 和 read_plan |
| 配置技能已有原生热重载入口 | `watcher/skills/task-panel-configure/SKILL.md` 的“让配置生效”使用 WezTerm 重新加载配置 |
| 活动 Codex 进程先于面板登记存在 | 本轮在独立官方 Codex 与 WezTerm 中延后 launcher 登记，按系统进程选择后，两个 viewer 显示各自计划。第二会话事件先于其登记且第一会话保留原任务；记录 `official-hooks-20261024-200645/process-routing-verification.json` |
| macOS 可取得实际进程目录和启动时间 | 本轮读取 ps 的 lstart 与 lsof 的 cwd；上述隔离进程关联探针保存 PID、process_started_at 和目录 |

实测版本是证据中的被测对象。方案使用事件字段和现有本地接口。

## 3. 验收清单

| 编号 | 产出物与级别 | 处境、目标与可核验结果 | 对应目标 |
|---|---|---|---|
| R1 | 观察器、配置脚本；用户级、承诺内 | 用户自定义或清空标题与 status_line，在项目当前目录执行官方 codex 或 codex resume 后创建中文任务面板；两处设置内容保持用户原样 | 独立于标题与状态栏 |
| R2 | 会话绑定与 hook；用户级、承诺内 | 启动先出现等待状态，当前主会话的 SessionStart、UserPromptSubmit 或 update_plan PostToolUse 到达后，使用原生 session_id 关联当前面板 | 当前会话的事件关联 |
| R3 | 历史恢复、计划缓存；用户级、承诺内 | 恢复会话的首次原生事件提供编号与 transcript_path 后加载其已有计划；后续计划替换与清空更新相同编号的缓存 | 原生事件恢复和更新 |
| R4 | viewer；用户级、承诺内 | 默认显示任务、连接状态和保存时间；最多四条任务、更多数量提示、滚动及 m/a 保持原行为；q 在当前 Codex 运行期间保持关闭，重新运行 Codex 后创建面板 | 任务的独立显示与既有操作 |
| R5 | 配置技能与稳定运行文件；运维级 | 用户调用技能并重载 WezTerm 后接入观察器；现有 Codex 工作继续运行，首次后续事件自动关联；插件更新刷新同一稳定路径 | 配置后的自动运行 |
| R6 | 自动测试、隔离真实使用记录；测试代码 | 自动验证配置保持、字段格式、事件路由、恢复与关闭；真实官方 Codex 和 WezTerm 验证自定义显示设置、计划同步和恢复 | 验证 R1 至 R5 |
| R7 | 使用说明与中文演示；文案 | 清楚说明首次事件前的等待、恢复时机、q 的现有重开办法和正式操作分工 | 正确解释目标行为 |

正式安装、更新、刷新与配置技能调用由用户执行。开发验证采用隔离配置和独立 WezTerm 窗口。

## 4. 内部数据与关联

### 4.1 本地 pane 登记

WezTerm 继续通过 update-status 识别本地交互 Codex。以实际 Codex PID 作为该次运行的挂载标识，创建三行底部 pane，把 PID、cwd 与真实父 pane 编号传给 task_panel_launch。子 pane 自己取得真实 WezTerm socket 和 pane 编号。

新增 task_panel_process.py 负责本地交互 Codex 进程的枚举与信息读取，提供 pid、cwd、started_at。cwd 来自系统记录的进程工作目录并解析为实际本地路径，started_at 来自系统记录的进程启动时间。交互进程沿用现有观察器的识别条件：executable 为 codex，argv 中出现 exec、app-server 或 mcp-server 时由对应运行入口处理。

launcher 的 prepare 仍是绑定创建入口。它按实际 PID 查询系统进程信息，绑定增加 owner_pid、owner_cwd、owner_started_at 与 session_confirmed 字段；owner_started_at 表示系统记录的进程启动时间。初始 session_id 使用内部 pending-PID 占位，session_confirmed 为 false。字段由 Store 校验；旧记录可读取，具备 owner 字段的新记录参与原生事件关联。viewer 在占位阶段显示“等待当前会话信息”。

### 4.2 原生事件登记与路由

新增 task_panel_binding.py 承担本地会话事件与 pane 绑定的关联。原生事件先完成会话缓存写入或恢复，再读取实际交互 Codex 进程信息，选择会话对应的运行实例，将 session_id、cwd、observed_at、owner_pid、owner_started_at 和 ended 状态写入 Store 的 sessions 记录。记录按完整 session_id 保存；SessionEnd 标记对应记录 ended。

收到活动事件后，按以下顺序从实际交互 Codex 进程中选择：已有相同 session_id 登记且 PID 与系统启动时间仍对应的存活进程；同 cwd 最新的未关联进程；同 cwd 最新的进程。未关联指该进程实例尚无活动 sessions 记录。排序按系统 started_at、PID 递增取最后一项；最后一档承担同进程切换会话的关联。事件缓存的 owner_pid 和 owner_started_at 一旦确定，面板按这对信息汇合。

会话记录写入完成后，再查找同 owner_pid、owner_started_at 的 pane 绑定。目标 binding_transaction 内读取最新记录，更新 session_id、session_confirmed 和 attachment_id。nonce 与子 pane 身份继续由现有 viewer 使用。

cwd 参与首次找到本地运行实例，计划内容始终按原生 session_id 存取。已关联事件优先按 session_id 定位。主 Agent 的事件进入此入口；子 Agent 的 agent_id 按既有过滤规则处理。

WezTerm 登记与 hook 到达的先后由不同进程决定。launcher 先保存绑定，再读取同 owner_pid、owner_started_at 的活动 sessions 记录，按最近 observed_at 消费；后续 hook 继续使用同一关联函数。事件先到时，由稍后的 launcher 消费；面板先到时，由稍后的 hook 更新。双方均先保存自身记录，再读取对方记录，关联后读取已有计划。

首次进程选择暂未成功时，sessions 保存会话事实与空 owner 字段，等待后续活动事件或 launcher 调用同一进程选择函数重试。owner_pid 与 owner_started_at 同时为有效值或同时为空。系统信息读取失败或耗尽两秒总预算时，保存计划，输出具体可重试提示；viewer 保持等待。读取外部命令时使用总预算内的剩余时限。原生 PostToolUse 的五秒 hook 预算和 SessionStart 的十二秒预算继续适用。

这个本地实例选择是启发式：日常一个目录运行一个 Codex，以及按顺序启动并首次使用的同目录会话按上述规则关联。多个同目录实例同时首次提交消息时，事件与实际进程的对应取决于进程启动与关联的次序。这里采用自动选择；任务数据仍分别保存在原生会话编号下。用户已明确要求常规使用自动运行。

### 4.3 已有 viewer 与生命周期

原生事件直接更新已有绑定，viewer 按现有 target 切换加载计划。WezTerm 的创建记录只跟踪 Codex PID；同 PID 的编号变化由 hook 与 viewer 处理。

q 保留当前运行的关闭状态，后续事件继续保存计划。进程离开后观察器清理自己创建的 pane；新的 Codex PID 创建新绑定和 viewer。SessionEnd 只结束当时仍对应相同 session_id 的绑定；同进程切换到新会话后，活动原生事件将绑定恢复为连接状态。closed 状态继续由 q 的约定控制。

### 4.4 依据与依赖

| 做法 | 方案依据 |
|---|---|
| PID 识别与三行 pane | 项目内同类处理，task-panel-wezterm.lua 的 interactive_codex 与 pane:split |
| 原生 session_id 与计划恢复 | 项目内同类处理，task_panel_hook.py 的 Handler.handle 与 task_panel_session.py 的 recover_plan |
| 在既有 viewer 中切换目标 | 项目内同类处理，task_panel.py 的 target 与 current 路径；本轮真实隔离验证通过 |
| 事务、字段校验、计划缓存 | 项目内同类处理，task_panel_store.py 的 _validate、_transaction 与 save_plan |
| 本地 owner 字段、sessions 事件记录和选择顺序 | 纯内部判断；实际进程提供先于面板存在的运行实例，GUI 与 hook 通过进程登记汇合，事件记录接住不同的到达顺序 |

**纯内部取舍**：owner 登记、事件记录和实例选择属于本项目内部设计推断，第一轮返回的共同修订方案已经用户确认。DD 已验证“hook 直接更新绑定、现有 viewer 刷新”与按实际进程接入晚登记面板的可行性；完整 schema、异常分支、Linux 和 GUI 首次观察晚于事件的真实顺序仍须后续验证。

| 平台 | 进程信息接口与依据 | 验证范围 |
|---|---|---|
| macOS | ps 提供 PID、executable、argv、lstart；lsof 的 cwd 项提供目录。设置 LC_ALL=C 解析系统时间，PID 与启动时间组成运行实例身份 | 本轮系统接口和独立官方 Codex 窗口探针 |
| Linux | /proc/PID/exe、cwd、cmdline、stat 提供对应字段；stat 第 22 项为启动时钟数，结合 /proc/stat 的 btime 和 SC_CLK_TCK 形成启动时间。依据为 [进程 stat 手册](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)、[系统 stat 手册](https://man7.org/linux/man-pages/man5/proc_stat.5.html)、[cwd 手册](https://man7.org/linux/man-pages/man5/proc_pid_cwd.5.html) 和 [cmdline 手册](https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html) | 本轮核对官方接口文档；真实 Linux 进程读取在受影响范围验证中完成 |

运行依赖为 Python 3.11+ 标准库与 curses、WezTerm 本地 Lua 接口、官方 Codex 的现有 hooks，以及上述系统进程接口。Python 包依赖沿用已有范围。配置技能检查本机对应系统接口并报告缺失项。

## 5. 状态、事件与唯一写入点

下表为对用户可见的组合状态。原始 starting、visible、closed、ended、error 字段继续由既有 Store 表达；等待与已关联由 session_confirmed 表达。

| 状态 | 检测新 Codex PID | 活动会话事件 | update_plan | q | SessionEnd | 进程离开 | 读写失败或超时 | 后续读取成功 |
|---|---|---|---|---|---|---|---|---|
| 无面板 | launcher 创建等待状态 | 保存会话记录与历史缓存，等待登记 | 保存记录与计划，等待登记 | 无入口，pane 尚未创建 | 标记事件记录 ended | 保持无面板 | 保留缓存并报告错误 | 下次检测或事件继续处理 |
| 等待会话信息 | 同 PID 保持；新 PID 重新创建 | 路由后关联并显示缓存 | 保存后关联并显示完整计划 | 写 closed 并退出 viewer | 同编号时结束；占位编号保持等待 | 观察器关闭 pane 并清登记 | viewer 显示中文错误，数据保留 | 重新读取和路由 |
| 已关联 | 同 PID 保持；新 PID 创建新绑定 | 同编号恢复缓存，新编号切换读取目标 | 替换当前编号的计划 | 写 closed 并退出 viewer | 同编号写 ended | 观察器关闭 pane 并清登记 | viewer 显示中文错误，数据保留 | 显示已保存计划 |
| 已关闭 | 同 PID 保持关闭；新 PID 创建等待状态 | 更新记录与缓存，保持关闭 | 更新计划，保持关闭 | 无入口，viewer 已退出 | 标记 ended 事件，绑定保持 closed | 清登记 | 保留记录并报告错误 | 同 PID 继续保持关闭 |
| 会话已结束 | 同 PID 保留；新 PID 创建等待状态 | 活动事件关联后恢复连接 | 活动事件保存并恢复连接 | 写 closed 并退出 viewer | 保持结束 | 观察器关闭 pane 并清登记 | viewer 显示中文错误，数据保留 | 保持结束并显示最后计划 |

已验证的状态基础来自现有 Panel.ready、close、current、Handler._end 和本轮 hook 更新绑定实验；早到事件、无登记事件、结束后新会话的路由结果属于本补充设计推断。

| 事实 | 唯一写入入口与不变量 |
|---|---|
| pane 创建与观察记录 | WezTerm 观察器；每个本地父 pane 的当前 Codex PID 对应一个创建记录 |
| owner 与占位绑定 | launcher.prepare；owner_pid、owner_cwd 和起始时间在该绑定内保存 |
| 运行实例信息 | task_panel_process；PID、cwd、系统启动时间由对应平台的进程接口读取 |
| 会话事件登记与关联目标 | task_panel_binding；完整 session_id 来自原生事件，先记录其进程实例，再更新同实例的 pane，关联过程保留当前 viewer 的 nonce |
| 完整计划内容 | Store.save_plan；缓存文件名与 session_id 一致，替换和清空沿用原有事务 |
| viewer 就绪、关闭与结束 | 现有 Panel.ready、close 与 Handler._end；写入前读取当前绑定，保持原有实例归属 |

## 6. 配置与界面

task_panel_setup 的安装写入范围为 WezTerm 加载区段和稳定运行文件。Codex 配置按用户当前内容保持；技能检查 hooks 信任、计划工具与解释器，用户使用原生设置管理标题和状态栏。既有安装中的编号显示项继续受用户设置控制。

运行文件列表加入 task_panel_binding.py 和 task_panel_process.py。SessionStart 与 UserPromptSubmit 沿用 sync_runtime 更新稳定路径。用户执行配置技能并重载 WezTerm 后，当前 Codex 可以在下一次原生事件到达时关联面板。

viewer 第二行显示连接状态及已有保存时间；等待阶段显示“等待当前会话信息”。标题、最多四条任务、溢出数量、滚动与 m/a 布局沿用紧凑设计。窄终端沿用现有字符格裁剪与错误提示，颜色沿用 curses 的终端主题。演示为 `codex-session-event-panel-demo.html`，包含新建、恢复、更新、清空、关闭、进程重新进入和错误读取路径。

## 7. 验证与交付

先新增失败测试，覆盖配置字节保持、owner 与 sessions 字段校验、系统进程信息读取、按编号优先和按 cwd 进程选择、早到事件消费、agent_id 过滤、活动和结束事件、q 后保持关闭、新 PID 接入及默认编号隐藏。第一轮两项回归固定为独立用例：已有面板运行时新会话事件先到、新面板后登记；事件早于首次 GUI 观察而进程已经存在。既有计划恢复、nonce、四条显示和手动尺寸测试继续验证。

受影响验证覆盖 hook 入口、配置技能、稳定文件同步与清单。macOS 在隔离真实 WezTerm 使用官方 Codex 新建和恢复会话，自定义标题与 status_line，记录首次消息前等待、首次事件后的历史计划、计划替换/清空、两个按顺序首次使用的同目录会话、早到事件的两种顺序、q 及重新运行后的面板。Linux 运行真实进程接口 smoke，核对运行实例发现与单 PID 读取。核对实际 pane 行数、可见任务数和截图中的第二行结构。

设计审查、测试先行、实现审查、视觉审查、文档与文案审查、最终验证按协作规范执行。代码与 PR 由 AI 准备，PR 由用户检查并亲自合并。
