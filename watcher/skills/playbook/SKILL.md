---
name: playbook
description: >
  分步工作方法 — 协作规范 3.3.5 指向的那份参考。协作规范管每轮都适用的流程和决策；
  这里放只在某一步才用得上的做法，每步一份参考文件。
  做下列事之前，先读对应那一份：调研与选型、拿实测读数或会变的状态（PR、CI、进程、端口）
  当证据或汇报、跨仓操作；写拍板表、汇报问题、写范围断言或概括原文、建任务清单、会话压缩之后；
  写设计、定方案和验收结果、
  demo 转实现；派对抗者或 agent 写 prompt、核实对抗返回、写修复方案；定类、准备加防护；
  同步文档、做删除或改名类清理、提 PR 前；写或核测试、批量替换、挑 smoke；起进程、造负载、
  清进程；commit、push、开或更新 PR、中断恢复、判是否本次引入、清场、派出 agent 之后。
  用户也可以手动输入 `/watcher:playbook`。
---

# Playbook — 分步工作方法

协作规范定流程和裁决，这里按步骤补做法；两者冲突时以协作规范为准。

只写流程和决策逻辑。语言、shell、操作系统、框架、具体命令和 API 写在项目的 `AGENTS.md` 或项目 skill 里。

用语沿用协作规范 1.1.2：「我」指决策人，「你」指执行方。每条是一句规则、一句理由，多数带一句判定题。

到了哪一步就只读那一份：

| 文件 | 什么时候读 |
|---|---|
| [references/research.md](references/research.md) | 查业界做法、选第三方库、拿实测读数或状态当证据、跨仓操作之前 |
| [references/decisions.md](references/decisions.md) | 写拍板表或「需要确认的是」、汇报问题、写范围断言、概括原文、建任务清单、会话压缩之后 |
| [references/design-demo.md](references/design-demo.md) | 写设计文档、设计涉及状态流转、定方案和验收结果、demo 转实现和收尾比对时 |
| [references/adversary-review.md](references/adversary-review.md) | 收到任何对抗 workflow 结果、核实返回、写修复方案、写对抗或 workflow prompt 时 |
| [references/classification.md](references/classification.md) | 给返回或问题定级定类、判做不做、准备加防护时 |
| [references/doc-sync.md](references/doc-sync.md) | 同步文档、做删除或改名类清理、文案对抗和提 PR 前、写说明性文档时 |
| [references/testing.md](references/testing.md) | 写或核守卫类测试、定测试范围、批量替换、挑受影响范围验证的 smoke/E2E、跑全量测试时 |
| [references/processes.md](references/processes.md) | 起开发服务或长活进程、造负载、起临时后台进程、清进程时 |
| [references/git-pr.md](references/git-pr.md) | commit、push、开或更新 PR、中断恢复、判是否本次引入、清场、派出 agent 之后 |
