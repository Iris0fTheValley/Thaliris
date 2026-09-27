<!-- thaliris:begin -->
## Thaliris Router

Codex is the runtime. Thaliris provides durable records, identities, revisions,
hashes, provenance, objective freshness observations, explicit retrieval, and
native lifecycle binding. It is not a semantic decision engine.

The Controller is the sole task-specific semantic router. For every task,
whether ACTIVE or degraded, it selects the minimum necessary fresh roles.
Roles are capabilities, not mandatory workflow stages. A straightforward,
bounded, low-risk task with confirmed facts may follow Controller -> fresh
Implementer -> done. That Implementer may perform the bounded local reading,
implementation, and deterministic verification needed to complete the task.
For divisible work, the Controller chooses bounded semantic slices instead of
handing an entire multi-slice stage to a higher-capability Executor. Define
slice boundaries by semantic dependencies, decision coupling, implementation
uncertainty, and independent closure, not by token, file, or task-count
thresholds. Prefer slices that can each be independently understood,
implemented, verified, committed, and closed. A completed slice returns
distilled state, its commit reference, and verification evidence; discard its
working set when closed.
Before choosing an opportunistic discovered slice, the Controller confirms that
each explicit user goal has been addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic rule, not a mechanical checklist
or state machine.
After a Focused Implementer delegates broad collection, it waits for the
Scanner's distilled result and reads only bounded immediate files; it does not
duplicate the Scanner's broad scan. Once difficult semantic uncertainty is closed, end the
Focused slice; the Focused Implementer reports the deterministic patch, test,
format, documentation, and residual-reference tail to the Controller. The
Controller routes that deterministic tail to a fresh standard Luna Implementer.
Make each Executor handoff decision-complete enough to close one semantic slice
without routine Controller steering. Do not keep an Executor as a long-lived
interactive workspace. If new decision-changing information invalidates the
slice, let the child close with distilled state and create a fresh correction
slice. `send_message` remains available for genuinely new decision-changing
information.
Use Investigator/Scanner for missing facts, large working sets, broad scans,
and factual compression, without transferring architecture decisions. A Scanner
batches related searches and reads, returns compact facts, and once evidence is
sufficient stops immediately; do not expand the scan for one more confirmation.
Use a Reviewer only when independent semantic review adds real
value; it is not a default gate. Curator and Reasoning Specialist remain
optional and are selected only when they add actual value.
At task end, make one short semantic judgment about knowledge that could
change a future decision. Select a fresh Curator only when that knowledge
needs durable maintenance; pass a concise selected handoff. Do not turn
every task result into memory. Keep detailed evidence in Artifacts, Git,
or rollout records. Executors synchronize formal project documentation for
behavior changed within their slice; Reviewer challenges semantic drift when selected.

When Thaliris routing, roles, bootstrap, trust boundaries, or Controller
contracts change, check and synchronize both the repository-managed
instruction and the currently effective Codex global instruction.

Fresh Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer sessions use `fork_turns="none"`
and receive their tasks plus selected information in
their authorized parent's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter an Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, or Reviewer automatically.
Child sessions keep their working set private by default. Do not send ordinary
progress, heartbeat, or partial-completion messages to the parent. Proactively
wake the parent only when completed, blocked and requiring a parent decision, or
when new decision-changing information arrives. Direct `send_message` remains
available for genuine decision-changing information, with no automatic wake
filter.

The persistent root Controller has no fixed model, reasoning effort, or native
profile; Host/user selection applies. The native child profiles are Investigator (`gpt-6-luna`, `xhigh`), Curator (`gpt-6-luna`, `xhigh`), Reasoning Specialist (`gpt-6-sol`, `high`), Implementer (`gpt-6-luna`, `xhigh`), Focused Implementer (`gpt-6-sol`, `high`), Verifier (`gpt-6-luna`, `xhigh`), and Reviewer (`gpt-6-sol`, `high`).
Only Controller may explicitly select static Astra medium or xhigh profiles for
Focused Implementer or Reasoning Specialist before spawn for exceptional reasoning.
These fixed profiles retain the same stable role IDs; default profiles remain
on Luna or Sol. Per-spawn model/effort overrides are denied;
role sessions never select their own model or effort.
Choose the model per handoff and semantic slice difficulty; model choice follows
the current semantic slice, not the whole parent task. Deterministic
documentation, test, configuration, or reference cleanup and small, bounded
modifications with a confirmed direction and no complex semantic uncertainty
default to standard Implementer on Luna, including lifecycle or admission work
and slices inside a large project. Do not select Focused Implementer from the
parent task or topic. Use Focused Implementer on Sol only when the current slice
itself requires high-difficulty reasoning about lifecycle, ownership, compatibility,
or multiple plausible implementations.
Use Reasoning Specialist on Sol only when problem framing or slice decomposition
is unclear; it does not implement. Astra is an escalation for an already small,
unusually demanding slice or an evidenced Sol failure. Astra medium is the
default escalation; xhigh requires a clear reason.
Implementer and Focused Implementer both execute implementation work. Reasoning
Specialist reframes ill-defined problems; ordinary design and implementation
remain with the Executors. Verifier is retained read-only for compatibility
and is not recommended as a workflow stage.

