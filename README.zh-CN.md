# Orime — Claude Code 插件市场

> 给 Claude Code 用的自省 + 知识整理插件集合

[English / 英文文档](./README.md)

## Orime 是啥

Orime 是 [Claude Code](https://claude.ai/code) 的插件市场，专门做"让 Claude 自我监督 + 让项目知识库保持同步"这两件事。

主力插件是 **`watcher`** —— 每轮对话开始前注入规则，Claude 停下时做知识审计，让 Claude 始终按规矩走。

### 段结构（v0.1.88 起 5 段）

| 段 | 管什么 | 子节 |
|---|---|---|
| 1 | 怎么跟我说话 | 1.1 段和编号、1.2 输出格式、1.3 用词和语气、1.4 让我拍板 |
| 2 | 怎么干活 | 2.1 动手前先定性（产出物三种、级别三级、用户级再分三类）、2.2 挖根因靠证据、2.3 彻底方案不打折、2.4 自己干还是拆开派活、2.5 提完 PR 别当结束、2.6 计划外的问题先告诉我 |
| 3 | 编码任务规范 | 3.1 开工先立三样依据、3.2 三道关共用的规矩、3.3 文档先行（末尾 Gate 1）、3.4 先红后绿、3.5 全量验证（末尾 Gate 2）、3.6 收尾（Gate 3 加提交） |
| 4 | 封顶铁律：说的话必须跟事实一致 | 无 |
| 5 | 说到底 | 无 |

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
| `UserPromptSubmit` hook（`announce-intent.sh`）| 你每次发 prompt | 注入一个 `<system-reminder>`，里面有 5 段规则 |
| `Stop` hook（`suggest-watcher.sh`）| Claude 每轮结束 | 拦住这轮，提示 Claude 调用 `watcher` skill；后台有 `subagent`/`workflow` 任务还在跑（running/pending）、或本轮没有收尾文本时整轮跳过（读 `background_tasks`），把审计推到任务跑完唤醒的那轮；每个真正的收尾轮还会报告当前时间 + 上下文 token 用量（K + %），超 85% 提醒手动 `/compact`。`/watcher:watcher-off` 关掉本项目的 audit、**但仍每轮显示时间 + token + 未审轮次状态**（关 audit ≠ 关状态）；`/watcher:watcher-on` 恢复审计 |
| `watcher` skill（只做审计）| 被 Stop hook 触发或手动 `/watcher:watcher` | 跑 5 步审计 + 输出 7 段结构化摘要。**不建配置**——那是下面那个独立命令的活 |
| `/watcher:watcher-configure` slash 命令 | 你手动跑 | **配置的唯一入口**：建/改当前项目的 `.watcher/` 三件套（问你项目情况 → 草稿给你确认 → 才落盘）|
| `/watcher:watcher-off` / `/watcher:watcher-on` slash 命令 | 你手动跑 | 按项目开关每轮收尾自动跑的 watcher 审计（翻转 `.watcher/audit-state.json` 的 `enable-audit` 字段）|

### 每轮注入的 5 段规则

`watcher` 每轮注入 5 段规则（中文为主、大白话）。下面只列每段管什么，**完整原文以 [`watcher/hooks/announce-intent.sh`](./watcher/hooks/announce-intent.sh) 为准**——那是唯一的源，这里不复制全文，避免两处各写一份然后漂移。

1. **怎么跟我说话** —— 段和编号（标题层级、编号白名单、严禁拿 bullet 和分隔线假装表格）；输出格式（2+ 结构相似项一律 Markdown 表格、无场景例外）；用词和语气（大白话、能中文就中文、按正常中文语法写、你是团队一员不是外部乙方）；让我拍板（表格前先把要定的问题写精确、3 列表格、选项不许凭想象编、禁用 AskUserQuestion）
2. **怎么干活** —— 动手前先定性，三层往下走：先分产出物三种（会跑的代码往下走、测试代码照先红后绿写且已有的只在契约真变了时才改、文案发现过旧或说错就当场改对）；会跑的代码再定级别三级（用户级是正当用户用得到的、开发级是只有我们写代码时用得到的比如 CI 检查、运维级是部署和线上维护用得到的）；用户级的再定类三类（承诺内类必须改到丝滑、承诺外类只给提示和明确下一步、不正当使用类入口兜底加留痕），开发级和运维级不分类。代码质量另算一把尺、不分级别也不进三类。后果外溢到正当用户或我们自己头上的、级别或类拿不准的，必须直接问、不允许私自决定；挖根因靠证据别靠记忆（先看全貌、先本地后远程、试错满 2 次就停下搜、引用既定规则先亮原文和来源）；彻底方案不打折；自己干还是拆开派活（严禁为开而开，workflow 拿回的结论是输入不是定论、交回后的核实不许再派出去）；提完 PR 别当结束；计划外的问题先告诉我别自己闷头消化
3. **编码任务规范** —— 先立三样依据（规范关、验收清单、岔路怎么问）；3.2 是三道关共用的规矩；然后按顺序走 3.3 文档先行（选型复用优先加商用许可硬门、UI 要连视觉面一起定、末尾 Gate 1 攻方案）→ 3.4 先红后绿 → 3.5 全量验证（smoke/E2E 真启动，末尾 Gate 2 四关攻成品）→ 3.6 收尾（先同步文案、再过 Gate 3 攻注释和文档、最后提交 PR，commit 和 PR 说明全英文、不加 attribution）。问题怎么分类不在这段，全在 2.1
4. **封顶铁律：说的话必须跟事实一致** —— 唯一红线是糊弄；心里冒出拿不准就是去查的信号；发现错误立刻改，不分新旧
5. **说到底** —— 这套规则是把活干漂亮的底气，找真根因和上彻底方案这两条尤其要紧

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

装好之后，你每次发 prompt 都会触发 `UserPromptSubmit` hook。Claude 看到一个 `<system-reminder>`，里面有 5 段规则，然后：

1. 动手改东西之前先说打算干啥
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
/watcher:watcher-configure
```

这个命令问你项目情况、把草稿给你确认，然后写这 3 个文件（**它是唯一的配置入口**——`watcher` skill 只做审计、不建配置）。之后每次审计都会同时跑全局规则 + 你的项目规则。

## 按项目开关每轮收尾的 watcher 审计

不想在某个项目里每轮收尾都自动跑 watcher 审计（比如临时调试 / 跑 trivial 任务 / 给别人演示）——可以**按项目**关掉,不影响其他项目,也不影响 UserPromptSubmit 规则注入。

| Slash 命令 | 干啥 | 效果 |
|---|---|---|
| `/watcher:watcher-off` | 关掉当前项目每轮收尾的 watcher 审计 | 把 `<项目>/.watcher/audit-state.json` 的 `enable-audit` 写成 `false` |
| `/watcher:watcher-on` | 重新打开当前项目每轮收尾的 watcher 审计 | 把 `<项目>/.watcher/audit-state.json` 的 `enable-audit` 写成 `true` |

工作原理——状态存在一个文件 `<项目>/.watcher/audit-state.json`（`{ "enable-audit": true/false, "unaudited-rounds": N }`）；on/off 只改字段、从不删文件：

- Stop hook 读 `<cwd>/.watcher/audit-state.json`，分三种：
  - **文件不存在**——项目没配置，或 CC 给 hook 的 `cwd` 不是项目根（后台任务跑完唤醒那轮会这样）→ **不审，但仍显示时间 + token 状态 + 一句「当前没 `.watcher/`」提示**（这样在没配的目录里也不丢时间/token 读数）。走 `{"continue":false,"stopReason":…}` **急停通路**：显示完 CC 就真停、不会被这条提醒唤醒去接着干活
  - **`enable-audit: false`** → 只显状态（时间 / token / 未审轮次），不审；同样走 `continue:false` 急停通路
  - **`enable-audit: true`**（配了 `.watcher/` 后的默认）→ 正常 `decision:"block"` 流程，提示 Claude 调 `watcher` skill

  两条通路别混用：`decision:"block"` 的语义是「别停、继续」——Claude 看得到 reason、CC 启动下一轮（ON 分支要的就是这个）；`continue:false` 是「停」——Claude 看不到 stopReason，但**你在终端看得到** `Operation stopped by hook: …`，CC 不启动下一轮（只报状态的两个分支要的是这个）。
- 让文件常驻、只翻字段（而不是靠一个标记文件存不存在），正是"路径错→文件找不到"能跟"用户手动关了"区分开的关键
- `UserPromptSubmit` 的规则注入**不受影响**——只关每轮结束的 audit 提醒
- 每个项目有自己独立的文件,不互相影响

你也可以手动改 `.watcher/audit-state.json`（`enable-audit` 填 true/false）。旧版 `.stop-disabled` / `.skip-count` 会在下一轮自动迁移过来。

## 改 announce 规则

5 段规则放在 `watcher/hooks/announce-intent.sh` —— 一个 Bash 脚本，输出 stdout，Claude Code 在 `UserPromptSubmit` 时把它包装成 `<system-reminder>`。

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
