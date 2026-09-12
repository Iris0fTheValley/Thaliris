# Thaliris Routing Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v2 -->

## Single semantic path

```text
Controller --explicit native handoff--> Child
Child --distilled result + optional Artifact pointer--> Controller
Controller --next explicit handoff--> next Child
```

The Controller is the sole task-specific semantic router. It chooses the Child,
task, facts, constraints, decisions, unknowns, and pointers to send. A missing
fact is a Controller/model error; Core must not infer or append it.

`SubagentStart` is lifecycle-only. It validates the authorized Child and binds
identity, role, session, start time, provenance, handoff ID, and payload hash.
It does not construct a role packet or inject task state.

## Private work and return

A Child may use a large private working set. Its default result is a concise
conclusion, key findings, decision-changing unknowns, contradictions,
verification performed, and optional Artifact references. The detailed working
set does not automatically re-enter the Controller.

When detailed material should survive, the Child writes a free-form Markdown or
JSON Artifact and returns its pointer. Registration records path and content
identity; it does not read, summarize, interpret, or propagate the body.

## Explicit retrieval

Artifact bodies and memory documents are available only through explicit
retrieval. Search results are candidates, never automatic context. A Controller
may copy selected retrieved content into a later native handoff.

## Mechanical observations

Freshness reports recorded versus current file identities. Verification reports
an observed invocation and result identity. Task surface reports baseline,
current state, and delta. The Controller decides what any observation means.

## Native boundary

The Host owns creation, execution, waiting, continuation, and result delivery.
The adapter owns fresh isolation, authorized serial lifecycle, identity binding,
and wait normalization for real pending dependencies. Core owns durable records,
CAS, atomicity, hashes, provenance, addressing, and explicit retrieval.

No hidden auditor, role projection, semantic dependency graph, correction state
machine, or benchmark authority participates in this production path.
