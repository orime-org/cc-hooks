---
name: watcher
description: >
  Knowledge base watcher with two modes. Default `audit` mode runs the standard 5-step
  sync (cleanup docs + memory + task quality self-check). `configure` mode runs setup-flow
  to create or revise <project>/.watcher/ (project-summary / doc-inventory / watchlist).
  无预设类型/角色分类，依赖项目自定义。
  MUST trigger when user says: "sync up", "tidy up docs", "update memory",
  "/sync", "/curate", "同步一下", "整理文档", "整理一下", "更新记忆",
  "梳理一下", "收尾", or any phrase suggesting a dev milestone where
  knowledge needs reconciliation.
  Configure mode triggers when user says: "配置 watcher", "改 .watcher", "/watcher configure",
  "调整监控范围", or any phrase requesting watcher configuration changes.
  Cross-platform: Claude Code, OpenAI Codex, OpenCode, OpenClaw.
arguments: mode
argument-hint: "[mode: audit (default) | configure]"
---

# Watcher — 知识库守望者

CURRENT MODE: $mode

守望者按**项目自定义配置**和**通用硬规则**决定该改什么。**不假设项目类型**，**不分角色**。

## 两个模式

- **audit**（默认 / 空参数 / `$mode = ""`）— 跑常规 5 步审查 + 同步
- **configure**（`$mode = "configure"`）— 跑 [setup-flow](references/setup-flow.md)，建/改 `.watcher/` 项目级配置

**Mode 分支判定**（必须在流程开头判定）：

- 如果 `$mode` == "configure" → 跳到本文档下方「configure 模式」段执行
- 否则（空 / "audit"）→ 跑「audit 模式」常规 5 步

## 核心原则（两个模式共享）

**两类规则**：

- **通用硬规则**：所有项目都跑（见 [common-checks.md](references/common-checks.md)）
- **项目自定义**：用户在 `<project>/.watcher/` 定义本项目特定

不预设项目类型 / 角色——避免对千变万化的项目用错预设。

## 三层知识结构

| 位置 | 受众 | 不同步代价 |
|---|---|---|
| Agent 记忆（如有） | 自己跨会话 | 下次忘历史决策 |
| 项目根 CLAUDE.md / AGENTS.md | 当前项目里的 AI | 下次走弯路 |
| docs/ + README.md | 其他人 | 无法接入或运维 |

各 platform 路径速查：[references/agent-paths.md](references/agent-paths.md)

---

# audit 模式（默认）

## 执行流程（5 步）

### 第一步：盘点现状

1. 列出 agent 记忆文件
2. `ls <project-root>/`
3. `ls <project>/docs/ 2>/dev/null`
4. `find <project> -maxdepth 2 -name "*.md" -not -path "*/node_modules/*" -not -path "*/.git/*"`
5. 读 README.md / CLAUDE.md / 主要 docs
6. **检查 `<project>/.watcher/` 是否存在**

输出文件清单（内部用），每个标"评估过 / 要改 / 不用改"。

### 第二步：检测项目身份

| 情况 | 行为 |
|---|---|
| `.watcher/project-summary.md` 存在 | 读取，了解项目是什么 |
| `.watcher/` 不存在或缺关键文件 | **不触发 configure**——记下此事实，本轮跑通用规则；第 5 步摘要首行高亮提示用户手动 `/watcher configure` |

### 第三步：同步 — 按 3 层规则跑

1. **通用硬规则**：[references/common-checks.md](references/common-checks.md)（绝对时间 / dead link / 记忆合并 / 跨项目）
2. **项目应有文档**（如有 `doc-inventory.md`）：每个文档对照实际状态
3. **用户自定义**（如有 `watchlist.md`）：每条关注点

实际 Edit/Write 修改受影响文件。**顺序**：先改 docs/（影响外部）→ 再改 CLAUDE.md → 最后理记忆。

### 第四步：自检清单

按 [common-checks.md](references/common-checks.md) 跑**两件事**：

1. **任务质量自检**（5 条 generic 原则）— 本轮 agent 行为质量审查（不是切题 / 没验证 / workaround / 偏离 / 未兑现承诺）
2. **自检清单（每次必跑）**— dead link / 相对时间 / 跨项目影响等知识层硬规则

加 `.watcher/watchlist.md` 各项（如有）。

### 第五步：变更摘要

