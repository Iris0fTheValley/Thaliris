<!-- thaliris:begin -->
## Thaliris Router

Codex is the runtime. Thaliris provides durable records, identities, revisions,
hashes, provenance, objective freshness observations, explicit retrieval, and
native lifecycle binding. It is not a semantic decision engine.

Task authority is durable human task intent, recorded by an explicit Controller
operation under a governance boundary. `task-start --authority-contract <json>`
selects the actual human instruction, boundary, invariants, acceptance, and
execution mode (`delegated`, `controller-direct`, or `single-agent`). Never
infer human authorship from UserPromptSubmit, field absence, session equality,
PID, environment, or SessionSource. Host actor assurance remains UNKNOWN.
Known children, readonly roles, and fenced actors cannot establish, expand,
rewrite, recover, or reactivate authority. Unrecognized delegates and shared
OS access are not universally authenticated or isolated by this contract.

The external anchor under the user's `.thaliris/task-authority/` preserves
project/task identity, goal, intent, lifecycle evidence and the original
security baseline independently of mutable repository configuration. Ordinary
continuation survives turns, network, Hook, session and daemon interruption;
it requires no repeat Root identity proof. `task-recover-authority` with the
exact external authority hash and a reason archives conflicts, restores the
recorded bytes and fences known old children. It retains death proof UNKNOWN
and cannot bless changed security bytes or remove fences. Scope, goal,
acceptance, execution mode, unfencing or a new security baseline require an
actual superior human decision; child prompts, state or config cannot grant it.
Authority ends on closure, human revocation, Controller abandonment or replacement.

Explicit human Controller-direct intent overrides the default role split:
Controller may read, edit, test, verify, commit and finish; fresh auxiliary
roles apply only when semantically useful, with no implementation spawn.
Explicit single-agent/no-children intent allows ordinary Codex execution and
closure with no children. Overrides are persisted task intent, never inferred
from convenience. Without an explicit override, the default routing and child
completion contract below remain unchanged. Fresh isolation, reviewer/verifier
readonly and explicit Astra authorization remain in force in every mode.

The Controller is the sole task-specific semantic router. For every task,
whether ACTIVE or degraded, it selects the minimum necessary fresh roles.
Roles are capabilities, not mandatory workflow stages. A straightforward,
bounded, low-risk task with confirmed facts may follow Controller -> fresh
Implementer -> done. That Implementer may perform the bounded local reading,
implementation, and deterministic verification needed to complete the task.
For divisible work, Root routes by semantic Workstream. Define Workstream
boundaries by semantic dependencies, decision coupling, implementation
uncertainty, and independent closure, not by token, file, or task-count
thresholds. A Workstream is held by Root and executed by one authorized child
session; it does not create another role or semantic Controller. A semantic
checkpoint is not necessarily a scheduling checkpoint. Root routes workstreams.
Executors close local loops inside them.

Within a stable Workstream, the same Implementer session may complete multiple
local closures: batch relevant reads, plan, implement, run focused verification,
fix ordinary in-scope failures, synchronize generated output and documentation,
run needed integration verification, inspect diff and status, and complete
assigned Git closure. These are available execution checkpoints, not a mandatory
bundle. A local verification PASS does not require returning to Root or
switching roles. Root chooses the semantic boundary and may assign a separate
closure Workstream when the remainder is independently deterministic. A new semantic Workstream may use a different role; the profile chosen for one
Workstream does not bind the task's remaining operational work. Ordinary
test fixes, generated or documentation synchronization, integration checks,
and assigned Git closure are not automatically separate semantic routing
boundaries. Local deterministic failures in paths, arguments, manifests,
generated files, installation environment, documentation, fixtures, or Git may
be fixed by the current executor within its assignment. The child retains
execution authority only within the assigned goal, scope, invariants, and
acceptance; this authority never expands Controller-assigned scope.
Very small direct routine operations need no ceremonial child handoff when the
Controller is already authorized to perform them; this does not change
delegated, controller-direct, or single-agent authority.

