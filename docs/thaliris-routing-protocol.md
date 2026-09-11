# Thaliris Routing and Evidence Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v1 -->

This document is the runtime-neutral product protocol for placing correct,
current information into the next reasoning context. Benchmark documents may
observe and score this protocol, but ordinary Thaliris tasks do not depend on
benchmark names, fixtures, cost thresholds, or a particular host.

## Task specification and evidence

The Task Specification is the user- or benchmark-supplied set of required
observable behavior, constraints, and compatibility requirements. Evidence is
current repository or runtime fact used to choose among compliant
implementations. If the specification requires behavior that is absent, the
state is an `IMPLEMENTATION_GAP` and the Reasoning Specialist returns a
bounded `DECISION`; it is not an `EvidenceRequest`.

`NEED_EVIDENCE` is reserved for an unresolved repository or runtime fact that
can change the choice between two or more compliant implementations. The
request is bounded and names the decision question, missing fact, why it can
change the choice, preferred evidence surface, and verification requirement.

## Reusable evidence

When evidence crosses a role boundary, the lifecycle is:

```text
need -> fresh Investigator -> bounded artifact -> Controller registration
     -> selected facts -> named consumer -> decision / implementation / review
```

An Evidence Artifact contains only bounded reusable facts, verifiable source
references, affected files or symbols, confirmed facts, inferences, unknowns,
contradictions, and verification performed. Its bytes receive a SHA-256
identity before the Controller registers the pointer. A pointer is selective
access; it is not automatic full-text injection.

Registration preserves an immutable historical pointer. If bytes change, that
pointer is stale. A replacement may append `supersedes: [artifact_id, ...]`;
the prior record is never rewritten. Supersession targets must exist, cannot
self-reference or form a cycle, and stale or superseded artifacts are not
current selected sources. A downstream handoff carries selected facts together
with enough artifact identity for provenance; a child final message is not the
evidence store.

## Role boundaries

The Controller selects bounded context and records accepted decisions and
constraints. Investigator working sets remain private. Sol makes one bounded
decision attempt and does not perform broad investigation. Implementers apply
an accepted modification boundary. A mechanical or local-semantic review
finding receives a fresh bounded correction Implementer and targeted fresh
Reviewer. An architectural finding returns to the Controller for a new
decision route; the Implementer never becomes a fallback Investigator.

Reviewers are fresh independent checkers for each candidate and are read-only
where the host provides that native boundary. Preserve findings, constraints,
candidate identities, and verification—not prior reasoning trajectories.
Review is also a synchronization point for the candidate: no concurrent
candidate-writing managed role may overlap an accepted review. A verdict is
valid only when the host-computed candidate identity is unchanged from
review-start through review completion. Native read-only isolation is used
where the host provides it as defense in depth, not as the sole correctness
mechanism.

## Runtime boundary

Thaliris controls information ingress and persistence only. The host runtime
owns child creation, waiting, continuation, closing, and scheduling. When a
host has no surviving-child continuation surface, one sufficiently long native
blocking wait per real dependency is valid; short model-driven polling loops
are not.
