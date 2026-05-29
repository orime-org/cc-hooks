# Changelog

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
