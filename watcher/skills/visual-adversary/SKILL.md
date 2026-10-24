---
name: visual-adversary
description: >
  视觉对抗 — UI 改动做完后，看它长成什么样。
  启动真实 app，截图，取一份数值，派几个人各看一个角度，出一份报告和一页 HTML demo。
  报告分两节：可访问性底线项，和值得考虑的改进建议。
  **只有两个触发口**：协作规范流水线走到「视觉对抗」这一步；用户手动输入 `/watcher:visual-adversary`。
---

# 视觉对抗

## 平台对照

本 skill 在 Claude Code 和 Codex 里都会用到。正文按 Claude Code 的说法写，在 Codex 里按下表换成对应的东西：

| 正文里的写法 | 在 Codex 里 |
|---|---|
| Claude Code、CC | Codex |
| Read、Edit、Write、Bash 工具 | 用 `exec_command` 读文件和跑命令，用 `apply_patch` 改文件 |
| WebSearch、WebFetch | 联网搜索 |
| workflow | 用 `spawn_agent` 派子代理；判对抗是否跑成，看每个子代理的 `wait` 结果都是 completed、没有报错（对应 `agents_error`、`agents_done`、`agent_count`） |
| Monitor | 用 `gh pr checks <N> --watch` 盯 CI，用 `gh pr view <N> --json state,mergeStateStatus,reviewDecision` 看合并和 review |
| `/watcher:xxx`、`/watcher` | `$watcher:xxx`、`$watcher:watcher` |
| `CLAUDE.md` | `AGENTS.md` |
| `${CLAUDE_SKILL_DIR}` | 本 SKILL.md 所在目录的绝对路径 |
| Skill 工具 | 读对应 skill 的 SKILL.md |

像设计师那样看这个界面，不像 QA 那样对着规则打勾。

看的是效果：一眼看到什么、哪里挤、哪里松、状态分不分得清、有没有人看不清或点不到。截图是主要证据，数值用来补肉眼看不出的那部分 —— 差 1 的色号、差 1px 的间距、3.8:1 的对比度。

## 怎么跑

### 1. 判范围

改动沾到界面、用户可感知的交互、前端框架或设计系统，就跑。都不沾，说一句「本次无 UI 范围」结束。

### 2. 启动、截图、取数

真实启动 app，走 HTTP。

先建一个本次专用的工作目录，记下它打印的绝对路径。下文的 `<工作目录>` 都指这个路径，每条命令里直接写它：

```bash
node -e "console.log(require('fs').mkdtempSync(require('path').join(require('os').tmpdir(), 'va-')))"
```

改动涉及的每个页面截一张图。移动端布局有变的，再截一张 375 宽的。项目有暗色模式且改动涉及配色的，暗色再截一张。**够用就行，不用穷举组合。**

每张图存成文件（`<工作目录>/<页面>-<视口>.png`）。派活时给的是路径 —— workflow 的对抗者收到的只有文字，看不到你上下文里的图。

token 扫一次就够（它是项目级的）：

```bash
node "${CLAUDE_SKILL_DIR}/scripts/extract-tokens.js" . > <工作目录>/tokens.json
```

取数则是**每张截图对应注入一次** —— 同一个页面、同一个视口、同一个主题拿一份 JSON，各存一份到 `<工作目录>/<页面>-<视口>.json`。底线那节的结论只对被注入过的组合成立，375 宽的溢出和暗色下的对比度在 1440 亮色的样本里查不到。

注入方式：把 `inject-collect.js` 的 `CONFIG` 占位符换成 `{"tokens":[...]}`，见 [references/data-format.md](references/data-format.md)。

输出是聚合结果：页面用到的颜色、字号、间距各是哪些值，哪些不在项目 token 里，加上对比度、触控目标、溢出的实测。

项目没有 token 定义就说一句，跳过 token 那部分，其余照跑。

### 3. 派几个人各看一个角度

开 workflow，按改动规模派 2 到 4 个，执行方不兼任。角度：