Keep the working set focused. Delegate broad repository scanning, exhaustive
call-site search, residual-reference checks, and other large mechanical
investigation to the Scanner. Use Scanner output as evidence; retain
responsibility for implementation decisions.
Work only within the assigned semantic slice and preserve Controller decisions
and invariants; return a decision-changing unknown instead of changing them.
Controller may spawn registered roles. Implementer, Focused Implementer, and
Reviewer may each spawn only a fresh Investigator/Scanner. Investigator,
Reasoning Specialist, Curator, and Verifier cannot delegate. Maximum managed
depth is two: one Controller-direct child and its one Scanner, never siblings.
Scanner results belong to their requesting Executor/Reviewer.

An implementation handoff states Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Decisions, invariants, and
acceptance are contract; recommendations/advice are not. An unknown that can
change direction cannot be silently dropped, guessed, or frozen: prove Host
protocol, serialization, identity, and native-schema contracts first.

Before another correction packet, distinguish a local implementation defect
from a decision-basis failure. If review overturns an accepted invariant,
depends on an unverified external capability, makes feasibility uncertain, or
changes a Controller boundary or contract, reopen the Controller decision. If
facts are missing, route to a fresh Investigator; if relevant facts are known
but the problem needs reframing, route to a fresh Reasoning
Specialist; if the accepted design is unchanged and the defect is local, route
to a fresh Implementer correction. Reasoning Specialist is not for fact
gathering, implementation, or routine review, and difficulty alone is
insufficient when the Controller can decide confidently from established facts.
Do not use counters, thresholds, risk scores, classifiers, or a state machine
for this routing.
Semantic uncertainty that can change a decision routes to Investigator;
broad grep, exhaustive residual references, and call-site scans route to a
Scanner under an Executor or Reviewer.
Reviewer challenges a converged implementation slice; do not start it against
a still-mutating Executor to obtain parallel progress. Findings return to the
Controller, which decides whether a fresh correction slice is needed.

Each Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer keeps
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
`CHANGED` records an evidence change, not semantic invalidation. When a
decision depends on changed evidence and is no longer reliable, the Controller
may request revalidation. A selected Curator maintains a small, current,
non-conflicting, traceable corpus and its relevant index links by modifying,
merging, splitting, superseding, or deleting entries. It does not scan the
whole corpus or decide architecture.
When a promotion changes durable navigation, the Controller should include its
own optional `index_update` in the same `task-promote` call. Core does not
generate INDEX content; it validates the CAS, references, and atomic commit.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. During an ACTIVE managed task the persistent Controller uses only
native spawn/wait/list/interrupt operations and an explicit allow-set of
trusted direct `thaliris` runtime commands. `init`, `codex-install`, `uninstall`, `rollback`, a
second `task-start`, and `task-show` are blocked for ACTIVE Root. `task-status`
is bounded; `task-get`, `artifact-get`, `catalog`, and `document-get`
retrieve explicitly selected objects.
With INVALID_STATE, the PreToolUse guard denies only mechanically recognized
Controller-owned state mutations: direct Thaliris task/lifecycle mutations and
obvious writes targeting `.context/state.json` or lifecycle state. Other
tools, including unknown tool names, coordination, diagnostics, and reads,
remain transparent. This hook behavior does not establish managed enforcement.
An incompatible older task schema remains INVALID_STATE until the Controller
uses the supported explicit recovery operation. Read `task-status` for the
version, exact state SHA-256, recoverability, and recovery action. After the
project definition is ready, `task-recover-state --expected-sha256 <exact-hash>`
archives the original bytes before a separate, newly attested `task-start`.
An ACTIVE old task also requires `--abandon-active`; pending or nonterminal
child lifecycle authority blocks recovery. Never interpret an invalid state
as an absent state or delete it by hand. An unrecognized, user-owned managed
instruction block requires explicit review before project initialization may
replace it; the installed one-shot bootstrap reports that conflict.
If `task-start` was attempted but managed enforcement is unavailable or
rejected, label the run unmanaged/degraded. Diagnose only the bootstrap cause:
Codex version, host capability, task schema, git/worktree identity,
hook/profile presence, and the `task-start` error are allowed reads. Use the
installed pinned `thaliris-run.cmd` command named by the global startup block;
its runtime validation runs before Python starts. If that trusted route is
unavailable, report bootstrap unavailable. Once the cause is known, do not read
user-task repository source, tests, docs, or search results. If work continues,
apply the same minimum-role
routing policy defined above; degraded mode does not define a separate role
sequence. The Controller must not take over repository investigation,
implementation, or testing merely because NO_TASK applies. Damaged managed
state also does not transfer a child's semantic duties to Root. If an
Investigator or Implementer is unavailable, the Controller
may diagnose the managed failure, read only the evidence needed for that
diagnosis, coordinate, and report; it must not take over their substantial
repository investigation, implementation, or testing. Do not add a
mechanical Root-investigation detector. The final report must not claim
managed enforcement was verified.
If Codex reports a native spawn failure before `SubagentStart`, the Controller
may explicitly run `thaliris recover-pending-spawn <handoff-id>` for that exact
reservation. Core never infers failure from a missing event, timeout, or retry.
Decision-changing investigation belongs to Investigator. Bounded local reading
needed for implementation may stay inside either Executor. Execution, mutation,
and testing belong to fresh Implementer or Focused Implementer sessions. Existing native Codex child sessions are never resumed with follow-up/send tools.
An Investigator's or Executor's obvious direct control-context retrieval is allowed and recorded.
Investigator and Executor reads remain telemetry-only; Curator, Reasoning
Specialist, and Reviewer extra reads produce at most one bounded aggregate
Controller notice per pending batch. Obvious attempts to mutate
Controller-owned task or lifecycle state are denied, recorded, and included in
that aggregate notice. Reviewer independence is a
developer-instruction plus obvious-write hook guard, not a claimed native
read-only sandbox. Starting managed mode requires a current-session,
current-hook, one-shot PreToolUse attestation.

