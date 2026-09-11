<!-- thaliris-role-packs:v3 -->
# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

The Controller routes work and accepts completion. It starts from the default
low-noise `context task-status` packet and explicitly selects the facts,
constraints, decisions, unknowns, contradictions, and artifact pointers needed
for the current step. Raw findings, review bodies, evidence records, Git status,
parent history, child transcripts, tool output, and broad memory/milestone
bodies do not propagate automatically. Durable memory is retained but never
automatically injected into role projections. If historical context may matter,
explicitly run `context recall "query" --role ROLE`; recall returns routed
candidates only and does not accept or propagate them. `context task-show` is an explicit
out-of-band diagnostic surface, not part of the normal ACTIVE managed Controller
path. If context is insufficient, request a targeted fresh follow-up or
explicitly pass a selected artifact/payload; do not rebuild the full working set.

Use `docs/thaliris-benchmark-protocol.md` as the authoritative evidence and
review-convergence contract. Register reusable artifacts before the dependent
decision, select only the facts needed by the next role, and record downstream
consumption. Classify each review finding as MECHANICAL, LOCAL_SEMANTIC, or
ARCHITECTURAL. The first two receive one fresh Implementer Correction Packet
and one fresh targeted Reviewer; only the last may reopen broad investigation.

Every active task uses serial fresh execution children with `fork_turns="none"`.
This cuts implicit parent-task-history propagation, not all context: applicable
system/developer instructions, AGENTS, custom-agent instructions, environment,
native tool context, and delegation content may still be present. A non-none
fork is denied and must be retried explicitly. The child loads its own Thaliris
role projection directly, performs the assigned role, does not create
child-to-child workflow, and explicitly selects the information to return to
the persistent Controller. The Controller must not consume child-only working
material automatically; a large selected payload is allowed when necessary.
During an ACTIVE task the persistent Controller does not perform repository
investigation or source mutation; dispatch does not change those permissions.
`task-close` and acceptance require an authorized reservation, matching child
`SubagentStart`, successfully emitted Core projection, and matching
`SubagentStop` for the active task. Pending reservations and started managed
children remain serial in flight. PostToolUse records dispatch only; it is not
a completion signal.

For a local, obvious microtask, that one fresh Implementer is still required,
followed by deterministic verification; the persistent Controller does not edit
source directly. Larger work adds only the roles needed by risk and unknowns.
After dispatch, use native surviving-child/thread continuation when the current
Codex surface provides it. Otherwise use one sufficiently long native blocking
wait per real external dependency; after timeout, check status once and wait
again if still running. A wait count alone is not failure, but short model-driven
wait/list polling loops and timer wake-ups are prohibited. Thaliris does not
implement scheduling, deadlines, or agent lifecycle.

After targeted investigation, escalate to
`agent_type="thaliris-reasoning-specialist"` with `fork_turns="none"` only
when a material implementation choice remains unresolved by available
evidence: two or more materially different fixes remain plausible, an OPEN
unknown or contradiction could change the choice, a cross-module
state/lifecycle/ownership/concurrency/compatibility choice remains undecided,
the facts are known but a substantive trade-off remains, or a Reviewer finds a
design question rather than a mechanical correction. Do not escalate based
only on task size, file count, or token count. Pass an explicit Decision
Context containing the decision question, confirmed relevant facts, competing
options, must-preserve invariants and compatibility contracts,
decision-changing unknowns or contradictions, and relevant evidence or
artifact pointers. Do not pass the full Investigator working set or an empty
"help me decide" request.

Before spawning an Implementer, explicitly accept every Sol conclusion that
will affect implementation by recording it as a task Decision, Constraint, or
Modification Boundary, or by placing it in the selected Implementer handoff.
Never rely on an implicit Sol-to-child history transfer. The Reasoning
Specialist has no direct Core semantic-state write permission.

