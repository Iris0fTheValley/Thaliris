# Thaliris

Thaliris 是一个 Git-native 的机械上下文与生命周期层。它不运行 Agent，
也不替模型判断什么重要、正确或足以完成任务。

> 模型负责语义。机械层负责执行。

0.4.2 runtime drift, current Host identity limits, and offline recovery:
[Runtime drift and recovery](docs/thaliris-runtime-recovery.md).

Persistent human task intent, reconnect recovery, explicit Controller-direct
and single-agent modes: [Task authority](docs/thaliris-task-authority.md).

## 生产信息流

```text
Controller
    │ explicit task + selected information
    ▼
selected role session
    ├── private working set
    ├── optional detailed Artifact
    └── distilled result
            │
            ▼
        Controller
            └── decides next handoff
```

授权父级的原生 spawn message 是各角色唯一的 task-specific 语义输入。
`SubagentStart` 只验证授权、身份、角色与 session，绑定 lifecycle 和 handoff
metadata；它不构建 task-specific `additionalContext`。

不存在以下生产路径：

```text
task state -> role projection -> automatic native Codex child injection
hidden model auditor -> Controller correction/block
```

## 职责

Controller 负责路由、上下文选择、解释、接受与完成判断。无论 ACTIVE 还是 degraded，
Controller 都只选择完成任务所需的最少 fresh roles；role 是认知分工，不是必经的
workflow stage。当前设计把主要认知负载分开：Controller 维持目标并选择上下文；
Investigator 承担大 working set、仓库扫描和事实压缩；Implementer 承担实现；
Reviewer 独立挑战结果。复杂实现可以使用更聚焦、更高能力的执行绑定，但实现决策仍由
执行角色负责。Reasoning Specialist 只在问题定义、抽象或前提本身不清楚时用于元认知
重构；Curator 用于把已选择材料压缩成可复用知识。兼容或专用 profile 可以存在，但
不构成 mandatory workflow。

Implementer 与 Focused Implementer 都负责实现，保持聚焦的 working set；
Investigator 可以拥有较大的私有 working set，将广泛扫描、调用点和残留引用
压缩成事实、位置、证据和未知项。执行角色利用这些证据，并保留实现决策权。
Reasoning Specialist 用于重构不明确的问题。Verifier 仅保留只读兼容，
不推荐作为流程阶段。Focused Implementer 负责语义收敛；当核心实现和不变量已落实、
会改变方向的未知已解决、证据能说明核心语义，而且剩余工作不太可能改变已定架构、因果模型、安全边界、
范围或验收时，可以带上候选状态、证据限制和剩余任务返回 FINAL。测试通过本身不会切换角色。
安装或 smoke 检查若仍用于证明核心语义，仍属于 Focused Implementer 的收敛工作。
Root 决定后续是否仍需 Focused reasoning，或可将独立且确定的收尾交给普通 Implementer。
小型直接常规操作无需仅为流程而建立子角色；这仍受既有执行模式约束。

Controller 的 model、effort、native profile 均无固定值，由 Host/用户选择。
Investigator、Curator 和标准 Implementer 默认 `gpt-6-luna/xhigh`；Focused
Implementer、Reasoning Specialist 和 Reviewer 默认 `gpt-6.1-sol/high`；兼容 Verifier
为 `gpt-6-luna/xhigh`。只有 Controller 可以在 spawn 前为特殊推理明确选择固定的
Astra medium 或 xhigh profile，但必须获得当前任务的用户授权；自动路由止于 Sol，
跨领域不确定性也不会自动启用 Astra。子角色不能自行选择 model/effort。
这些 profile 仍映射至相同 role ID；不允许
通过每次 spawn 的 model/effort 参数覆盖 profile。

所有 role session 保留私有中间工作，默认只返回精炼结论、关键发现、会改变
决策的未知、矛盾、验证与 Artifact pointer。

Core 只提供：

- task / native Codex child / handoff / artifact identity
- revision 与 compare-and-swap
- lock、atomic write、backup 与 rollback
- hash、provenance、supersedes/history
- 文件的 `FRESH` / `PARTIAL` / `RECORDED` / `CHANGED` / `MISSING` / `UNKNOWN` 客观事实
- verification 与 task surface 的机械 observation
- 显式 store / catalog / exact-path get

Core 不判断 relevance、importance、correctness、role applicability、task
completion，也不根据 stale evidence 自动改写 decision、constraint 或 workflow。