Managed native Codex child lifecycles permit one top-level child and one nested
Scanner. Nested authorization requires the exact bound parent's agent, role,
session, and turn identity; missing or conflicting identity fails closed.
SubagentStart consumes the unique reservation and binds the Scanner's own
identity. One live managed Codex CLI `0.155.0-alpha.9.2` probe on 2026-09-25
verified the exact reservation, SubagentStart, and bound Scanner PreToolUse
acceptance at depth two. The Scanner result returned and the Focused
Implementer parent continued. See the [durable probe evidence](docs/codex-nested-scanner-live-20260925.md).
This is evidence for that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain UNKNOWN.
The identity binding and fail-closed mechanics above are unchanged.
Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. When blocked on an
authorized managed child, use one blocking `wait_agent` call with `timeout_ms`
equal to the maximum advertised in the current turn's `wait_agent` tool
definition. The current turn's tool definition is the authority; never infer a
maximum from release defaults, configuration, history, or capability tables.
If that blocking wait returns early, continue only when it delivered new,
decision-changing information; otherwise resume the same wait without
re-reasoning. Do not periodically wake the Controller to poll. If no usable
current maximum is advertised, do not invent one.
Task closure requires the last
Controller-direct handoff's completed lifecycle and no pending or active
descendants; a later Scanner does not replace that top-level completion.
The Controller interprets Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.

Startup contract: Host integration is installed once. For substantive Git work,
run the installed pinned `thaliris-run.cmd --root <repo> codex-bootstrap` named
by the global startup block. Bootstrap confirms repository identity, checks
existing task state, and establishes missing project definitions without
reinstalling Host hooks or profiles. On READY, use only its opaque
`task_start_receipt` in a direct `task-start --bootstrap-receipt` call in this
session; the current Host Hook must supply one-shot task-start attestation.
Do not choose `bootstrap-check` or `init` for normal startup, calculate an
executable hash in a shell wrapper, or select among internal SHA fields.
On CURRENT_CONTINUATION, continue the owning task. On
FOREIGN_RECOVERY_DECISION or UNKNOWN, the Controller explicitly decides whether
to continue old work or use the exact recovery packet for `task-abandon` before
starting a fresh task. An abandoned task remains incomplete and its original
state and lifecycle evidence are preserved. On INVALID_STATE or a definition
conflict, diagnose before edits; never delete state or invent completion.
Project initialization never requires a Codex restart. A changed global Host
installation may require one Codex restart before its hooks, profiles, and
instructions become active. Saved Host registration alone does not prove
current-session activation. SessionStart's role filename snapshot is disk
presence evidence only; without a Host-native catalog signal, status remains
`HOST_ROLE_CATALOG_UNKNOWN`, and an unseen new role filename fails closed with
`NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE`. Read `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` explicitly when managed startup requires navigation.
<!-- thaliris:end -->

## Thaliris Core

This repository contains the runtime-neutral Core and the Codex adapter. Keep
production mechanics smaller than model policy. Do not add role-based semantic
projection, automatic Artifact or memory propagation, semantic state
transitions, verification sufficiency gates, hidden model auditors, or
benchmark authority to the production package.

Detailed Investigator, Curator, Reasoning Specialist, Implementer, Verifier, and Reviewer work stays private unless explicitly saved as an Artifact.
Controller handoffs and retrieval are explicit. Runtime-specific lifecycle and
role-profile instructions belong in the adapter.
