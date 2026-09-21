<!-- thaliris:begin -->
## Thaliris Router

Codex is the runtime. Thaliris provides durable records, identities, revisions,
hashes, provenance, objective freshness observations, explicit retrieval, and
native lifecycle binding. It is not a semantic decision engine.

The Controller is the sole task-specific semantic router. Fresh Investigator,
Curator, Reasoning Specialist, Implementer, and Reviewer sessions use `fork_turns="none"`
and receive their tasks plus selected information in
the Controller's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter an Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer automatically.

Persistent root Controller default: `gpt-5.6-sol` with `xhigh` reasoning. This
is root instruction metadata, not a native Codex child profile and does not
change a current task model automatically.

An implementation handoff states Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Decisions, invariants, and
acceptance are contract; recommendations/advice are not. An unknown that can
change direction cannot be silently dropped, guessed, or frozen: prove Host
protocol, serialization, identity, and native-schema contracts first.

Each Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer keeps
its private working set private. By default it returns a distilled conclusion, key findings,
decision-changing unknowns or contradictions, verification performed, and
optional Artifact pointers. Detailed reusable material may be saved in a
repo-relative Artifact. The Controller decides whether to register or retrieve
it and whether any selected content belongs in a later handoff. Artifact
registration stores address, producer, revision, hash, provenance, and optional
supersession only; it does not interpret the body.

Memory and milestones are ordinary explicit storage. Search results are ordinary explicit inputs.
Status is a bounded mechanical record label. Legacy durable Markdown Status metadata remains readable
as opaque compatibility data, never routing authority. Freshness reports only FRESH, PARTIAL, RECORDED, CHANGED, MISSING, or
UNKNOWN mechanical facts. `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` are model-maintained thin global maps of the durable
tree; Core does not reconstruct a second catalog by recursively scanning the
filesystem or impose a taxonomy. SessionStart only points to these maps; before
`task-start`, the Controller explicitly reads the root navigation, and if a map
is missing it establishes a minimal thin INDEX first. During an active task,
navigation is not reread automatically; the Controller may reread it when the
map changed, is insufficient, freshness is invalid, or work is resumed after
compaction. The Controller explicitly uses `catalog` or
`document-get` to retrieve selected durable material. A single bounded
`document-get` may name up to eight explicit paths; it never searches, ranks,
or supplements the selection.
When a promotion changes durable navigation, the Controller should include its
own optional `index_update` in the same `task-promote` call. Core does not
generate INDEX content; it validates the CAS, references, and atomic commit.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. During an ACTIVE managed task the persistent Controller uses only
native spawn/wait/list/interrupt operations and an explicit allow-set of
trusted direct `thaliris` runtime commands. `init`, `uninstall`, `rollback`, a
second `task-start`, and `task-show` are blocked for ACTIVE Root. `task-status`
is bounded; `task-get`, `artifact-get`, `catalog`, and `document-get`
retrieve explicitly selected objects.
If `task-start` was attempted but managed enforcement is unavailable or
rejected, label the run unmanaged/degraded. Diagnose only the bootstrap cause:
Codex version, host capability, task schema, git/worktree identity,
hook/profile presence, and the `task-start` error are allowed reads. Once the
cause is known, do not read user-task repository source, tests, docs, or search
results. If work continues, use fresh serial Investigator, Implementer, and Reviewer sessions (`fork_turns="none"`),
distilled returns, and a fresh Reviewer; the Controller must not take over
repository investigation, implementation, or testing merely because NO_TASK
applies. The final report must not claim managed enforcement was verified.
If Codex reports a native spawn failure before `SubagentStart`, the Controller
may explicitly run `thaliris recover-pending-spawn <handoff-id>` for that exact
reservation. Core never infers failure from a missing event, timeout, or retry.
Repository investigation belongs to fresh Investigator sessions; execution,
mutation, and testing belong to fresh Implementer sessions. Existing native Codex child sessions are never resumed with follow-up/send tools.
An Investigator's or Implementer's obvious direct control-context retrieval is allowed and recorded.
Investigator and Implementer reads remain telemetry-only; Curator, Reasoning
Specialist, and Reviewer extra reads produce at most one bounded aggregate
Controller notice per pending batch. Obvious attempts to mutate
Controller-owned task or lifecycle state are denied, recorded, and included in
that aggregate notice. Reviewer independence is a
developer-instruction plus obvious-write hook guard, not a claimed native
read-only sandbox. Starting managed mode requires a current-session,
current-hook, one-shot PreToolUse attestation.

Managed native Codex child lifecycles are serial. Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. A short native wait
is normalized only while an authorized reservation or managed native Codex child is pending
and the current-session effective maximum is mechanically verified; otherwise
no automatic long-wait normalization occurs. The Controller interprets Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.
<!-- thaliris:end -->

## Thaliris Core

This repository contains the runtime-neutral Core and the Codex adapter. Keep
production mechanics smaller than model policy. Do not add role-based semantic
projection, automatic Artifact or memory propagation, semantic state
transitions, verification sufficiency gates, hidden model auditors, or
benchmark authority to the production package.

Detailed Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer work stays private unless explicitly saved as an Artifact.
Controller handoffs and retrieval are explicit. Runtime-specific lifecycle and
role-profile instructions belong in the adapter.
