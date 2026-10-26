# 官方 Codex 任务面板方案

> 历史材料：本文中的任务面板及配套构建方案已于 0.2.0 退役。当前功能及已有面板移除步骤见 [Codex 使用指南](./codex-usage.zh-CN.md)。

## 1. 当前支持范围

使用官方 Codex 的原生 hooks、本地进程信息与 WezTerm 自动事件显示任务面板。用户先进入项目目录，再执行 `codex` 或 `codex resume`，沿用官方共享后台与升级方式。

详细设计、R1 至 R7 验收清单和状态流转以 [原生会话事件设计](codex-session-event-panel-design.md) 为准；使用入口见 [Codex 使用说明](codex-usage.zh-CN.md)。

## 2. 组件与数据流

| 组件 | 职责 |
|---|---|
| WezTerm update-status | 识别当前 pane 的本地交互 Codex PID，创建三行底部面板 |
| task_panel_process | 从系统读取 PID、工作目录和进程启动时间 |
| SessionStart、UserPromptSubmit | 刷新已安装运行文件，从原生 session_id 与 transcript_path 恢复计划，并关联实际进程对应的面板 |
| PostToolUse，matcher 为 ^update_plan$ | 保存主 Agent 的完整 plan，关联并刷新当前会话面板 |
| task_panel_binding | 使用原生会话事件与实际进程记录接入已登记或随后登记的面板 |
| viewer | 显示任务、连接状态和保存时间，处理四条显示上限、滚动、m/a 与 q |
| SessionEnd、进程离开 | 标记对应会话结束，进程退出后清理其面板 |

启动先显示“等待当前会话信息”。首次原生事件到达后按完整 session_id 读取任务；恢复会话的历史任务在该时刻接入。后续 update_plan 替换或清空相同会话的完整计划。

同目录实例的首次关联使用已确认的本地进程启发式；按顺序启动和首次使用的两个会话已有真实验证。标题与 status_line 使用用户自己的设置，会话编号用于插件内部关联。

## 3. 配置与操作

用户安装或更新插件、信任 hooks 后，调用 `$watcher:task-panel-configure`。技能检查环境、备份 WezTerm 配置、安装稳定运行文件并接入加载区段。用户通过 WezTerm 原生重载使配置生效，现有 Codex 可在下一次原生事件到达时加载任务。

自动模式使用三至七行，最多显示四条任务，超出数量有提示并支持滚动。先点击任务面板取得焦点，再使用上下键、PgUp/PgDn、m/a 或 q。q 在当前 Codex 进程运行期间保持关闭，重新进入 Codex 后再次创建面板。

## 4. 执行记录

当前目录的真实启动、恢复、计划更新、清空及关闭记录位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-current-directory-20261025/native/report.json`。实现审查与范围处理见 [审查记录](codex-session-event-panel-implementation-review.md)。中文流程演示见 [会话事件演示](codex-session-event-panel-demo.html)。

2026-10-25 用户明确本次免做视觉对抗，继续完成文档和交付。PR 由用户检查并亲自合并。
