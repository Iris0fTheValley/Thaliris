# Design

Thaliris Core is a deterministic, Git-native information topology layer. It
stores bounded task state and evidence, provides low-noise default projections
for semantic roles, and preserves useful material without automatically
propagating every working-set detail.

Its boundary is information routing: every Core invariant exists to help place
the correct, current, role-appropriate information in a reasoning context, not
to manage agents, schedules, or generic workflows.

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
never rewrite recorded history. Active constraints remain pinned even when their
provenance is stale, with `STALE_PROVENANCE` exposed in role projections.
Active decisions and contradictions with stale evidence receive
`REVALIDATION_REQUIRED`; unknowns remain open rather than being erased.

Schema-v1 state remains readable. Its anonymous semantic statements are mapped
deterministically to IDs on load and are persisted as v5 by the next
successful mutation or explicit `context migrate`; no resolve or supersession
relationship is inferred during that migration.

Schema-v2 `verification_evidence` is likewise retained for audit during the
v5 upgrade, but it remains ordinary model-authored evidence and cannot satisfy
a close gate. A v2 task with a verification target has no trustworthy
task-surface baseline to reconstruct, so it must be reconciled before closing
rather than being silently treated as verified.

## Verification And Artifacts

An artifact pointer records a SHA-256 content identity at registration. It is a
historical address even when the file later changes or disappears; projections
report whether the recorded identity is fresh, stale, missing, or legacy.

A task without a verification target can close with the existing CAS rule. A
task with a target requires a trusted, immutable execution result with outcome
`PASSED`; ordinary model-authored `test` or `runtime` evidence, including a
`passed` summary or a command-looking locator, cannot close a task. The Core
does not execute or independently prove arbitrary commands. A trusted runtime
adapter records an observed result through the adapter-only Core ingress; Core
then validates its native `source_refs`, outcome, freshness, and coverage.
Once set, a verification target cannot be removed or replaced by ordinary task
update.

Each new verification result is recorded only while a target exists and carries
a deterministic canonical fingerprint of that target plus its observation state
revision. Close accepts only a fresh `PASSED` result whose fingerprint equals
the current immutable target; Core does not infer target identity from a
summary, locator, or command text. Results created before v5 remain readable
but have no retroactively guessed `covered_surface`, so they cannot prove a
non-regular surface or close a targeted task. The v4-to-v5 migration preserves
their recorded facts and deliberately does not invent surface identities.

Task-start records the Git-visible dirty surface as a baseline. At close, an
explicit target, verification-target artifact bindings, declared changed surface, and new or
changed Git paths inside the modification boundary form the task-attributable
surface. A changed source or artifact makes the result stale. A new Git change
outside those signals cannot be safely attributed, so close fails with an
explicit reconciliation requirement rather than silently treating it as
verified. Unchanged dirty files present at task start remain baseline workspace
state and do not automatically become task work.

The v4 baseline records a task-start `HEAD` and distinguishes absent paths from
deleted files, regular-file content/mode, symlinks, and unsafe or special Git
paths without following a link. A Git-reported path is never silently skipped:
unsupported identity remains visible and fails attribution safely. Trusted
verification may bind deleted files and symlinks through Core-computed surface
identity; `SPECIAL`, `UNSAFE`, and legacy shapes require reconciliation rather
than receiving an invented content identity. When `HEAD`
changes, Core uses only the task-start-to-current Git interval to identify paths
that need attribution; it does not claim to distinguish concurrent human commits
from task commits automatically.

The runtime-neutral routing and evidence protocol is defined in
`docs/thaliris-routing-protocol.md`. Reusable evidence is registered before the
dependent decision, selected explicitly, and consumed by named downstream
roles. A stale artifact is never silently treated as current; append-only
replacement artifacts may explicitly supersede prior pointers. Review findings
carry a classification and bounded correction packet. Only architectural
findings can reopen broad investigation; mechanical and local semantic
findings receive a fresh targeted correction/review pair. Benchmark collection
and cost/evaluator thresholds belong to
`docs/thaliris-benchmark-protocol.md`; neither document creates a second
lifecycle runtime.

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

The model decides which retained facts are relevant to the next decision.
Thaliris bounds automatic propagation, not the size of an explicitly selected
handoff, and does not act as a semantic firewall that excludes an important
constraint merely because it originated in another role's working set.

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
