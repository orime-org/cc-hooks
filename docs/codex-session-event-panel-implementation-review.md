# 会话任务面板实现审查记录

## 1. 第一轮审查

审查提交为 `bfac7da89483ce9fac63b3f5b7b2aab5aa9723a2`，独立审查者为 `session_panel_implementation_review`。审查完成后主代理确认工作树干净，重新 fetch 后 origin/main 与 merge-base 均为 `3c4882415d7c38dbbfa1bfacbd856759a2151d79`。

| 问题 | 成立与否及证据 | 归属 | 类或级别及代码质量 | 根因或目标缺口 | 彻底方案及方案依据 |
|---|---|---|---|---|---|
| 首次关联把系统进程的工作目录当成 Codex 会话目录。官方 `--cd/-C` 可以使二者不同，因此即使只有一个 Codex 实例，真正的 SessionStart 已到达，面板仍保持 pending；后续事件也无法修复这一目录不匹配。 | 成立。主代理用官方 Codex、隔离 CODEX_HOME、有界 PTY 与真实 SessionStart 重新复现：系统 cwd 为 invocation，事件 cwd 为 project，生产 SessionRouter 保存 owner_pid=null，生产 prepare 创建的绑定保持 pending。主代理记录为 `/private/tmp/session-panel-implementation-audit-i2jj_244/result.json`。 | 本次引入。新 task_panel_binding.py 的首次候选和 launcher 重试依赖 cwd 相等；原主分支通过原生编号显示取得身份。 | 用户级、承诺内，P2；功能问题 | R2、R3 的常规 CLI 启动关联存在缺口。当前进程读取提供系统目录，首次关联需要 Codex 的有效会话目录。 | 在公共目录解析入口使用已读取的完整 argv，识别官方 --cd 与 -C，按系统目录解析相对路径；首次匹配、launcher 重试和项目名显示共用有效目录。PID 与系统启动时间继续标识运行实例。补失败测试及从其他目录启动的真实回归。依据为现有 ProcessReader 的完整 argv 与官方 CLI 参数；属于内部字段语义修正。 |

独立审查返回一项问题，主代理已核实成立。修复方案等待用户按协作规范第 4.6.5 条确认。

## 2. 实际影响

| 使用路径 | 当前验证结果 |
|---|---|
| 在项目目录直接启动 Codex | 真实新建、任务更新、最多四条和清空通过 |
| 在同一项目目录恢复会话 | 首次消息后恢复历史任务通过；q 后计划继续保存 |
| 会话事件先于面板观察或登记 | 真实独立窗口中两种顺序均通过 |
| 从其他目录使用 --cd/-C 指定项目 | 关联保持等待，需要本轮修正 |

## 3. 执行记录

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

下一步建议按公共有效目录方案修正，并把已复现路径固化为测试。用户确认审查结果与方案后进入修复。
