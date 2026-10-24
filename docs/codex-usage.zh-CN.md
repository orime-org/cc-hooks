# 在 Codex 中使用 watcher

watcher 共用 Claude Code 的协作规范、提交检查和审计技能，在 Codex 中另提供自动 WezTerm 任务面板。

## 运行条件

使用官方 Codex CLI，保持正常的共享后台及官方升级方式。本轮已在官方 0.164.0 上实测；面板使用 update_plan hook、session_id 和官方会话身份显示能力。

需要 `jq`、Python 3.11+（含 curses）和配套 CLI 可用的 WezTerm 安装。面板通过 WezTerm 自身的可执行目录定位 CLI。其他终端仍能使用协作规范、提交检查及审计技能。

## 安装与启动

先使用官方 Codex 注册市场并安装插件。以下路径是本机当前源码工作树；其他机器使用自己的完整路径：

```bash
codex plugin marketplace add /Users/songxiulei/Desktop/Unit_Agent/work_temp/orime-official-codex-panel-wt --json
codex plugin add watcher@orime --json
```

本地市场更新后重复 `codex plugin add watcher@orime --json` 刷新安装缓存。在 `/hooks` 检查并信任 watcher 的 hook。

第一次启用面板时运行一次设置脚本：

```bash
python3 /Users/songxiulei/Desktop/Unit_Agent/work_temp/orime-official-codex-panel-wt/watcher/hooks/task_panel_setup.py
```

脚本在官方 `tui.status_line`、`tui.terminal_title` 中加入会话身份显示，保留已有选项；在 WezTerm 配置前添加托管加载区段，保留原有配置正文。修改已有配置前保存备份，并输出完整路径。若 WezTerm 使用非默认配置文件，用 `--wezterm-config` 传入其完整路径。`--check` 预览目标路径并校验待写入的 Codex 配置。

默认 Codex 配置目录为 `~/.codex`，设置了 `CODEX_HOME` 时使用该目录。默认插件数据目录为其中的 `plugins/data/watcher-orime`。自定义安装位置可通过 `--data-dir` 指定，须与 hook 的 `PLUGIN_DATA` 一致。插件更新后，SessionStart 会通过独立临时文件和原子替换刷新已安装的面板脚本。

确认官方配置已启用计划工具：

```toml
[tools.update_plan]
enabled = true
```

之后照常执行 `codex` 或 `codex resume`。WezTerm 配置重载后生效；新开的 Codex 会话读取更新后的会话身份配置。

## 下方任务面板

启动或恢复时，WezTerm 通过当前 Codex 原生显示的会话编号自动创建底部 pane，输入焦点留在上方 Codex。同一目录的不同会话拥有各自的任务和面板，用户无需选择。面板优先读取该 session_id 的缓存；没有缓存时读取并核验对应会话的保存记录，恢复最后一次成功的 update_plan。新会话没有计划时显示“等待首次计划更新”；之后同步主 Agent 的 update_plan hook。

原生 Tasks 完成数/总数与面板使用同一份 update_plan 清单。SessionStart 读取已有数据，显示过程不要求 Agent 再调用一次 update_plan。官方 SessionStart 在本轮实测中到首次输入才触发，因此首次输入前的创建由 WezTerm 周期事件完成。

面板第二行显示八位会话编号、连接状态和计划保存时间；关联、恢复与缓存使用完整 session_id。页脚的“先点面板”提示先将焦点切入下方，再使用按键。

| 情况或操作 | 结果 |
|---|---|
| 自动模式 | 按内容使用三至七行，最多显示四条任务；还有任务时显示数量及省略提示 |
| 上下方向键、PgUp/PgDn | 滚动查看完整任务，缓存不会截成四条 |
| 按 m 后拖动分隔线 | 进入手动模式，计划变化保留实际高度 |
| 按 a | 恢复自动高度 |
| 按 q 或关闭底部 pane | 当前 Codex 进程和会话中保持关闭；重新启动或切换会话可再次创建 |
| 会话结束 | 释放对应面板；不处理其他会话的面板 |

按键需要底部 pane 获得焦点。没有面板时，先检查 WezTerm 托管加载区段、Codex 原生会话编号显示、hook 信任状态、Python 版本及 WezTerm CLI。新版本若改变相关字段，应更新插件适配。

## 提交检查及需要问用户的情况

保留原版跨目录检查：根据 `git -C`、提交前的 `cd` 和 hook 提供的目录上下文定位目标仓库；普通输入以会话 `cwd` 为起点。绝对 `git -C` 路径可以明确目标仓库。目标仓库根目录有 `.watcher/` 时检查主分支、提交标题和署名规则；未配置的仓库不启用这些项目规则。

有明确约定和事实，Agent 就按它们执行。正常查证后仍无法确定，使用插件的 Agent 应询问它当前的用户，再按答复处理。用户确认目标目录不代表跳过该仓库的提交规则。

当前已知的两类目录歧义会中止本次调用并明确提示询问用户：`cd -P ""` 的 shell 差异，以及初始符号链接目录下依赖逻辑父目录的操作。确认目标后用绝对 `workdir` 或绝对 `git -C` 路径重试。目录不确定提示不会伪装成主分支违规。

解析器沿用启发式兼容边界，未实现完整 shell 解释器。动态变量、命令替换、复杂分组等仍走原版兼容路径，不能把 hook 放行当作对任意 shell 命令的完整证明；Agent 对目标不清楚时继续按上面的方式询问用户。远端环境的提交策略由远端配置负责。

## 审计与 PR

关闭自动审计只关闭自动触发；用户显式调用 `$watcher:watcher` 仍执行一次审计，并保持自动开关关闭。项目配置、开启及关闭分别使用 `$watcher:watcher-configure`、`$watcher:watcher-on`、`$watcher:watcher-off`。

AI 可以准备提交、PR 并跟踪 CI/review。PR 必须由用户检查并亲自合并；AI 不执行合并或启用自动合并。

## 验证范围

官方 0.164.0、独立 WezTerm 配置和离线模型下，已验证同目录两个新会话自动创建各自面板、真实 PostToolUse 同步，以及删除插件缓存后 resume 在首次输入前从官方保存数据恢复任务。受限 GUI PATH 和中文数据目录组合、完整保存时间、四条显示上限、切入面板后的 m/a 切换及 q 关闭也已实测。测试使用共享官方后台。真实用户模型的任务内容由 Agent 实际调用 update_plan 决定。

先前配套构建的设计与验证记录作为历史材料留档；当前安装入口为本说明中的官方 CLI 和一次性设置脚本。
