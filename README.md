# Thaliris

Thaliris 是一个 Git-native 的机械上下文与生命周期层。它不运行 Agent，
也不替模型判断什么重要、正确或足以完成任务。

> 模型负责语义。机械层负责执行。

## 生产信息流

```text
Controller
    │ explicit task + selected information
    ▼
Child
    ├── private working set
    ├── optional detailed Artifact
    └── distilled result
            │
            ▼
        Controller
            └── decides next handoff
```

Controller 的原生 spawn message 是 Child 唯一的 task-specific 语义输入。
`SubagentStart` 只验证授权、身份、角色与 session，绑定 lifecycle 和 handoff
metadata；它不调用 `prepare`，也不返回 task-specific `additionalContext`。

不存在以下生产路径：

```text
task state -> role projection -> automatic child injection
hidden model auditor -> Controller correction/block
```

## 职责

Controller 负责路由、上下文选择、解释、接受与完成判断。Child 在私有 working
set 中调查、实现或审查，默认只返回精炼结论、关键发现、会改变决策的未知、
矛盾、验证与 Artifact pointer。

Core 只提供：

- task / child / handoff / artifact identity
- revision 与 compare-and-swap
- lock、atomic write、backup 与 rollback
- hash、provenance、supersedes/history
- 文件的 `FRESH` / `CHANGED` / `MISSING` / `UNKNOWN` 客观事实
- verification 与 task surface 的机械 observation
- 显式 store / list / search / get

Core 不判断 relevance、importance、correctness、role applicability、task
completion，也不根据 stale evidence 自动改写 decision、constraint 或 workflow。

Codex adapter 只负责 fresh spawn、`fork_turns="none"`、授权的串行 Child、
handoff hash、SubagentStart/Stop identity、missing-stop reconciliation 和 native
wait。只有确实存在 pending reservation 或 managed Child 时，短 wait 才会被规范化
为 Host 支持的长 blocking wait。

## Task ledger

Task state 是一个带 revision 的机械账本。Controller 可以保存含 `id`、`kind`、
`text`、`producer`、`status`、`source_refs`、`supersedes` 的记录。`kind` 和
`status` 是模型写入的标签；Core 只验证 schema、identity 与引用完整性。

`task-close` 检查 task identity、revision、基本状态一致性，以及 adapter 的授权
lifecycle。它不判断测试是否充分，也不裁决任务语义上是否完成。

## Artifact、Memory 与 Milestone

Artifact 正文位于显式路径中；账本只保存 ID、producer、path、content hash、
created revision、source refs 与 optional supersedes。Artifact 不会被自动读取或
传播。Controller 显式取回正文，并自行选择是否交给下一个 Child。

Memory 默认不注入。`recall` 只返回搜索候选，`memory-get` 才取回一篇选定正文。
Audience、Topics、Symbols、Applicability、Kind、Status 与 Confidence 仅是模型写入
的搜索或展示 metadata，不是传播权限。

Milestone 是普通长期文档。Curator 是普通可选 Child。`task-promote` 保存
Controller 明确选择的记录；Core 不裁决其 epistemic legitimacy。

## Verification 与 task surface

Verification 记录 command/tool、outcome、candidate identity、observed files、
timestamp 与 result hash。Task surface 记录 start HEAD、dirty baseline、current
state 与 delta。两者都只提供事实，不成为 correctness、ownership 或 close gate。

## 命令

```text
context init
context task-start "goal"
context task-status
context task-update --role controller --base-revision N --input update.json
context task-artifact --base-revision N --id A-001 --path path/to/file.md --summary "..."
context recall "query" --role controller
context memory-get memory/path.md
context task-promote --role controller --base-revision N --input promotion.json
context task-close --base-revision N
context stale
context rollback BACKUP_ID
context doctor
```

`prepare --role <execution-role>` 只返回 `CONTROLLER_HANDOFF_ONLY` 标记，不重建
task context。

## Benchmark 边界

`benchmarks/abcd/` 可以包含复杂 collector、formal authority 与离线评分。
Production `thaliris` package 不依赖 D11、formal registry、capture authority 或
benchmark receipt issuer。Benchmark 观察 production；它不定义 production 架构。

完整契约见 [DESIGN.md](DESIGN.md) 与
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md)。