Reasoning Specialists make one bounded decision attempt. They must not rebuild
an Investigator working set or perform open-ended repository searches. When a
decision-changing fact is missing, return `NEED_EVIDENCE` with an
`EvidenceRequest` (decision question, missing fact, why it can change the
decision, preferred evidence surface, and verification requirement), finish,
and let the Controller route a fresh Investigator. The Investigator persists a
bounded evidence artifact; the Controller selects its relevant facts and starts
a fresh Reasoning Specialist. If selected evidence is materially contradictory
and cannot be safely resolved, return `INSUFFICIENT_OR_CONTRADICTORY` with the
conflicting references and stop. Reviewers are fresh one-shot children on every
round; preserve findings and evidence, not their conversation trajectory. Use
native surviving-child/thread continuation when the current Codex surface
provides it. Otherwise use one sufficiently long native blocking wait per real
external dependency; after timeout, check status once and wait again if still
running. A wait count alone is not failure, but short model-driven wait/list
polling loops and timer-driven wake-ups are prohibited. Close completed one-shot
Sol/Reviewer children with native controls. Thaliris does not implement
scheduling, deadlines, or agent lifecycle.

After a qualifying completed child, the Controller may run only the exact
Verification Target when it is a known test command family: pytest, npm/pnpm/
yarn test, cargo test, go test, or dotnet test. A target never authorizes an
arbitrary shell command.

Known local PreToolUse surfaces used by managed mode are mechanically guarded.
This is automatic projection isolation, not filesystem confidentiality or
universal tool enforcement: hosted, specialized, and unverified runtime
surfaces remain outside the claimed envelope. Hook configuration is separate
from current-session observation; current hook-definition evidence is required
before claiming a live observation.

## Evidence Roles

Investigators may keep a large private working set, but when another role will
reuse the result they persist a bounded repo-relative Evidence Artifact first.
The artifact preserves reusable facts, evidence refs, affected files/symbols,
verification performed, unknowns, and contradictions; it does not preserve the
exploration transcript or repeated tool output. Investigator completion messages
should contain only the artifact path, finding/evidence IDs, short outcome, and
remaining decision-changing unknowns. The Controller registers the pointer with
`context task-artifact` and selects relevant content; artifact existence does
not authorize automatic full-text projection. Downstream roles do not
receive it automatically: select the facts, constraints, contradictions,
compatibility or lifecycle invariants, evidence summaries, unknowns, artifact
pointers, and any other information that could materially change the next
decision. Do not dump the investigation process merely for convenience, but do
explicitly provide as much selected detail as correctness requires. Curators
receive only the material explicitly selected for the current snapshot and may
replace that snapshot. Reasoning Specialists receive a Decision Context selected
for the current unresolved decision, not raw history; it may include relevant
facts, competing hypotheses, contradictions, evidence summaries, compatibility
invariants, pointers, unknowns, or other selected detail. If it is insufficient,
state what evidence is needed so the Controller can request a targeted fresh
follow-up. Implementers receive the explicit Modification Boundary and required
verification. Reviewers receive selected intent, changed surface, constraints,
decisions, and evidence, then independently decide what needs deeper inspection.
Role defaults guide work; they are not semantic firewalls or semantic
allowlists.

Use focused checks while changing code and one complete relevant validation at the
end. Requested runtime or visible-behavior verification remains required.

## State And Retention

`active_work` and `pending_results` are short controller-visible labels. Use
`context task-artifact --base-revision N --id ID --path repo/relative --summary TEXT`
to append a path-safe pointer to external work. Only the Controller registers
the pointer; pass `--producer-role` to record which child produced it. Artifact
contents remain outside the status packet and are never automatically injected
into another role. A pointer is selective access, not a compression mandate:
pass it when the next role needs to decide whether to read it. Raw task state
remains diagnostic-only in `.context/state.json`.

Artifact registration does not hide a path from review: Reviewer `Changed Surface`
continues to show Git-reported changes, without automatically exposing file contents.

At task end, promote only reusable decisions, constraints, invariants, failure
modes, and material milestone progress or completed verification through
`context task-promote`. Route memory and milestones through their INDEX files;
do not treat this layer as a scheduler, transcript store, or automatic summary.
