# 官方 Codex 任务面板方案

## 1. 目标与确认状态

唯一目标：使用官方 Codex 的现有 hooks 和自动化脚本，在 WezTerm 中自动显示并同步任务列表。用户正常执行 `codex` 或 `codex resume`，使用共享后台和官方更新。任务面板最多显示四条，更多任务有数量提示并可滚动。

用户已明确要求保持 Codex 源码和官方程序原样使用。每个 Codex 会话按自己的 session_id 拥有任务数据和面板；多个会话可以使用同一本地文件夹。面板读取当前会话已有计划并接收后续变化。文件夹用于工作和查找数据。界面沿用已确认的中文紧凑面板；配套中文流程为 `codex-official-hooks-demo.html`。

## 2. 当前事实

| 内容 | 本轮证据 |
|---|---|
| 官方支持计划工具 hook | [官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks) 的工具表明确列出 update_plan；官方 rust-v0.164.0 的 registry.rs 默认函数工具路径生成 PostToolUse 输入 |
| 计划参数实际可读 | 官方二进制实测 PostToolUse 的 tool_name 为 update_plan，tool_input.plan 为完整任务数组。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-144524/report.json` |
| SessionStart 在首条消息触发 | 两个官方 TUI 均在输入前没有 hook，首条消息后得到 SessionStart 和 PostToolUse。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-144803/tui-report.json` |
| 共享后台的 pane 环境可来自首个终端 | 上述两客户端共用 PID 7826；实际 pane 为 96、97，两次 hook 环境均报告 pane 96 |
| WezTerm 可以观察本地前台进程 | 官方 [update-status](https://wezterm.org/config/lua/window-events/update-status.html) 周期事件和 [get_foreground_process_info](https://wezterm.org/config/lua/pane/get_foreground_process_info.html) 提供对应 pane 的进程信息 |
| 本机计划工具已开启 | 本机配置 tools.update_plan.enabled 为 true；安装说明按实际配置检查此项 |
| 原生 Tasks 计数与计划同源 | 官方 on_plan_update 根据 UpdatePlanArgs.plan 计算完成数和总数，terminal_title_task_progress 显示该计数；官方 tui/src/chatwidget/turn_runtime.rs:595–608、status_surfaces.rs:1103–1109 |
| 官方配置可以显示当前会话身份 | tui.terminal_title 和 tui.status_line 支持 session-id；两个同目录、共享后台的 TUI 均在首次输入前显示各自会话编号，编号与之后 hook 的 session_id 一致。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-154328/identity-report.json` |
| 恢复数据来源 | 原始 transcript 保存 update_plan 的 function_call 参数及对应 Plan updated 结果。官方 thread/read 的本轮实测返回中只有 userMessage、agentMessage；PlanUpdate 事件在官方 rollout policy 中为 transient |

官方二进制实测版本为 0.164.0。此版本是本轮验证对象；插件按事件名称、输入字段和依赖能力判断可用性。

## 3. 职责与数据流

| 组件 | 职责 |
|---|---|
| WezTerm 自动事件 | 检测本地 pane 的 Codex 交互进程，从原生会话标识显示取得当前身份，为该会话创建底部面板 |
| SessionStart | 根据官方 session_id、transcript_path 读取当前会话已有计划，并刷新已安装的面板脚本 |
| PostToolUse，matcher 为 ^update_plan$ | 从 tool_input.plan 保存根 Agent 的完整计划，更新相同 session_id 的面板 |
| 面板 viewer | 读取插件数据，显示中文空态、最多四条任务及更多提示，处理滚动、m/a 和 q |
| SessionEnd / 进程离开 | 使用已有绑定关闭或结束对应面板 |

启动链路自上而下为：官方 Codex 显示当前会话身份 → WezTerm 创建并关联该会话面板 → 按 session_id 读取已有计划 → SessionStart 补充 transcript_path → PostToolUse 保存新计划 → viewer 刷新。

WezTerm 回调按窗口遍历其标签页和 pane，使用本地前台进程信息识别交互 Codex。后台服务、headless exec 和面板 viewer 保持各自职责。进程信息暂不可读时继续扫描并保留已有记录。

WezTerm 事件负责“首条消息之前就显示面板”，依据是第 2 节实测时机。回调扫描、挂载及恢复已在独立测试窗口验证，记录见第 8 节。

## 4. 按原生会话身份自动关联

WezTerm 负责记录真实 pane 身份。官方配置的 session-id 显示由该 TUI 的当前 thread_id 产生；hook 输入中的 session_id 标识同一个会话。两者按会话编号汇合，目录仅用于标题及查找保存位置。

安装时合并官方 tui.status_line 的 session-id 项，使完整会话编号可读；官方 tui.terminal_title 的 session-id 项作为辅助线索。本机标题显示会缩短编号，因此最终身份使用完整 session_id。终端配置读取到的完整编号须与原生标题的会话编号对应。会话身份尚不可读时继续扫描，读取恢复后自动创建对应面板。

计划缓存按 session_id 保存完整列表。面板启动先读取该编号的插件缓存；历史会话已有任务时，可从该会话的 transcript 读取最后一份完成更新的 update_plan 参数，并以相同 call_id 的成功结果确认。SessionStart 提供准确的 transcript_path；此前可按会话编号查找并核验对应文件。新会话没有计划时显示空态。PostToolUse 随后更新这份会话缓存。

SessionStart 负责读取和展示已有计划。update_plan 是实际写入计划的工具；启动显示直接使用已有数据。原生 Tasks 计数和面板内容均以 update_plan 清单为来源。

用户确认的视觉调整已实现：面板元数据使用 session_id 前八位呈现，以显示完整保存时间；绑定和缓存继续使用完整编号。页脚提供“先点面板”提示，按键作用于获得焦点的任务 pane。

这是纯内部方案：使用官方提供的会话身份、计划工具事件和该会话的保存数据完成自动同步。两个同目录 TUI 的原生身份与 hook 已实测一致；完整面板与恢复链路的实测记录见第 8 节。

## 5. 状态与事件

| 状态 | 官方会话事件 | update_plan 成功事件 | q | Codex 进程退出 | 同 pane 新 Codex 进程 |
|---|---|---|---|---|---|
| 无面板 | 读取该会话已有计划，等待终端观察 | 保存完整计划，等待终端观察 | 无操作入口 | 保持无面板 | 取得原生身份后建立面板 |
| 等待会话信息 | 按 session_id 读取该会话已有计划 | 保存计划，取得原生身份后显示 | 无操作入口，等待时尚未创建 pane | 清理该进程的面板记录 | 取得原生身份后建立面板 |
| 已关联 | 核对当前绑定并恢复缓存 | 更新该会话缓存和显示 | 进入已关闭 | 结束对应面板 | 清理旧进程记录，建立空态面板 |
| 已关闭 | 同一进程保持关闭 | 更新缓存，同一进程保持关闭 | 保持关闭 | 清理该进程记录 | 建立新的空态面板 |

首次检测到已显示会话编号的 Codex 后，唯一创建入口是 WezTerm 观察逻辑的原生 pane:split；子面板进程取得 WezTerm 为它设置的真实 socket、pane 环境及 CLI 位置，记录父面板和完整 session_id。官方 hook 按 session_id 写入现有 Store。缓存或终端读取错误显示中文提示，恢复读取后刷新；q 和进程退出继续按上表处理。

## 6. 安装与日常使用

插件安装步骤配置一次 WezTerm 模块加载，记录备份及托管区段。已有终端配置通过托管区段接入；默认配置场景创建最小加载入口。加载入口使用稳定的插件数据路径，更新插件时刷新模块位置。

本机取证时默认的两个用户配置位置均不存在，当前 GUI 使用默认配置入口。一次性设置脚本备份并合并 Codex 与 WezTerm 配置；插件安装、hook 信任及计划工具开关按使用说明分别检查。

日常命令为 `codex` 或 `codex resume`。窗口识别和面板创建由 WezTerm 自动处理。官方 hook 负责保存计划，Agent 调用 update_plan 时面板随之更新。新会话没有计划时显示“等待首次计划更新”。

## 7. 验收与验证

| 验收项 | 产出及验证方式 |
|---|---|
| 官方程序使用 | 用户级、承诺内；正常官方 CLI 新建及恢复会话，保留共享后台；实际进程和命令记录 |
| 启动空态 | 用户级、承诺内；首条消息前在正确 pane 下看到三行中文面板；真实 WezTerm 截图与 pane 数据 |
| 计划同步 | 用户级、承诺内；实际 PostToolUse 输入包含完整 plan，状态与清空更新同步；原生 hook 捕获和 viewer 检查 |
| 自动跟随当前 Codex | 用户级、承诺内；按当前 session_id 自动关联，读取其已有计划并接收变化；新建、恢复及同目录两个不同会话的实际 TUI 验证 |
| 紧凑显示与关闭 | 用户级、承诺内；复用四条上限、滚动、m/a 和 q 行为；已有测试及真实终端验证 |
| 安装配置 | 运维级；核对实际配置入口、备份和托管区段，记录安装后检查结果 |
| 官方使用说明 | 文案；普通启动命令、首次安装、能力缺失提示及当前验证范围与实际一致 |

实现后运行受影响模块和真实官方 TUI。PR 由用户检查并亲自合并。

## 8. 实现与实测记录

官方 Codex 0.164.0、隔离 CODEX_HOME 和独立 WezTerm GUI 中，两个同目录会话在首次输入前各自显示空面板，真实 PostToolUse 更新后显示各自计划。删除第一会话的插件缓存，再 resume 相同 session_id，首次输入前已从官方 transcript 恢复两条任务。实现链路记录：`/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-160007/plugin-panel-report.json`。通过一次性安装脚本生成配置与稳定路径后，同样的场景再次通过：`/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-160543/plugin-panel-report.json`。

受限 GUI PATH、中文数据目录及视觉调整后的完整实测包括自动创建、六任务只见四条、八位编号与完整保存时间、任务 pane 获得焦点后 m/a 切换、resume 恢复和 q 关闭。记录：`/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-170118/plugin-panel-report.json`。受影响单元与入口测试 132 项、插件清单 80 项、紧凑演示浏览器检查 18 项通过。
