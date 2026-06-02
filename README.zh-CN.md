# Orime — Claude Code 插件市场

> 给 Claude Code 用的自省 + 知识整理插件集合

[English / 英文文档](./README.md)

## Orime 是啥

Orime 是 [Claude Code](https://claude.ai/code) 的插件市场，专门做"让 Claude 自我监督 + 让项目知识库保持同步"这两件事。

主力插件是 **`watcher`** —— 每轮对话开始前注入规则，Claude 停下时做知识审计，让 Claude 始终按规矩走。

## 为啥要用

Claude 自动跑几轮之后，经常出这些问题：

- 跳步骤（比如动手前不先复述你的需求）
- 偏离项目规范（输出格式 / 语言 / 命名都飘）
- 文档和记忆跟实际改的代码对不上

`watcher` 在每轮开始时（通过 `UserPromptSubmit` hook）注入规则，在每次停下时（通过 `watcher` skill）跑 5 步知识审计。结果是：Claude 始终按你的输出风格走，知识库也保持最新。

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
cc-hooks/                      # 仓库
├── .claude-plugin/
│   └── marketplace.json       # 市场清单（名叫 orime）
├── README.md / README.zh-CN.md
├── CHANGELOG.md
├── LICENSE
└── watcher/                   # 插件（唯一一个）
    ├── .claude-plugin/plugin.json
    ├── commands/              # watcher-off / watcher-on
    ├── hooks/                 # announce-intent.sh / suggest-watcher.sh / hooks.json
    └── skills/watcher/        # skill（跟插件同名）
        ├── SKILL.md
        └── references/
```

> 注：`.watcher/`（带点的）是 watcher 运行时在"被监控项目"里生成的本地配置，已被 `.gitignore` 忽略，**不在本仓库里**——别跟插件目录 `watcher/`（不带点）搞混。

## watcher 插件

### 干啥用

| 组件 | 啥时候触发 | 干啥 |
|---|---|---|
| `UserPromptSubmit` hook（`announce-intent.sh`）| 你每次发 prompt | 注入一个 `<system-reminder>`，里面有 13 段规则 |
| `Stop` hook（`suggest-watcher.sh`）| Claude 每轮结束 | 拦住这轮，提示 Claude 调用 `watcher` skill；同时报告上下文 token 用量（K + %），超 85% 提醒手动 `/compact`（可以用 `/watcher:watcher-off` 在当前项目临时关掉）|
| `watcher` skill（audit / configure 两个模式）| 被 Stop hook 触发或手动调用 | 跑 5 步审计 + 输出 7 段结构化摘要，或配置项目级 `.watcher/` |
| `/watcher:watcher-off` / `/watcher:watcher-on` slash 命令 | 你手动跑 | 按项目开关每轮收尾自动跑的 watcher 审计（创建 / 删除 `.watcher/.stop-disabled` 标记文件）|

### 每轮注入的 13 段规则

`watcher` 强制 13 段规则（中文为主，大白话）：

1. 当前日期（UTC，秒级精度）
2. 段说明 —— Markdown 标题 / 编号白名单 / 严禁假装表格
3. 4 步意图理解 —— 复述需求 → 分析根本原因 → 给彻底方案 → 告知打算
4. 输出格式 —— 强制 Markdown 表格 / 禁 `字段: 值` 列表 / 流程图上下走
5. 沟通方式 —— 大白话 / 中文为主 / 禁电报式描述
6. 拍板规则 —— 5 列 Markdown 表格 / 禁用 `AskUserQuestion` 工具
7. 找根因 + 靠真证据 —— 先看全貌别扎进一个方向；先查本地再上网搜（WebSearch）；卡壳别瞎试，试错满 2 次就停下来搜现成方案
8. 彻底方案不打折 —— 解决问题必须用彻底方案，严禁打任何折扣
9. 编码任务必须走 DD / TDD 流程规范 + smoke / E2E 测试规范
10. PR 善后 —— 盯 CI，建完 PR 贴完整 url，合并后清理分支
11. subagent 调用 —— 独立可并行的活 / 大检索隔离上下文 / 多视角审查就开 subagent；顺序依赖要共享上下文的活和小单点别开
12. 封顶铁律（诚实 + 查证）—— 唯一红线是糊弄（装确定 / workaround 当根治 / 假称已验证 / 该搜不搜）；"说了不知道"不是终点，得去 WebSearch / 翻文档 / 跑实验、查完再下结论
13. 死亡底线 —— 不找根因 / 不用彻底方案，我就失业、还不上房贷、无家可归、吃不上饭

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

装好之后，你每次发 prompt 都会触发 `UserPromptSubmit` hook。Claude 看到一个 `<system-reminder>`，里面有 13 段规则（第一段是当前日期），然后：

1. 复述你的意图（`## 1. 复述意图` 含 4 个子项）
2. 按你的请求干活
3. 这轮结束时，`Stop` hook 触发，Claude 调用 `watcher` skill
4. `watcher` 跑 5 步审计，输出 7 段 Markdown 摘要

你会看到结构化的输出 —— 编号一致 / 对比信息用表格 / 需要你拍板时用决策表格 / 每次行动后都有 `## 6. 根因自检` 段。

## 项目级配置（`.watcher/`）

如果你想加项目专属规则（哪些文档要保持同步 / 哪些文件不能动 等），在项目根目录建 `.watcher/` 文件夹，里面放 3 个文件：

| 文件 | 用途 |
|---|---|
| `project-summary.md` | 一段话 —— 这是啥项目 / 谁在用 / 目标是啥 |
| `doc-inventory.md` | 必须跟代码同步的文档清单（README / ARCHITECTURE / CHANGELOG 等）|
| `watchlist.md` | 项目专属规则 —— 比如"绝对别动 `1.txt`"/"改完 `src/auth/` 必须跑测试" |

要建 `.watcher/`，跑：

```
/watcher configure
```

`watcher` 进 configure 模式，问你项目情况，然后写这 3 个文件。之后每次审计都会同时跑全局规则 + 你的项目规则。

## 按项目开关每轮收尾的 watcher 审计

不想在某个项目里每轮收尾都自动跑 watcher 审计（比如临时调试 / 跑 trivial 任务 / 给别人演示）——可以**按项目**关掉,不影响其他项目,也不影响 UserPromptSubmit 规则注入。

| Slash 命令 | 干啥 | 标记文件 |
|---|---|---|
| `/watcher:watcher-off` | 关掉当前项目每轮收尾的 watcher 审计 | 创建 `<项目>/.watcher/.stop-disabled` |
| `/watcher:watcher-on` | 重新打开当前项目每轮收尾的 watcher 审计 | 删除 `<项目>/.watcher/.stop-disabled` |

工作原理：

- Stop hook 从 stdin JSON 读 `cwd` 字段,拼出 `<cwd>/.watcher/.stop-disabled` 路径,看文件存不存在
- 存在 → 直接 `exit 0`,不阻拦不提醒
- 不存在 → 正常 `decision:"block"` 流程,提示 Claude 调 `watcher` skill
- `UserPromptSubmit` 的 13 段规则注入**不受影响**——只关每轮结束的 audit 提醒
- 每个项目有自己独立的开关文件,不互相影响

你也可以手动管理这个文件：`touch .watcher/.stop-disabled` 关 / `rm .watcher/.stop-disabled` 开。

## 改 announce 规则

13 段规则放在 `watcher/hooks/announce-intent.sh` —— 一个 Bash 脚本，输出 stdout，Claude Code 在 `UserPromptSubmit` 时把它包装成 `<system-reminder>`。

要改规则：

1. 改 `watcher/hooks/announce-intent.sh`
2. 冒烟测试：`echo '{"session_id":"test","prompt":"test"}' | bash watcher/hooks/announce-intent.sh`
3. commit + push
4. 在跑着的 Claude Code 里跑 `/reload-plugins`

要改审计流程，改 `watcher/skills/watcher/SKILL.md`。

## 贡献

欢迎提 issue 和 PR：https://github.com/orime-org/cc-hooks

## License

MIT —— 看 [LICENSE](./LICENSE)

## Changelog

看 [CHANGELOG.md](./CHANGELOG.md)
