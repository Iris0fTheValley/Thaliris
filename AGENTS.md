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
handing an entire multi-slice stage to one implementation role. Define
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
The Controller owns the complete user objective, its decomposition, role and
context choice, overall invariants, boundaries and acceptance, interpretation
of child results, and task-level decisions to reopen, review, continue, or end.
It may do bounded reading needed to frame a handoff and interpret evidence, but
does not perform broad repository scans, implementation, or the full task test
suite. The Investigator role gathers broad evidence, including through the
Scanner working pattern. Local code decisions and implementation within the
accepted packet belong to Implementer or Focused Implementer.
The Focused Implementer can complete complex implementation as well as
focused judgment. It directly inspects known, decision-critical sources, including
source code, relevant call chains, the current diff, failed tests, and raw
evidence that bears on the decision. When the target is known, read it
directly. Delegate one independent discovery working set to a fresh
Investigator doing Scanner work when a larger or unknown evidence surface must be
discovered, enumerated, filtered, or classified. Ask the Scanner for key
conclusions, exceptions, UNKNOWNs, and accurate raw locations. The Scanner
narrows the search space; it does not replace reasoning-coupled reading. After
it returns, targeted reopening of relevant originals to verify findings is
useful. There is no per-read delegation deliberation or file, token, or
search-count threshold; small local searches may be direct. Delegate when
doing so removes the discovery working set and leaves reasoning and
implementation with the Focused Implementer. After delegating, it waits for the
distilled result and does not repeat the discovery pass. It continues complex
implementation within the assigned slice when that work still benefits from
focused reasoning. Close the Focused slice when its accepted semantic and
implementation work is complete; report a deterministic remainder for
Controller routing only when it is outside the slice or independently closable
without the Focused model's reasoning.
The Controller makes each child handoff decision-complete enough to close one
semantic slice without routine steering. Do not keep a child as a long-lived
interactive workspace. If new decision-changing information invalidates the
slice, let the child close with distilled state and decide whether a fresh
correction slice is needed. `send_message` remains available for genuinely new
decision-changing information.
Use the Investigator role for missing facts, large working sets, broad scans,
and factual compression, without transferring architecture decisions. Its
Scanner working pattern batches related searches and reads, returns compact
facts, and once evidence is sufficient stops immediately; do not expand the
scan for one more confirmation.
Use a Reviewer only when independent semantic review adds real
value; it is not a default gate. Use Reasoning Specialist as an optional,
independent metacognitive challenger when a challenge may materially change
direction. Test framing, hidden assumptions, causal models, decomposition,
boundaries, decision basis, and premature convergence; this includes apparently
coherent framing and unexpected outcomes when a challenge could change direction.
The Specialist grounds critique in selected information, reports material
alternatives and critical missing facts, and does not make the final decision.
It does not perform broad fact gathering, implementation, routine review, or
ordinary hard-problem solving.
At task end, before `task-close`, make one short semantic judgment: did the task
add, change, or overturn durable knowledge that could affect a future decision
and would otherwise require reinvestigation? If no, silently skip Curator. If
yes, select a fresh Curator and provide the selected durable facts plus exact
relevant prior knowledge/documents. Curator is optional, never triggered by
task size, and not a mandatory stage. It keeps durable memory under
`.agent-memory/`; detailed evidence and task results remain in Artifacts, Git,
or rollout records. Implementer roles keep product/protocol documentation and
README aligned with current behavior; Reviewer challenges semantic drift when
selected.

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
Focused Implementer or Reasoning Specialist before spawn. Each profile retains
the same semantic role identity and does not create another role.
These fixed profiles retain the same stable role IDs; default profiles remain
on Luna or Sol. Per-spawn model/effort overrides are denied;
role sessions never select their own model or effort.
Use Reasoning Specialist on Sol when an independent challenge may materially
change direction, including when the framing appears coherent or an outcome is
unexpected; difficulty alone is not a trigger. It challenges the decision basis
and reports its analysis without making the final decision.
Implementer and Focused Implementer make local code decisions and execute
implementation within their assigned packets. Verifier is retained read-only
for compatibility and is not recommended as a workflow stage.

