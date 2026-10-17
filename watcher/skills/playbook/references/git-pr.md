# push、PR、清场、多 worktree

commit、push、开或更新 PR、PR 开出之后、中断恢复后、判是否本次引入、清场、派出 agent 之后读。下文的 `origin/main` 指远端主分支，仓库主分支不叫 main 时换成它的名字。

## 1. push 前确认 PR 状态和分支

push 或更新 PR 前，用 `gh pr view --json state,headRefName` 确认 PR 仍是 OPEN、分支对得上；已 MERGED 就从主分支新开分支和 PR。删分支前用 `git log origin/main..origin/<branch>` 查有没有孤立 commit。报「已推」之前看远端的证据。

理由：往已合并分支 push 的 commit 进不了主分支；commit、push、进 PR、进主分支是四件事。

判定：当前分支的 PR 还是 OPEN 吗？

## 2. push 异常时和合并后核实

push 输出异常（对已存在的分支报 new branch、出现 force、range 不对）时，用 `git ls-remote origin <branch>` 和 PR 的 `headRefOid` 核远端 head 等于本地 HEAD。我说「已合并」之后：同步主分支；用 `git branch -r --contains <最后的 commit>` 证明它在主分支上；逐个核本次的关键文件；同一时期有别的 PR 碰过同一文件的，逐处比对。

理由：不核就是假设 PR 和 CI 用的是最后那个 commit；后合并的 PR 可能整段覆盖先合并的改动。

判定：PR 和 CI 用的真是最后那个 commit 吗？

## 3. PR 开出后发现漏项

PR 开出后发现交付条件没满足：当场 `gh pr ready <N> --undo` 转成草稿，补完再标就绪，并在发现的那一刻告诉我。

理由：开着的 PR 我随时可能合，漏项不能留在可合并的位置上补。

判定：这个 PR 现在处在可合并的位置吗？交付条件都满足了吗？

## 4. 开完 PR 起 Monitor

开完 PR 的同一轮起 Monitor，盯 CI 和合并状态；判 BLOCKED 之前排除进行中的状态（`IN_PROGRESS`、`QUEUED`）。

理由：不盯会漏掉就绪信号；不排除进行中的状态会报假警报。

## 5. 工作树里的文件就提交

本次产出的文件在仓库工作树里就提交，不问；仓库外的不提、不问、不列进待办；被 `.gitignore` 排除的同样不问。提 PR 前跑 `git status --untracked-files=all`，`??` 逐个提交或说明来源。

理由：判据只看是不是本次产出、在不在工作树里，跟内容无关；这条命令列出来的才是全部候选。

判定：这个文件是本次产出的、并且在某个仓库的工作树里吗？

## 6. commit 用明确文件列表

commit 用明确的文件列表，禁用 `git add -A`、`git add <目录>`。commit 前扫一遍暂存区，不是本次产出的陌生文件 `git restore --staged`，在汇报里说明它的来源。

理由：工作树里可能有后台 agent 或测试留下的非源码文件。

判定：暂存区里每个文件都是打算提交的吗？

## 7. 中断的写操作先验证

被中断的写操作（`gh pr create`、push、写文件）恢复之后，先验证产物存在，再引用它；没验证的产物不拿去起后台监视，不写进文档。

理由：没验证的产物传下去，会把一个假前提扩散好几轮。

判定：这个产物亲眼验证过存在吗？

## 8. 归属判定用远端主分支

判「是不是本次引入」，先 `git fetch`，再用 `origin/main`；`git merge-base HEAD origin/main` 记下 hash，之后复用。判归属不用本地 `main`（它可能停在旧提交）。

理由：本地 `main` 停在上次碰它的时刻，别人合进去的提交会被整段算成本次的改动。

判定：命令里的主分支是 `origin/main` 吗？

## 9. 清场只处理自己建的

清场先问归属：这东西是谁建的、归谁？答不上，按不是自己的处理；归属确认之后，才问能不能删。分支名空间和 worktree 注册表是全仓共享的。`git worktree remove --force` 不用来绕过它的拒绝。进程按 [processes.md](processes.md) 清。

理由：「删了不丢数据」推不出「这是我的」；worktree 删除时的拒绝，是拦住别人还在用的东西的最后一关。

判定：这东西是谁建的？

## 10. 有 agent 读工作树时冻结它

有后台 agent 或对抗者在读工作树时，冻结工作树：不切分支，不 stash，不 rebase，不 build；要并行，就 `git worktree add` 另开目录。

理由：agent 读的是工作树，切走之后它整轮查的是错的代码，而且不会报错。

判定：现在有后台 agent 在读这个仓吗？
