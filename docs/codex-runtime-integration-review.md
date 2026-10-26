# Codex 运行集成设计审查记录

> 历史材料：本文中的任务面板及配套构建方案已于 0.2.0 退役。当前功能及已有面板移除步骤见 [Codex 使用指南](./codex-usage.zh-CN.md)。

## 1. 审查对象和结果

第一轮审查对象为提交 `aca219198034769b7312e8dcac68e1dc0443a0e0` 的补充设计和 HTML 演示。独立对抗者为该轮 `runtime_design_adversary`，完成只读审查并逐项自驳后返回四项问题。我已逐条核对，四项成立。2026-10-22 用户确认下表结论与修订方案。第 2、3 节保留第一轮证据和原始行号，第 4 节记录确认后的修订；第 5 至 8 节记录第二轮审查及确认后的修订。

目标方向对应用户已确认的 CC hooks Codex 适配及自动 WezTerm 下方面板。原适配代码仍位于任务分支；原生目录修复、面板及新增原生集成处于设计审查阶段。

## 2. 完整审查表

| 方向/范围/方案 | 对抗者原话 | 成立与否及证据 | 怎么改及方案依据 |
|---|---|---|---|
| 方案，R5、R6 | 计划锁保证顺序，但当前方案没有保证已发布计划在取消后进入缓存，任务面板仍可能永久保留旧计划。 | 成立。补充设计 `:89`、`:93` 依赖同步 PostToolUse。原生 [plan.rs:86](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/handlers/plan.rs#L86) 先发布事件；[registry.rs:767](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/registry.rs#L767) 的回调带取消包装；[parallel.rs:247](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/src/tools/parallel.rs#L247) 对普通工具可中止 dispatch。事件发布到回调开始之间存在取消窗口。 | 明确计划提交点。等待计划锁和提交前保持可取消；提交后沿用原生 `finishes_on_cancellation` 的完成机制，使同步回调在配置的时限内结束后释放锁。外层 dispatch 和 registry 内层取消语义同时覆盖。回调失败须有明确诊断及恢复规则。加入事件发布后、缓存写入前取消的确定性测试。依据为原生完成机制及本次内部集成推断；需在修订设计中写清界限。 |
| 方案，R4、R9 | 持久化 starting 状态缺少创建进程被中断后的恢复规则，后续启动可能一直保持 starting。 | 成立。补充设计 `:99` 允许保存 starting；`:118` 对新 attach 和重复事件均保持该状态。写完状态后、执行 split 前终止 hook，会留下有效锁已释放、没有 viewer 和 ready 的持久状态。正常超时路径不能覆盖进程已终止的情况。 | 为 starting 保存创建期限；启动和重试在绑定锁内走同一核对入口。有对应 nonce 的有效 pane 则接管；期限内继续核对；期限已过且没有实例时原子替换 nonce 并重新创建；晚到旧实例核对 nonce 后结束自身。加入“落盘 starting 后终止 hook”测试。依据为现有设计的实例 nonce 与不确定创建机制，属于内部修订。 |
| 范围，R1、R2、原适配验收 6 | 无条件拦截 remote commit 扩大了已有 gate 的作用域，当前设计尚未得到这项行为变更的确认。 | 成立。补充设计 `:56` 写了远端 commit 诊断并拦截。现有 `watcher/hooks/bash-gate.sh:19`、`:113` 和 `docs/bash-gate-design.md:84` 要求目标 Git 根目录配置 `.watcher/` 才启用；remote 标识无法证明已配置。 | 本轮工作目录修复按本地真实目录兑现既有 `.watcher/` 契约。远端执行上下文准确输出，远端策略写清支持边界；删除草案中无条件远端阻断行为。完整远端 opt-in 识别与执行策略若有后续需求，再按确认的目标处理。依据为项目现有 gate 作用域和原适配验收 6。 |
| 方案，R3、R4、R8、R9 | 独立安装方案遗漏了新增 Codex 原生能力的交付与能力检查，当前官方 0.163.0 上安装插件不能满足自动启动契约。 | 成立。补充设计 `:43` 的运行依赖表遗漏了 `:62` 至 `:74` 拟新增的客户端上下文和 attach 调度。原生 [session_start.rs:40](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/hooks/src/events/session_start.rs#L40) 缺少这些字段，`hook_runtime.rs:128` 使用 pending 调度。插件启动条件要求当前官方输入尚未提供的字段。 | 将具备这些能力的 Codex 客户端及 daemon 明列为配套交付产物，定义能力标识与握手检查。安装说明提供可安装构建产物、来源提交、能力验证和升级步骤；旧 CLI 或客户端与 daemon 能力不一致时输出具体诊断。测试覆盖缺能力、匹配能力和版本组合。依据为当前官方接口和本设计新增能力，属于本次交付方案修订。 |

第一、第二、第四项修订中的新增机制属于内部设计推断。它们分别对应已生效计划的同步、面板创建恢复和独立安装目标；修订时应继续接受独立设计审查。

## 3. 执行记录和验证范围

| 执行方及检查 | 结果及证据 |
|---|---|
| 对抗者读取设计与本地代码 | 完整阅读补充设计、演示、原适配设计、gate 设计及 hook、清单、smoke 和复用 viewer；回报具体行号与自驳记录 |
| 对抗者读取原生源码 | 核对 v0.163.0 的 plan、registry、parallel、SessionStart、SessionEnd、hook runtime、command runner 及 resume 路径 |
| 我核实取消窗口 | 重新读取 plan 事件发布、registry 的 PostToolUse 取消包装，以及 parallel 的完成与 abort 分支；确认窗口发生在回调开始前也可造成缺失 |
| 我核实状态与作用域 | 重新读取补充设计第 6、7 节及 gate 的 `.watcher/` 作用域判断；确认中断路径未定义、远端条款扩大原契约 |
| 我核实能力与依赖 | 重新读取原生 SessionStartRequest 字段和当前连接状态；对照补充设计 R8 和第 5 节，确认交付前提遗漏 |
| 工作树核对 | 对抗前后 HEAD 为 `aca2191`，工作树为空；本记录在对抗结束后新增 |
| 演示脚本 | 语法检查和 15 项基于 DOM 桩的交互检查通过；记录在仓库外 `codex-support-validation-2026-10-22/runtime-demo-script-checks.json` |
| 浏览器渲染 | 本机 Chromium 因 `sandbox_parameters_mac.mm:87` 的 `Input/output error (5)` 退出，未得到截图。记录在 `runtime-demo-browser.log`；本轮进程退出码为 -5，临时配置目录已清理 |
| 原生运行及交付 | GitHub 下载、Git fetch、WezTerm IPC 及嵌套 Codex 启动的既有外部限制继续存在，相关步骤尚待完成 |

## 4. 确认后的修订

| 审查问题 | 本轮设计改动 | 核对方式及后续验证 |
|---|---|---|
| 取消后的计划缓存 | 补充设计第 6.1 节定义提交点、Session 完成任务、有界回调、错误诊断及阶段转移表；R5、R9 对应更新 | 对照原生取消窗口检查外层调度及 registry 两处处理；演示增加“计划生效后取消”；原生取消测试在测试先行阶段执行 |
| starting 中断恢复 | 第 6.2 节定义持久创建期限、统一核对入口、到期重建、时钟回拨及迟到实例；第 7 节状态表同步更新 | 演示增加启动中断、推进创建期限、重复启动及旧实例迟到；真实进程中断测试在实现阶段执行 |
| 远端 gate 作用域 | 第 4 节明确本机 `.watcher/` 支持范围及远端支持边界；原适配设计第 4.5 节同步有效目录修复依据 | 回读现有 opt-in 判定及原验收 6；本地与远端分支自动验证在实现阶段执行 |
| 配套原生能力交付 | 第 10 节定义能力协商、hook 能力字段、诊断、同源构建、来源及 SHA-256 和独立安装验收；R8、R9 与依赖表对应更新 | 演示增加能力不匹配及恢复；真实构建、查询及独立安装在交付验证阶段执行 |

用户同时要求完整可见的本地绝对路径和中文演示。工作区 `AGENTS.md` 保存这两条长期偏好；HTML 的标题、操作、状态、说明、无障碍标签及数据流转文字已改为中文，工具和 API 名称保留原名。

修订后执行 38 项基于 DOM 桩的演示交互检查，结果通过，覆盖 24 个按钮的中文标签、四条中文数据流、正常交互及本轮新增恢复场景。记录在仓库外 `codex-support-validation-2026-10-22/runtime-demo-zh-script-checks.json`。浏览器渲染受第 3 节记录的环境限制阻断，真实 WezTerm 尚待运行验证。

本轮设计修订完成后，按协作规范第 4.3.7 条报告整体情况。建议再进行一轮设计对抗，重点核对提交点后的任务所有权、有界回调和能力协商契约；由用户决定下一轮设计对抗或进入测试先行。

## 5. 第二轮设计对抗

用户确认继续后，独立对抗者 `runtime_design_round2` 对提交 `fa558265f5063e9db3395057c390aaac457400d8` 完成只读审查。对抗者完成逐项自驳后返回一项问题。我重新阅读补充设计、验收清单和演示脚本，并在 Node VM 中执行演示状态函数，确认下表路径成立。用户随后确认本轮结论及统一协调方案，第 6 节记录确认内容，第 8 节记录修改与验证。

| 方向/范围/方案 | 对抗者原话 | 成立与否及证据 | 怎么改及方案依据 |
|---|---|---|---|
| 方案，R4、R9 | 创建期限只有判断规则，缺少无 viewer 时推动到期恢复的执行者。期限内重试仍可能永久停在 starting。 | 成立。审查提交 fa55826 的补充设计第 118、120、141 行规定期限内保持 starting，推进依赖后续事件。该提交演示第 100、119 行采用相同规则。执行顺序为创建中断、期限内 attach、期限到达；结果依次保持 starting、零可见 pane，调度回调数量为零；增加 duplicate 后才转为 visible。复现属于演示状态机验证，原生运行验证处于后续步骤。 | 将创建及恢复收束到当前 attach 的有界协调入口，统一承担锁等待、旧尝试核对、到期重建、ready 确认、焦点恢复和终态诊断。创建尝试期限与整个 hook 预算分别配置。协调过程在面板可见或故障已告知时结束。依据为现有同步 SessionStart hook、绑定锁及实例 nonce；这是内部设计推断，2026-10-22 用户已确认。 |

| 轮次 | 方向成立 | 范围成立 | 方案成立 | 不成立 |
|---|---|---|---|---|
| 1 | 0 | 1 | 3 | 0 |
| 2 | 0 | 0 | 1 | 0 |

starting 恢复机制连续两轮产生设计缺口，命中 playbook `references/adversary-review.md` 第 8 条的停修信号。统一协调应归属创建入口；数据期限负责表达尝试有效期，当前 hook 进程负责推进流程。

## 6. 第二轮确认的修订

| 项目 | 具体方案 | 验证目标 |
|---|---|---|
| 协调职责 | SessionStart 调用唯一创建协调函数；attach 与重复启动进入同一函数。每次核对持绑定锁，等待 ready 和期限时释放锁，再取得锁核对最新目标、closed 状态及 nonce。 | 同时启动、切换会话、用户关闭及迟到实例均遵循同一绑定更新入口。 |
| 时间预算 | 每次创建尝试 4 秒，其中 CLI 操作总预算 3 秒、viewer 确认 1 秒；整次协调使用单调时钟限制为 10 秒，SessionStart hook timeout 为 12 秒。持久创建期限采用独立的 4 秒配置。 | 期限内重开可等待旧尝试到期并完成一次重建；锁等待、轮询和 CLI 均消耗同一协调预算。 |
| 终态与接管 | 原协调进程中断后，下一次 attach 的协调函数接管核对。当前协调返回时给出可见面板或含恢复操作的故障诊断；预算耗尽时记录故障并保留待核对的 nonce。较新 attach 和用户关闭按绑定身份核对生效。 | 重开后停留首条输入界面即可得到结果；故障后重开能继续核对已有实例。 |
| 状态与演示 | 将创建期限到达和协调预算耗尽纳入状态表。演示推进创建期限后由协调流程自动完成恢复，展示正在等待及终态结果。 | 用户可从中文演示观察自动恢复；测试推进假时钟即可驱动同一流程。 |
| 确定性测试 | 覆盖 starting 落盘后终止、期限内重开后保持空闲、并发接管、预算耗尽、时钟回拨、较新 attach、q 和迟到 nonce。 | 每条路径核对最终 pane、绑定状态、焦点及诊断，验证 R4、R6、R7、R9。 |

本节为用户已确认的内部方案，补充设计第 6.2、7、8、11 节按本节修订。根据协作规范第 4.3.7 条，修改与核对完成后报告，再由用户决定后续步骤。

## 7. 第二轮执行记录

| 检查 | 结果及证据 |
|---|---|
| 独立审查执行 | `runtime_design_round2` 状态为 completed，返回一项问题及自驳、源码和检查范围；该轮执行完成。 |
| 工作树核实 | 独立审查结束后 `git status --short` 为空，HEAD 为 fa558265f5063e9db3395057c390aaac457400d8。随后新增本轮审查记录。 |
| 我核实状态机 | Node VM 直接执行演示中的 reset、apply、attach 和 reconcile；结果保存在 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-support-validation-2026-10-22/runtime-design-round2-reproduction.json`。 |
| 原生源码准备 | 本机已有稀疏源码的 HEAD 为 83086188ae0614bd882818ff1aa23f3194962012；GitHub 标签对象 129b8ec7ee6f4511557a4856279f529025c25af4 指向此提交。源码副本位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-src`，Git 工作树干净。 |
| 源码完整性 | 稀疏副本已有 core、hooks、tui 等目录；补全时 Git 报 `Could not resolve host: github.com`，app-server 等目录仍需取得。 |
| 当前流水线 | 第二轮审查及逐条核实完成，用户已确认修订方案。设计与演示修改结果见第 8 节。 |

## 8. 第二轮确认后的修改与验证

| 审查问题 | 设计与演示改动 | 验证结果 |
|---|---|---|
| 无 viewer 时恢复缺少推进者 | 补充设计第 6.2 节将创建与恢复集中到当前 SessionStart 的 `coordinate_panel`；分别定义创建、CLI、viewer、协调及 hook 预算；明确等待时释放锁、接管、终态诊断和焦点恢复 | 核对配置为 4 秒创建期限、10 秒协调预算、12 秒启动 hook timeout；计划 PostToolUse 的 5 秒预算继续适用于计划保存回调 |
| 同一启动协调中的状态与退出 | 第 7 节增加 deadline、budget、interrupt，完整填写六种状态与十三种事件；每个状态仍由 store 的持锁绑定更新入口写入 | 自动核对两张表共 78 个单元格，均有拟定行为及“推断”标记 |
| 用户观察自动恢复与故障 | 中文演示通过单一协调定时任务推进；期限内重开后保持空闲可自行恢复；增加协调超时、协调进程及剩余预算显示，以及创建中断恢复数据流 | 27 项脚本场景检查通过，覆盖 26 个按钮的中文标签、五条竖向数据流、自动恢复、重复启动、会话切换、关闭、超时、重置及既有计划行为 |
| 检查是否识别恢复缺口 | 修改演示前执行新检查；分别删除自动推进、定时任务清理和预算守卫进行变异核验 | 修改前 18/27 项通过，自动恢复等九项因目标行为缺失而失败；修改后 27/27 项通过；三项变异分别触发对应失败 |

上述状态、预算与协调归属为用户已确认的内部设计。演示验证使用 DOM 桩和假单调时钟；真实浏览器及 WezTerm 的运行验证继续按补充设计第 11 节执行。

| 执行记录 | 完整路径 |
|---|---|
| 可复跑演示检查脚本 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-support-validation-2026-10-22/runtime-demo-coordinator-checks.cjs` |
| 修改前失败结果 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-support-validation-2026-10-22/runtime-demo-coordinator-before.json` |
| 修改后通过结果 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-support-validation-2026-10-22/runtime-demo-coordinator-after.json` |
| 定时推进、清理及预算守卫变异结果 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-support-validation-2026-10-22/runtime-demo-coordinator-mutations.json` |
| 状态表和预算一致性结果 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-support-validation-2026-10-22/runtime-demo-coordinator-contracts.json` |

本轮设计修订及演示检查完成。建议下一步进入测试先行，将自动恢复、进程中断、锁和 CLI 时限落实为真实插件测试；原生目录、连接上下文及计划取消行为按既有验收执行原生测试。根据协作规范第 4.3.7 条，由用户决定进入测试先行、再次设计对抗或继续修订。