Routing terminology: Investigator, Implementer, and Focused Implementer are semantic roles;
Scanner is a nested Investigator discovery working pattern, not a separate
role. Executor is a category covering Implementer and Focused Implementer, not
a selectable or spawnable role; route work by the actual role name. A native
execution profile selects model and effort for a semantic role and does not
create another role.

Choose one model/profile for the current implementation slice from its work
shape, not as a ladder. The standard Implementer on Luna is the default for a
stable problem structure and direction, including remaining execution, local
code judgment, tests, synchronization, and mechanical consistency, regardless
of task size. Choose Focused Implementer on Sol when the problem model and
direction are stable enough, but implementation needs sustained reasoning
across coupled invariants, nonlocal effects, or constraints. Choose a Focused
Implementer Astra profile when the solution path is unstable and understanding,
exploration, implementation, runtime feedback, and remodeling are coupled; it
may own a bounded explore-understand-implement-run-observe-revise loop within
the Controller's goal, hard invariants, scope, and acceptance. Astra medium and
xhigh are exceptional execution profiles of the same Focused Implementer role.
Choose the profile once for the slice; Sol failure is not a prerequisite and
there is no need to prove Sol inadequate. Importance, file count, cross-module
scope, or ordinary alternatives alone do not determine the choice.

Keep the working set focused. Directly read known, decision-critical sources.
Use Scanner work for discovery over a larger or unknown evidence surface and
for a clearly large, low-reasoning-density collection that can be compressed
independently. With the Sol Focused Implementer profile, consider offloading
broad or exhaustive peripheral call-site, rollout/log, and residual-reference
collections when that removes an independent working set. With an Astra
Focused Implementer profile, explore evidence needed for the current slice
directly and use Scanner work only for a clearly large, low-reasoning-density
collection that can be compressed independently. The collection choice does
not predetermine which evidence is relevant. Targeted reading of known sources
remains part of the implementation role's work; small local searches may be
direct. Delegate when doing so removes an independent working set. Use its output as evidence. Children work only within their assigned semantic slice,
preserve Controller decisions and invariants, and return a decision-changing
unknown instead of changing them. Local code decisions belong to Implementer or
Focused Implementer.
Once the slice goal, authority, and boundary are known, batch the relevant source,
test, generation, and documentation reads, plan, and make coherent edits.
Avoid per-patch, per-read, or per-grep reasoning rounds unless new information
could change direction. Match verification to the changed behavior and its
concrete regression surface. Start with focused checks for the changed
contract, generated output, and acceptance. If those pass without a failure,
anomaly, or new broader-risk evidence, stop. Broaden checks only for a concrete
compatibility or integration risk. After fixing a test failure, rerun the
smallest acceptance-relevant range. A commit, push, or final report alone does
not call for another test run. Do not use counts, time, file or token limits,
or a stopping state machine.
Controller may spawn registered roles. Implementer, Focused Implementer, and
Reviewer may each spawn only a fresh Investigator doing Scanner work. Investigator,
Reasoning Specialist, Curator, and Verifier cannot delegate. Maximum managed
depth is two: one Controller-direct child and its one nested Investigator
session doing Scanner work, never siblings. Results belong to the requesting
Implementer, Focused Implementer, or Reviewer.

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
facts are missing, route to a fresh Investigator. When an independent challenge
could materially change direction, route the selected framing and evidence to a
fresh Reasoning Specialist, even if the current framing appears coherent or an
outcome was unexpected. The Specialist challenges hidden assumptions, causal
models, decomposition, boundaries, decision basis, premature convergence, and
direction-changing alternatives; it reports critical missing facts for the
Controller to route and does not decide the task. Do not use it for broad fact
gathering, implementation, routine review, or ordinary hard-problem solving.
Difficulty alone is not a trigger when the Controller can decide confidently
from established facts. If the accepted design is unchanged and the defect is
local, route to a fresh Implementer correction. Do not use counters, thresholds,
risk scores, classifiers, or a state machine for this routing.
Missing factual information routes to the Investigator role. Broad grep,
exhaustive residual references, and call-site discovery can use the Scanner
working pattern under Implementer, Focused Implementer, or Reviewer. The
Controller interprets findings,
decides whether to reopen the basis, selects any review, and decides when work
continues or ends.
Reviewer challenges a converged implementation slice; do not start it against
a still-mutating Implementer or Focused Implementer to obtain parallel progress. Findings return to the
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
The Controller may explicitly run `thaliris recover-pending-spawn <handoff-id>`
only after the Hook records exact, trusted native failure for that unbound
reservation: a name-bound `interrupted`, `errored`, or `shutdown` observation,
or an exact spawn failure callback. Missing events, `not_found`, completed,
timeouts, and Controller reports cannot release it. A pre-Start native failure
without a Hook callback or identity remains unresolved.
Decision-changing investigation belongs to the Investigator role. Bounded local reading
needed for implementation may stay inside Implementer or Focused Implementer. Execution, mutation,
and testing belong to fresh Implementer or Focused Implementer sessions. Existing native Codex child sessions are never resumed with follow-up/send tools.
An Investigator's, Implementer's, or Focused Implementer's obvious direct control-context retrieval is allowed and recorded.
Investigator, Implementer, and Focused Implementer reads remain telemetry-only; Curator, Reasoning
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
SubagentStart consumes the unique reservation and binds the nested
Investigator session's own identity. One live managed Codex CLI `0.155.0-alpha.9.2` probe on 2026-09-25
verified the exact reservation, SubagentStart, and bound Scanner PreToolUse
acceptance at depth two. The Scanner work result returned and the Focused
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
After a child finishes, call `list_agents` once before `task-close` to obtain
its exact native name and Completed status. A `wait_agent` result that only
reports `timed_out: false` is a wake signal, not completion evidence. If the
name-bound status is unavailable, leave completion UNKNOWN and keep the task
open; do not infer it from SubagentStop, child prose, or elapsed time.
Task closure requires the last
Controller-direct handoff's completed lifecycle and no pending or active
descendants; a later Scanner does not replace that top-level completion.
The Controller interprets Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.

