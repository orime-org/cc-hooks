# Changelog

## 0.1.22 — 2026-06-01

### Module: Watcher

- **Stop hook reason 去掉「Per-turn Reminder」英文 label**：`suggest-watcher.sh` 每轮提醒开头的「📋 Per-turn Reminder — 调用 Skill…」精简成「📋 调用 Skill…」——去掉冗余英文标签，保留 📋 和核心指令（调 watcher 跑收尾）

## 0.1.21 — 2026-06-01

### Module: Watcher

- **announce 新增段 11「该派 subagent 的活别自己硬扛，但严禁为开而开」**：补"该并行没并行 / 该隔离上下文没隔离"的短板。写成条件式——「该开」（同时查多文件夹·模块、大检索隔离上下文、多视角审查）+「严禁开」（顺序依赖要共享上下文的活、小单点）+ 一句判断口诀（活能否切成互不依赖的块）。死亡底线段 11 → 12
- README.md / README.zh-CN.md 同步：段数 11 → 12、段列表加 subagent 条、死亡底线挪 12；顺手把几处残留的"10 段"旧计数也校正成 12

## 0.1.20 — 2026-06-01

### Module: Watcher

- **watcher-off / watcher-on 命令描述改成「效果式」**：原描述「关闭当前项目的 watcher Stop hook 提醒」写的是底层机制（Stop hook 提醒），看不出实际效果。改成说清效果——「关掉当前项目每轮收尾自动跑的 watcher 审计（项目级）」。同步改了：两命令的 `description` / 标题 / 回话文案，README.md / README.zh-CN.md 的命令表行 + 开关章节标题/表格行。机制说明（`.stop-disabled` → Stop hook `exit 0`）保留不动——那是"怎么实现"，本身准确

## 0.1.19 — 2026-06-01

### Module: Watcher

- **audit 支持多文件夹同步审计（SKILL.md）**：一个 CC 会话同时管多个本地文件夹时，audit 不再只盯 cwd 一个项目，而是审「本轮覆盖的一组文件夹」。改了 4 处：
  - **第一步加「描述式文件夹发现」**：本轮覆盖范围 = 直接涉及（本轮 Edit/Write/Read 动过它文件的文件夹）∪ 间接涉及（本轮没碰它、但改动让它文档过时的文件夹，如上游 API / 共享 schema / 子域 / SDK 的下游）。判断间接涉及靠"会不会让 X 的文档过时"这个语义问题，**不靠机械枚举路径**——机械枚举只逮得到直接涉及，逮不到"虽没碰但该同步"的下游。盘点对每个发现的文件夹各跑一次
  - **`.watcher/` 不向上爬、只认文件夹自己的**：审某个文件夹只用它自己目录下的 `.watcher/`，绝不往父目录爬找——避免误抓上层无关项目 / 沙盘的 `.watcher/`（实测 orime 嵌在非 git 的 work_temp 下、两者都有 `.watcher/`，向上爬会错抓）。文件夹自己没配 → 当未配置、按第二步分级提醒用户手动处理，不借父目录的
  - **第二步缺 `.watcher/` 分级**：直接涉及缺 → 刷首行高亮提醒在该文件夹配置；间接涉及缺 → 只通用规则审 + 「未处理」轻提，不刷高亮（下游大概率不归当前会话主理，狂提醒反成噪音）
  - **第五步首行高亮 + 特殊情况对齐**：首行高亮只对直接涉及且缺 `.watcher/` 的文件夹刷，间接涉及不进高亮；摘要文档变更按文件夹分组
- README 不动：本次是 SKILL.md 审计流程内部改动，README「5 步审计」表述未变错（与 0.1.4 / 0.1.5 / 0.1.7 同类 SKILL.md 内部改动一致，CHANGELOG-only）

## 0.1.18 — 2026-05-31

### Module: Watcher

