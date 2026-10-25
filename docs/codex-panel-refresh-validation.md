# 任务面板查询修复与验证

## 1. 目标和范围

目标为消除面板空闲轮询引起的持续 Broken pipe 和连接误报，保持任务同步及已有操作。2026-10-25 用户在根因说明后要求解决问题，随后明确任务与终端操作应随 hook 和用户操作发生。

本次属于用户级、承诺内的小型逻辑修复，生产改动集中在 `watcher/hooks/task_panel.py` 的显示循环和高度调用预算。仓库已有 smoke/E2E；项目缺少独立 DD、TDD 和选择澄清流程规范，建议完善。本任务按协作规范执行测试先行，新增回归在主分支实现上先失败，再验证修复结果。

| 验收项 | 产出物、级别与目标对应 |
|---|---|
| 空闲刷新结束持续查询 | viewer，用户级、承诺内；任务和尺寸保持不变时，后续刷新新增 CLI 调用为零，消除现场的持续连接触发源 |
| 更新任务并保留操作 | viewer，用户级、承诺内；hook 写入的缓存继续刷新，内容和状态变化保持可见；四条上限、滚动、m/a 和 q 可继续使用 |
| 慢响应与失败恢复 | viewer，用户级、承诺内；高度处理共享五秒预算；失败后等待递增间隔，缓存更新继续处理，成功后按当前数据恢复 |
| 复现与真实使用 | 回归测试及隔离 E2E，测试代码；覆盖前三项并核实十二个实际 WezTerm 面板的空闲行为 |

## 2. 根因和实现

原显示循环每轮检查父窗格，再查询高度；两个路径各使用一秒预算。现场对照中，三秒内的 Broken pipe 数量依次为运行时 25、暂停十二个面板时 0、恢复后 14；暂停时正常列表查询耗时 1.164 秒。

同版 WezTerm 会向 CLI 连接发送 mux 通知；短连接关闭后继续写入可能产生 Broken pipe，见 [WezTerm dispatch](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/wezterm-mux-server-impl/src/dispatch.rs)。具体触发的通知类型尚未逐条确认。

显示循环通过已有 curses 尺寸、目标高度、当前挂载和模式识别高度处理的触发条件。计划读取继续使用本地缓存。父 pane 关闭由既有 `task-panel-wezterm.lua` 观察器处理，退出信号保留 `Panel.finish` 的收尾检查。

这是内部触发条件调整；依据为 `show_panel` 已有本地尺寸读取、`Height.fit` 的目标判断和 WezTerm 观察器的 `close_owned`。失败间隔为 2、4、8、16、30 秒，此后保持三十秒；成功、新挂载和 m/a 操作重置。

## 3. 执行记录

| 检查 | 结果与证据 |
|---|---|
| 测试先行 | 三项新增回归在主分支实现上分别复现空闲重复查询、连续重试、慢响应失败；日志 `/private/tmp/task-panel-refresh-checks-20261025/red.log` |
| 项目检查 | CI 同组二十二项本地通过；进程 smoke 首次受沙箱 ps 权限限制，获准只读进程信息后通过；完整记录 `/private/tmp/task-panel-refresh-checks-20261025/checks.json` |
| 十二个真实面板 | 独立 WezTerm 中十二个面板均为七行；八秒空闲新增 CLI 调用零次、Broken pipe 零次；滚动、手动保留高度、自动恢复和 q 通过；记录 `/private/tmp/task-panel-refresh-20261025-r2/report.json` |
| 日志归属 | 被测 GUI 的 stdout/stderr 指向测试日志；记录 `/private/tmp/task-panel-refresh-20261025-r2/log-descriptors.txt` |
| 测试清理 | 按记录的 GUI 与十二个 viewer PID 核对，测试进程均已结束；记录 `/private/tmp/task-panel-refresh-20261025-r2/cleanup.json` |

真实验证直接运行 viewer 和计划存储，调用方另由已有 hook、入口、配置及存储 smoke 覆盖。正式插件更新由用户执行，运行中的旧 viewer 在重新创建后加载新代码。
