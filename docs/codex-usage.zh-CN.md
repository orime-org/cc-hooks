# 在 Codex 中使用 watcher

watcher 共用 Claude Code 的协作规范、提交检查和审计技能，在 Codex 中另提供自动 WezTerm 任务面板。

## 运行条件

本次配套运行时基于 Codex 0.163.0，目前构建产物面向 macOS arm64。它补充了官方该版本缺少的执行目录、交互终端、连接启动和计划提交回调；仅安装插件不能给官方二进制增加这些能力。无需新增目录 RPC。

需要 `jq`、Python 3.11+（含 curses）。面板还需要 WezTerm，且 `wezterm` CLI 在 PATH 中可用。其他终端仍能使用协作规范、提交检查及审计技能，不创建下方面板。

## 本机安装和启动

下面是本次交付的实际路径；在其他机器上安装时，替换为各自安装目录的绝对路径。

| 内容 | 完整路径或版本 |
|---|---|
| 配套可执行文件 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/bin/codex` |
| 原生来源提交 | `da4b63f654d52a20504ec3e6531f17da5cd99dbe` |
| 插件源码 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/orime-playbook-wt` |
| 构建清单及文件校验 | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/build-manifest.json`、`/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/SHA256SUMS` |
| 原生源码 bundle | `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/source/cc-hooks-runtime.bundle` |

先检查安装包文件：

```bash
cd /Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23
shasum -a 256 -c /Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/SHA256SUMS
```

在正常使用的 Codex 配置下，注册本地市场并安装插件：

```bash
/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/bin/codex plugin marketplace add /Users/songxiulei/Desktop/Unit_Agent/work_temp/orime-playbook-wt --json
/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/bin/codex plugin add watcher@orime --json
```

若已安装旧版，更新本地源码后重复执行上面的完整 `codex plugin add watcher@orime --json` 命令，即可刷新同版本安装缓存；本地市场不使用 Git 市场的 upgrade 操作。不要只修改市场源码后假定已安装缓存随之更新。安装或更新后，在 Codex 的 `/hooks` 中检查并信任 watcher 的六项 hook，再重新打开或恢复会话。

在 WezTerm 中使用下面的完整路径启动，沿用现有模型和登录配置：

```bash
/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/bin/codex --cd /Users/songxiulei/Desktop/Unit_Agent/work_temp -c tools.update_plan.enabled=true
```

不必覆盖系统的 `codex` 命令，也不要将离线测试用的 `CODEX_HOME` 或 `mock-model` 配置作为日常工作配置。后续恢复会话时继续使用该配套运行时和 `tools.update_plan.enabled=true`。

查询当前客户端与后台服务是否匹配：

```bash
/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-installation-2026-10-23/bin/codex debug hook-capabilities --json
```

`client.build_commit` 应为上面的来源提交。连接成功时 `server` 给出实际后台服务，`effective.features` 应包含 `effective_tool_context`、`interactive_terminal_context`、`session_start_on_attach`、`committed_plan_callbacks`。`server: null` 仅表示此次没有连上后台服务，不能据此说后台已验证。若提示版本不匹配，按诊断确认所连接的服务，并用同源运行时重开会话；不要关闭其他人的服务。

## 下方任务面板

启动或恢复时自动创建独立的 WezTerm 底部 pane，并将输入焦点留在上方 Codex。首次没有计划时显示“等待首次计划更新”；之后同步主 Agent 成功提交的 `update_plan`。

| 情况或操作 | 结果 |
|---|---|
| 自动模式 | 按内容使用三至七行，最多显示四条任务；还有任务时显示数量及省略提示 |
| 上下方向键、PgUp/PgDn | 滚动查看完整任务，缓存不会截成四条 |
| 按 m 后拖动分隔线 | 进入手动模式，计划变化保留实际高度 |
| 按 a | 恢复自动高度 |
| 按 q 或关闭底部 pane | 当前连接中保持关闭；重新连接可再次创建 |
| 会话结束 | 释放对应面板；不处理其他会话的面板 |

按键需要底部 pane 获得焦点。没有面板时，先查看 hook 信任状态、Python 版本、WezTerm CLI 及能力查询提示；缺少前置条件会显示诊断。

## 提交检查及需要问用户的情况

保留原版跨目录检查：根据 `git -C`、提交前的 `cd` 和执行目录定位目标仓库；Codex 额外传递真实的 `workdir`。目标仓库根目录有 `.watcher/` 时检查主分支、提交标题和署名规则；未配置的仓库不启用这些项目规则。

有明确约定和事实，Agent 就按它们执行。正常查证后仍无法确定，使用插件的 Agent 应询问它当前的用户，再按答复处理。用户确认目标目录不代表跳过该仓库的提交规则。

当前已知的两类目录歧义会中止本次调用并明确提示询问用户：`cd -P ""` 的 shell 差异，以及初始符号链接目录下依赖逻辑父目录的操作。确认目标后用绝对 `workdir` 或绝对 `git -C` 路径重试。目录不确定提示不会伪装成主分支违规。

解析器沿用启发式兼容边界，未实现完整 shell 解释器。动态变量、命令替换、复杂分组等仍走原版兼容路径，不能把 hook 放行当作对任意 shell 命令的完整证明；Agent 对目标不清楚时继续按上面的方式询问用户。远端环境的提交策略由远端配置负责。

## 审计与 PR

关闭自动审计只关闭自动触发；用户显式调用 `$watcher:watcher` 仍执行一次审计，并保持自动开关关闭。项目配置、开启及关闭分别使用 `$watcher:watcher-configure`、`$watcher:watcher-on`、`$watcher:watcher-off`。

AI 可以准备提交、PR 并跟踪 CI/review。PR 必须由用户检查并亲自合并；AI 不执行合并或启用自动合并。

## 从源码构建

构建入口为 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/orime-playbook-wt/scripts/build-codex-runtime.py`，`--help` 列出选项。需要干净的原生源码树及全新的绝对输出目录；脚本校验固定上游基础、来源提交、运行时能力、资源摘要和许可证，并包含可恢复原生修改的 Git bundle。原生源码位于 `/Users/songxiulei/Desktop/Unit_Agent/work_temp/codex-runtime-integration-wt`；bundle 的还原方法见包内 `source/README.txt`。