- **Stop hook token 水位提醒阈值 75% → 85%**：`suggest-watcher.sh` 的 `COMPACT_PCT` 从 75 改 85——贴近"快撑爆才提醒"、减少中段噪音；85% 以下显示「📊 未到不用压」，超 85% 才切「⚠️ 建议手动 /compact」。同步 README 中英两版描述
- **精简 ⚠️ 告警文案**：去掉「（CC 自动压缩已被服务端 reactive-only 模式关掉，得手动压）」这句解释性括号，⚠️ 告警只留「建议你手动输入 /compact 压缩会话」

## 0.1.17 — 2026-05-31

### Module: Watcher

- **Stop hook（suggest-watcher.sh）新增上下文 token 水位提醒**：每轮收尾从 transcript 算当前 context token 数（input+cache_read+cache_creation，不含 output），显示「📊 上下文已用 XXXK / YY%」；超过 75% 切成「⚠️ 建议手动 /compact」告警。根因：CC 自动压缩被服务端 reactive-only 实验（growthbook `tengu_cobalt_raccoon`）关掉、`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 失效，靠 hook 自算 token% 提醒用户手动压缩补位

## 0.1.16 — 2026-05-30

### Module: Watcher

- announce 段 11 激励句语序微调："帮助我完成出色的工作" → "帮助我出色的完成工作"

## 0.1.15 — 2026-05-30

### Module: Watcher

- announce 段 11「死亡底线」末尾加一句正向激励："我知道你是一个智商达到爱因斯坦这个级别的超级 AI。你一定可以帮助我完成出色的工作，让我不至于死掉。"——在卖惨式后果施压之外，叠加"捧高 + 你一定能帮我"的情感杠杆
- README 段 11 概要未动（核心"不找根因则惨"不变，新增句是话术补充、不改变概要含义）

## 0.1.14 — 2026-05-30

### Module: Watcher

- **段 7 加「先看全貌、再挖根因」前置条**：复杂问题先退一步扫一圈（牵涉哪几层 / 有无多个并发原因 / 是不是需求本身错了），再决定往哪挖；防隧道视野（别扎进第一个方向死挖）+ 防分析瘫痪（全面看要有边界，小问题直接挖）。根因是原段 7 只讲"挖得深"（深度），缺"先看宽"（广度）这个前置维度
- README.md / README.zh-CN.md 段 7 描述同步

## 0.1.13 — 2026-05-30

### Module: Watcher

- **Stop hook reason 末尾加开关说明**：每轮收尾提醒里直接告诉用户怎么关/开本项目的 watcher（`/watcher:watcher-off` 关、`/watcher:watcher-on` 开），并明确"这是用户的开关，Claude 别自作主张去关"。根因是开关命令 0.1.1 就有但只写在 README，用户被提醒轰炸、最想关时眼前没逃生门

## 0.1.12 — 2026-05-29

### Module: Watcher

修自相矛盾的格式 bug：

- **段 7 的触发清单原来用了带圈数字 ①②③④**，而段 2.3 明确把带圈数字列为禁用符号——announce 自己违反了自己定的规范，且每轮注入给模型看等于做了坏示范。改成分号平铺，去掉所有带圈数字
- 顺手清掉 `suggest-watcher.sh` 注释里的 ①②（纯注释、不注入模型，但避免以后被当残留）
- CHANGELOG 历史条目（0.1.6）里的 ①② 保留——那是档案记录，非规则、不注入

## 0.1.11 — 2026-05-29

### Module: Watcher

announce 段 7（找根因）加强网络取证，治"碰到技术问题不搜、自己绕圈试错"：

- **新增「必须 WebSearch」触发清单**：报错看不懂 / API·库·工具用法不确定 / 第三方行为不符预期 / 同一问题试了 2 次没解决 → 必须先上网搜（报错原文、官方文档、GitHub issue·Stack Overflow 现成方案）
- **新增「反绕圈刹车」**：严禁盲目试错绕圈，同一问题试错满 2 次立刻停下来搜，先搜到证据再动手
- 根因是原段 7 把 WebSearch 写成"再查远程"的可选补充，既不强制、又无触发条件、又无反绕圈机制
- README.md / README.zh-CN.md 段 7 描述同步

## 0.1.10 — 2026-05-29

### Module: Watcher

- announce 段 11 段标「死刑底线」→「死亡底线」（配合 0.1.9 内容从辱骂改后果代入式，标题语气对齐）；README 中英两版段 11 同步

## 0.1.9 — 2026-05-29

### Module: Watcher

- announce 段 11「死刑底线」收尾施压语从辱骂式（"你他妈的就给我去死吧"）改为后果代入式（"我将失去我的工作，还不上房贷、无家可归、吃不上饭"）——换一种情感杠杆驱动模型尽责
- README.md / README.zh-CN.md 段 11 描述同步

## 0.1.8 — 2026-05-29

### Module: Watcher

- announce 段 10（PR 善后）加一条：建完 PR（`gh pr create` 成功）后，必须把 PR 完整 url 单独贴出来给用户，方便直接点开

## 0.1.7 — 2026-05-29

### Module: Watcher

补全 0.1.6 跳过计数的另一半（SKILL.md）：

- **第四步任务质量自检加「范围放宽」**：reason 带"已累计 N 轮没审"提示时，audit 范围从「只本轮」放宽到「本轮 + 这 N 轮被跳过的工作」，5 条原则按放宽后范围逐一过；没带提示就照常只审本轮
- 0.1.6 只做了 hook reason 注入计数，SKILL.md 流程仍写「只本轮」，两头不自洽（reason 让放宽、SKILL.md 没接住）——本版补上 SKILL.md 那一半，流程自洽

## 0.1.6 — 2026-05-29

### Module: Watcher

跳过计数：让最终 audit 知道「攒了多少轮没审」并放宽审计范围（改 suggest-watcher.sh）：

- **计数**：每次 stop 因 ① 中途无收尾文本（skip-no-last-msg）② watcher 手动关闭期间（skip-project-disabled）被跳过 → `<cwd>/.watcher/.skip-count` +1。`active=true`（audit 自己那轮）不计
- **存储**：项目本地 `.watcher/.skip-count`（项目相关语义，非 per-session）；仅当 `.watcher/` 已存在时计，不给未配置项目凭空造 `.watcher/`
- **注入 + 清零**：正常 stop（有 last_assistant_message）提醒跑 audit 时，读计数 → 拼进 reason（"已累计 N 轮没审，这次范围从『只本轮』放宽到『本轮 + 这 N 轮被跳过的工作』一起审"）→ 清零。reason 改用 jq 构造（安全转义）
- 解决 SKILL.md audit 是「只本轮」范围导致的「被跳过的轮永远没被审」

## 0.1.5 — 2026-05-29

### Module: Watcher

只在 CC「正常 stop」时跑 audit + 提醒闭环（改 suggest-watcher.sh，SKILL.md 不动）：

- **last_assistant_message 闸**：Stop hook 提取 `last_assistant_message`，字段缺失/null/空 → skip（不进 watcher）。CC 只在「最后一条 assistant 消息有纯文本」时才填这个字段（源码 `utils/hooks.ts:3662-3668`）；缺失 = CC 不是「给了最终收尾文本的正常 stop」（中途停 / 结尾是工具调用）→ 不该打扰它跑 audit。新增 log status `skip-no-last-msg`
- **reason 加闭环指令**：跑完 watcher audit 后必须自己处理 audit 结果（按自检发现做修正），处理完原任务没干完就继续干，别停在 audit
- **`active=true` 防递归不动**：它是防死循环的唯一保险，绝不能碰

## 0.1.4 — 2026-05-29

### Module: Watcher

修双 audit + 砍空 audit 噪音（SKILL.md）：

- **A — 砍自动触发**：frontmatter description 删掉 "MUST trigger ... 收尾 / 任何暗示里程碑的话" 自动触发语，改成"不要自己主动调，audit 只由 Stop hook reason 显式指示或用户显式命令触发"。
  - 修了"CC 自己主动调 watcher（1 次）+ Stop hook 再触发（1 次）= 双 audit"的 bug
- **B — fast-path**：新增「第零步：fast-path 判定」——本轮无文件变更 + 无新事实（纯问答 / 查看 / trivial）→ 跳过第一~三步同步与存量审查，只跑任务质量自检，摘要缩成「意图复述 + 任务完成度 + 根因自检」三段
  - 调和 3 处旧条款：摘要"禁止一句话替代"加 fast-path 例外；"对话无新事实仍审查"改成"无文件变更则 fast-path 跳过，存量审查改 opt-in"

## 0.1.3 — 2026-05-29

### Module: Watcher

announce 治理框架完整升级——根因主线 + 硬命令句风对齐：

- **段 3 整段重组**：
  - 4 步流程拆成 `### 3.1 复述需求` / `### 3.2 分析根因` / `### 3.3 给彻底方案` / `### 3.4 我打算干啥` 三级子段
  - 段首加问询例外开关："如果我只是问一个事，那么直接答就行；否则就必须严格按照以下四步流程"
  - 段 3.2 段标 "分析本质" → "分析根因"，内容强化根因思考的强制性
  - 段 3.3 内容改 "基于真实根因思考彻底的解决方案是啥"，临时方案必须明说找不到根因
  - 多步任务规则前置（TaskCreate 高频规则放前），问询例外后置
  - "用 TaskCreate" → "必须用 TaskCreate" 措辞强化
