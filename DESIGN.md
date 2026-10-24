# Thaliris Architecture

## Principle

**Models own semantics. The mechanical layer executes model decisions.**

Core is not a semantic decision engine. It does not decide relevance,
importance, correctness, role applicability, task completion, or whether changed
evidence invalidates a conclusion.

Core provides durable records, identities, revisions and compare-and-swap,
atomic writes and rollback, provenance, objective freshness observations,
Artifact addressing, task-surface observations, and explicit retrieval.

The Codex adapter also preserves explicitly selected human task intent in an
external governance anchor. Root identity and human prompt authorship remain
UNKNOWN; explicit task selection is a semantic Controller decision, not a
UserPromptSubmit inference. Continuation survives session/daemon interruption.
Known children, readonly and fenced actors cannot alter authority. Explicit
Controller-direct and single-agent modes override the default role split;
absent an explicit override, existing routing remains. See
[Persistent task authority](docs/thaliris-task-authority.md) for the contract,
recovery, security baseline and shared-OS limitations.

## Production information flow

```text
Controller
    │
    │ explicit task + selected information
    ▼
Investigator / Curator / Reasoning Specialist / Implementer / Focused Implementer / Reviewer
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

For every task, whether ACTIVE or degraded, the Controller selects the minimum
necessary fresh roles. Roles are capabilities, not mandatory workflow stages.
A straightforward, bounded, low-risk task with confirmed facts may go from the
Controller directly to a fresh Implementer and then finish. The Implementer may
perform bounded local reading, implementation, and deterministic verification.
Decision-changing investigation belongs to Investigator; Reviewer, Curator,
and Reasoning Specialist are selected only when they add real value, and
Reviewer is not a default gate.

Implementer and Focused Implementer own implementation decisions and focused
working sets. They and Reviewer may delegate broad mechanical investigation
to Investigator/Scanner, at maximum managed depth two with one active Scanner.
Scanner results belong to the requesting parent; architecture decisions stay
with the Executor/Controller. Reasoning Specialist reframes ill-defined
problems. Verifier is read-only compatibility, not a recommended stage.

The Controller writes each native handoff, chooses the information in that
handoff, interprets results and observations, accepts or rejects conclusions,
and decides when the task is complete.

An INVALID_STATE task state degrades the mechanical guard to a strict
blacklist: it denies direct, recognized Controller-owned Thaliris task and
lifecycle mutations and obvious writes to `.context/state.json` or lifecycle
state. Unknown tools, coordination, diagnostics, and reads remain transparent.
This does not prove managed enforcement. Damaged managed state does not
transfer Investigator or Implementer duties to Root. If those roles are
unavailable, Root may diagnose the managed failure, read the evidence needed
for that diagnosis, coordinate, and report; it does not take over substantial
repository investigation, implementation, or testing.

Routing, categorizing, and status labels in task records are model-authored.
Core does not attach behavior to them.

### Role sessions

Each role session receives task-specific information only from its authorized parent's explicit
native spawn message. Repository reads, search results, test output, logs, and
intermediate exploration stay in its private working set.

The default return is a distilled result: conclusion, key findings,
decision-changing unknowns, contradictions if any, verification performed, and
optional Artifact references. These are prompt conventions, not Core schema
authority.

Exact parent agent/session/turn/role identity authorizes the unique nested
reservation. The matching Start binds the Scanner's own identity. One live
managed Codex CLI `0.155.0-alpha.9.2` probe verified that reservation, Start,
and bound Scanner PreToolUse acceptance at depth two; the Scanner result
returned and the Focused parent continued. See the [durable probe evidence](docs/codex-nested-scanner-live-20260925.md).
This scoped probe does not establish raw Host wire-byte equality, behavior on
other Host builds or Desktop scenarios, or native child `Completed`/`task-close`
completion; those remain UNKNOWN. Missing or conflicting identity still fails
closed. The flat lifecycle ledger remains bounded, not an arbitrary tree.
Task-close selects the last Controller-direct handoff and rejects pending or
active descendants. Stable role and historical producer IDs do not change.

Curator is an optional ordinary role session. Reviewer classifications are ordinary
model output. Neither role activates a Core workflow state machine.

### Core

The task ledger stores bounded records with identity, model-authored kind and
status labels, text, producer, revision, source references, and optional
supersession references. Core validates schema and reference integrity only.

It does not implement semantic transitions such as resolve, reopen,
adjudicate, revalidation, correction routing, snapshot coverage, or epistemic
promotion.

Mechanical round-trip support (Core 0.5.1) keeps strict revision CAS while
making each refusal actionable and each response small:

- Failures raise `ThalirisError`, a `ValueError` with a stable UPPER_SNAKE
  `code`, a short mechanical `recovery` hint and bounded `details`; `str(exc)`
  keeps the historical message text. The CLI adds `code`, `recovery` and
  `details` beside `error`.
- `TASK_REVISION_CONFLICT` carries `base_revision`, `current_revision` and a
  bounded `changes_since` review hint. It is deliberately not an exact delta:
  persisted state gains no new fields, because states written by Core 0.5.1
  must stay valid for Core 0.5.0 (several Hosts may share one `.context`
  during rollout or after a downgrade), and 0.5.0 rejects unknown fields on
  continuity objects. The hint is `{base_revision, current_revision,
  revision_gap, exact: false, records, recent, evidence}`: `records` are the
  ids of records whose stored revision is above the base; `recent` holds the
  last k handoff ids, observation `{id, handoff_id, requirement_refs}` and
  judgment `{id, requirement_ref, outcome}` entries with
  k = min(revision_gap, 16), and may include items older than the base;
  `evidence` is the open-evidence summary (unincorporated observations and
  unresolved judgments: totals plus bounded items, paged by `next_offset`),
  which is what the Controller must review before retrying. Nothing is
  rebased or merged.
- `task-judge` accepts one judgment or `{"judgments": [...]}`; observation
  writes accept one observation or `{"observations": [...]}`. A batch
  validates all-or-nothing, keeps list order and costs one revision.
- `task-status --view compact` returns the routing header, counts, Active Work,
  Pending Results, recent artifact ids and a compact evidence summary (totals
  always, open items paged within a byte budget); `--since-revision N` adds the
  same bounded, non-exact `changes_since` hint under `Changes Since`. The default full view is unchanged. Continuity writes accept
  `--compact-evidence` to return the same summary instead of a status re-read.
- Task ids for continuity objects remain opaque and unique per task; adapters
  namespace child-chosen ids (for example `<handoff>.<id>`). A collision is
  refused as `CONTINUITY_ID_COLLISION` with a suggested qualified id.
- Input JSON is read as UTF-8, UTF-8 with BOM or UTF-16 with BOM; Git output is
  decoded as UTF-8 independent of the console code page.

### Host adapters

[Codex](https://github.com/Iris0fTheValley/Thaliris-Codex) and
[DSH](https://github.com/Iris0fTheValley/Thaliris-DSH) are separate adapters over
the shared `thaliris.core` and `thaliris.authority` APIs. Native bootstrap,
lifecycle, trust, model profiles and actor identity belong to their Host. Main
ships the neutral ledger, retrieval, evidence and authority machinery, shared
semantic guidance, and benchmark protocol and historical evidence.

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

The `task-promote` input creates only new Markdown documents and refuses to
overwrite an existing target. It may also update an existing `INDEX.md` under
`.agent-memory/` or `.milestones/`, including nested namespaces. Each INDEX
update supplies the complete content and its `base_sha256`; Core checks the
baseline, size, and link references, then writes it through the backup path in
the same transaction as the new documents. Each document's `source_refs` may
cite only evidence or artifacts already recorded in the selected Task ID.
Promotion uses task-revision CAS and does not advance that revision. Core does
not impose semantic categories, evidence freshness or `CONFIRMED` thresholds,
promotion quotas, or milestone fields.

### Verification and task surface

Verification records command/tool identity, outcome, candidate identity,
observed files, timestamp, and result hash. These are observations. Core does
not decide whether testing is sufficient and does not use verification as a
semantic task-close gate.

Task start records Git HEAD and dirty-surface identities. Later reads expose
before, after, and delta. Core does not attribute ownership or block close based
on that delta.

### Project identity

The repository-tracked `.project-identity/` namespace holds one project-level,
cross-task baseline: what the project is for and what must not change silently.
It is versioned (v1, v2, …) and changes only through an immutable amendment that
records the human owner's decision as asserted by its caller. Challenges record
evidence against identity; typed purpose relations (`serves`, `supports`,
`challenges`, `supersedes`) record why significant decisions exist. All are
append-only files; resolution and retraction are new files.

Core records, versions, validates ref syntax and existence at registration,
enforces task-revision and baseline compare-and-swap, writes under the lock
through backup and atomic write (the ledger is the commit point), observes `UNRECORDED_CHANGE` and
`INVALID`, and returns bounded content with canonical (LF-normalized) hashes. It
does not decide layers, challenge validity, amendment wisdom, affected scope or
revalidation; nothing propagates or is injected, and absent identity changes no
existing behavior. Identity mutations do not bump task revision, do not alter
Task Authority, and are refused by `rollback`. Reading Core's own bounded
`challenges/` and `relations/` directories is not a corpus scan. Legacy memory
metadata confers no identity authority. See
[Project identity](docs/thaliris-project-identity.md).

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
