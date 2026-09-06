# Design

Thaliris Core is a deterministic, Git-native information topology layer. It
stores bounded task state and evidence, projects the right facts to each
semantic role, and preserves useful material without automatically propagating
every working-set detail.

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

Working set is not handoff set. Retention is not propagation. Availability is
not injection. A Controller packet contains task identity, active work, pending
results, unresolved questions, accepted constraints and decisions, modification
boundary, verification target, and artifact pointers. Retained parent history,
child transcripts, raw findings, evidence registries, logs, tool output, memory
bodies, and artifact contents do not cross a role boundary automatically. They
remain retained or externally addressable until a model explicitly selects what
the next role needs.

The model decides which retained facts are relevant to the next decision.
Thaliris constrains propagation paths, not the size or meaning of information a
model explicitly chooses to send. A large selected payload is valid when it is
needed for correctness. Core bounds protect persistent state, snapshots,
packets, promotion records, and other storage structures; they are storage
invariants, not a semantic payload quota or a handoff-size limit. Artifact
pointers provide selective access, not a mandatory compression rule.

The model decides which retained facts are relevant to the next decision.
Thaliris bounds the amount and automatic propagation of a handoff, but does not
act as a semantic firewall that excludes an important constraint merely because
it originated in another role's working set.

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
