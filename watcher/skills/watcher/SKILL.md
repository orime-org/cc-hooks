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

- **通用硬规则**：所有项目都跑（见第三步「通用硬规则」段）
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

实际 Edit/Write 修改受影响文件。**顺序**：先改 docs/（影响外部）→ 再改 CLAUDE.md → 最后理记忆。

#### 1. 通用硬规则

以下 5 个维度**并行审查**（不分先后），每条命中就改：

##### 1.1 记忆层规则

| 情况 | 处理 |
|---|---|
| 过期事实 | 改记忆文件 + 更新索引（如 MEMORY.md）的 description |
| 相对时间（"今天" / "最近" / "today"） | 转绝对日期（`2026-04-29` 而非"今天"） |
| 重复记录（多条说同一件事） | 合并为一条，改索引 |
| 已完成的待办 | 删除——知识库不是历史档案 |
| 推翻的决策 | 删旧条目，留新决策（如果失败教训值得留，放 reference 类记忆） |
| 跨会话只用一次的临时上下文 | 删除 |
| 记忆间无法自动判断的矛盾 | 列「未处理」让用户决定 |

##### 1.2 跨项目影响检查

**判断方法**：这次改的东西有没有 SDK / 子域 / 共享配置 / 跨进程协议？有就要在所有依赖项目里搜一遍。

| 场景 | 必须改 |
|---|---|
| 上游 API 变了 | 下游 SDK 文档、集成指南 |
| 共享子域 / 路由 / 环境变量改了 | 所有 consumer 项目的 setup 文档 |
| 认证中台变更 | 所有接入应用的 integration guide |
| 公共组件 / 基础设施升级 | 各项目 runbook 提及版本号的地方 |
| 共享 design tokens 改了 | 所有使用该 tokens 的项目的 component 文档 |
| 共享 schema 改了 | 所有依赖该 schema 的 data 项目 |

##### 1.3 时间格式

- 永远**绝对日期**：`2026-05-13`（ISO 8601）
- **禁止**：今天 / 昨天 / 刚刚 / 最近 / 上周 / today / yesterday / recently / just now
- 跨年情境特别带年份（"2026-01-03" 不是 "1-3"）
- 不准确到日 → 写到月（`2026-05`）；不准确到月 → 季度或年

##### 1.4 文档结构通用约定

无论项目类型，下面四件事是高频查询，**必须保持"所见即最新"**：

1. **README.md** 项目入口 — 一句话定位 + 怎么跑起来
2. **入口配置表**（环境变量 / API key / 必备文件）— 项目根 markdown 或专门 *.md
3. **术语表 / glossary** — 项目特有词汇定义
4. **现状清单**（"已完成 / 进行中 / 待办" 或 CHANGELOG）— 给接手者看进度

##### 1.5 编辑原则

- **合并优于追加**：新信息是对旧的更新就改旧条目，不要叠加
- **删除优于保留**：完成的临时计划、推翻的决策、过期上下文，删掉
- **精确优于冗长**：一条说一件事
- **受众不混**：CLAUDE.md 写给"下次的自己"，docs/ 写给"接手的别人"
- **绝对时间** + **真实路径**：所有引用都要可验证

#### 2. 项目应有文档（如有 `doc-inventory.md`）

每个文档对照实际状态——按 `.watcher/doc-inventory.md` 跑。

#### 3. 用户自定义（如有 `watchlist.md`）

每条关注点——按 `.watcher/watchlist.md` 跑。

### 第四步：自检清单

跑**两件事**：

#### 1. 任务质量自检（Stop hook 优先跑）

watcher 在 Stop event 触发时，**先看本轮 agent 行为质量**——这是知识同步的前置审查。

5 条 generic 原则（不分编程 / 文档 / 调研，所有任务都适用）：

- [ ] **真的解决用户原始问题**——不是切题但没答 / 不是侧面 / 不是部分

- [ ] **做了适当验证**（按任务性质选合理方式）：
  - 编程类：编译 / 测试 / smoke run
  - 调研类：本地 grep / Read / git log 实证
  - 信息类：WebSearch / WebFetch 官方文档取权威

- [ ] **解决根本问题**——根因 + 彻底方案两个层面：
  - **根因层**：信息源走完整链了吗？
    - [ ] 先查本地（代码 / 文档 / CLAUDE.md / git log）
    - [ ] 再查远程（WebSearch / 官方文档）取权威信息
    - [ ] 跑最小复现实验验证
    - 禁：靠记忆 / 推测 / 类比下结论
  - **方案层**:彻底执行了吗？
    - [ ] 不是 workaround / 注释绕过 / 临时 fix（临时方案必须明示告知用户）
    - [ ] 没有用 scope / phase / 下次 PR / "本次只做 X" 借口拆解本应一起改的事
    - 禁：时间 / token / 成本 / PR 大小作为跳过彻底治根的借口

- [ ] **没未告知的偏离**——自作主张改方向 / 加了功能 / 跳过步骤 → 列在「未处理」让用户确认

