# 会话任务面板实现审查记录

## 1. 第一轮审查

审查提交为 `bfac7da89483ce9fac63b3f5b7b2aab5aa9723a2`，独立审查者为 `session_panel_implementation_review`。审查完成后主代理确认工作树干净，重新 fetch 后 origin/main 与 merge-base 均为 `3c4882415d7c38dbbfa1bfacbd856759a2151d79`。

| 问题 | 成立与否及证据 | 归属 | 类或级别及代码质量 | 根因或目标缺口 | 彻底方案及方案依据 |
|---|---|---|---|---|---|
| 首次关联把系统进程的工作目录当成 Codex 会话目录。官方 `--cd/-C` 可以使二者不同，原生事件到达后面板仍保持 pending。 | 技术现象成立，处于最新确认范围之外。主代理用官方 Codex、隔离 CODEX_HOME、有界 PTY 与真实 SessionStart 复现：系统 cwd 为 invocation，事件 cwd 为 project，SessionRouter 保存 owner_pid=null。记录为 `/private/tmp/session-panel-implementation-audit-i2jj_244/result.json`。 | 本次关联实现中的跨目录现象；按用户定稿归承诺外。 | 用户级、承诺外；技术现象 | 进程目录与会话目录不同。当前验收以在项目目录启动或恢复 Codex 为入口。 | 按用户明确范围撤下跨目录参数解析及专用测试。用户先进入目标项目目录，再启动或恢复会话。依据为 2026-10-25 用户原话“我们就讲最简单的，在当前目录下进行工作的这么一种情况”。 |

独立审查返回一项，主代理复现后归为承诺内并添加了扩展。2026-10-25，用户明确当前目录的支持范围；本表按该定稿纠正分类。跨目录扩展已撤下，当前目录验证见第 7 节。

## 2. 实际影响

| 使用路径 | 当前验证结果 |
|---|---|
| 在项目目录直接启动 Codex | 真实新建、任务更新、最多四条和清空通过 |
| 在同一项目目录恢复会话 | 首次消息后恢复历史任务通过；q 后计划继续保存 |
| 会话事件先于面板观察或登记 | 真实独立窗口中两种顺序均通过 |
| 从其他目录使用 --cd/-C 指定项目 | 承诺外；用户先进入项目目录，再启动或恢复会话 |

## 3. 审查前执行记录