Codex adapter 只负责 fresh spawn、`fork_turns="none"`、授权的有限二层 native Codex child lifecycle、
handoff hash、SubagentStart/Stop identity、missing-stop reconciliation 和 native
wait。Controller 本身由 Host/user 当前选择的根 session 承载；child profile 的模型与
reasoning effort 由 adapter 的 role binding 管理。短 wait 只有在确实存在 pending
reservation 或 managed native Codex child，且当前 session effective maximum 已被机械验证时，
才会被规范化为长 blocking wait。当前 Host hook 尚未暴露该 maximum，因此会保留请求的
timeout，不会自动扩展。`SubagentStop` 本身不是成功；
只有明确观测到 native `Completed` 才满足 lifecycle completion。

Controller 可以选择注册角色；仅 Implementer、Focused Implementer 和 Reviewer
可以再委派一个 fresh Investigator/Scanner。最多一个顶层子角色与一个 Scanner
同时活动，Scanner 结果归请求它的父级。嵌套授权要求父级精确的 agent、role、
session、turn 身份，缺失或冲突即拒绝。一个 live managed Codex CLI
`0.155.0-alpha.9.2` probe 已验证二层 Scanner 的精确 reservation、Start 和绑定的
PreToolUse 接受，Scanner 结果已返回且 Focused parent 继续执行；详见
[durable probe evidence](docs/codex-nested-scanner-live-20260925.md)。该证据只覆盖这一个
CLI 构建与 probe；raw Host wire-byte equality、其他 Host 构建和其他 Desktop 场景仍为
UNKNOWN。另一次 2026-09-28 Codex Desktop probe 观察到 `list_agents` 返回精确 child name
和 native `completed` status；端到端 Desktop `task-close` 尚未观测。`task-close` 要求最后一个
Controller 直接 handoff 有匹配的 Start、Stop 和 native `Completed` observation，且没有
pending 或 active 后代。

## Task ledger

Task state 是一个带 revision 的机械账本。Controller 可以保存含 `id`、`kind`、
`text`、`producer`、`status`、`source_refs`、`supersedes` 的记录。`kind` 和
`status` 是模型写入的标签；Core 只验证 schema、identity 与引用完整性。

`task-close` 检查 task identity、revision、基本状态一致性，以及 adapter 的授权
lifecycle。它不判断测试是否充分，也不裁决任务语义上是否完成。

## Artifact、Memory 与 Milestone

Artifact 正文位于显式路径中；账本只保存 ID、producer、path、content hash、
created revision、source refs 与 optional supersedes。Artifact 不会被自动读取或
传播。Controller 显式取回正文，并自行选择是否交给后续被选中的 role session。

Memory 默认不注入。模型自行维护 `.agent-memory/INDEX.md` 和
`.milestones/INDEX.md` 里的薄语义导航地图，而不是单纯的文件清单。条目简要说明所链知识
涵盖什么、何时适合读取，以及在有帮助时说明当前或历史/已取代的适用范围；让当前相关知识
优先可见。Controller 读取描述后，选择要通过 `document-get` 明确恢复的文档。模型自行选择
目录、层级与措辞，不设固定格式或 taxonomy。Core 不解释、生成或重建 INDEX 内容，只做路径、
CAS、大小、链接与原子写入的机械检查。SessionStart 只提示两个 root INDEX 的路径，不注入
完整地图。开始 managed task 前，Controller 应显式读取 root navigation；若 INDEX 尚不存在，
先建立最小薄 INDEX 再开始 task。
任务进行中不会自动重复读取，除非地图已修改、信息不足、freshness 失效，或 resume/compact
需要恢复导航。
`document-get` 可一次读取最多 8 个由 Controller 明确给出的 path，并受总返回大小
限制；它不自动搜索、排序或补充文档。ACTIVE Controller 使用 bounded
`task-status` 和单对象 `task-get`；`init`、`uninstall`、`rollback`、再次
`task-start` 与完整 `task-show` 均不属于 ACTIVE allow-set。
`Status` 是有界的记录标签。旧文档中的其它 metadata 仍可读取，但只作为不透明兼容字段，
不是传播权限。

长期知识是否需要准入由 Controller 独自判断。正常任务进行中，Root 留意用户指令、自己的架构或治理
决策、Investigator 证据、Executor FINAL、Reviewer 发现和 Specialist 挑战中出现的可复用知识。这只是
Controller 当前工作上下文中的判断；不建立候选清单、持久准入状态、分数、计数器、阈值或额外检查点，
也不为记忆审查中断正在执行的 Workstream。Executor 返回正常结果、证据和会改变决策的信息，不追踪
记忆候选、不生成 Curator、不维护 durable INDEX 导航，也不在 FINAL 增加单独的长期治理内容。

