# bash-gate 设计文档

把协作规范里 4.1.3、4.7.5、4.7.7 三条从文字约束变成工具层面拦截。

## 1. 任务目标

在 watcher 插件里新增 Bash 命令拦截，把规范 4.1.3 主分支保护、4.7.5 提 PR 前置、4.7.7 commit 标题格式与禁署名这几条，从文字约束变成工具层面拦截。

按 4.2.2，此目标已确认，全程不改。

## 2. 验收清单

产出物按 1.2 术语表判定：脚本和 `hooks.json` 都是**生产代码**；级别按 3.1.2 判定为**开发级** —— 它拦的是 CC 干活时的 git 命令，只在开发过程中起作用。按 3.1.3，开发级不进三类。

设计对抗曾主张判成用户级（理由是 orime 是插件市场、脚本会在别人机器上跑），我一度接受；最终由决策者裁定为开发级，以此为准。相应地，验收标准是「会不会挡住开发进行」，而不是三类各自的处理程度。

| # | 做什么 | 产出物·级别 | 场景／目标／结果 | 对应目标哪部分 |
|---|---|---|---|---|
| 1 | 主分支上拦 `git commit` | 生产代码·开发级 | 场景：CC 在 main 或 master 上执行 commit。目标：改动不直接落主分支。结果：调用被拦，CC 收到「当前在主分支，先建任务分支」 | 4.1.3 |
| 2 | 分支判定用 stdin 的 `cwd` | 生产代码·开发级 | 场景：CC 写 `cd /path && git commit` 或 `git -C /path commit`，hook 进程自己的目录在别处。目标：判定 CC 真正提交的那个仓库。结果：两种写法都能判出正确分支 | 4.1.3 |
| 3 | commit 标题格式校验 | 生产代码·开发级 | 场景：CC 执行带 `-m` 的 commit。目标：标题符合 `type: summary`、≤72 字符、无句号结尾、不含 `Co-Authored-By`。结果：不符合的被拦并说明违反哪一条 | 4.7.7 |
| 4 | 无验证标记时拦 `gh pr create` | 生产代码·开发级 | 场景：CC 要提 PR。目标：交付验证没做完不许提。结果：`/tmp/cc-<会话id>-verified` 不存在就拦 | 4.7.5 |
| 5 | 读输入失败时拦住 | 生产代码·开发级 | 场景：python3 缺失或 stdin 不是合法 JSON。目标：检查器自身故障不得假装通过。结果：拦下并说明故障，不静默放行 | 1.3.6 |
| 6 | `hooks.json` 加接线 | 生产代码·开发级 | 场景：插件加载。目标：脚本挂到 `PreToolUse[Bash]`。结果：新接线生效，原有 `UserPromptSubmit` 和 `Stop` 两条不动 | 支撑 1 到 5 |
| 7 | `smoke-bash-gate.py` | 测试代码 | 场景：改完脚本、提交前。目标：1 到 5 每条都有能跑的断言。结果：构造真实 stdin 跑脚本、断言退出码和 stderr，不全绿不许提交 | 4.2.6 |

## 3. 依据：已查实的事实

设计建立在这些实测结果上，不靠记忆或推测。

| 事实 | 出处 |
|---|---|
| hook stdin 含 `session_id`、`transcript_path`、`cwd`、`permission_mode`、`hook_event_name` 公共字段 | 官方 hooks 文档公共字段清单；本仓 `watcher/hooks/suggest-watcher.sh:36` 已在用 `jq -r '.cwd'` |
| `PreToolUse` 的 `tool_input` 对 Bash 工具含 `command` 字段 | 官方 hooks 文档 PreToolUse 输入示例 |
| `PreToolUse` 退出码 2 拦截调用，且 stderr 回传给模型 | 2.1.221 二进制字符串 `Exit code 2 - show stderr to model and block tool call` |
| 退出码 1 是非阻塞错误，工具照常执行 | 官方 hooks 文档「treats exit code 1 as a non-blocking error and proceeds with the action」 |
| hook stdout 上限 10000 字符，按每个 hook 各自计 | 官方 hooks 文档「Hook output strings … are capped at 10,000 characters」 |
| 插件 `hooks.json` 支持 `PreToolUse` | 官方插件文档「Plugin hooks respond to the same lifecycle events as user-defined hooks」 |
| `${CLAUDE_PLUGIN_ROOT}` 在 hook 命令里作为环境变量可用 | 官方插件文档「All three are exported as environment variables to hook processes」 |
| 插件不能声明 `includeCoAuthoredBy` 等顶层 settings 键 | 官方插件文档「Only the `agent` and `subagentStatusLine` keys are supported」 |

