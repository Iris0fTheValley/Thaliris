# Thaliris Architecture

## Principle

**Models own semantics. The mechanical layer executes model decisions.**

Core is not a semantic decision engine. It does not decide relevance,
importance, correctness, role applicability, task completion, or whether changed
evidence invalidates a conclusion.

Core provides durable records, identities, revisions and compare-and-swap,
atomic writes and rollback, provenance, objective freshness observations,
Artifact addressing, task-surface observations, and explicit retrieval.

## Production information flow

```text
Controller
    │
    │ explicit task + selected information
    ▼
Investigator / Curator / Reasoning Specialist / Implementer / Reviewer
    │
    ├── private working set
    ├── optional detailed Artifact
    │
    └── distilled result
            │
            ▼
        Controller
            │
            └── decides the next handoff
```

The only adjacent mechanisms are the Task Ledger, Artifact Store, Explicit
Retrieval, and Native Lifecycle.

There is no production path from task state through a Core-generated role
projection into a role session. There is no hidden model auditor that corrects or
blocks the Controller.

## Responsibility boundaries

### Controller

The Controller selects the next Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer, writes the native handoff, chooses the
information in that handoff, interprets results and observations, accepts or
rejects conclusions, and decides when the task is complete.

Routing, categorizing, and status labels in task records are model-authored.
Core does not attach behavior to them.

### Role sessions

An Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer receives task-specific information only from the Controller's explicit
native spawn message. Repository reads, search results, test output, logs, and
intermediate exploration stay in its private working set.

The default return is a distilled result: conclusion, key findings,
decision-changing unknowns, contradictions if any, verification performed, and
optional Artifact references. These are prompt conventions, not Core schema
authority.

Curator is an optional ordinary role session. Reviewer classifications are ordinary
model output. Neither role activates a Core workflow state machine.

### Core

The task ledger stores bounded records with identity, model-authored kind and
status labels, text, producer, revision, source references, and optional
supersession references. Core validates schema and reference integrity only.

It does not implement semantic transitions such as resolve, reopen,
adjudicate, revalidation, correction routing, snapshot coverage, or epistemic
promotion.

### Codex adapter

The adapter handles fresh native spawn isolation, authorized serial native Codex child
lifecycle, handoff identity/hash binding, SubagentStart/Stop identity,
missing-stop reconciliation, Reviewer developer instructions plus an
obvious-write guard, and explicit blocking wait normalization. The current
stable Host does not provide an independent role-level read-only sandbox.

`SubagentStart` is lifecycle-only. It never constructs a context packet and never
returns task-specific `additionalContext`.

## Mechanical objects

### Handoff

The native spawn message carries the content. The adapter records only bounded
metadata such as handoff ID, task ID/revision, role, producer, payload hash, and
creation time. This proves which explicit handoff was bound to a native Codex child without
creating a second knowledge system.

### Artifact

An Artifact is external memory addressed by ID and repo-relative path. Its
record stores producer, task/revision identity, content hash, creation time,
source references, and optional supersession.

Core never reads an Artifact body for automatic propagation and never changes
workflow from its contents. The Controller explicitly retrieves any body and
selects any content placed in a later handoff.

Freshness is an objective observation: `FRESH`, `PARTIAL`, `RECORDED`,
`CHANGED`, `MISSING`, or `UNKNOWN`. It never mutates a task record or model
conclusion.

### Memory and milestones

Memory is explicit storage and retrieval. The model maintains the directory
tree and its canonical `.agent-memory/INDEX.md` and `.milestones/INDEX.md`
maps; Core imposes no taxonomy and does not recursively scan the filesystem to
derive another catalog. `document-get`
returns only 1–8 Controller-selected paths under one total response bound.
Status is a bounded record label. Legacy metadata is preserved as opaque
compatibility data, not propagation permissions or semantic gates.

SessionStart points Root only to the two root INDEX paths; it does not inject
their bodies. Before a managed task, the Controller explicitly reads that
navigation. The maps may point directly to deep leaves so normal retrieval
needs one explicit call; they do not select relevant content. ACTIVE Root
uses an explicit runtime-command allow-set, bounded `task-status`, and
single-object `task-get`; `init`, `uninstall`, `rollback`, another `task-start`,
and full `task-show` are blocked.

Milestones are ordinary long-lived documents. Core does not inject them into
role context or treat them as semantic authority.

`task-promote` stores exactly the Controller-selected record at the explicit
`.agent-memory/**.md` path chosen by the Controller, with identity and source
references. It does not classify by document metadata or decide whether
evidence makes that record legitimate. Models may create, edit, move, split,
merge, or delete durable documents through normal repository changes; INDEX
validation reports broken references without choosing a replacement.

### Verification and task surface

Verification records command/tool identity, outcome, candidate identity,
observed files, timestamp, and result hash. These are observations. Core does
not decide whether testing is sufficient and does not use verification as a
semantic task-close gate.

Task start records Git HEAD and dirty-surface identities. Later reads expose
before, after, and delta. Core does not attribute ownership or block close based
on that delta.

## Retained guarantees

- Git-native persistence
- task, native Codex child, handoff, and Artifact identity
- revision/CAS
- lock, atomic write, backup, and safe rollback
- Artifact content hash, provenance, history, and supersession references
- `fork_turns="none"` and fresh Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer lifecycles
- authorized serial spawn
- SubagentStart/Stop identity binding
- bounded missing-stop reconciliation
- explicit native blocking wait, only with a pending dependency
- explicit `catalog` and exact-path `document-get` retrieval and Artifact addressing
- Reviewer developer instruction and obvious-write guard
- mechanical candidate and task-surface identity
- adapter/hook/lifecycle diagnostics

## Benchmark boundary

`benchmarks/abcd/` may implement formal collectors, scoring, and offline
evaluation. Production `thaliris` does not import or provide D11 authority
registries, formal capture authority, or benchmark receipt issuers. Benchmark
requirements observe production behavior; they do not define production
architecture.
