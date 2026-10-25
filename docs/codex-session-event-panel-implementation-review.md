# 会话任务面板实现审查记录

## 1. 第一轮审查

审查提交为 `bfac7da89483ce9fac63b3f5b7b2aab5aa9723a2`，独立审查者为 `session_panel_implementation_review`。审查完成后主代理确认工作树干净，重新 fetch 后 origin/main 与 merge-base 均为 `3c4882415d7c38dbbfa1bfacbd856759a2151d79`。

| 问题 | 成立与否及证据 | 归属 | 类或级别及代码质量 | 根因或目标缺口 | 彻底方案及方案依据 |
|---|---|---|---|---|---|
| 首次关联把系统进程的工作目录当成 Codex 会话目录。官方 `--cd/-C` 可以使二者不同，因此即使只有一个 Codex 实例，真正的 SessionStart 已到达，面板仍保持 pending；后续事件也无法修复这一目录不匹配。 | 成立。主代理用官方 Codex、隔离 CODEX_HOME、有界 PTY 与真实 SessionStart 重新复现：系统 cwd 为 invocation，事件 cwd 为 project，生产 SessionRouter 保存 owner_pid=null，生产 prepare 创建的绑定保持 pending。主代理记录为 `/private/tmp/session-panel-implementation-audit-i2jj_244/result.json`。 | 本次引入。新 task_panel_binding.py 的首次候选和 launcher 重试依赖 cwd 相等；原主分支通过原生编号显示取得身份。 | 用户级、承诺内，P2；功能问题 | R2、R3 的常规 CLI 启动关联存在缺口。当前进程读取提供系统目录，首次关联需要 Codex 的有效会话目录。 | 在公共目录解析入口使用已读取的完整 argv，识别官方 --cd 与 -C，按系统目录解析相对路径；首次匹配、launcher 重试和项目名显示共用有效目录。PID 与系统启动时间继续标识运行实例。补失败测试及从其他目录启动的真实回归。依据为现有 ProcessReader 的完整 argv 与官方 CLI 参数；属于内部字段语义修正。 |

独立审查返回一项问题，主代理已核实成立。2026-10-25，用户表示“另外，你继续完成你当前的工作。我认可你当前工作的分析和建议，继续吧”，确认本轮修复方案。修复提交为 `2a8320e`，真实终端回归与清理检查提交为 `0309d01`。

## 2. 实际影响

| 使用路径 | 当前验证结果 |
|---|---|
| 在项目目录直接启动 Codex | 真实新建、任务更新、最多四条和清空通过 |
| 在同一项目目录恢复会话 | 首次消息后恢复历史任务通过；q 后计划继续保存 |
| 会话事件先于面板观察或登记 | 真实独立窗口中两种顺序均通过 |
| 从其他目录使用 --cd/-C 指定项目 | 修正后，真实绝对路径 --cd、相对路径 -C 连写，以及 resume 的 --cd= 相对路径均完成关联；项目名来自有效会话目录 |

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

| 轮次 | 承诺内 | 承诺外 | 不正当使用 | 开发/运维级 | 代码质量 |
|---|---|---|---|---|---|
| 1 | 1 | 0 | 0 | 0 | 0 |

## 5. 第一轮修复表

| 问题 | 修否 | 改了什么 | 怎么验证 |
|---|---|---|---|
| --cd/-C 使系统目录与会话目录不同时，面板关联持续等待 | 已修复 | task_panel_process.session_directory 统一识别 --cd、-C、等号和短参数连写形式，使用系统目录解析相对路径，按 -- 结束参数解析。macOS 与 Linux 读取共用该函数；首次路由、launcher 消费早到事件及项目名使用同一有效目录。 | 失败测试先记录 28 个失败子用例；修复后进程读取 34 项、调用方与面板入口合计 213 项测试通过。真实 WezTerm 验证三个启动参数形式、早到事件、两会话独立计划、清空、恢复和 q 后继续保存。 |

## 6. 修复后执行记录

| 检查 | 结果与证据 |
|---|---|
| 测试先行与受影响验证 | 失败测试提交为 `7c5e569`。九套 unittest 共 213 项通过，清单检查 91 项通过；完整输出及 affected-summary.json 位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-fix/` |
| 平台进程读取 | macOS 当前 12 个真实 Codex 进程的枚举与单 PID 读取一致；Linux 在无网络、只读代码挂载的自动删除容器中，真实读取跨目录进程的 /proc/cmdline，解析出带空格的项目目录，夹具退出后读取为空。容器名为 cc-hooks-cd-process-20261025 |
| 真实跨目录回归 | 系统 cwd 为 invocation，原生事件及绑定目录为 project；--cd 绝对路径、-C../project、resume 的 --cd=../project 通过。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-native-20261025/report.json` |
| 截图校对 | 多窗口采集现保存各测试窗口。主代理查看六任务、清空和恢复的目标截图，确认分别为四条可见任务加两条溢出提示、三行空态、五行恢复态。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-native-cleanup-timeout-20261025/` 中的 six-tasks.png、clear.png 与 resume-after-first-event.png |
| 测试进程清理 | E2E 保存私有目录下的 PID、启动时间和命令，逐 PID 核对身份后清理并等待退出。正常停止后残留的辅助进程已回收；注入 daemon stop 超时后，两个已记录测试进程退出，remaining_owned_daemon_processes=[]。超时演练记录为上述目录的 report.json |
| 独立清理复查 | E2E 退出后重新枚举进程并查询指定测试容器，本轮测试进程与容器残留均为空。记录为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/session-event-cd-fix/final-process-check.json` |

本轮修复及受影响验证已完成。建议再进行一轮实现审查，核对公共目录语义及三个调用位置；下一步由用户按协作规范第 4.6.8 条决定。