- **段 7 段标全句化**："解决任何问题必须先找根因，并且根因必须靠真正的证据来决定"
- **段 8 段标全句化**："解决问题必须用彻底的解决方案，严禁打任何折扣"
- **新增段 11 死刑底线**："你出现任何分析问题不找根因和解决问题不用彻底方案的行为，那么你他妈的就给我去死吧！"
- **段 9 / 段 10 内容互换**：DD/TDD/smoke/E2E 测试规范优先于 PR 善后（按触发频率排序）
- **段 10 → 段 9 扩展**：从 DD/TDD 二元扩到 DD/TDD/smoke/E2E 四元测试规范覆盖；提示文案改 "缺少某某 的流程规范，请你先完善，完善后我会更好的为你工作"
- **全局 "用户" → "我"**（脚本顶部 comment 保留——不进 hook stdout）
- **README.md / README.zh-CN.md 同步**：组件表 + 章节标题 + 列表 10 段 → 11 段；段 7/8/11 表达对齐

## 0.1.2 — 2026-05-28

### Module: Watcher

- announce 段 7 标题升级为硬命令句全句风：`解决任何问题必须先找根因，并且根因必须靠真正的证据来决定`
- announce 段 8 标题升级为硬命令句全句风：`解决问题必须用彻底的解决方案，严禁打任何折扣`
- 新增 announce 段 11 `死刑底线`——治理框架顶规则封顶强调
- README.md / README.zh-CN.md 同步:组件表/章节标题/列表 10 段 → 11 段
- slash command 命名引用 `/watcher-off` `/watcher-on` → `/watcher:watcher-off` `/watcher:watcher-on`（修 0.1.1 命名引用 bug，跟实际 plugin 加载形态对齐）
- 段内 bullet 内容不变,只升级段标语气

## 0.1.1 — 2026-05-28

### Module: Watcher
- Per-project Stop hook toggle: `/watcher:watcher-off` and `/watcher:watcher-on` slash commands
- Stop hook reads `cwd` from stdin and skips reminder if `<cwd>/.watcher/.stop-disabled` exists
- UserPromptSubmit announce rules remain active when Stop reminder is toggled off

## 0.1.0 — 2026-05-15

Initial release.

### Module: Watcher
- `UserPromptSubmit` hook: Pre-turn 4-step intent guard
- `Stop` hook: Knowledge audit reminder + root-cause review trigger
- `watcher` skill (two modes: audit / configure)
- Project-level config support via `<project>/.watcher/` (3 files: project-summary / doc-inventory / watchlist)