最后一条决定了本次范围：插件不碰任何人的全局配置，禁署名只靠第 3 条的 commit message 检查覆盖。这是已确认的边界，见第 7 节。

## 4. 参考实现的四处缺陷

设计的起点是一份外部 CC 提供的 `bash-gate.sh`（`~/Downloads/cc-spec-deploy-all-in-one.md` 第 251 到 304 行）。逐行核过，四处缺陷全部确认成立，本设计逐条修正。

| # | 缺陷 | 原文位置 | 后果 | 本设计的修法 |
|---|---|---|---|---|
| 一 | `field()` 用 `2>/dev/null` 吞掉 python3 全部报错 | 第 259 行 | python3 缺失或 JSON 解析失败时 `cmd` 取空，三个 grep 全不匹配，走到 `exit 0` 放行。拦截器停止工作且不出声 | 不再屏蔽错误；解析失败时拦住并说明故障 |
| 二 | `git branch --show-current` 跑在 hook 进程自己的目录 | 第 265 行 | hook 的 cwd 不是目标仓库时返回空，检查跳过；是另一个仓库时判错 | 用 stdin 的 `cwd`，`git -C "$cwd"` |
| 三 | 命令匹配漏 `git -C <path> commit` | 第 264、297 行 | `grep -qE 'git[[:space:]]+commit'` 对中间隔着 `-C /path` 的写法匹配不到，整段跳过 | 匹配模式覆盖 `git` 与 `commit` 之间夹选项的形式 |
| 四 | message 提取只覆盖 `-m` 写法 | 第 271 到 275 行 | `git commit -F -` 和 heredoc 写法拿不到 message | 保留此边界，见第 7 节 |

## 5. 怎么设计

### 5.1 脚本结构

`watcher/hooks/bash-gate.sh`，挂 `PreToolUse[Bash]`，读 stdin 的 JSON，按顺序做三组检查，任一不过即 `exit 2`，全过 `exit 0`。

```
读 stdin
  ↓
解析 command / session_id / cwd    ← 解析失败：exit 2，说明检查器故障
  ↓
命令含 git commit？
  ├─ 是 → 判分支（目标仓库）
  │        ├─ 在 main/master → exit 2
  │        └─ 否则 → 校验 message 格式 → 不合规 exit 2
  └─ 否 → 继续
  ↓
命令含 gh pr create？
  ├─ 是 → /tmp/cc-<sid>-verified 存在？
  │        ├─ 否 → exit 2
  │        └─ 是 → 继续
  └─ 否 → 继续
  ↓
exit 0
```

### 5.2 关键行为

| 检查 | 触发条件 | 判据 | 不通过时 |
|---|---|---|---|
| 输入解析 | 每次调用 | python3 存在，且 stdin 是合法 JSON，且能取到 `tool_input.command` | `exit 2`，stderr 说明检查器自身故障和修法 |
| 主分支保护 | commit 所在命令段 | 目标目录按「段内 `-C` 路径 → 段前最后一个 `cd` → stdin 的 `cwd`」定，再用 `rev-parse --show-toplevel` 取仓库根；该仓库当前分支不是 main 或 master | `exit 2`，stderr 报当前分支名并要求先建任务分支 |
| 标题类型 | 命令含 `-m` 且能取到 message | 首行匹配 `^(feat\|fix\|refactor\|docs\|test\|chore\|perf\|ci)(\(...\))?: .+` | `exit 2`，列出允许的 type |
| 标题长度 | 同上 | 首行字符数 ≤ 72 | `exit 2`，报实际长度 |
| 标题结尾 | 同上 | 首行不以 `.` 或 `。` 结尾 | `exit 2` |
| 禁署名 | 命令含 git commit | 整条命令不含 `Co-Authored-By`（不分大小写） | `exit 2` |
| 提 PR 前置 | 命令含 gh pr create | `/tmp/cc-<session_id>-verified` 存在 | `exit 2`，说明按 4.7.5 完成验证后 `touch` 该文件再提 |

### 5.3 已决定的选择