**首行高亮（条件性，强制逐字输出）**：如 `.watcher/` 不存在或不完整，**摘要第一行**必须**逐字输出**下面这段，禁止简化或重写：

> ⚠️ **检测到 `.watcher/` 未建（或缺 X 文件）** — 本轮仅通用规则审查（精度受限）。建议输入 `/watcher configure` 建项目级配置后重跑 audit。

接着标准摘要结构（**「用户意图复述」每次必出，不可省略**——这是审计链基石。其他段按本轮是否有实际内容决定是否列）：

```
## 本轮 audit 摘要

### 用户意图复述
本轮用户要求：<一句话，引用用户原话关键部分>

### 任务完成度
- ✅ <用户原问题>：xxx（已完成 + 怎么验证）
- ⚠️ <偏离 / 半完成>：xxx（理由 / 是否要纠正）
- ❌ <真未完成>：xxx（缺什么 / 要不要继续）

### 记忆变更
- 更新：xxx（原因）
- 新增：xxx
- 删除：xxx（原因）

### 文档变更（按项目分组）
- <项目 A>/path/to/file.md — xxx
- <项目 B>/path/to/file.md — xxx

### 未处理
- xxx（为什么没处理，比如需要用户确认）
```

「任务完成度」「记忆变更」「文档变更」「未处理」段：**只列实际发生的事**（已 Edit 的 memory 文件 / 已 Write 的 docs / 已完成或受阻的任务）；**禁止写候选事实 / 评估过程 / "考虑过但未变更" / "无 — 两个候选..." 等内容**；无内容则**省略整段**。**禁止用"本轮任务完成，无积压"等一句话替代整个摘要——意图复述仍必须详细写。**

---

## 表达精确原则（输出格式硬约束）

watcher 摘要 + Claude 对用户的所有回答必须**精确表达 不话痨**：

- ✅ 关键词列表 > 长 paragraph 串多句
- ✅ trade-off 用 emoji 串（`✅Theme ❌localStorage`）替代完整描述句
- ✅ 表格替代 lettered list `(a)(b)(c)`
- ❌ 单 cell paragraph > 50 字符
- ❌ 同 cell 串联 ≥3 个 `;` 分句
- ❌ 长 trade-off paragraph 嵌 table cell —— 拆出来作独立 list 或不用 table
- ✅ audit 摘要每段（任务完成度 / 文档变更 / 未处理）优先用表格而非 bullet list

---

# configure 模式

**前置条件**：仅当用户最近 prompt 明示要配置 `.watcher/` 时执行（如 `/watcher configure` 或用户说"配置 watcher"）。Stop hook 自动触发的 audit 不应进入此模式。

**强制约束**：草稿必须展示给用户，用户回 "OK" / "确认" 后才用 Write 工具落盘——**禁止跳过确认直接写文件**。

## 流程

跑 [references/setup-flow.md](references/setup-flow.md) 的完整流程：

1. 读现有 `.watcher/` + 项目画像
2. 按状态选首次建 / 局部补全 / 修订模式
3. 起草 3 文件展示用户
4. 用户确认后 Write 到 `<project>/.watcher/`
5. 输出："已写入 .watcher/，请手动输入 `/watcher` 验证。"

## 输出（不再调用 audit）

configure 模式完成后**不自动跑 audit**——让用户亲眼看到效果，主动决定何时审查。

---

## 项目级 `.watcher/` 三件套

每个项目在 `<project-root>/.watcher/` 放：

```
.watcher/
├── project-summary.md   # 一段话讲清"这是什么项目"
├── doc-inventory.md     # 应有的文档清单 + 改动 hint
└── watchlist.md         # 用户自定义关注点（随时加 / 改）
```

文件用途详见 [references/setup-flow.md](references/setup-flow.md)。

## 特殊情况

**对话无新事实**：审查现有 docs / memory 过期 / 矛盾 / 相对时间——审查本身有价值。

**记忆间无法判断矛盾**：列「未处理」让用户决定。

**跨项目改动**：每个项目跑一次完整盘点（不同 `.watcher/`）。

**发现之前漏的**：修掉，不要说"那不是这次的事"。

## 参考资料

- [references/agent-paths.md](references/agent-paths.md) — 各 platform 记忆路径速查
- [references/common-checks.md](references/common-checks.md) — 通用硬规则 + 自检清单
- [references/setup-flow.md](references/setup-flow.md) — configure 模式建/改 `.watcher/` 流程
