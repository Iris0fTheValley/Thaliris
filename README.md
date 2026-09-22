# Thaliris

Thaliris 是一个 Git-native 的机械上下文与生命周期层。它不运行 Agent，
也不替模型判断什么重要、正确或足以完成任务。

> 模型负责语义。机械层负责执行。

## 生产信息流

```text
Controller
    │ explicit task + selected information
    ▼
Investigator / Curator / Reasoning Specialist / Implementer / Reviewer
    ├── private working set
    ├── optional detailed Artifact
    └── distilled result
            │
            ▼
        Controller
            └── decides next handoff
```

Controller 的原生 spawn message 是 Investigator、Curator、Reasoning Specialist、Implementer 与 Reviewer 唯一的 task-specific 语义输入。
`SubagentStart` 只验证授权、身份、角色与 session，绑定 lifecycle 和 handoff
metadata；它不构建 task-specific `additionalContext`。

不存在以下生产路径：

```text
task state -> role projection -> automatic native Codex child injection
hidden model auditor -> Controller correction/block
```

## 职责

Controller 负责路由、上下文选择、解释、接受与完成判断。无论 ACTIVE 还是 degraded，
Controller 都只选择完成任务所需的最少 fresh roles；role 是 capability，不是必经的
workflow stage。简单、明确、低风险的任务可以只经过 fresh Implementer，由它完成有界
本地阅读、实现和确定性验证。只有会改变实现方向的调查才交给 Investigator；Reviewer、
Curator 和 Reasoning Specialist 均按需使用，Reviewer 不是默认 gate。

Investigator、Curator、Reasoning Specialist、Implementer 与 Reviewer 在私有 working
set 中调查、实现或审查，默认只返回精炼结论、关键发现、会改变决策的未知、
矛盾、验证与 Artifact pointer。

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

Codex adapter 只负责 fresh spawn、`fork_turns="none"`、授权的串行 native Codex child lifecycle、
handoff hash、SubagentStart/Stop identity、missing-stop reconciliation 和 native
wait。只有确实存在 pending reservation 或 managed native Codex child、且当前 session effective
maximum 已被机械验证时，短 wait 才会被规范化为长 blocking wait；否则不会自动规范化。
`SubagentStop` 本身不是成功；只有明确观测到
native `Completed` 才满足 lifecycle completion。

## Task ledger

Task state 是一个带 revision 的机械账本。Controller 可以保存含 `id`、`kind`、
`text`、`producer`、`status`、`source_refs`、`supersedes` 的记录。`kind` 和
`status` 是模型写入的标签；Core 只验证 schema、identity 与引用完整性。

`task-close` 检查 task identity、revision、基本状态一致性，以及 adapter 的授权
lifecycle。它不判断测试是否充分，也不裁决任务语义上是否完成。

## Artifact、Memory 与 Milestone

Artifact 正文位于显式路径中；账本只保存 ID、producer、path、content hash、
created revision、source refs 与 optional supersedes。Artifact 不会被自动读取或
传播。Controller 显式取回正文，并自行选择是否交给下一个 Investigator、Curator、Reasoning Specialist、Implementer 或 Reviewer。

Memory 默认不注入。模型自行维护 `.agent-memory/INDEX.md` 和
`.milestones/INDEX.md` 里的薄全局树状地图，并自行决定目录、层级、移动、合并与
删除；Core 不递归扫描文件系统来重建第二套 catalog，也不规定 taxonomy。SessionStart
只提示两个 root INDEX 的路径，不注入完整地图。开始 managed task 前，Controller
应显式读取 root navigation；若 INDEX 尚不存在，先建立最小薄 INDEX 再开始 task。
任务进行中不会自动重复读取，除非地图已修改、信息不足、freshness 失效，或 resume/compact
需要恢复导航。
`document-get` 可一次读取最多 8 个由 Controller 明确给出的 path，并受总返回大小
限制；它不自动搜索、排序或补充文档。ACTIVE Controller 使用 bounded
`task-status` 和单对象 `task-get`；`init`、`uninstall`、`rollback`、再次
`task-start` 与完整 `task-show` 均不属于 ACTIVE allow-set。
`Status` 是有界的记录标签。旧文档中的其它 metadata 仍可读取，但只作为不透明兼容字段，
不是传播权限。

Milestone 是普通长期文档。Curator 是普通可选角色。`task-promote` 保存
Controller 明确选择的记录；Core 不裁决其 epistemic legitimacy。
当一次 promotion 会改变 durable navigation 时，Controller 应在同一次
`task-promote` 中提供自己写好的 optional `index_update`。Core 不生成 INDEX
内容，只验证 CAS、引用和原子提交。
若 Codex 在 `SubagentStart` 前明确返回 native spawn failure，Controller 可针对
该 handoff 调用 `thaliris recover-pending-spawn HANDOFF_ID`；Core 不从缺失事件、超时或重试推测失败。

## Verification 与 task surface

Verification 记录 command/tool、outcome、candidate identity、observed files、
timestamp 与 result hash。Task surface 记录 start HEAD、dirty baseline、current
state 与 delta。两者都只提供事实，不成为 correctness、ownership 或 close gate。

## 命令

```text
thaliris init
thaliris task-start "goal"
thaliris task-status
thaliris task-get OBJECT_ID
thaliris task-update --role controller --base-revision N --input update.json
thaliris task-artifact --base-revision N --id A-001 --path path/to/file.md --summary "..."
thaliris catalog
thaliris document-get .agent-memory/model-chosen/a.md .milestones/current/status.md
thaliris task-promote --role controller --base-revision N --input promotion.json
thaliris task-close --base-revision N
thaliris recover-pending-spawn HANDOFF_ID
thaliris stale
thaliris rollback BACKUP_ID
thaliris doctor
```

`task-promote` 输入中的每条记录必须由 Controller 明确给出 `.agent-memory/**.md`
目标 path；Core 不按文档 metadata 自动分类。Controller 的 native handoff 是
Investigator、Curator、Reasoning Specialist、Implementer 与 Reviewer 的唯一工作输入。

## Benchmark 边界

`benchmarks/abcd/` 可以包含复杂 collector、formal authority 与离线评分。
Production `thaliris` package 不依赖 D11、formal registry、capture authority 或
benchmark receipt issuer。Benchmark 观察 production；它不定义 production 架构。

完整契约见 [DESIGN.md](DESIGN.md) 与
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md)。
