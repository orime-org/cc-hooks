# Orime — Claude Code 插件市场

> 给 Claude Code 用的自省 + 知识整理插件集合

[English / 英文文档](./README.md)

## Orime 是啥

Orime 是 [Claude Code](https://claude.ai/code) 的插件市场，专门做"让 Claude 自我监督 + 让项目知识库保持同步"这两件事。

目前有一个插件：**`watcher`**。

## 为啥要用

Claude 自动跑几轮之后，经常出这些问题：

- 跳步骤（比如动手前不先复述你的需求）
- 偏离项目规范（输出格式 / 语言 / 命名都飘）
- 文档和记忆跟实际改的代码对不上
- 在主分支上直接 commit，或者 commit 标题不合格式

`watcher` 装上之后，这几件事分别由四个组件管：每轮开始注入一份协作规范，每轮收尾跑知识审计，`git` 和 `gh` 命令过一道工具层拦截，输出走中文工程风格。

## 仓库结构（名字速览）

这个项目有好几个名字，先理一下免得绕：

| 名字 | 是什么 |
|---|---|
| `cc-hooks` | GitHub 仓库名 |
| `orime` | 仓库里的插件市场（marketplace），安装时写 `@orime` |
| `watcher` | 市场里目前唯一的插件 |
| `watcher` skill | 插件内部的那个 skill（跟插件同名，所以路径里会看到两层 `watcher`）|

目录长这样：

```
cc-hooks/                          # 仓库
├── .claude-plugin/
│   └── marketplace.json           # 市场清单（名叫 orime）
├── README.md / README.zh-CN.md
├── CHANGELOG.md
├── LICENSE
├── docs/
└── watcher/                       # 插件（唯一一个）
    ├── .claude-plugin/plugin.json
    ├── commands/                  # watcher-configure / watcher-off / watcher-on
    ├── hooks/                     # announce-intent.sh / bash-gate.sh / suggest-watcher.sh / hooks.json
    ├── output-styles/             # chinese-engineering.md
    ├── scripts/                   # check-size.sh + smoke 测试
    └── skills/watcher/            # skill（跟插件同名）
        ├── SKILL.md
        └── references/
```

`.watcher/`（带点的）是 watcher 运行时在"被监控项目"里生成的本地配置，已被 `.gitignore` 忽略，**不在本仓库里**——跟插件目录 `watcher/`（不带点）是两个东西。

## watcher 插件

### 干啥用

| 组件 | 啥时候触发 | 干啥 |
|---|---|---|
| `UserPromptSubmit` hook（`announce-intent.sh`）| 你每次发 prompt | 注入一份协作规范，四段：总则、表达、通用工作规程、编码任务规程 |
| `PreToolUse` hook（`bash-gate.sh`）| Claude 每次跑 Bash 命令 | 拦三种情况：在主分支 commit、commit 标题不合 `type: summary` 格式或带 `Co-Authored-By`、本会话没有验证标记就提 PR。只管仓库根有 `.watcher/` 的项目 |
| `Stop` hook（`suggest-watcher.sh`）| Claude 每轮结束 | 提示 Claude 调用 `watcher` skill 做审计；每轮报告当前时间和上下文 token 用量，超 85% 提醒跑 `/compact`。后台有 `subagent` / `workflow` 任务还在跑时跳过审计，等任务跑完那轮再做 |
| `watcher` skill | 被 Stop hook 触发，或手动 `/watcher:watcher` | 跑 5 步审计，输出 7 段摘要 |
| 输出风格（`chinese-engineering.md`）| 装上插件就生效 | 中文工程模式：先给结论，短句，不写 AI 腔 |
| `/watcher:watcher-configure` | 你手动跑 | 建或改当前项目的 `.watcher/` 三件套。这是配置的唯一入口 |
| `/watcher:watcher-off` / `/watcher:watcher-on` | 你手动跑 | 按项目开关每轮收尾的自动审计 |

### 每轮注入的规则

每轮开始时注入一份协作规范，四段：总则、表达、通用工作规程、编码任务规程。

原文在 [`watcher/hooks/announce-intent.sh`](./watcher/hooks/announce-intent.sh)，那是唯一的源。

## 安装

### 从 GitHub

```bash
/plugin marketplace add orime-org/cc-hooks
/plugin install watcher@orime
```

### 从本地 clone

```bash
git clone https://github.com/orime-org/cc-hooks.git
/plugin marketplace add /path/to/cc-hooks
/plugin install watcher@orime
```

装完或拉了新版本之后，在 Claude Code 里跑：

```
/reload-plugins
```

## 快速开始

装好之后每轮是这样跑的：

1. 你发 prompt，`UserPromptSubmit` hook 注入协作规范
2. Claude 动手改东西之前先说打算干啥，然后按你的请求干活
3. Claude 跑 `git commit` 或 `gh pr create` 时，`PreToolUse` hook 校验分支、标题格式、验证标记
4. 这轮结束时 `Stop` hook 触发，Claude 调用 `watcher` skill
5. `watcher` 跑 5 步审计，输出 7 段 Markdown 摘要

你会看到结构化的输出：编号一致、对比信息用表格、需要你拍板时用决策表格、每次行动后有 `## 6. 根因自检` 段。

## 项目级配置（`.watcher/`）

要加项目专属规则（哪些文档要保持同步 / 哪些文件不能动），在项目根目录建 `.watcher/`，里面放 3 个文件：

| 文件 | 用途 |
|---|---|
| `project-summary.md` | 一段话 —— 这是啥项目 / 谁在用 / 目标是啥 |
| `doc-inventory.md` | 必须跟代码同步的文档清单（README / ARCHITECTURE / CHANGELOG 等）|
| `watchlist.md` | 项目专属规则 —— 比如"绝对别动 `1.txt`"/"改完 `src/auth/` 必须跑测试" |

建 `.watcher/` 跑这个命令：

```
/watcher:watcher-configure
```

它问你项目情况、把草稿给你确认，然后写这 3 个文件。之后每次审计都会同时跑通用规则和你的项目规则。

`.watcher/` 建好之后，这个项目也进入 `bash-gate.sh` 的管辖范围。

## Bash 命令拦截

仓库根有 `.watcher/` 的项目，Claude 跑 `git commit` 和 `gh pr create` 时会过一道校验：

| 检查 | 拦截条件 |
|---|---|
| 分支 | 当前在 `main` 或 `master` |
| commit 标题 | 不是 `type: summary` 格式，type 取 `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci`；summary 超 72 字符；结尾有句号 |
| commit message | 含 `Co-Authored-By` |
| 提 PR | 本会话没有验证标记文件 `/tmp/cc-<session_id>-verified` |

被拦时 Claude 会收到具体是哪条不合格。验证标记由 Claude 在完成交付验证后自己写入。

没配 `.watcher/` 的仓库一律放行。

## 按项目开关每轮收尾的审计

| Slash 命令 | 效果 |
|---|---|
| `/watcher:watcher-off` | 把 `<项目>/.watcher/audit-state.json` 的 `enable-audit` 写成 `false` |
| `/watcher:watcher-on` | 写成 `true` |

关掉之后每轮仍显示时间、token 用量、未审轮次计数，只是不跑审计。每轮注入的协作规范不受影响。

每个项目有自己的 `audit-state.json`，互不影响。这个文件也可以手动改。

## 改规则

协作规范在 [`watcher/hooks/announce-intent.sh`](./watcher/hooks/announce-intent.sh)，一个 Bash 脚本，输出 stdout，Claude Code 在 `UserPromptSubmit` 时把它包装成 `<system-reminder>`。

改完跑三件事：

```bash
bash watcher/scripts/check-size.sh                                    # 字符数上限 9000
echo '{"session_id":"test","prompt":"test"}' | bash watcher/hooks/announce-intent.sh
python3 watcher/scripts/smoke-stop-hook.py
```

`check-size.sh` 的 9000 是硬上限：Claude Code 对单个 hook 的 stdout 上限是 10000 字符，超了会被截成 2000 字符的预览。

commit + push 之后，在跑着的 Claude Code 里跑 `/reload-plugins`。

改审计流程改 [`watcher/skills/watcher/SKILL.md`](./watcher/skills/watcher/SKILL.md)。改 Bash 拦截规则改 `watcher/hooks/bash-gate.sh`，改完跑 `python3 watcher/scripts/smoke-bash-gate.py`。

## 贡献

欢迎提 issue 和 PR：https://github.com/orime-org/cc-hooks

## License

MIT —— 看 [LICENSE](./LICENSE)

## Changelog

看 [CHANGELOG.md](./CHANGELOG.md)