- [ ] **信守中途承诺**——会话中说过的"稍后我会…"、"等会处理 X" 都做了

##### 判定级别

- ❌ **真未完成**：用户明确要 X 但只做 50% / 跑题完全
- ⚠️ **偏离 / 半完成**：用户没要求但顺手做了 / 该验证没验证 / **该一起改的事被借口拆开做**
- ✅ **完成**：用户原问题已答 + 关键承诺已兑现 + 根因走完整 + 彻底执行无打折

不通过的项 → 第 5 步摘要 "**任务完成度**" 段列出（在记忆/文档变更之前）。watcher 口吻是**提醒**不是质问——避免烦人。

#### 2. 自检清单（每次必跑）

- [ ] 第一步列出的每个文件都判断了「不用改 / 已改」
- [ ] 记忆索引每个链接指向真实存在的文件（无 dead link）
- [ ] 每个记忆 description 跟内容对得上
- [ ] 记忆间没有互相矛盾
- [ ] 项目根 markdown 提到的路径 / 命令 / 工具 / 环境变量在代码中真实存在
- [ ] README 的安装 / 运行步骤跟代码 / 配置一致
- [ ] 跨项目影响：下游项目的 docs 跟着改了
- [ ] 没有相对时间遗留（`grep -E "今天|昨天|刚刚|最近|上周|today|yesterday|recently"` 清零）
- [ ] `.watcher/watchlist.md` 每条关注点都跑过（如有）
- [ ] `.watcher/doc-inventory.md` 列的每个文档都对照实际状态（如有）

哪条打不了勾，**回去补**。

### 第五步：变更摘要

**首行高亮（条件性，强制逐字输出）**：如 `.watcher/` 不存在或不完整，**摘要第一行**必须**逐字输出**下面这段，禁止简化或重写：

> ⚠️ **检测到 `.watcher/` 未建（或缺 X 文件）** — 本轮仅通用规则审查（精度受限）。建议输入 `/watcher configure` 建项目级配置后重跑 audit。

**段内格式约束**：5 段摘要内任何段如含 **2+ 同结构项**（如多个用户问题 / 多个任务 / 多个文档变更 / 多个未处理项 / 多个根因发现），**强制 markdown 表格**——禁堆成 paragraph。表格列设计参考：「项 / 啥事 / 上下文 / 状态」或「维度 / 内容」等结构化列头。

接着标准摘要结构（**「用户意图复述」每次必出，不可省略**——这是审计链基石。其他段按本轮是否有实际内容决定是否列）：

```
## 1. 本轮 audit 总说明

<cwd 标识 / .watcher 状态等首行声明>（如 .watcher/ 不存在，这里逐字输出首行高亮警告）

## 2. 用户意图复述

本轮用户要求：<一句话，引用用户原话关键部分>

## 3. 任务完成度

- ✅ <用户原问题>：xxx（已完成 + 怎么验证）
- ⚠️ <偏离 / 半完成>：xxx（理由 / 是否要纠正）
- ❌ <真未完成>：xxx（缺什么 / 要不要继续）

## 4. 记忆变更

- 更新：xxx（原因）
- 新增：xxx
- 删除：xxx（原因）

## 5. 文档变更（按项目分组）

- <项目 A>/path/to/file.md — xxx
- <项目 B>/path/to/file.md — xxx

## 6. 根因自检

- **真根因诊断**：本轮处理是不是真解决根本问题（按 announce 段 3 "想想需求的本质 + 根本原因"+ 段 8 "彻底方案别打折"做自检）
- **实证手段**：按 announce 段 7 "找根因要靠真证据"做了哪些实证（先本地 / 再远程 / 跑实验）
- **workaround 明示**（如有）：本轮如果有任何治标不治本的临时方案，必须在这里明示——按 stop hook reason 要求

## 7. 未处理

- xxx（为什么没处理，比如需要用户确认）
```

**段结构规则**：摘要按 announce hook 段定义跑——每个段用 `## N. xxx` 二级标题写顶层段（不要用单段套 ### 子段的旧模式）；段编号从 1 开始重新数,每次新 audit 都独立编号。

「任务完成度」「记忆变更」「文档变更」「未处理」段：**只列实际发生的事**（已 Edit 的 memory 文件 / 已 Write 的 docs / 已完成或受阻的任务）；**禁止写候选事实 / 评估过程 / "考虑过但未变更" / "无 — 两个候选..." 等内容**；无内容则**省略整段**。**禁止用"本轮任务完成，无积压"等一句话替代整个摘要——意图复述仍必须详细写。**

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

## 全局配置极度克制

`~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` 等全局文件——只有用户在对话中明确表达**跨项目的核心原则**才动。日常项目细节绝不进全局。

## 参考资料

- [references/agent-paths.md](references/agent-paths.md) — 各 platform 记忆路径速查
- [references/setup-flow.md](references/setup-flow.md) — configure 模式建/改 `.watcher/` 流程