| 角度 | 材料 | 看什么 |
|---|---|---|
| 能不能用 | 取数的 `checks` + 截图 | 看得清吗、点得到吗、有没有被裁掉 |
| 跟项目一不一致 | 取数的 `offToken` + 组件清单 + 截图 | 哪些值没走 token，哪些地方本可以用已有组件 |
| 看着怎么样 | 截图 + [references/aesthetic-notes.md](references/aesthetic-notes.md) | 层级、密度、对齐、节奏、配色关系 |
| 跟 demo 差在哪 | demo 图 + 实现图 | 差异点，以及哪一版效果更好 |

每人先自驳一遍，驳得倒的自己删，剩下的全部交回。

### 4. 核实

交回的逐条核：数值类回 `<工作目录>` 里的 JSON 对一下，看的类自己再看一遍截图。

数对不上的删掉。说不清「换一种做法效果差在哪」的删掉。

### 5. 出报告和 demo

两节：

| 节 | 对应协作规范 | 表的列 |
|---|---|---|
| 底线节 | 底线类 | `问题｜标准｜实测值｜彻底方案及方案依据` |
| 建议节 | 建议类 | `处境｜现在什么效果｜另一种做法什么效果｜代价｜方向` |

方案依据按协作规范 1.2 的定义三选一；标成纯内部的，在底线节表后单列一节强调。

建议节只描述差异并给方向，不判对错。

底线节上方写一行未判定：`checks.contrastUnknown` 非空说明有文字压在图或渐变上没测出对比度，写明几处、截图上确认没确认。

建议节里每条都要能让人看出「换了之后有什么不同」。看不出的不写。

视觉问题好不好只有看了才能判断，所以两节的每一条都画进一页静态 HTML demo，一条不漏。两节连续编号，从第 1 条开始，报告的两张表用同一套编号，决策者按编号回复。

| 位置 | 内容 |
|---|---|
| 页面顶部 | 总结列表，一条一行：第几条、原因是什么、跟第几条重复。列表下写回复格式：「第 N 条：同意 / 不同意 / 需要完善的地方」 |
| 每条的开头 | 醒目的「第 N 条」，加类别：底线类或建议类 |
| 每条的中间 | 左右对比，左边是当前问题，右边是修改方案。两边都用 HTML/CSS 画出问题所在的局部，颜色、字号、间距、尺寸取 `<工作目录>` 里 JSON 的实测值，右边只改方案涉及的值。问题位置用框线标出，旁边标实测值和目标值，如「对比度 3.2:1，需 ≥ 4.5:1」。左边可另附真实 app 的局部截图作佐证：用 Playwright 的 `locator.screenshot()` 只截相关元素，`deviceScaleFactor: 2` |
| 每条的底部 | 执行方是否认可（认可、部分认可、不认可，附理由），以及跟哪几条重复 |

demo 存成 `<工作目录>/demo.html`，交付时给绝对路径和 `file://` URL，连同两张表一起交。

报告和 demo 出完就结束。所有条目都不直接改，由决策者在 demo 上逐条定改实现、改规范还是不动。

## 判据

**底线类**只有可访问性和可用性这一类，判据是公开标准：

| 项 | 标准 |
|---|---|
| 正文对比度 | ≥ 4.5:1（WCAG 2.2 SC 1.4.3 AA） |
| 大字对比度 | ≥ 3:1（≥24px，或 ≥18.66px 且 ≥700 字重） |
| 触控目标 | ≥ 24×24（WCAG 2.2 SC 2.5.8 AA）；句子里的链接除外，标准自带这条例外。`<a><svg/></a>` 这类图标链接不属于例外 |
| 允许缩放 | 无 `user-scalable=no`、无 `maximum-scale=1` |
| 内容不被裁掉 | 无隐式溢出、无意外横向滚动 |

**其余全是建议**，包括没走 token、没复用组件、跟 demo 不一样、看着可以更好。

理由：规范可能定得早、场景没覆盖到；已有组件可能不满足这次的需求；实现可能比 demo 更好。这些都不是错，是值得摆出来让人选的岔路。

项目规范跟公开标准冲突时，两边理由都写进建议节。落在可访问性上的，说清楚再交决策者。

## 参考

- [references/checks.md](references/checks.md) — 看什么、证据怎么写
- [references/data-format.md](references/data-format.md) — 脚本用法和输出结构
- [references/aesthetic-notes.md](references/aesthetic-notes.md) — 视觉效果的观察角度
