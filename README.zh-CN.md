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
| `Stop` hook（`suggest-watcher.sh`）| Claude 每轮结束 | 拦住这轮，提示 Claude 调用 `watcher` skill；后台有 `subagent`/`workflow` 任务还在跑（running/pending）、或本轮没有收尾文本时整轮跳过（读 `background_tasks`），把审计推到任务跑完唤醒的那轮；每个真正的收尾轮还会报告当前时间 + 上下文 token 用量（K + %），超 85% 提醒手动 `/compact`。`/watcher:watcher-off` 关掉本项目的 audit、**但仍每轮显示时间 + token 状态**（关 audit ≠ 关状态）；`/watcher:watcher-on` 恢复审计 |
| `watcher` skill（audit / configure 两个模式）| 被 Stop hook 触发或手动调用 | 跑 5 步审计 + 输出 7 段结构化摘要，或配置项目级 `.watcher/` |
| `/watcher:watcher-off` / `/watcher:watcher-on` slash 命令 | 你手动跑 | 按项目开关每轮收尾自动跑的 watcher 审计（创建 / 删除 `.watcher/.stop-disabled` 标记文件）|

### 每轮注入的 13 段规则

`watcher` 强制 13 段规则（中文为主，大白话）：

1. 当前日期（UTC，秒级精度）
2. 段说明 —— Markdown 标题 / 编号白名单 / 严禁假装表格；开头加目的前言（这些规矩是为把话说清、违反会话说不清并抬高解决成本），结尾加发出前自检（扫禁用符号→换合规编号 / 2+ 相似项漏表格→补表格 / 段编号从 1 数 + 4 步意图齐 / 拍板误调 AskUserQuestion→改决策表格）兜底"知规却手滑"的违规
3. 4 步意图理解 —— 复述需求 → 分析根本原因 → 给彻底方案 → 告知打算
4. 输出格式 —— 强制 Markdown 表格 / 禁 `字段: 值` 列表 / 流程图上下走（2+ 结构相似项一律表格，汇报 / 解释 / self-check 也算、无场景例外）
5. 沟通方式 —— 大白话 / 中文为主 / 禁电报式描述 / 你是团队一员（提产品·项目·公司用"我们的"、别用"你们的"）
6. 拍板规则 —— 3 列 Markdown 表格（选项 / 做什么 / 理由含后果），推荐在选项格标 `A（推荐）`不单占一列 / 禁用 `AskUserQuestion` 工具
7. 找根因 + 靠真证据 —— 先看全貌别扎进一个方向；先查本地再上网搜（WebSearch）；卡壳别瞎试，试错满 2 次就停下来搜现成方案；靠既定规则 / 已批准决策 / 之前证据撑结论时先把规则原文 + 来源引出来再下结论（回查源别凭记忆）；碰到计划外问题先告诉我别自己消化 —— 挡路的停下查根因给方案、不挡路的加 todo 由我决定（这套挂 todo / 先确认只管会跑的代码；纯文档 / 注释 / 记忆不一致零代价、按段 12.1 发现就直接改）
8. 彻底方案不打折 —— 解决问题必须用彻底方案，严禁打任何折扣
9. 编码任务必须严格遵守以下规范 —— 规范关（动码前先确认有没有 DD / TDD + smoke / E2E + 逻辑澄清 规范、第一道关别跳过），过关后按固定顺序走：9.1 文档先行（先过选型关：写自己代码前先搜工业级现成开源库、有就用别重造轮子、尤其前端，且选中的库必须可免费商用——宽松许可 MIT/Apache-2.0/BSD/ISC 放行，GPL/AGPL 传染 copyleft、CC-BY-NC 禁商用、BSL/SSPL/Elastic/Redis RSAL 等限商用一律禁、真看 LICENSE 别凭印象、吃不准含 MPL/LGPL 按段 7 停下问；再写文档前先按表格问清逻辑岔路、只问真岔路、有合理默认先用默认 + 标注；文档写完动代码前做 Gate 1 设计对抗、见 9.5；做 UI 时设计还要一起覆盖视觉面——布局 / 状态 / 动效 / 一致性，新做或大改视觉的先出能看的 demo（做成独立 HTML，用 http 还是 artifact 由各项目自己定）让用户拍板视觉再实现，改已能跑的现有 UI 就 dogfood 真 app）→ 9.2 先写测试（TDD 红灯、测试先于实现；E2E 不在此强制红灯、留 9.4）→ 9.3 写实现 + 重构（绿灯，含模块化 / 抽共用、冒新逻辑岔路按段 7 问、发现既有代码问题主动提改前确认、文档 / 注释 / 记忆不一致按段 12.1 直接改）→ 9.4 全量验证（smoke / E2E，UI/app 必须真启动 app + 真浏览器走 http 真驱动、走 MCP 工具不吃 bash 沙箱、不许 mock 糊弄、提交 PR 前必须全过）→ 9.5 对抗式验证（折进这里：派独立对抗者、别自评、两道关——Gate 1 设计期写代码前做→过后提文档 PR，Gate 2 本次有代码 PR 要提交且先过 smoke/dogfood 才攻，纯样式 / CSS / 文案 / 配置等无攻击面小改免；攻→修→复攻到无新洞、上限普通 3 高危 5、咬到固化成测试；Gate 2 三 lens：代码对抗（崩不崩）/ 代码质量对抗（模块化 / 一致 / DRY / 成色）/ 方案根因对抗（创可贴？）；裁决按段 11 收口底线复核 + 每轮累积报、不过关停下报我）→ 9.6 同步文档收尾 → 9.7 提交 PR（commit 与 PR 说明一律全英文、走 Conventional Commits、不加 attribution）；任务有定稿 / 规范时三层贯穿：9.1 拆成逐条验收清单当硬依据、9.2 必须把规范关键约束写成可跑测试（视觉回归 / 契约 / schema 校验）、9.4 拿清单逐条对照成品（跟 smoke 各管各的）、9.6 经确认的偏差更新定稿
10. PR 善后（任何 PR）—— 盯 CI，建完 PR 贴完整 url，合并后清理分支
11. 派活（subagent / workflow）—— 开工前先想"能不能拆开并行 / 编排"，判断只认更高效 + 质量更高；三档：11.1 自己干（顺序依赖 / 一眼小事）/ 11.2 派 subagent（并行查多处 / 大检索 / 多视角，轻、随时用）/ 11.3 跑 workflow（散出去还要收口·校验·合成 / 循环 / 成规模，按实际情况自行判断、不用等开口，够格直接上）；严禁为开而开。**收口底线**：委派拿回的结论（subagent / workflow 都算）是输入、不是定论——别照单全收"干净 / 0 洞 / 全绿"、由 CC own 最终判断：确认真跑过（有过程痕迹、别把空 / 缓存 / 跑挂的假绿当已验证）+ 抽验关键结论、按风险缩放（不整个重跑）；**防回归硬约束**：二次核实 CC 自己做、绝不再派 workflow 查 workflow（对抗裁决的复核也走这条、边界见 9.5）
12. 封顶铁律（诚实 + 查证）—— 唯一红线是糊弄（装确定 / workaround 当根治 / 假称已验证 / 该搜不搜）；"说了不知道"不是终点，得去 WebSearch / 翻文档 / 跑实验、查完再下结论；发现了错误就立刻改（不分新旧、再小也别拖）——并按修复代价二分：12.1 改文档 / 注释 / 记忆（零代价、可逆）发现就改、不挂 todo 不先问，12.2 改既有代码（有风险）才先报告 + 确认方案
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