| 选择 | 决定 | 理由 |
|---|---|---|
| 检查器自身故障时拦还是放 | **拦住** | 规范 1.3.6「工具、权限或外部条件不可用时说明阻断……不得跳过、伪造通过或称完成」。校验器坏了还放行即伪造通过。影响范围限于 `git commit` 和 `gh pr create` 两类命令，不影响其他 Bash 调用 |
| 解析 JSON 用什么 | python3 | 参考实现已从 jq 改为 python3，理由是 jq 普及度低。本仓 `suggest-watcher.sh` 用的是 jq，但那是既有代码，本次不动它（3.2.7 目标外不扩入） |
| 分支名判定范围 | 只认 main 和 master | 术语表「主分支」定义为「仓库默认主分支，通常为 main/master」。更准的做法是读 `git symbolic-ref refs/remotes/origin/HEAD`，但那需要远端存在且已 fetch，失败率高于收益 |
| 提 PR 标记的位置 | `/tmp/cc-<session_id>-verified` | 按会话隔离，机器重启即清，无残留。沿用参考实现的做法 |

### 5.4 已知边界，明示不解决

| 边界 | 说明 |
|---|---|
| `git commit -F -` 和 heredoc 写法的 message 拿不到 | message 从 stdin 进入 git，hook 只能看到命令行文本。要覆盖须在各仓库装 git 原生 `commit-msg` 钩子，那是另一个任务。本次不做，不假装覆盖 |
| 提 PR 验证标记是留痕式软证据 | CC 技术上可以未验证就 `touch` 标记。拦截信息里写明「未验证而创建标记即为虚报，违反 1.3.1」，把跳过变成必须主动执行一条留痕命令。硬化做法（测试命令包装、退出码为 0 才写标记）留作后续 |
| 用 Bash 的 `cat >`、`sed -i` 改代码不受本脚本管 | 本脚本只管 git 和 gh 两类命令。文件编辑类拦截本次不做 |
| 插件不写 `includeCoAuthoredBy` | 插件机制不支持声明该键（见第 3 节）。本机已单独配置，其他使用者靠第 3 条的 commit message 检查覆盖 `-m` 写法 |
| `git commit -m "$(cat <<EOF ... EOF)"` 不做 message 判定 | message 由命令替换生成，命令行文本里是脚本片段不是最终文本。拿片段去判会误拦合规提交，所以这种写法只做分支检查，标题格式与禁署名不生效 |
| 换行分隔的多行命令只认第一段 | `git push ...` 换行接 `gh pr create` 这类写法，第二行的命令不受检查。用 `&&` 连接则正常生效 |
| `commit -C <commit>`（复用某次提交的 message）会被当成 `git -C <path>` | 取到的路径不是仓库，作用域判否后放行 |

## 6. 如何验证

`watcher/scripts/smoke-bash-gate.py`，照 `smoke-stop-hook.py` 的模式：构造真实 stdin JSON、跑脚本、断言退出码和 stderr 内容。

| 用例 | 输入 | 预期 |
|---|---|---|
| A | 在 main 分支的临时仓库，`git commit -m "feat: x"` | exit 2，stderr 含分支名 |
| B | 在任务分支，`git commit -m "feat: add thing"` | exit 0 |
| C | 在任务分支，`git commit -m "add thing"`（无 type） | exit 2，stderr 提到 type |
| D | 在任务分支，标题 73 字符 | exit 2，stderr 报长度 |
| E | 在任务分支，标题以句号结尾 | exit 2 |
| F | 命令含 `Co-Authored-By` | exit 2 |
| G | `cd /path && git commit`，hook 的 cwd 在别处 | 按 `cwd` 字段判定，不受 hook 进程目录影响 |
| H | `git -C /path commit -m "..."` | 能匹配到并检查 |
| I | `gh pr create`，标记不存在 | exit 2 |
| J | `gh pr create`，标记存在 | exit 0 |
| K | stdin 不是合法 JSON | exit 2，stderr 说明检查器故障 |
| L | 非 git、非 gh 的普通命令（如 `ls`） | exit 0 |

按 4.4.1 测试先行：先写这些用例并运行，确认全部因功能未实现而失败，再写实现。

## 7. 不在本次范围

| 项 | 为什么 |
|---|---|
| `rules/base.md`、`rules/coding.md` | announce hook 每轮注入完整规范 8492 字符，第 1 到 4 章全在上下文里，副本会与权威源漂移（3.1.6 不留会漂移的重复实现） |
| `require-coding-rules.sh`、`mark-rules-read.sh` | 存在目的是强制 Read `coding.md`，该文件已不做 |
| AskUserQuestion 拦截 | 规范 2.3.6 已明写不用该工具，实际未发生违反。按 3.1.4 承诺外类「未承诺部分提示下一步」，不写代码杜绝 |
| `includeCoAuthoredBy` 写入 | 插件机制不支持；已单独在本机 `~/.claude/settings.json` 配置 |
| 修改 `announce-intent.sh` | 目标外，且规范正文已定稿 |