Root regains control at the semantic Workstream boundary. A child returns
distilled state, its commit reference, and verification evidence after its
assigned Workstream is complete. If new evidence changes task direction,
ownership, observable semantics, accepted architecture, security boundary, a
hard invariant, compatibility contract, or acceptance, or reveals an unverified external dependency that can change the
decision, the child stops and returns the concrete unknown in FINAL for Root to
decide. Only the Controller decides what follows; no child acts as a second
semantic Controller. Do not use file, tool, token, time, or local-closure
counts to end a Workstream or to choose the executor profile.
When completed Investigator discovery is selected for a later semantic slice,
the Controller handoff carries its confirmed facts, exact source locations and
affected surfaces, relevant unknowns or contradictions, and covered and
uncovered scope. This lets the next implementation role use the selected map
without reconstructing the same broad inventory.
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
When an implementation handoff selects completed Investigator discovery from
an earlier slice, Implementer or Focused Implementer starts from that evidence
map. Reopen decision-critical originals, call chains, diffs, and tests as needed
for implementation; do not repeat broad discovery or delegate a Scanner over
the covered surface. A fresh Scanner may collect only a genuinely uncovered
decision-changing evidence gap needing independent broad discovery, limited to
that gap. Apply this by judgment about evidence coverage, without a cache,
threshold, state machine, or new evidence system.
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
implementation within the assigned Workstream across local checkpoints when
that work still benefits from focused reasoning. A local verification PASS
does not force a return to Root or switch models. Focused Implementer owns
semantic convergence of its implementation candidate. It may return FINAL once
core implementation and hard invariants are in place, decision-changing
unknowns are resolved, focused evidence demonstrates the candidate's core
semantics, the candidate is internally coherent, and remaining work is unlikely
to change the causal model, scope, acceptance, or direction. A focused-test
PASS alone does not meet this boundary or trigger a role switch. The FINAL
handoff identifies candidate state and exact source locations or diff,
invariants satisfied, focused evidence and its limits, explicit remaining
tasks, acceptance, and the escalation boundary. Documentation, generated
output, configuration, installation, Host smoke checks, fixtures, and Git
closure are not automatically required before this handoff; include any check
needed to prove core semantics. Installation or smoke feedback that exposes a
semantic defect stays with Focused Implementer while needed to establish the
candidate. The Controller decides whether remaining work still needs the core
reasoning or is an independent deterministic closure for an ordinary
Implementer. Coupled work may stay in the active Focused Workstream. After a
child returns FINAL, it is complete and cannot be resumed; further work
requires a fresh session and Controller handoff. If evidence changes the
accepted architecture or causal model, security boundary, hard invariant,
compatibility, scope, acceptance, or direction, return
the issue to Root without redesigning it.
The Controller makes each child handoff decision-complete enough to close one
semantic Workstream without routine steering. Do not keep a child as a long-lived
interactive workspace. If new decision-changing information invalidates the
Workstream, the child closes with a distilled FINAL containing the unknown, and
the Controller decides what semantic work follows.
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
Throughout normal task work, the Controller alone notices possible reusable
knowledge from the user's instruction, its own architecture or governance
decisions, Investigator evidence, Executor FINAL results, Reviewer findings,
and Reasoning Specialist challenges. Keep that awareness in the Controller's
working context; do not create a candidate register, persisted admission state,
score, counter, or threshold, add a separate checkpoint, or interrupt an active
Workstream for memory review. Executors return their normal distilled result,
evidence, and decision-changing information. They do not track memory
candidates, spawn Curator, maintain durable INDEX navigation, or add a
durable-governance product to FINAL.

Near the task's natural end, as part of ordinary closure before `task-close`,
the Controller decides whether the task established, revised, invalidated, or
materially clarified reusable project knowledge and whether a concise, sourced,
retrievable memory entry would improve, constrain, or accelerate future
decisions or recovery. This is not limited to facts a future agent would
otherwise need to reinvestigate. When selected candidates exist, the Controller
hands a fresh Curator the selected candidates, their facts and
supporting evidence, exact relevant prior memory and INDEX navigation, and
canonical sources/documents needed to reconcile them. If there are no
candidates or no future decision value, finish without Curator; small ordinary
tasks can skip it entirely. No task-size or architecture-work trigger makes it
mandatory.

Existing documentation, source, instructions, tests, commits, and rollout
records are neither automatic exclusions nor a reason by themselves to create
memory. Use them as evidence, and do not duplicate canonical text. A future-
agent recovery entrance may summarize and link easy-to-locate canonical
material or preserve the decision basis that is spread across code, Host,
history, or design; do not impose a fixed split between memory and formal
documentation. Curator reconciles selected candidates with supplied prior
memory and canonical sources. If existing material is already sufficient, it
returns an explicit no-write conclusion. Keep `.agent-memory/` concise,
traceable, and linked; detailed raw evidence remains in canonical sources,
Artifacts, Git, or rollout records, with only the basis and references needed
for future recovery in memory. Implementer roles keep product/protocol
documentation and README aligned with current behavior; Reviewer challenges
semantic drift when selected.

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
when new decision-changing information arrives. A decision-changing unknown
requiring a Controller decision ends the child Workstream in FINAL. Do not send a
MESSAGE and stay ACTIVE for a wait.