| 检查 | 结果与证据 |
|---|---|
| 单元与受影响检查 | 九套 unittest 共 209 项通过，清单检查 91 项通过；记录位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-tdd/` 的 final-affected.log 与 affected-summary.json |
| macOS 与 Linux 进程读取 | macOS 对 12 个实际 Codex 的枚举和单 PID 读取一致；Linux 在独立无网络容器中真实读取 /proc，退出夹具并删除容器；Linux 记录为同目录 linux-native-smoke.log |
| 守卫验证 | 删除 headless 过滤、时限守卫、owner schema 检查和进程匹配检查，分别使对应测试失败。绑定侧记录为同目录 binding-mutations.json；进程侧记录在 process-reader-tdd-20261024-203449 |
| 正常 GUI 流程 | 官方 Codex、独立 WezTerm 和隔离配置完成启动、同目录两会话、空标题和状态栏设置、六条显示四条、清空、删除缓存后恢复、q 后继续保存。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-native-r4/report.json` |
| 最终早到流程 | 事件先到后启用 GUI 观察，以及已有第一面板时第二会话先产生事件后登记面板，随后恢复和关闭流程通过。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-native-final/report.json` |
| 屏幕与尺寸 | 主代理查看启动、六任务和清空真实截图；空态三行、两任务五行、六任务七行且显示四条。清空时采集原始文本含旧行，按实际 pane 行数取可见区域，与三行空态截图对应；派生记录位于 session-event-native-r4/viewport-measurements.json |
| 配置保持 | 安装脚本前后字节保持断言通过，运行结束的 terminal_title、status_line 保持原数组。Codex 自身写入 screen_reader_detection_done 与 model_availability_nux，使整个运行期间的 config_unchanged 记录为 false；该字段记录整文件事实 |
| 独立审查执行 | 审查者回读 R1–R7、成品和截图，独立重跑四套 94 项测试，通过原生 hook 复现目录问题；原始记录为 `/private/tmp/session-panel-implementation-audit-p65fkp3y/result.json` |
| 主代理复现及清理 | 重新执行 `/private/tmp/root-repro-session-panel-cd.py`，获得相同目录不匹配。隔离进程退出，私有后台停止超时后按本次目录逐 PID 清理，最终 remaining_owned=[] |

## 4. 轮次表

本表按用户最新确认的范围修正第一轮分类。

| 轮次 | 承诺内 | 承诺外 | 不正当使用 | 开发/运维级 | 代码质量 |
|---|---|---|---|---|---|
| 1 | 0 | 1 | 0 | 0 | 0 |

## 5. 用户确认后的范围修正

task_panel_process.py、task_panel_launch.py、task-panel-wezterm.lua 和 test-task-panel-process.py 恢复到添加跨目录扩展之前的 `014310a`。真实终端回归在项目目录直接执行 codex 和 codex resume，测试进程的身份核对、退出等待与多窗口截图采集继续使用。

## 6. 扩展撤回前的历史执行记录

以下记录对应扩展撤回前的代码；当前验收记录见第 7 节。

| 检查 | 结果与证据 |
|---|---|
| 测试先行与受影响验证 | 失败测试提交为 `7c5e569`。九套 unittest 共 213 项通过，清单检查 91 项通过；完整输出及 affected-summary.json 位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-fix/` |
| 平台进程读取 | macOS 当前 12 个真实 Codex 进程的枚举与单 PID 读取一致；Linux 在无网络、只读代码挂载的自动删除容器中，真实读取跨目录进程的 /proc/cmdline，解析出带空格的项目目录，夹具退出后读取为空。容器名为 cc-hooks-cd-process-20261025 |
| 真实跨目录回归 | 系统 cwd 为 invocation，原生事件及绑定目录为 project；--cd 绝对路径、-C../project、resume 的 --cd=../project 通过。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-native-20261025/report.json` |
| 截图校对 | 多窗口采集现保存各测试窗口。主代理查看六任务、清空和恢复的目标截图，确认分别为四条可见任务加两条溢出提示、三行空态、五行恢复态。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-native-cleanup-timeout-20261025/` 中的 six-tasks.png、clear.png 与 resume-after-first-event.png |
| 测试进程清理 | E2E 保存私有目录下的 PID、启动时间和命令，逐 PID 核对身份后清理并等待退出。正常停止后残留的辅助进程已回收；注入 daemon stop 超时后，两个已记录测试进程退出，remaining_owned_daemon_processes=[]。超时演练记录为上述目录的 report.json |
| 独立清理复查 | E2E 退出后重新枚举进程并查询指定测试容器，本轮测试进程与容器残留均为空。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-fix/final-process-check.json` |

## 7. 当前目录验收记录

| 检查 | 结果与证据 |
|---|---|
| 单元与入口验证 | 九套 unittest 共 209 项通过，清单检查 91 项通过。完整输出及 affected-summary.json 位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-current-directory-20261025/` |
| 真实当前目录流程 | 独立 WezTerm 的工作目录设为项目目录，直接执行 codex 和 codex resume。等待、首次事件接入、两会话任务显示、六条显示四条、清空、恢复历史任务及 q 后继续保存通过。记录为上述目录 native/report.json |
| 屏幕核对 | 主代理查看 startup.png、six-tasks.png 和 resume-after-first-event.png，确认三行等待、七行四任务与溢出提示、五行恢复态；截图位于上述目录 native/ |
| 测试清理 | GUI 正常退出，私有 daemon stop 返回 0，残留辅助进程回收后 remaining_owned_daemon_processes=[]。独立复查 remaining_owned_processes=[]，记录为上述目录 final-process-check.json |

后续审查与交付按项目当前目录的支持范围执行。
