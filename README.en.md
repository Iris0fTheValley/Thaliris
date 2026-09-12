# Thaliris

Thaliris is a Git-native mechanical context and lifecycle layer. It does not
run agents and does not decide what is relevant, correct, or sufficient to
finish a task.

> Models own semantics. The mechanical layer executes model decisions.

## Production flow

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
            └── decides the next handoff
```

The Controller's native spawn message is the Child's only task-specific
semantic input. `SubagentStart` validates authorization, identity, role, and
session and binds lifecycle and handoff metadata. It neither calls `prepare`
nor returns task-specific `additionalContext`.

There is no production path from task state through a role projection into a
Child, and no hidden model auditor that corrects or blocks the Controller.

## Responsibilities

The Controller owns routing, context selection, interpretation, acceptance,
and completion. A Child keeps repository reads, searches, logs, tests, and
intermediate work private and normally returns only a distilled conclusion,
key findings, decision-changing unknowns, contradictions, verification, and
optional Artifact pointers.

Core provides identities, revisions and compare-and-swap, locking, atomic
writes and rollback, hashes, provenance, supersession history, objective file
freshness observations, mechanical verification and task-surface observations,
Artifact addressing, and explicit retrieval.

Core does not decide relevance, importance, correctness, role applicability,
task completion, or whether changed evidence invalidates a model conclusion.

The Codex adapter provides fresh spawn isolation, `fork_turns="none"`, an
authorized serial Child lifecycle, handoff hashes, SubagentStart/Stop identity,
bounded missing-stop reconciliation, and native blocking waits. A wait is
normalized only when a pending reservation or managed Child actually exists.

## Mechanical stores

The task ledger accepts Controller-authored records with identity, text,
producer, revision, source references, optional supersession, and descriptive
kind/status labels. Core validates schema and references but attaches no
semantic workflow to those labels.

Artifacts store an ID, producer, repo-relative path, content hash, created
revision, optional source references, and optional supersession. Core never
reads an Artifact body for automatic propagation. The Controller explicitly
retrieves it and selects any material for a later handoff.

Memory is explicit store/list/search/get. Search results are candidates.
Audience, Topics, Symbols, Applicability, Kind, Status, and Confidence are
model-authored search/display metadata, not propagation permissions.

Milestones are ordinary documents. Curator is an optional ordinary Child.
`task-promote` stores what the Controller explicitly selected without an
epistemic qualification gate.

Freshness reports only `FRESH`, `CHANGED`, `MISSING`, or `UNKNOWN` file facts.
Verification stores command/tool, outcome, candidate identity, observed files,
timestamp, and result hash. Task surface stores before, after, and delta.
Neither verification nor surface attribution determines semantic completion.

## Commands

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

`prepare --role <execution-role>` returns only a
`CONTROLLER_HANDOFF_ONLY` marker. It never reconstructs task context.

## Benchmark boundary

`benchmarks/abcd/` may contain complex collectors, formal authority, and
offline scoring. The production `thaliris` package does not depend on D11,
formal registries, capture authority, or benchmark receipt issuers. Benchmarks
observe production; they do not define production architecture.

See [DESIGN.md](DESIGN.md) and
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md).
