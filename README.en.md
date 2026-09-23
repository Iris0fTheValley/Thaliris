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
Investigator / Curator / Reasoning Specialist / Implementer / Focused Implementer / Reviewer
    ├── private working set
    ├── optional detailed Artifact
    └── distilled result
            │
            ▼
        Controller
            └── decides the next handoff
```

The authorized parent's native spawn message is each role session's only task-specific
semantic input. `SubagentStart` validates authorization, identity, role, and
session and binds lifecycle and handoff metadata. It does not construct a context packet
nor returns task-specific `additionalContext`.

There is no production path from task state through a role projection into a
role session, and no hidden model auditor that corrects or blocks the Controller.

## Responsibilities

The Controller owns routing, context selection, interpretation, acceptance,
and completion. For ACTIVE and degraded work, it selects the minimum necessary
fresh roles; roles are capabilities, not mandatory stages. A straightforward,
bounded, low-risk task may use only a fresh Implementer, including bounded local
reading, implementation, and deterministic verification. Decision-changing
investigation belongs to Investigator. Reviewer, Curator, and Reasoning
Specialist are optional, and Reviewer is not a default gate.

Both Implementer and Focused Implementer execute implementation work. Keep the
working set focused. Delegate broad repository scanning, exhaustive call-site
search, residual-reference checks, and other large mechanical investigation to
the Scanner. Use Scanner output as evidence; retain responsibility for
implementation decisions. Investigator/Scanner compresses facts without making
architecture decisions. Reasoning Specialist reframes ill-defined problems,
not ordinary design or implementation. Verifier is a read-only compatibility
role and is not recommended as a workflow stage.

Controller has no fixed model, effort, or native profile; Host/user selection
applies. Investigator, Curator, and standard Implementer default to
`gpt-6-luna/xhigh`; Focused Implementer, Reasoning Specialist, and Reviewer to
`gpt-6-sol/high`; compatibility Verifier to `gpt-6-luna/xhigh`.
Only Controller may select static Astra medium or xhigh profiles before spawn
for exceptional reasoning. Those profiles map to the same stable role IDs. Per-spawn
model/effort overrides are denied.

An Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer keeps repository reads, searches, logs, tests, and
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
authorized bounded depth-two native Codex child lifecycle, handoff hashes, SubagentStart/Stop identity,
bounded missing-stop reconciliation, and native blocking waits. An automatic
long-wait normalization occurs only when a pending reservation or managed native Codex child
exists and a current-session effective maximum is mechanically verified;
otherwise the requested timeout is preserved without automatic expansion.

Only Implementer, Focused Implementer, and Reviewer may delegate one fresh
Investigator/Scanner. There is one active top-level role session and at most
one nested Scanner; its result belongs to its requesting parent. Exact parent
agent/session/turn/role identity is required, with missing/conflicting fields
denied. Grandchild Host hook identity remains UNKNOWN; scenario fixtures do
not prove live managed activation. Task-close still requires the latest
Controller-direct handoff's successful lifecycle and no pending or active
descendants.

## Mechanical stores

The task ledger accepts caller-authored records with identity, text,
producer, revision, source references, optional supersession, and descriptive
kind/status labels. Core validates schema and references but attaches no
semantic workflow to those labels.

Artifacts store an ID, producer, repo-relative path, content hash, created
revision, optional source references, and optional supersession. Core never
reads an Artifact body for automatic propagation. The Controller explicitly
retrieves it and selects any material for a later handoff.

Durable navigation uses `catalog` and explicit exact-path `document-get` only.
Legacy semantic metadata is opaque compatibility data, never search, display,
or routing authority.
SessionStart only points to the two root INDEX paths; it does not inject their
contents. Before starting managed work, the Controller explicitly reads the
root navigation and creates a minimal thin INDEX first if one is missing.
Navigation is not reread automatically during the task unless the map changed,
is insufficient, freshness is invalid, or resume/compact requires recovery.

Milestones are ordinary documents. Curator is an optional role session.
`task-promote` stores what the Controller explicitly selected without an
epistemic qualification gate.
When a promotion changes durable navigation, the Controller should provide its
own optional `index_update` in the same `task-promote` call. Core does not
generate INDEX content; it validates CAS, references, and the atomic commit.
If Codex explicitly reports a native spawn failure before `SubagentStart`, the
Controller may call `thaliris recover-pending-spawn HANDOFF_ID` for that exact
handoff; Core never infers failure from a missing event, timeout, or retry.

Freshness reports only `FRESH`, `CHANGED`, `MISSING`, or `UNKNOWN` file facts.
Verification stores command/tool, outcome, candidate identity, observed files,
timestamp, and result hash. Task surface stores before, after, and delta.
Neither verification nor surface attribution determines semantic completion.

## Commands

```text
thaliris init
thaliris task-start "goal"
thaliris task-status
thaliris task-update --role controller --base-revision N --input update.json
thaliris task-artifact --base-revision N --id A-001 --path path/to/file.md --summary "..."
thaliris task-promote --role controller --base-revision N --input promotion.json
thaliris task-close --base-revision N
thaliris recover-pending-spawn HANDOFF_ID
thaliris stale
thaliris rollback BACKUP_ID
thaliris doctor
```

## Benchmark boundary

`benchmarks/abcd/` may contain complex collectors, formal authority, and
offline scoring. The production `thaliris` package does not depend on D11,
formal registries, capture authority, or benchmark receipt issuers. Benchmarks
observe production; they do not define production architecture.

See [DESIGN.md](DESIGN.md) and
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md).
