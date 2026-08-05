# Orime — Claude Code 插件市场

> 给 Claude Code 用的自省 + 知识整理插件集合

[English / 英文文档](./README.md)

## Orime 是啥

Orime 是 [Claude Code](https://claude.ai/code) 的插件市场，专门做"让 Claude 自我监督 + 让项目知识库保持同步"这两件事。

主力插件是 **`watcher`** —— 每轮对话开始前注入规则，Claude 停下时做知识审计，让 Claude 始终按规矩走。

### 段结构（v0.1.87 起，13 段收成 6 段）

| 段 | 管什么 | 子节 |
|---|---|---|
| 1 | 当前 UTC 时间 | 无 |
| 2 | 怎么跟我说话 | 2.1 段和编号、2.2 输出格式、2.3 用词和语气、2.4 让我拍板 |
| 3 | 怎么干活 | 3.1 先定性两问定类、3.2 挖根因靠证据、3.3 彻底方案不打折、3.4 自己干还是拆开派活、3.5 提完 PR 别当结束、3.6 计划外的问题先告诉我 |
| 4 | 编码任务规范 | 通则四条（规范关、验收清单、逻辑岔路、对抗怎么跑）+ 4.1 文档先行、4.2 先红后绿、4.3 全量验证、4.4 收尾提交 |
| 5 | 封顶铁律：说的话必须跟事实一致 | 无 |
| 6 | 说到底 | 无 |

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
| `Stop` hook（`suggest-watcher.sh`）| Claude 每轮结束 | 拦住这轮，提示 Claude 调用 `watcher` skill；后台有 `subagent`/`workflow` 任务还在跑（running/pending）、或本轮没有收尾文本时整轮跳过（读 `background_tasks`），把审计推到任务跑完唤醒的那轮；每个真正的收尾轮还会报告当前时间 + 上下文 token 用量（K + %），超 85% 提醒手动 `/compact`。`/watcher:watcher-off` 关掉本项目的 audit、**但仍每轮显示时间 + token + 未审轮次状态**（关 audit ≠ 关状态）；`/watcher:watcher-on` 恢复审计 |
| `watcher` skill（只做审计）| 被 Stop hook 触发或手动 `/watcher:watcher` | 跑 5 步审计 + 输出 7 段结构化摘要。**不建配置**——那是下面那个独立命令的活 |
| `/watcher:watcher-configure` slash 命令 | 你手动跑 | **配置的唯一入口**：建/改当前项目的 `.watcher/` 三件套（问你项目情况 → 草稿给你确认 → 才落盘）|
| `/watcher:watcher-off` / `/watcher:watcher-on` slash 命令 | 你手动跑 | 按项目开关每轮收尾自动跑的 watcher 审计（翻转 `.watcher/audit-state.json` 的 `enable-audit` 字段）|

### 每轮注入的 13 段规则

`watcher` 强制 13 段规则（中文为主，大白话）：

1. 当前日期（UTC，秒级精度）
2. 段说明 —— Markdown 标题 / 编号白名单 / 严禁假装表格
3. 4 步意图理解 —— 复述需求 → 分析根本原因 → 给彻底方案 → 告知打算
4. 输出格式 —— 强制 Markdown 表格 / 严禁拿 bullet、`字段: 值` 列表、`────` 分隔线、A. B. C. 列表假装表格 / 流程图上下走（2+ 结构相似项一律表格，汇报 / 解释 / self-check 也算、无场景例外）
5. 沟通方式 —— 大白话 / 中文为主 / **按正常中文语法写**（句子完整、逗号句号分号断句，破折号别当逗号，括号只放补充说明，箭头和斜杠别当标点）/ 禁电报式描述 / 你是团队一员（提产品·项目·公司用"我们的"、别用"你们的"）
6. 拍板规则 —— **表格前一行先把要定的问题写精确**（写「要定的是：xxx」，标准是光看这句加表格就能拍、不用往上翻）；3 列 Markdown 表格（选项 / 做什么 / 理由含后果），推荐在选项格标 `A（推荐）`不单占一列 / 禁用 `AskUserQuestion` 工具；**选项不许凭想象编**：涉及有成熟外部实践可参照的（产品行为 / 交互 / 架构 / 协议 / 格式 / 安全）先 WebSearch 看 2~3 个工业级产品或主流开源怎么做再拟选项，**每个选项都要能追到依据**（业界实践给出处 / 项目内既有事实 / 明标"这是我的推断、没查到先例"），标了"业界这么做"却没真查 = 段 12 装懂死罪；纯项目内取舍免外部调研但依据仍要写清，拿不准算哪类就按"有外部实践"办、先查
7. 找根因 + 靠真证据 —— 先看全貌别扎进一个方向；先查本地再上网搜（WebSearch）；卡壳别瞎试，试错满 2 次就停下来搜现成方案；靠既定规则 / 已批准决策 / 之前证据撑结论时先把规则原文 + 来源引出来再下结论（回查源别凭记忆）；碰到计划外问题先告诉我别自己消化 —— 挡路的停下查根因给方案、不挡路的加 todo 由我决定（这套挂 todo / 先确认只管会跑的代码；纯文档 / 注释 / 记忆不一致零代价、按段 12.1 发现就直接改）
8. 彻底方案不打折 —— 解决问题必须用彻底方案，严禁打任何折扣
9. 编码任务必须严格遵守以下规范 —— 规范关（动码前先确认有没有 文档 / TDD + smoke / E2E + 岔路澄清 规范、第一道关别跳过）；**开工先立验收清单**，写清这次做哪几项、每项要满足什么用户需求或体验，逐条可勾；有权威定稿或规范的从定稿拆，没有就照用户说的列、给用户确认；全程守这条线，每步都要追到清单某条，严禁凭记忆造或偏离：9.1 立清单当硬依据 → 9.2 必须把关键约束写成可跑测试（视觉回归 / 契约 / schema 校验，是必须项不是选配）、写实现时盯着清单别偏离 → 9.3 提交前拿清单逐条对照成品勾上、对不上或没做的算未完成不许放行（smoke 管跑不跑得起来、这关管跟定稿一不一致）→ 偏差经确认就当场更新回清单，9.5 连定稿一起改、跟成品一致；**逻辑岔路全程都问用户拍板**（9.1 写文档前先按表格问、9.2 写实现时冒出文档没覆盖的新岔路也停下问，别自己拍别凭假设替用户定，只问"多种选择 + 拍错代价高"的、有合理默认先用默认 + 标注）。过关后按固定顺序走：**9.1 文档先行**（先过选型关：写自己代码前先搜工业级现成开源库、有就用别重造轮子、尤其前端，且选中的库必须可免费商用——宽松许可 MIT/Apache-2.0/BSD/ISC 放行，GPL/AGPL 传染 copyleft、CC-BY-NC 禁商用、BSL/SSPL/Elastic/Redis RSAL 等限商用一律禁、真看 LICENSE 别凭印象、吃不准含 MPL/LGPL 按段 7 停下问；再写文档，做 UI 时设计还要一起覆盖视觉面——布局 / 状态 / 动效 / 一致性，新做或大改视觉的先出能看的 demo 让用户拍板视觉再实现，改已能跑的现有 UI 就 dogfood 真 app；文档写完动代码前做 Gate 1 设计对抗、见 9.4）→ **9.2 先红后绿**（先红：动实现前先按文档写测试、跑一遍确认按预期失败，E2E 不在此强制红灯、留 9.3；再绿：写最小实现让测试通过再重构，这步守三条——模块化抽共用 / 冒新岔路别自己拍停下问 / 发现既有代码问题主动提改前确认）→ **9.3 全量验证**（smoke / E2E，UI/app 必须真启动 app + 真浏览器走 http 真驱动、走 MCP 工具不吃 bash 沙箱、不许 mock 糊弄、提交代码 PR 前必须全过）→ **9.4 对抗式验证**（10 条职责单一的规则）：**怎么攻**——派独立对抗者、别自评，**对抗里要套 verify/judge 层**（发现洞后，在同一次对抗里再起独立的一层逐条驳、驳不倒的才交回）；Gate 1 设计期写代码前做、过后提文档 PR，Gate 2 有代码 PR 要提交且先过 smoke/dogfood 才攻，纯样式 / CSS / 文案 / 配置等无攻击面小改两关都免；每个对抗者各自最多找 5 条、各自这批驳完剩几条交几条；攻→修→复攻到本轮零行为洞且轮数够档、上限普通 3 高危 5、咬到的行为洞修完固化成测试；**洞怎么分**——**行为洞**（会崩 / 逻辑错 / 根因没治 / 名字跟代码矛盾 / 重复逻辑 / 漏错误边界 / 巨型函数 / 各处各写，判据是"能穷举完、能固化成检查"）、**描述洞**（措辞 / 注释 / 命名 / 风格，语义没错、只凭品味）不进 loop、不卡收敛，但仍要上表 1 和表 2、改不改用户定；**Gate 1 攻啥 / Gate 2 攻啥**（四关：需求兑现对抗拿 9.1 清单逐项验、不限条数、问用户要的给了没有 / 代码对抗崩不崩 / 代码质量对抗模块化·一致·DRY·成色 / 方案根因对抗创可贴？）；**对抗跑完先出轮次表**——第 1~N 轮累计、每轮一行、3 列「轮次｜行为洞几个｜描述洞几个」、别复述洞；**怎么核实**——**报回来的一律先当不成立、举证责任在 CC**，证得出才成立、证不出就是不成立；先确认真攻过（没痕迹=没验、打回重跑），每条过两层、全过才成立：**现象真不真**（能跑的真跑复现、跑不了的回读 file:line）+ **算不算数**（是本次 PR / 任务该管的吗？跟用户体验冲不冲？跟文档写的这次任务对不对得上？一问不对=不成立），没复现但说得出机理=待定、列给用户定；**修复前先出表 1、用户确认了才动手**（硬停点：逐条一行、一条不许漏不许合并，不成立的和待定的也列，只准 4 列「洞：编号+对抗者原话｜成不成立·凭什么｜根因｜彻底方案·修不修」，用户确认前一个字都不许改）；**怎么修**——照表 1 确认过的方案动手、同根因或同模式的归一组，每组一次改到底、能抽共用就抽、不许一条一条零敲碎打，**修洞也照样按段 7 找根因、段 8 给彻底方案**（别照着对抗者那句改字面，先问这类洞为啥出现、同源的还有没有，点状补丁下轮必再冒问题），「已修」同样逐条验；**修完再报（表 2）**——按组、一组一行、4 列「组｜本组的洞：表 1 编号+每条下落｜改了什么｜怎么验的」，「待定·不挡路」另起一段说机理；**算不算过**——**收敛只看行为洞**（本轮行为洞零条、判要修的全修完、轮数够档就收敛，描述洞剩着不挡），到轮数上限还有行为洞 / 判是创可贴 / 还有没修完的都停下报用户，挡住干活的当场报别攒着→ **9.5 收尾**（同步文档：验证通过、代码稳定后回头全扫受影响文档改对，撞见的单处不一致按 12.1 当场改；提交 PR：文档/代码/测试都齐、smoke/E2E 全过才提交，commit 与 PR 说明一律全英文、走 Conventional Commits、不加 attribution）
10. PR 善后（任何 PR）—— 盯 CI，建完 PR 贴完整 url，合并后清理分支
11. 派活（workflow）—— 开工前先想"能不能拆开并行 / 编排"，判断只认更高效 + 质量更高；两档：11.1 自己干（顺序依赖 / 一眼小事）/ 11.2 跑 workflow（要派出去的活一律走它：并行查多处 / 大检索 / 多视角汇总 / 需统一收口 / 循环跑到达标 / 成规模大活，够格就直接上、不用先问）；严禁为开而开。收口底线：workflow 拿回的结论是输入不是定论 —— 别对"查完了 / 干净 / 0 洞 / 全绿"照单全收，信不信自己 own；先确认真跑过（有过程痕迹、不是空跑或假绿），再**按类型分**：对抗类（Gate 1 / Gate 2 报回的洞和「已修」）逐条按证据定、不抽验（见 9.4）；其他委派（搜索 / 调研 / 检索）抽验关键结论、按风险缩放，不是整个重跑。防回归硬约束：交回之后这道核实必须自己做、不许再派出去。
12. 封顶铁律（诚实 + 查证）—— 唯一红线是糊弄（装确定 / workaround 当根治 / 假称已验证 / 该搜不搜）；"说了不知道"不是终点，得去查（按段 7 先本地后远程再实验）、查完再下结论；发现了错误就立刻改（不分新旧、再小也别拖）——并按修复代价二分：12.1 改文档 / 注释 / 记忆（零代价、可逆）发现就改、不挂 todo 不先问，12.2 改既有代码（有风险）才先报告 + 确认方案
13. 说到底 —— 这套规则是把活干漂亮的底气，找真根因 / 上彻底方案这两条尤其要紧

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
