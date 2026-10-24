# 官方 Codex 任务面板方案

## 1. 目标与确认状态

唯一目标：使用官方 Codex 的现有 hooks 和自动化脚本，在 WezTerm 中自动显示并同步任务列表。用户正常执行 `codex` 或 `codex resume`，使用共享后台和官方更新。任务面板最多显示四条，更多任务有数量提示并可滚动。

用户已明确要求保持 Codex 源码和官方程序原样使用。本文件提出插件与终端侧的实现，待用户确认后实现。界面沿用已确认的中文紧凑面板；配套中文流程为 `codex-official-hooks-demo.html`。

## 2. 当前事实

| 内容 | 本轮证据 |
|---|---|
| 官方支持计划工具 hook | [官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks) 的工具表明确列出 update_plan；官方 rust-v0.164.0 的 registry.rs 默认函数工具路径生成 PostToolUse 输入 |
| 计划参数实际可读 | 官方二进制实测 PostToolUse 的 tool_name 为 update_plan，tool_input.plan 为完整任务数组。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-144524/report.json` |
| SessionStart 在首条消息触发 | 两个官方 TUI 均在输入前没有 hook，首条消息后得到 SessionStart 和 PostToolUse。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-144803/tui-report.json` |
| 共享后台的 pane 环境可来自首个终端 | 上述两客户端共用 PID 7826；实际 pane 为 96、97，两次 hook 环境均报告 pane 96 |
| WezTerm 可以观察本地前台进程 | 官方 [update-status](https://wezterm.org/config/lua/window-events/update-status.html) 周期事件和 [get_foreground_process_info](https://wezterm.org/config/lua/pane/get_foreground_process_info.html) 提供对应 pane 的进程信息 |
| 本机计划工具已开启 | 本机配置 tools.update_plan.enabled 为 true；安装说明按实际配置检查此项 |

官方二进制实测版本为 0.164.0。此版本是本轮验证对象；插件按事件名称、输入字段和依赖能力判断可用性。

## 3. 职责与数据流

| 组件 | 职责 |
|---|---|
| WezTerm 自动事件 | 检测本地 pane 的 Codex 交互进程，为该 pane 创建底部面板，记录 pane、进程和项目目录 |
| SessionStart / UserPromptSubmit | 根据官方 session_id、cwd 关联终端记录；恢复已有计划；接收首次消息或已加载会话的新消息 |
| PostToolUse，matcher 为 ^update_plan$ | 从 tool_input.plan 保存根 Agent 的完整计划，按 session_id 刷新对应面板 |
| 面板 viewer | 读取插件数据，显示中文空态、最多四条任务及更多提示，处理滚动、m/a 和 q |
| SessionEnd / 进程离开 | 使用已有绑定关闭或结束对应面板 |

启动链路自上而下为：WezTerm 观察到交互 Codex → 创建三行空态面板 → 官方事件提供 session_id → 关联并恢复计划 → PostToolUse 保存新计划 → viewer 刷新。

WezTerm 回调按窗口遍历其标签页和 pane，使用本地前台进程信息识别交互 Codex。后台服务、headless exec 和面板 viewer 保持各自职责。进程读取不可用时保留空态及可知提示。

此处使用 WezTerm 事件是为了满足“首条消息之前就显示面板”的已确认目标，依据是第 2 节实测时机。具体回调的扫描与挂载行为仍须在独立测试窗口验证。

## 4. 会话关联与不确定情况

WezTerm 负责记录真实 pane 身份。hook 输入中的 session_id 是会话身份来源；hook 进程继承的 WEZTERM_PANE 仅作为诊断信息。

SessionStart、UserPromptSubmit 和 PostToolUse 共用一个关联入口。先使用已存在且仍有效的会话绑定；新关联按规范化项目目录匹配当前交互 Codex 终端记录。候选唯一时绑定；候选缺失时保留计划并提示终端记录尚不可用；有多个候选且无法确定时，hook 提供候选面板标识，使用中的 Agent 询问当前用户后调用插件的明确关联操作。

用户确认面板归属后保存 session_id 与 pane 的对应关系。计划缓存按 session_id 保存完整列表，显示容量限制为四条。关联无法确定时保持原数据，提示下一步。

这是纯内部方案：终端身份来自终端本身，会话与计划来自官方事件；无法确定的情况按用户确认的“询问当前使用者”原则处理。

## 5. 状态与事件

| 状态 | 官方会话事件 | update_plan 成功事件 | q | Codex 进程退出 | 同 pane 新 Codex 进程 |
|---|---|---|---|---|---|
| 无面板 | 保存可用会话信息，等待终端观察 | 保存完整计划，等待终端观察 | 无操作入口 | 保持无面板 | 建立空态面板 |
| 等待关联 | 唯一候选则绑定并恢复缓存，否则提示确认 | 保存计划并尝试同一关联入口 | 进入已关闭 | 清理该进程的面板记录 | 建立新的空态面板 |
| 已关联 | 核对当前绑定并恢复缓存 | 更新该会话缓存和显示 | 进入已关闭 | 结束对应面板 | 清理旧进程记录，建立空态面板 |
| 已关闭 | 同一进程保持关闭 | 更新缓存，同一进程保持关闭 | 保持关闭 | 清理该进程记录 | 建立新的空态面板 |

首次检测到 Codex 的唯一创建入口在 WezTerm 观察逻辑；用户确认及官方事件进入同一会话关联入口；计划写入继续使用现有 Store。缓存或终端读取错误显示中文提示，恢复读取后刷新；q 和进程退出继续按上表处理。

## 6. 安装与日常使用

插件安装步骤配置一次 WezTerm 模块加载，记录备份及托管区段。已有终端配置通过托管区段接入；默认配置场景创建最小加载入口。加载入口使用稳定的插件数据路径，更新插件时刷新模块位置。

本机已检查默认的两个用户配置位置均不存在；实现前还需核对当前 GUI 的实际配置入口。安装行为包括刷新 hook 信任与确认计划工具开启，具体变更在实际安装前展示。

日常命令为 `codex` 或 `codex resume`。窗口识别和面板创建由 WezTerm 自动处理。官方 hook 负责保存计划，Agent 调用 update_plan 时面板随之更新。首次关联完成前显示等待提示。

## 7. 验收与验证

| 验收项 | 产出及验证方式 |
|---|---|
| 官方程序使用 | 用户级、承诺内；正常官方 CLI 新建及恢复会话，保留共享后台；实际进程和命令记录 |
| 启动空态 | 用户级、承诺内；首条消息前在正确 pane 下看到三行中文面板；真实 WezTerm 截图与 pane 数据 |
| 计划同步 | 用户级、承诺内；实际 PostToolUse 输入包含完整 plan，状态与清空更新同步；原生 hook 捕获和 viewer 检查 |
| 关联不明 | 用户级、承诺内；同项目多候选时明确询问当前用户，确认后关联；两个实际 TUI 验证 |
| 紧凑显示与关闭 | 用户级、承诺内；复用四条上限、滚动、m/a 和 q 行为；已有测试及真实终端验证 |
| 安装配置 | 运维级；核对实际配置入口、备份和托管区段，记录安装后检查结果 |
| 官方使用说明 | 文案；普通启动命令、首次安装、能力缺失提示及当前验证范围与实际一致 |

实现前对启动检测、关联及官方 payload 写失败测试；实现后运行受影响模块和真实官方 TUI。后续按项目规则完成独立实现、视觉及文案审查、最终验证与 PR。PR 由用户检查并亲自合并。