The persistent root Controller has no fixed model, reasoning effort, or native
profile; Host/user selection applies. The native child profiles are Investigator (`gpt-6-luna`, `xhigh`), Curator (`gpt-6-luna`, `xhigh`), Reasoning Specialist (`gpt-6.1-sol`, `high`), Implementer (`gpt-6-luna`, `xhigh`), Focused Implementer (`gpt-6.1-sol`, `high`), Verifier (`gpt-6-luna`, `xhigh`), and Reviewer (`gpt-6.1-sol`, `high`).
Only Controller may explicitly select static Astra medium or xhigh profiles for
Focused Implementer or Reasoning Specialist before spawn, and only with current-task
user authorization. Automatic routing stops at Sol, including when uncertainty
crosses surfaces. Each profile retains
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

Choose one model/profile for the current Workstream from its work
shape, not as a ladder. The standard Implementer on Luna is the default for a
stable problem structure and direction, including remaining execution, local
code judgment, tests, synchronization, and mechanical consistency, regardless
of task size. Choose Focused Implementer on Sol when the smallest coherent
Workstream has a stable direction but inherently needs sustained reasoning
across coupled invariants, nonlocal effects, or constraints. Routine local
closures do not trigger a new role or profile choice. Astra medium and
xhigh remain exceptional profiles of
the same Focused Implementer role, available only with current-task user
authorization. Cross-surface uncertainty alone does not authorize Astra.
Choose the profile once for the Workstream. Importance, file count, cross-module
scope, number of local closures, or ordinary alternatives alone do not determine
the choice.

Keep the working set focused. Directly read known, decision-critical sources.
Use Scanner work for discovery over a larger or unknown evidence surface and
for a clearly large, low-reasoning-density collection that can be compressed
independently. With the Sol Focused Implementer profile, consider offloading
broad or exhaustive peripheral call-site, rollout/log, and residual-reference
collections when that removes an independent working set. With an Astra
Focused Implementer profile, explore evidence needed for the current Workstream
directly and use Scanner work only for a clearly large, low-reasoning-density
collection that can be compressed independently. The collection choice does
not predetermine which evidence is relevant. Targeted reading of known sources
remains part of the implementation role's work; small local searches may be
direct. Delegate when doing so removes an independent working set. Use its output as evidence. Children work only within their assigned semantic Workstream,
preserve Controller decisions and invariants, and return a decision-changing
unknown instead of changing them. Local code decisions belong to Implementer or
Focused Implementer.
Once the Workstream goal, authority, and boundary are known, batch the relevant source,
test, generation, and documentation reads, plan, and make coherent edits.
Avoid per-patch, per-read, or per-grep reasoning rounds unless new information
could change direction. Match verification to the changed behavior and its
concrete regression surface. Start with focused checks for the changed
contract, generated output, and acceptance. If those pass without a failure,
anomaly, or new broader-risk evidence, continue any remaining assigned local
closures within the Workstream. Broaden checks only for a concrete
compatibility or integration risk. After fixing a test failure, rerun the
smallest acceptance-relevant range and continue the Workstream. A commit, push,
or final report alone does not call for another test run. Do not use counts,
time, file or token limits, or a stopping state machine.
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

