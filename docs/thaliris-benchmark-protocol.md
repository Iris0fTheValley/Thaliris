# Thaliris Benchmark Protocol

This document is the authoritative protocol for benchmark evidence, review
convergence, candidate identity, and fast-path accounting. Role packs and the
benchmark validator derive their required fields from these rules.

## Evidence lifecycle

Reusable evidence is required only when a result must cross a role boundary:

```text
need -> fresh Investigator -> bounded artifact -> Controller registration
     -> selected facts -> downstream consumer -> decision/implementation/review
```

The Controller registers the artifact pointer before the dependent decision with
`context task-artifact --base-revision N --id ID --path repo/relative
--summary TEXT --producer-role investigator` (or the corresponding curator role).
Registration computes the artifact content identity. An artifact record must
identify its producer role, task and revision,
repo-relative path and content SHA-256, source references, affected
files/symbols, confirmed facts, inferences, unknowns, contradictions, and
verification performed. Registration must precede the dependent decision.
Selection and every downstream consumer must be recorded.

The artifact pointer is selective access, not automatic full-text injection.
Content changes make the pointer stale. A replacement must explicitly name the
superseded artifact; stale or contradictory artifacts cannot remain silently
active. A fast path records `evidence_required=NOT_REQUIRED` when no reusable
cross-role evidence exists.

## Review convergence

Every fresh Reviewer returns either a bounded READY verdict or a bounded Review
Packet. A Review Packet contains:

```text
finding_id
classification = MECHANICAL | LOCAL_SEMANTIC | ARCHITECTURAL
affected_surface
violated_invariant
verification_requirement
```

MECHANICAL and LOCAL_SEMANTIC findings permit exactly one fresh Implementer
Correction Packet followed by exactly one fresh targeted Reviewer. The packet
contains only the finding, affected surface, invariant, and verification
requirement; it does not carry Reviewer conversation history. An
ARCHITECTURAL finding is the only classification that may reopen broad
investigation or reasoning. A source mutation after READY invalidates that
review and requires another fresh Reviewer. External interruption is
`EXTERNALLY_INCOMPLETE`, never PASS.

## Candidate and cost proof

The same immutable candidate identity must be recorded after the final source
mutation and attached to runtime production, final Reviewer, deterministic
verification, frozen evaluator, and seal. A later mutation invalidates the
chain.

Telemetry reports observed-all invocations, including failed or orphaned child
sessions. Cost uses model-specific uncached input (`input-cached_input`) plus
cached input and output; reasoning tokens are diagnostic only. Waiting is
reported separately from model-driven polling.

## Fast path

A simple task uses one fresh Implementer, deterministic verification, and no
Investigator, Sol, Curator, or Reviewer unless a recorded semantic risk,
ambiguity, or verification failure causes escalation. The result records the
routing, sessions, calls, cost, quality, evidence requirement, and escalation
reason.

## Documentation consistency

The benchmark validator checks that this document is referenced by generated
role-pack output and by the benchmark protocol tests. Runtime observations are
reported separately from supported behavior and host limitations.
