# Design

Thaliris Core is a deterministic, Git-native information topology layer. It
stores bounded task state and evidence, provides low-noise default projections
for semantic roles, and preserves useful material without automatically
propagating every working-set detail.

## Core Responsibilities

- task state with revision-checked CAS and atomic recovery;
- bounded Controller packets;
- semantic role projections for controller, investigator, curator,
  reasoning-specialist, implementer, and reviewer;
- evidence confidence and freshness;
- external artifact pointers whose contents are never implicitly projected;
- project memory and milestone routing;
- explicit durable promotion with bounded persistent records;
- Git truth for changed surface and deterministic verification.

## Semantic State

Task semantic records use stable identities. Constraints, unknowns,
contradictions, and decisions are retained as historical records rather than
replaceable anonymous statement lists. Ordinary task updates cannot replace
those collections. The Controller may propose only a small Core-validated
transition vocabulary: `add`, `resolve`, `reopen`, `adjudicate`, and
`supersede`.

- constraints stay active until an explicit resolve transition;
- unknowns stay open until resolve and may be explicitly reopened;
- contradictions stay open until resolve or adjudicate;
- decisions stay active until an explicit supersession, which links the prior
  decision to its replacement without deleting either identity.

Raw investigation and review findings remain append-only. Curator snapshots
remain derived from raw findings, retain `supersedes` provenance, and cannot
promote epistemic status. Effective projections may demote stale evidence but
never rewrite recorded history.

Schema-v1 state remains readable. Its anonymous semantic statements are mapped
deterministically to v2 IDs on load and are persisted as v2 by the next
successful mutation or explicit `context migrate`; no resolve or supersession
relationship is inferred during that migration.

## Verification And Artifacts

An artifact pointer records a SHA-256 content identity at registration. It is a
historical address even when the file later changes or disappears; projections
report whether the recorded identity is fresh, stale, missing, or legacy.

A task without a verification target can close with the existing CAS rule. A
task with a target can close only when selected `test` or `runtime` evidence is
fresh and its existing native `source_refs` cover every explicitly bound
artifact or changed-surface path. A changed source or artifact makes that
evidence ineffective automatically. Verification descriptions and command-like
text are requirements only; they grant no execution authority and a bare model
claim is never sufficient evidence.

Working set is not handoff set. Retention is not propagation. Availability is
not injection. A Controller packet contains task identity, active work, pending
results, unresolved questions, accepted constraints and decisions, modification
boundary, verification target, and artifact pointers. Retained parent history,
child transcripts, raw findings, evidence registries, logs, tool output, memory
bodies, and artifact contents do not cross a role boundary automatically. They
remain retained or externally addressable until a model explicitly selects what
the next role needs.

Durable memory has three distinct stages: retention keeps evidence-backed memory
available; retrieval occurs only when a model explicitly invokes `context recall`;
and propagation occurs only when the model explicitly selects information for
task state or a role handoff. Recall returns routed candidates rather than
accepted facts, and never writes task state.

The model decides which retained facts are relevant to the next decision.
Thaliris constrains propagation paths, not the size or meaning of information a
model explicitly chooses to send. A large selected payload is valid when it is
needed for correctness. Core bounds protect persistent state, snapshots,
packets, promotion records, and other storage structures; they are storage
invariants, not a semantic payload quota or a handoff-size limit. Artifact
pointers provide selective access, not a mandatory compression rule.

## Runtime Boundary

Core does not execute agents or define a concrete runtime's lifecycle, child
creation, hooks, transport, or session semantics. Runtime adapters map these
projections to native mechanisms without redefining Core state or role meaning.

## Persistence

The task whiteboard remains `.context/state.json`. Artifact registration is
explicit and path-safe; registration validates an existing repository-local
regular file, while later disappearance does not invalidate task state. Durable
promotion is explicit, evidence-backed, bounded, and CAS-protected. Core
mutations use one lock, one coherent backup, atomic replacement, and guarded
rollback.
