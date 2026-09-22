# Thaliris Routing Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v2 -->

## Single semantic path

```text
Controller --explicit native handoff--> Investigator / Curator / Reasoning Specialist / Implementer / Reviewer
Role session --distilled result + optional Artifact pointer--> Controller
Controller --next explicit handoff--> next selected role session
```

The Controller is the sole task-specific semantic router. It chooses the Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer,
task, facts, constraints, decisions, unknowns, and pointers to send. A missing
fact is a Controller/model error; Core must not infer or append it.

For every task, the Controller selects the minimum necessary fresh role
sessions, serially. Roles are capabilities, not mandatory workflow stages.
This policy is identical for ACTIVE and degraded work; degraded mode does not
define a second routing flow. A straightforward, bounded, low-risk task with
confirmed facts may take the Controller -> fresh Implementer -> done path: the
Implementer may do necessary bounded local reading, implementation, and
deterministic verification. Decision-changing investigation belongs to
Investigator. Bounded local reading needed for implementation may stay inside
Implementer. Reviewer is conditional, not a mechanical post-implementation gate;
select it only when independent semantic review adds real value, such as
for architecture or cross-module changes, lifecycle, Host, identity, or
authority boundaries, compatibility invariants, multiple plausible
implementations, complex semantic repairs, or remaining correctness
uncertainty. Curator and Reasoning Specialist are optional and selected only
when they add actual value.

`SubagentStart` is lifecycle-only. It validates the authorized native Codex child and binds
identity, role, session, start time, provenance, handoff ID, and payload hash.
It does not construct a role packet or inject task state.

## Private work and return

An Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer may use a large private working set. The default result is a concise
conclusion, key findings, decision-changing unknowns, contradictions,
verification performed, and optional Artifact references. The detailed working
set does not automatically re-enter the Controller.

When detailed material should survive, the selected role session writes a free-form Markdown or
JSON Artifact and returns its pointer. Registration records path and content
identity; it does not read, summarize, interpret, or propagate the body.

## Explicit retrieval

Artifact bodies and durable documents are available only through explicit
exact-path retrieval. `catalog` lists bounded metadata; `document-get` reads one to eight named paths. A Controller
may copy selected retrieved content into a later native handoff.

## Mechanical observations

Freshness reports recorded versus current file identities. Verification reports
an observed invocation and result identity. Task surface reports baseline,
current state, and delta. The Controller decides what any observation means.

## Native boundary

The Host owns creation, execution, waiting, continuation, and result delivery.
The adapter owns fresh isolation, authorized serial lifecycle, identity binding,
and wait normalization for real pending dependencies only when a current-session
effective maximum is mechanically verified; otherwise it performs no automatic
long-wait normalization. Core owns durable records,
CAS, atomicity, hashes, provenance, addressing, and explicit retrieval.

No hidden auditor, role projection, semantic dependency graph, correction state
machine, or benchmark authority participates in this production path.
