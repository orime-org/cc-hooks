# 三项收尾与面板移除：实现验证记录

## 1. 当前验证对象

实现提交为 `bd42ebb`，测试先行提交为 `0b25d52`。目标及验收以同目录 `round-summary-panel-retirement-design.md` 为准。

本记录覆盖测试先行、实现后的受影响范围验证和隔离实际使用。实现审查及修正见同目录的 `round-summary-panel-retirement-implementation-review.md`。用户已明确本次免视觉对抗，并授权修正后继续 PR 和发布准备；最终验证见第 6 节。

## 2. 测试先行与自动检查

记录目录为 `/private/tmp/round-summary-validation-20261026`。

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 新规则注入的失败检查 | 两个平台缺少三项、字数及适用场景等规则，新增检查失败 | `announce-red.log`、`red-results.json` |
| 面板退役的失败检查 | 原有面板事件、运行文件、技能、构建和 CI 入口仍存在，新增检查失败 | `manifests-red.log`、`red-results.json` |
| 三项规则注入 | 两个平台的 49 项检查通过，含既有交接和子代理处理 | `smoke-announce.log` |
| 开发检查修正 | 新增临时目录失败回归先失败；设置严格模式后 50 项检查通过 | `tempfile-regression-red.log`、`tempfile-regression-green.log` |
| 发布布局及保留入口 | 75 项检查通过，面板相关事件、运行文件、配置技能及构建入口移除 | `smoke-manifests.log` |
| 注入长度 | 完整共享输出 9706 UTF-16 单元，低于 9800 门槛 | `check-size.log` |
| 长度测量分支 | Node、Python、wc 三条路径均测得 9706 并通过 | `check-size.log`、`size-paths.json` |
| CI 同组检查 | 11 项通过，覆盖两平台 Stop、手动审计、提交检查、命令上下文、解析、manifest 及注入 | `suite-results.json` 及对应完整日志 |
| 保留源码语法 | 保留的 Python 文件 AST 解析及 hook Shell 的 `bash -n` 通过 | 本轮命令执行记录 |

功能删除包括面板专用测试和旧配套构建入口；CI 采用保留的检查集合。Stop 实现和 Claude Code 的 hook 连接配置沿用主分支内容。

## 3. 真实 Codex 使用

使用本机官方 Codex、隔离的配置及插件文件副本，真实模型为当前用户配置的 `gpt-6.1-sol`。模型运行使用只读沙箱和临时会话；已核对源码的隔离 hook 通过自动化测试参数授权执行。首次受当前工具网络限制而退出，获准联网后完成以下验证。

| 场景 | 实际结果 | 证据 |
|---|---|---|
| 执行现有 smoke | 真实命令 `python3 smoke.py` 输出 `SMOKE_OK`，退出码 0；最终回复包含三项 | `codex-real/work-network.jsonl`、`work-network-final.txt` |
| 三项长度 | 当前任务 10 字、当前任务的阶段 6 字、工作纪律自评 10 字，合计 26 字 | `codex-real/verified-work.json` |
| 普通问答 | 回答“20 + 20 + 30 = 70”，三项字段未出现 | `codex-real/question-final.txt`、`verified-question.json` |
| 进程及凭证清理 | 两次成功运行及首次受限运行的已记录 PID 已退出；临时认证副本和生成的模型缓存、数据库、技能副本已清除 | `cleanup.json` |

本次观察验证了两个真实场景。规范由自然语言指引，实际遵循程度以运行结果说明。

## 4. 真实 WezTerm 移除验证

测试使用独立 WezTerm 配置、单独创建的窗口和旧版运行文件。旧运行文件来自主分支提交 `0f60acbd482861a98194c0e2376394fa8d550379`；本轮给隔离 Lua 副本的既有状态回调增加计数探针，观察重载后的停止情况。旧 viewer 通过原 `prepare` 及 `main` 运行，在真实底部窗格里按 q 退出。

| 操作 | 结果 | 证据 |
|---|---|---|
| 旧安装器配置加载区段 | 独立配置含原托管区段及运行副本，真实面板显示 | `wezterm-retirement/configured.lua`、`before.png`、`before-panel.txt` |
| 备份并移除加载区段 | 剩余配置正文与原始用户配置逐字一致 | `wezterm-retirement/wezterm.lua.backup`、`wezterm.lua`、`report.json` |
| 原生重载 | 回调计数停止增长 | `wezterm-retirement/status-probe.log`、`report.json` |
| 面板按 q | 面板进程退出，窗格从 2 个变为 1 个，原父窗格保留 | `wezterm-retirement/after.png`、`closed-bindings.json`、`report.json` |
| 清理专用数据 | `task-panel` 与 `task-panel-integration` 两个目录移除 | `wezterm-retirement/report.json`、`cleanup.json` |
| 清理测试进程 | GUI、父窗格进程及 viewer 的已记录 PID 全部退出 | `wezterm-retirement/owned-processes.json`、`report.json`、`cleanup.json` |

主 Agent 已查看前后真实截图，确认底部任务面板在移除后消失，父窗格继续显示原内容。本测试验证旧面板退出方式；新发布包入口移除另由自动检查覆盖。用户正式安装、更新和本机终端配置继续由用户执行。

## 5. 文案核对

独立对抗者 `/root/summary_retirement_copy_review` 核对两份 README、使用指南、新版本更新记录、设计与审查记录、18 份历史标记及 PR 草稿。返回的环境说明问题经主 Agent 回读 `bash-gate.sh:113` 及 `codex_gate_context.py:186` 核实后，将三处 Python 要求统一为项目现有的 Python 3.11+，提交为 `1654f16`。

安装和更新命令与已有隔离安装记录及当前官方 CLI help 对应；当前指南的本地链接均存在，历史材料均有退役标记。上述普通文案问题已修正。

## 6. 最终验证与交付条件

最终验证前同步 `origin/main`，任务分支与主分支关系为已同步。代码、版本及文案验证对象为 `1654f16`，主分支基线为 `0f60acbd482861a98194c0e2376394fa8d550379`。

| 项目 | 结果与记录 |
|---|---|
| CI 同组全部检查 | 11 项全部通过；完整输出在 `/private/tmp/round-summary-validation-20261026/final/`，结果见 `results.json` |
| 仓库语法检查 | 11 个 Python 文件 AST、4 个 Shell 文件 `bash -n`、3 个 JavaScript 文件 `node --check`、5 个 JSON 文件解析通过 |
| 版本和发布树 | 两个平台 manifest 均为 0.2.0；Git 发布树包含 32 个插件文件，面板运行文件及配置技能移除，Codex 保留三类共享 hook |
| Diff 检查 | 相对主分支的 `git diff --check` 通过 |
| 验证总记录 | `/private/tmp/round-summary-validation-20261026/final/verification.json` |

本仓库适用的自动检查由 CI 套件及源码语法检查覆盖；本次改动的真实使用证据见第 3、4 节。视觉审查脚本保持既有实现，本任务按用户确认免视觉对抗。

三项规则及适用场景、Stop 约定、面板退役、旧安装迁移、测试与文档同步均有对应证据。本次已发现的开发检查问题已修复，发布版本及更新记录已准备；PR 检查、用户合并及正式发布按实际后续状态处理。