Startup contract: Host integration is installed once. For substantive Git work,
the owning root Controller runs the installed pinned
`thaliris-run.cmd --root <repo> codex-bootstrap` named by the global startup
block. Bootstrap confirms repository identity, checks
existing task state, and establishes missing project definitions without
reinstalling Host hooks or profiles. On READY, use only its opaque
`task_start_receipt` in a direct `task-start --bootstrap-receipt` call in this
session; the current Host Hook must supply one-shot task-start attestation.
If operating as a managed child inside an ACTIVE task, follow the explicit
handoff and do not run project bootstrap, task-start, or task-abandon for the
parent's task; startup, admission, and continuation decisions belong to the
owning root Controller.
Do not choose `bootstrap-check` or `init` for normal startup, calculate an
executable hash in a shell wrapper, or select among internal SHA fields.
On CURRENT_CONTINUATION, the owner may continue or explicitly abort the
incomplete task using the exact `task-abandon` packet. An unbound pending spawn
must have trusted terminal recovery first; otherwise its future child identity
cannot be fenced. On FOREIGN_RECOVERY_DECISION or UNKNOWN, the Controller
explicitly decides whether to continue old work or use that exact recovery
packet before starting a fresh task. An abandoned task remains incomplete and its original
state and lifecycle evidence are preserved. On INVALID_STATE or a definition
conflict, diagnose before edits; never delete state or invent completion.
In user-facing status, describe the work and any concrete blocker in ordinary
task terms. Keep receipts, hashes, attestations, role/session binding details,
and lifecycle protocol out of that prose; report blocked work honestly.
Host maintenance uses a separate checkout and Codex session outside the ACTIVE
project task. That checkout can repair Thaliris source, tests, installed runtime,
hooks, profiles, and the global instruction without changing the original task
ledger. In an ACTIVE project, only exact installed, identity-checked direct
`codex-install` and `codex-uninstall` calls are Host maintenance exceptions;
ordinary source commands remain under the managed Controller boundary. A
self-invoked `codex-uninstall` may retain an inert runner until a later direct
cleanup or reinstall, and reports that state explicitly.
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
