# Codex 适配交付验证

## 当前官方方案

当前任务面板通过官方 Codex 的会话身份显示、SessionStart 与 update_plan PostToolUse，以及 WezTerm 原生周期事件实现。每个 session_id 拥有独立计划；同一目录的两个会话已实测分别创建与同步面板。安装与启动见 `codex-usage.zh-CN.md`，设计见 `codex-official-hooks-design.md`。

面板元数据显示八位会话编号和完整保存时间，页脚提供“先点面板”提示。绑定、缓存与恢复使用完整 session_id。自动高度三至七行，最多显示四条，溢出数量、滚动及 m/a/q 操作沿用已确认规则。

| 验证范围 | 结果与证据 |
|---|---|
| 任务面板配置技能 | 官方 Codex 通过 skills/list 发现 watcher:task-panel-configure；从已安装技能解析并运行共享配置脚本，预检保留配置、重复运行无变更、原有终端任务保持运行，原生重载后新会话创建三行空面板并通过真实 update_plan hook 同步两条任务。独立 GUI 与后台退出码均为 0；记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-182408/configure-skill-report.json` |
| 官方新建、共享后台与恢复 | 官方0.164.0、离线模型、独立WezTerm GUI；两个同目录会话在首次输入前创建各自空面板，真实hook更新后显示各自任务，删除缓存后resume在首次输入前恢复两条计划 |
| 安装环境与交互 | 受限GUI PATH与中文数据目录；八位编号、完整时间、六任务只见四条、切入任务pane后m/a、q关闭保持关闭，均通过。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-hooks-20261024-170118/plugin-panel-report.json` |
| 受影响验证 | 132项单元与入口测试、80项插件清单检查通过。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/visual-update-tests-20261024-170155/report.json` |
| 实现对抗 | 两轮；第一轮三个已确认问题已修正，第二轮保留发现0。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/official-session-implementation-round2.md` |
| 视觉及演示 | 两名独立审查者查看三组真实截图，底线保留项0；三个建议经用户确认后落实。旧紧凑演示的说明、链接及交互共18项浏览器检查通过；记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/任务面板视觉复核-2jv160nq/adjustment-report.md` |

真实用户模型的任务内容由Agent实际调用update_plan产生。PR由用户检查并亲自合并。

## 历史配套构建验证

以下保留配套构建交付时的记录。当前安装与测试结果使用上节的官方方案。

本记录更新于 2026-10-24。目标是让现有 watcher 能在 Codex 使用，并在 WezTerm 自动显示最多四条的任务面板。

### 实际交付

协作规范、提交检查、Stop 审计及技能入口共用现有规则。保留原版跨目录目标定位，并补齐 Codex 实际 workdir；没有新增目录 RPC。无法确定时，由使用中的 Agent 询问当前用户，再按答复处理。

面板通过真实 WezTerm 底部 pane 显示。自动高度三至七行，最多四条，溢出有数量提示并可滚动；m/a 切换手动及自动，q 关闭当前连接，恢复会话可重新创建。

配套运行时为 macOS arm64、Codex 0.163.0 基础的开发构建，来源 `da4b63f654d52a20504ec3e6531f17da5cd99dbe`。二进制、原生源码 bundle、许可和摘要位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23`。官方该版本的二进制不能仅靠安装插件取得新增原生回调。使用入口见 `codex-usage.zh-CN.md`。

### 本机验证

| 范围 | 结果及证据 |
|---|---|
| 插件检查 | 18 组脚本通过，包括两宿主规范与 Stop、手动审计、PR 权限、目录检查、面板、打包及清单；目录最终 62 项通过。日志目录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/final-basic-2026-10-24` |
| 新目录提示 | 两处目标测试先失败，最小实现后通过；删除两个判定分别能使测试失败。普通符号链接往返另有失败先行回归测试，并与真实 Bash/zsh 比对 |
| 真实 Codex | 新隔离配置经原生 exec 调用真实 hook：两处歧义返回询问用户提示，主分支拦截，任务分支正常提交；记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/final-gate-native-20261024-134124/report.json` |
| 真实 WezTerm | 新建测试 pane，验证启动、0/1/4/5/25 条、滚动、长中文、m/a、故障恢复、clear、q 和三次会话连接；三次退出码均为 0，本次 pane 已清理。记录 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-native-validation-2026-10-22/explicit-mode-wezterm-20261024-133541/report.json` |
| 产物 | 13 项 SHA-256 文件校验通过；源码 bundle 验证通过，HEAD 与构建来源一致 |
| 文案 | 独立核对实际 CLI、hook 信任、计划开关及本地缓存更新；补上重复 plugin add 的更新方法 |

### 实现审查记录

| 轮次 | 承诺内 | 承诺外 | 不正当使用 | 开发/运维级 | 代码质量 |
|---|---|---|---|---|---|
| 1 | 4 | 0 | 0 | 2 | 0 |
| 2 | 0 | 0 | 0 | 1 | 0 |
| 3 | 1 | 0 | 0 | 1 | 0 |
| 4 | 2 | 0 | 0 | 2 | 0 |
| 5 | 1 | 0 | 0 | 0 | 0 |

前四轮记录位于验收目录对应的中文汇总报告。第四轮两处目录歧义按用户最新要求改为运行时询问，不继续扩展 shell/RPC 设计。第五轮发现初始路径别名下的正常符号链接往返被额外询问；已复现并修正为分别推进两种初始路径拼写，原审查者亲自核验该误拦消除。

### 视觉审查

两名独立审查者实际查看本次面板截图，分别检查可用性、层级及与确认设计的结构一致性。主代理查看截图并核对行数与任务数量；保留底线问题 0、建议 0。

25 条截图为七行、四条可见并显示“还有 21 条”；一条恢复自动为四行，空计划为三行。手动十行属于用户选择的高度，不代表自动面板高度。手动十行截图的操作行有局部重绘差异，文本抓取完整；该截图不作为整条操作提示清晰的证据。

### 使用边界

提交目录解析仍有原版启发式边界，不解释任意动态 shell；Agent 正常查证后仍无法确认则问当前用户。远端策略由远端配置负责。原生修改源码和构建产物已经本机交付，尚未推送到 OpenAI 上游仓库。

PR 必须由用户检查并亲自合并，AI 不执行合并或自动合并。