接近任务自然结束时，Controller 在正常收尾中判断证据是否建立、修订、推翻或实质澄清了可复用的项目
知识，以及简明、有来源且容易检索的记忆条目是否能改善、约束或加快未来决策或恢复。这不限于未来
Agent 否则需要重新调查的知识。若选定的候选值得保留，Root 向新的 Curator 提供候选知识、事实与支撑
证据、精确相关的既有 memory 与 INDEX 导航，以及需要对照的规范来源和文档；没有候选或没有未来决策价值时则跳过。普通小任务可以完全
跳过 Curator；任务规模或架构工作本身不会触发必经阶段。

现有文档、源码、指令、测试、提交和 rollout 既不是自动排除理由，也不代表必须另建 memory；把它们当作
证据，并避免照抄规范文本。Memory 可以作为未来 Agent 的恢复入口，概述并链接容易找到的规范材料，或
压缩散落在代码、Host、历史和设计中的决策依据。Curator 应把选定候选与提供的资料对照；若既有知识
已经足够，应明确说明无需写入。添加、修订、合并、拆分、收窄、取代或删除选定 memory 时，Curator
也判断相关 INDEX 导航是否要更新，并在需要时更新。保留每条结论的来源和适用范围；新证据修订或取代旧结论时，在相关情况
下保留旧结论的历史适用性。任务时间线、实现日志、普通提交历史、临时测试输出或瞬时失败不应作为日志
保存；但如果它们能建立会改善、约束或加快未来决策或恢复的可复用知识，也不能自动排除。正式产品/协议
文档和 README 的行为同步由 Implementer 或 Focused Implementer 负责。详细原始证据保留在规范来源、
Artifact、Git 或 rollout 记录中；memory 只保留未来恢复所需的简明依据和引用。`CHANGED` 仅表示证据
变化；当依赖该证据的决策不再可靠时，Controller 可要求重新验证。Reviewer 被选用时检查文档与实现的
语义偏差。
`task-promote` 保存 Controller 明确选择的记录；Core 不裁决其 epistemic legitimacy。
当 Controller 通过 `task-promote` 写入会改变 durable navigation 的记录时，应在同一次
调用中提供 optional `index_update`。Curator 在单独整理 memory 时负责判断并维护相关导航。
Core 不生成 INDEX 内容，只机械验证路径、CAS、大小、链接并原子提交。
若 Codex 在 `SubagentStart` 前明确返回 native spawn failure，Controller 可针对
该 handoff 调用 `thaliris recover-pending-spawn HANDOFF_ID`；Core 不从缺失事件、超时或重试推测失败。

## Verification 与 task surface

Verification 记录 command/tool、outcome、candidate identity、observed files、
timestamp 与 result hash。Task surface 记录 start HEAD、dirty baseline、current
state 与 delta。两者都只提供事实，不成为 correctness、ownership 或 close gate。

## 命令

Git repository 中的 substantive work 应先运行已安装的
`thaliris-run.cmd --root <repo> codex-bootstrap`。若返回 READY，在同一 session
将返回的 bootstrap receipt 传给 `thaliris task-start "goal" --bootstrap-receipt <receipt> --authority-contract <json>`。
DEFINITION_READY_ACTOR_UNKNOWN 也可用此显式 Controller 操作建立任务意图；
Host Root 身份仍 UNKNOWN。外部授权保存 human instruction、boundary、invariants、
acceptance、execution_mode，断线重连无需重复 Root 证明。

```text
thaliris init
thaliris task-start "goal" --bootstrap-receipt <receipt> --authority-contract <json>
thaliris task-status
thaliris task-get OBJECT_ID
thaliris task-update --role controller --base-revision N --input update.json
thaliris task-artifact --base-revision N --id A-001 --path path/to/file.md --summary "..."
thaliris catalog
thaliris document-get .agent-memory/model-chosen/a.md .milestones/current/status.md
thaliris task-promote --role controller --base-revision N --input promotion.json
thaliris task-close --base-revision N
thaliris recover-pending-spawn HANDOFF_ID
thaliris task-recover-authority --expected-authority-sha256 <hash> --reason "recover interrupted work"
thaliris stale
thaliris rollback BACKUP_ID
thaliris doctor
```

`task-promote` 输入中的每条记录必须由 Controller 明确给出 `.agent-memory/**.md`
目标 path；Core 不按文档 metadata 自动分类。Controller 的 native handoff 是
被选中 role session 的唯一 task-specific 工作输入。

## Benchmark 边界

`benchmarks/abcd/` 可以包含复杂 collector、formal authority 与离线评分。
Production `thaliris` package 不依赖 D11、formal registry、capture authority 或
benchmark receipt issuer。Benchmark 观察 production；它不定义 production 架构。

完整契约见 [DESIGN.md](DESIGN.md) 与
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md)。