Before another semantic correction Workstream, distinguish a local implementation
defect from a decision-basis failure. During an active Workstream, the executor
fixes an ordinary local defect within the assigned scope in the same session and
reruns the smallest acceptance-relevant check. If review overturns an accepted invariant,
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
outside the active Workstream, Root may route a fresh Implementer Workstream.
Do not use counters, thresholds, risk scores, classifiers, or a state machine
for this routing.
Missing factual information routes to the Investigator role. Broad grep,
exhaustive residual references, and call-site discovery can use the Scanner
working pattern under Implementer, Focused Implementer, or Reviewer. The
Controller interprets findings,
decides whether to reopen the basis, selects any review, and decides when work
continues or ends.
Reviewer challenges a converged implementation Workstream; do not start it against
a still-mutating Implementer or Focused Implementer to obtain parallel progress. Findings return to the
Controller, which decides whether a fresh correction Workstream is needed.

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
`.milestones/INDEX.md` are model-maintained thin semantic navigation maps of
durable knowledge, not bare file listings. Keep entries concise about what
linked knowledge covers, when it is useful to read, and current versus
historical or superseded applicability where useful. The Controller reads the
maps and uses these descriptions to select exact recovery documents. Keep
currently relevant knowledge discoverable first; retain historical links when
they help explain earlier scope or decisions. Models choose natural paths,
hierarchy, and wording; there is no fixed schema or taxonomy, status classifier,
or state machine. Core never
interprets INDEX content, writes or rebuilds a catalog, or recursively scans
the filesystem. It performs only mechanical path, compare-and-swap, size,
link, and atomic-write checks. SessionStart only points to these maps; before
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
non-conflicting, traceable corpus and its relevant INDEX links by modifying,
merging, splitting, revising, narrowing, superseding, or deleting selected
entries. For those changes, Curator also judges whether the relevant semantic
navigation should change and updates it when needed. It does not scan the whole
corpus or decide architecture. When a `task-promote` call changes durable
navigation, the Controller supplies the optional model-authored `index_update`
in that same call. Core validates paths, CAS, size, links, and atomic writes;
it does not interpret or generate INDEX content.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. With persistent task intent or positive Host actor assurance, during an ACTIVE delegated managed task
the persistent Controller uses only
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
its runtime validation runs before Python starts. Runtime drift is evidence,
not a global work ban: detect it, diagnose concrete expected/actual differences,
then let the Controller decide to repair, restore, or explicitly accept a
legitimate upgrade within existing user authorization. Unknown runtime code
must not run as trusted. Ordinary source edits, tests, reads, and investigation
remain available through the assigned roles; report managed assurance UNKNOWN.
Changes to runtime/manifest/executable/package/hooks/profiles, Host upgrade or
topology, user configuration, control authority, and unexplained changes have
different consequences; a hash difference alone does not decide them. Deny
only unsafe managed control, child identity bypass, control-state writes,
fenced-session revival, or irreversible evidence replacement. If work continues,
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
native Completed status can satisfy lifecycle completion. Call `wait_agent` only
for a known unfinished child whose result is necessary to proceed. When blocked
on that child, use one blocking `wait_agent` call with `timeout_ms`
equal to the maximum advertised in the current turn's `wait_agent` tool
definition. The current turn's tool definition is the authority; never infer a
maximum from release defaults, configuration, history, or capability tables.
After a child FINAL, use its result and do not wait on it again. Repeat a timed-out
wait only while that child remains unfinished and necessary. A child reporting a
decision-changing unknown must end its Workstream in FINAL for Controller decision,
not send MESSAGE and remain ACTIVE for another wait. Do not periodically wake
the Controller to poll. If no usable
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
session with `--authority-contract <json>`; the current Hook witnesses the
explicit Controller operation without proving native Root or human authorship.
On DEFINITION_READY_ACTOR_UNKNOWN, definition configuration is ready; select
the actual human task instruction and contract in this explicit start operation.
Never manufacture a Root receipt. Ordinary work and explicit task admission
are governed by the human instruction with Host actor assurance UNKNOWN.
Codex 0.159.2 ThreadSpawn fields positively identify children; built-in Review
can share the owner session and omit them. Absence or a matching session alone
is not Controller proof. Known bound child and readonly rules still apply.
If operating as a managed child inside an ACTIVE task, follow the explicit
handoff and do not run project bootstrap, task-start, or task-abandon for the
parent's task; startup, admission, and continuation decisions belong to the
owning root Controller.
Do not choose `bootstrap-check` or `init` for normal startup, calculate an
executable hash in a shell wrapper, or select among internal SHA fields.
On CURRENT_CONTINUATION, the owner may continue or explicitly abort the
incomplete task using the exact `task-abandon` packet. An unbound pending spawn
needs trusted terminal recovery for ordinary task-abandon. The separate reviewed
repository source runner `tools/thaliris_offline_recovery.py` supports explicit
user-delegated offline administration while global integration is disconnected.
It archives exact state/lifecycle bytes, fences every extractable old session or
agent identity, and releases only the old task slot. Its authority is
OPERATOR_ASSERTED_USER_DELEGATED_ADMINISTRATION: flags are operator assertions,
not cryptographic consent, Host receipts, or Controller identity. All automated
actors, including ambiguous roots, are denied this operation while integration
is present. Unknown owner, unbound identity, incompatible fields, and Host
termination remain recorded UNKNOWN. Try native termination/observation for
known old children; missing death proof does not permanently lock this informed
recovery. The shared OS is not a privilege separation boundary. On FOREIGN_RECOVERY_DECISION or UNKNOWN, the Controller
explicitly decides whether to continue old work or use that exact recovery
packet before starting a fresh task. An abandoned task remains incomplete and its original
state and lifecycle evidence are preserved. On INVALID_STATE or a definition
conflict, diagnose the affected surface; never delete evidence or invent completion.
A configured CLI executable/version, shared daemon, process ancestry, environment,
or SessionSource does not prove a current Host session or Controller identity.
Use structured Hook event payloads; record CLI and daemon versions separately,
and retain UNKNOWN when the daemon version or current role catalog is unproved.
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
