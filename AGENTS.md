<!-- thaliris:begin -->
## Thaliris Router

Codex is the runtime. Thaliris provides durable records, identities, revisions,
hashes, provenance, objective freshness observations, explicit retrieval, and
native lifecycle binding. It is not a semantic decision engine.

The Controller is the sole task-specific semantic router. Every root child is
fresh (`fork_turns="none"`) and receives its task plus selected information in
the Controller's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter a child automatically.

A Child keeps its investigation, tool output, tests, and intermediate working
set private. By default it returns a distilled conclusion, key findings,
decision-changing unknowns or contradictions, verification performed, and
optional Artifact pointers. Detailed reusable material may be saved in a
repo-relative Artifact. The Controller decides whether to register or retrieve
it and whether any selected content belongs in a later handoff. Artifact
registration stores address, producer, revision, hash, provenance, and optional
supersession only; it does not interpret the body.

Memory and milestones are ordinary explicit storage. Search results and
Audience, Topics, Symbols, Applicability, Kind, Status, and Confidence metadata
are hints for models and displays, never routing permissions or correctness
gates. Freshness reports only FRESH, PARTIAL, RECORDED, CHANGED, MISSING, or
UNKNOWN mechanical facts. Root SessionStart receives only a small durable
catalog showing what documents exist. The Controller explicitly uses
`catalog`, `recall`, or `document-get` to retrieve selected durable material;
the catalog never includes document bodies or chooses relevance.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. During an ACTIVE managed task the persistent Controller uses only
native spawn/wait/list/interrupt operations and trusted direct `context`
control commands. `task-status` is bounded; `task-get`, `artifact-get`,
`catalog`, `recall`, and `document-get` retrieve explicitly selected objects.
`task-show` is offline/human diagnostics and is blocked for ACTIVE Root.
Repository investigation, execution, mutation, and testing belong to fresh
Children. Existing Child threads are never resumed with follow-up/send tools.
A Child's obvious direct control-context retrieval is allowed but recorded for
one short Controller notice. Obvious attempts to mutate Controller-owned task
or lifecycle state are denied and recorded. Reviewer independence is a
developer-instruction plus obvious-write hook guard, not a claimed native
read-only sandbox. Starting managed mode requires a current-session,
current-hook, one-shot PreToolUse attestation.

Managed children are serial. Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. A short native wait
is normalized to the host maximum only while an authorized reservation or
managed child is actually pending. The Controller interprets Child results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.
<!-- thaliris:end -->

## Thaliris Core

This repository contains the runtime-neutral Core and the Codex adapter. Keep
production mechanics smaller than model policy. Do not add role-based semantic
projection, automatic Artifact or memory propagation, semantic state
transitions, verification sufficiency gates, hidden model auditors, or
benchmark authority to the production package.

Detailed Child work stays private unless explicitly saved as an Artifact.
Controller handoffs and retrieval are explicit. Runtime-specific lifecycle and
role-profile instructions belong in the adapter.
