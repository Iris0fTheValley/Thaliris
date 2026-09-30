# Thaliris Routing Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v3 -->

The marker identifies this routing contract for D11. Version 3 records the
effective native agent-profile rule below as part of the semantic contract;
the Codex lifecycle schema is independent of this marker.

## Single semantic path

```text
Controller --explicit native handoff--> Investigator / Curator / Reasoning Specialist / Implementer / Focused Implementer / Verifier / Reviewer
Role session --distilled result + optional Artifact pointer--> Controller
Controller --next explicit handoff--> next selected role session
Implementer / Focused Implementer / Reviewer --explicit fresh handoff--> Investigator (Scanner working pattern)
Scanner working pattern --distilled evidence--> requesting role
```

The Controller owns the complete user objective, its decomposition, role and
context choice, overall invariants, boundaries and acceptance, interpretation
of child results, and task-level decisions to reopen, review, continue, or end.
It chooses the minimum necessary fresh role and supplies the task, facts,
constraints, decisions, unknowns, and pointers to send. It may do bounded
reading to frame a handoff and interpret evidence, but does not perform broad
repository scans, implementation, or the full task test suite. The Investigator
role gathers broad evidence, including through the Scanner working pattern.
Implementer and Focused Implementer make local code decisions within their
accepted packets and Workstreams.
A missing fact is a Controller/model error; Core must not infer or append it.

For every task, the Controller selects the minimum necessary fresh semantic
roles. One top-level child may delegate one nested Investigator session doing
Scanner work at a time, at maximum
managed depth two. Roles are capabilities, not mandatory workflow stages.
This policy is identical for ACTIVE and degraded work; degraded mode does not
define a second routing flow. A straightforward, bounded, low-risk task with
confirmed facts may take the Controller -> fresh Implementer -> done path: the
Implementer may do necessary bounded local reading, implementation, and
deterministic verification. Decision-changing investigation belongs to the
Investigator role, which also handles broad scanning and factual compression
of large working sets, without architecture decisions. Bounded local reading
needed for implementation may stay inside Implementer or Focused Implementer.
Reviewer is conditional, not a mechanical post-implementation gate;
select it only when independent semantic review adds real value, such as
for architecture or cross-module changes, lifecycle, Host, identity, or
authority boundaries, compatibility invariants, multiple plausible
implementations, complex semantic repairs, or remaining correctness
uncertainty. Curator and Reasoning Specialist are optional and selected only
when they add actual value. Use Reasoning Specialist when an independent
challenge may materially change direction, including when framing appears
coherent or an outcome is unexpected. It tests hidden assumptions, causal
models, decomposition, boundaries, decision basis, premature convergence, and
direction-changing alternatives. Difficulty alone is not a trigger.

With INVALID_STATE, the PreToolUse guard denies only mechanically recognized
Controller-owned state mutations: direct Thaliris task/lifecycle mutations and
obvious writes to `.context/state.json` or lifecycle state. Unknown tools,
coordination, diagnostics, and reads remain transparent. This does not prove
managed enforcement. Damaged state does not transfer child semantic duties
to Root. If Investigator or Implementer is unavailable, Root may diagnose
the managed failure, read the evidence needed for that diagnosis, coordinate,
and report; it does not take over substantial repository investigation,
implementation, or testing.

At task end, before `task-close`, the Controller makes one short semantic
judgment: did the task add, change, or overturn durable knowledge that could
affect a future decision and would otherwise require reinvestigation? If no,
it silently skips Curator. If yes, it selects a fresh Curator and supplies the
selected durable facts and exact relevant prior knowledge/documents. Curator
is optional, never selected by task size, and not a mandatory stage. Curator
maintains only Controller-selected durable knowledge under `.agent-memory/`
and relevant links in `.agent-memory/INDEX.md`. Preserve provenance and scope
for each retained claim; when new evidence updates or supersedes a conclusion,
preserve its original scope and historical applicability where relevant. Keep
the corpus small, current, non-conflicting, and traceable. Exclude task
chronology, implementation logs, ordinary commit histories, transient test
outputs, and momentary failures unless they establish stable knowledge that
could affect a future decision. If consistency depends on durable material the
Controller did not select, stop and report the missing knowledge area for the
Controller to select; do not scan the corpus. Product/protocol docs and README
aligned with current behavior belong to Implementer or Focused Implementer.
Curator does not make architecture decisions or delegate. Detailed evidence
stays in Artifacts, Git, or rollout records rather than memory. `CHANGED`
reports an evidence change, not semantic invalidation. The Controller may
request revalidation when a decision depends on changed evidence and has
become unreliable.

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
assigned Git closure. A local verification PASS does not require returning to
Root. Ordinary test fixes, generated or documentation synchronization,
integration checks, and assigned Git closure are execution checkpoints inside
the Workstream, not separate semantic routing boundaries. The child retains
execution authority only within the assigned goal, scope, invariants, and
acceptance; this authority never expands Controller-assigned scope.

Root regains control at the semantic Workstream boundary. A child returns
distilled state, its commit reference, and verification evidence after its
assigned Workstream is complete. If new evidence changes task direction,
ownership, observable semantics, a hard invariant, compatibility contract, or
acceptance, or reveals an unverified external dependency that can change the
decision, the child stops and returns the concrete unknown in FINAL for Root to
decide. Only the Controller decides what follows; no child acts as a second
semantic Controller. Do not use file, tool, token, time, or local-closure
counts to end a Workstream or to choose the executor profile.

When completed Investigator discovery is selected for a later semantic Workstream,
the Controller handoff carries confirmed facts, exact source locations and
affected surfaces, relevant unknowns or contradictions, and covered and
uncovered scope. Implementer or Focused Implementer starts from this selected
map, directly reopening decision-critical originals, call chains, diffs, and
tests as needed for implementation. It does not reconstruct the same broad
inventory or delegate a Scanner over the covered surface. A fresh Scanner may
collect only a genuinely uncovered decision-changing evidence gap needing
independent broad discovery, limited to that gap. Evidence coverage is judged
semantically; it does not create a cache, threshold, state machine, or new
evidence system.

Before choosing an opportunistic discovered slice, the Controller confirms that
each explicit user goal has been addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic rule, not a mechanical checklist
or state machine. Focused Implementer can complete complex implementation as
well as focused reasoning. Implementer and Focused Implementer directly inspect
known, decision-critical sources, including source code, relevant call chains,
the current diff, failed tests, and raw evidence. Scanner is a nested
Investigator discovery working pattern, not a separate role. Scanner work
discovers over a larger or unknown evidence surface, or compresses a clearly
large, low-reasoning-density collection that can be handled independently. It
returns key conclusions, exceptions, UNKNOWNs, and accurate raw locations. The
collection choice does not predetermine which evidence is relevant and does
not replace reasoning-coupled reading; targeted rereading of relevant
originals is useful. With the Sol Focused Implementer profile, consider
offloading broad or exhaustive peripheral call-site, rollout/log, and
residual-reference collections when doing so removes an independent working
set. With an Astra Focused Implementer profile, explore evidence needed for
the current Workstream directly and use Scanner work only for a clearly large,
low-reasoning-density collection that can be compressed independently. Small
local searches may be direct.
Focused Implementer continues complex implementation within its assigned
Workstream across local checkpoints when it still benefits from focused
reasoning. A local verification PASS does not force a return to Root. Close the
Workstream only at its semantic boundary or when its assigned acceptance is
complete. A deterministic remainder goes to Controller routing only when it
is outside the Workstream or independently closable without the Focused model's
reasoning.

Once the Workstream goal, authority, and boundary are known, Implementer and
Focused Implementer batch the relevant source, test, generation, and
documentation reads, form a plan, and make coherent edits. Avoid per-patch,
per-read, or per-grep reasoning rounds unless new information could change
direction. Match verification to the changed behavior and its concrete
regression surface. Start with focused checks for the changed contract,
generated output, and acceptance. If they pass without a failure, anomaly, or
new broader-risk evidence, continue any remaining assigned local closures
within the Workstream. Broaden checks only for a concrete compatibility or
integration risk. After a test fix, rerun the smallest acceptance-relevant
range and continue the Workstream. A commit, push, or final report alone does
not call for another test run. Do not use counts, time, file or token limits,
or a stopping state machine.

Controller has no fixed model, effort, or native profile. The Host/user selects
its model. Investigator, Curator, and standard Implementer use
`gpt-6-luna/xhigh`; Focused Implementer, Reasoning Specialist, and Reviewer use
`gpt-6-sol/high`. Verifier remains read-only `gpt-6-luna/xhigh` for
compatibility and is not recommended. Only Controller may explicitly choose
static Astra medium or xhigh profiles before spawn, only with current-task user
authorization. Automatic routing stops at Sol, including cross-surface
uncertainty. Each profile maps to the
same stable semantic role identity; defaults remain Luna or Sol. Per-spawn
model/effort overrides are denied. Role sessions cannot choose their own
model/effort. Reasoning Specialist independently challenges selected framing
and its decision basis; local implementation decisions belong to Implementer
and Focused Implementer.

Native agent definitions may come from personal `~/.codex/agents` or project
`.codex/agents`. The TOML `name` is the agent identity; the filename is only a
source location. D11 checks generated project files and effective Host treatment
separately. For a name defined in both locations, identical parsed definitions
retain both provenance records. Conflicting definitions fail closed as
`EFFECTIVE_AGENT_PROFILE_AMBIGUOUS` because their precedence is unverified.
Project trust in `config.toml` is a separate fact and does not by itself prove
that a project-only agent definition is active. The active native catalog and
selected profile still require Host observation.

Routing terms: Investigator, Implementer, and Focused Implementer are semantic
roles. Scanner is a nested Investigator discovery working pattern, not a
separate role. Executor is a category covering Implementer and Focused
Implementer, not a selectable or spawnable role; route by the actual role name.
A native execution profile selects model and effort for a semantic role and
does not create another role.

Choose one model/profile for the current Workstream from its work shape, not as
a ladder. Standard Implementer on Luna is the default for a stable problem
structure and direction, including remaining execution, local code judgment,
tests, synchronization, and mechanical consistency, regardless of task size.
Choose Focused Implementer on Sol when the smallest coherent Workstream has a
stable direction but inherently needs sustained reasoning across coupled
invariants, nonlocal effects, or constraints. Routine local closures do not
trigger a new role or profile choice. Choose a Focused
Astra medium and xhigh remain exceptional profiles of the same Focused
Implementer role, available only with current-task user authorization.
Cross-surface uncertainty alone does not authorize Astra. Choose the profile
once for the Workstream. Importance, file count, cross-module scope, number of
local closures, or ordinary alternatives alone do not determine the choice.
Use Reasoning Specialist on Sol when an independent challenge may materially
change direction. It reports the strongest challenge, material alternatives,
and critical missing facts for the Controller to route; it does not make the
final decision or implement. It does not gather broad facts, conduct routine
review, or solve an ordinary hard problem for its own sake.

Keep the working set focused. Implementer and Focused Implementer directly read known,
decision-critical sources. Use Scanner work for discovery over a larger or
unknown evidence surface, or to compress a clearly large, low-reasoning-density
collection. With the Sol Focused Implementer profile, consider offloading broad
or exhaustive peripheral call-site, rollout/log, and residual-reference
collections when this removes an independent working set. With an Astra Focused
Implementer profile, explore evidence needed for the current Workstream directly and
use Scanner work only for a clearly large, low-reasoning-density collection
that can be compressed independently. The collection choice does not
predetermine which evidence is relevant. Small local searches may be direct.
A Scanner batches related searches and reads, returns compact facts, and once
evidence is sufficient stops immediately; do not expand the scan for one more
confirmation.
Only Implementer, Focused
Implementer, and Reviewer may delegate a fresh Investigator for Scanner work. The remaining child roles
cannot delegate. Fresh children always use `fork_turns="none"`. Implementer and Focused Implementer work
only within their assigned semantic Workstream, preserve Controller decisions
and invariants, and return a decision-changing unknown rather than changing them.
They synchronize formal project documentation, including product/protocol docs
and README, for behavior changed within their Workstream. Focused Implementer waits
for a delegated Scanner's distilled discovery result and does not repeat its
discovery pass; after that, it may reopen relevant originals to verify the
evidence while retaining implementation responsibility. Reviewer challenges
semantic drift between a candidate and its formal project documentation when
selected.

When Thaliris routing, roles, bootstrap, trust boundaries, or Controller
contracts change, check and synchronize both the repository-managed instruction
and the currently effective Codex global instruction.

`thaliris codex-install` also maintains one marker-owned startup block in
`CODEX_HOME/AGENTS.md`. For substantive Git repository changes, including a
README task, without an explicit opt-out, that block gives one direct absolute
installed `thaliris-run.cmd --root <repo> codex-bootstrap` command. The wrapper
validates the complete installed runtime against `CODEX_HOME/thaliris-install.json`
before starting Python. Bootstrap reads
task state first, and performs one project `init` only for a missing definition.
It returns READY with one opaque `task_start_receipt` for same-session
`task-start --bootstrap-receipt`. The current Hook must attest task start. ACTIVE
returns exact state and lifecycle identities and owner evidence for a Controller
continuation or explicit `task-abandon` decision; it never initializes. Without
a current-session Host proof, owner match remains UNKNOWN. Invalid task state
also blocks initialization. Chatting, informational questions, read-only work,
and non-Git directories are excluded. The startup block does not carry task
routing policy or mutate repositories from a hook. Install replaces
only the well-formed `thaliris:global` span; uninstall removes only that span.
Text outside the span remains byte-for-byte intact, and damaged, duplicate, or
conflicting Thaliris markers require manual resolution. A newly saved global
instruction does not prove what the current session loaded.

Host maintenance uses a separate checkout and Codex session from an ACTIVE
project task. The maintenance checkout can edit and test Thaliris source and
replace the installed runtime, hooks, profiles, or global instruction without
altering the other project's lifecycle ledger. An ACTIVE Controller permits
only direct `codex-install` and `codex-uninstall` invocations through an exact
identity-checked installed route; ordinary project commands remain blocked by
the managed role boundary. When `codex-uninstall` is invoked through its own
Windows runner, the runner is retained inert after manifest removal and is
reported as such. Direct uninstall or reinstall can remove or replace it later.
The previous exact runner template has no self-invocation marker, so uninstall
also retains it on the first call while its manifest exists. A later direct
call removes the inert runner.

An owner may explicitly abort an incomplete ACTIVE task with its exact
recovery packet. The original state and lifecycle bytes remain archived as
incomplete, and the owner session can start a new task. A pending unbound
spawn blocks owner abort until exact trusted native failure evidence recovers
that reservation. An unknown child identity cannot be fenced. Pending-spawn
recovery accepts a name-bound native `interrupted`, `errored`, or `shutdown`
observation, or an exact spawn failure callback; `not_found`, successful
completion, absent callbacks, and timeouts do not release the reservation.
After owner abort, a spawn callback without a native tool call ID attaches a
name only when its session, reserving turn, agent type, and handoff match the
new reservation and differ from every recorded old spawn. Missing old
provenance or an identical old and new spawn remains uncorrelatable and fails
closed. A native tool call ID, when present on both events, remains the exact
correlation key.

`SubagentStart` is lifecycle-only. It validates the authorized native Codex child and binds
identity, role, session, start time, provenance, handoff ID, and payload hash.
It does not construct a role packet or inject task state.

## Private work and return

The Scanner working pattern absorbs large mechanical working sets; Implementer,
Focused Implementer, and Reviewer retain a focused private working set. The default result is a concise
conclusion, key findings, decision-changing unknowns, contradictions,
verification performed, and optional Artifact references. The detailed working
set does not automatically re-enter the Controller.
Child sessions do not send ordinary progress, heartbeat, or partial-completion
messages to the parent. They proactively wake the parent only when completed,
blocked and requiring a parent decision, or when new decision-changing
information arrives. A decision-changing unknown requiring a Controller
decision ends the Workstream in FINAL. The child does not send MESSAGE and remain
ACTIVE for another wait. Follow-up and input tools remain denied for managed
children.
Scanner results return to their requesting Implementer, Focused Implementer,
or Reviewer.

When detailed material should survive, the selected role session writes a free-form Markdown or
JSON Artifact and returns its pointer. Registration records path and content
identity; it does not read, summarize, interpret, or propagate the body.

## Explicit retrieval

Artifact bodies and durable documents are available only through explicit
exact-path retrieval. `catalog` lists bounded metadata; `document-get` reads one to eight named paths. A Controller
may copy selected retrieved content into a later native handoff.

## Mechanical observations

Freshness reports recorded versus current file identities. Verification reports
an observed invocation and result identity. Task surface reports baseline,
current state, and delta. The Controller decides what any observation means.

## Native boundary

The Host owns creation, execution, waiting, continuation, and result delivery.
The adapter owns fresh isolation, bounded depth-two lifecycle, identity binding,
and wait normalization for real pending dependencies only when a current-session
effective maximum is mechanically verified; otherwise it performs no automatic
long-wait normalization. Core owns durable records,
CAS, atomicity, hashes, provenance, addressing, and explicit retrieval.

No hidden auditor, role projection, semantic dependency graph, correction state
machine, or benchmark authority participates in this production path.

The flat adapter ledger adds parent agent hash, parent role, parent turn hash,
depth, and root handoff ID. A nested PreToolUse must match the live bound
parent's exact agent ID, role, session, and turn. One global reservation is
consumed only by a matching SubagentStart, which binds the Scanner's own
agent/turn identity; future Scanner tool calls must match that identity.
Start lacks parent ID on the observed wire, so the adapter uses the unique
authorized reservation, never path or shared session identity as parent proof.
Missing or conflicting identity denies execution. SubagentStart cannot block
native creation; an unbound child is blocked on its first tool call.

One live managed Codex CLI `0.155.0-alpha.9.2` probe on 2026-09-25 verified the
exact reservation, `SubagentStart`, and bound Scanner `PreToolUse` acceptance at
depth two. The Scanner result returned and the Focused Implementer parent
continued. See the [durable probe evidence](codex-nested-scanner-live-20260925.md).
This is evidence for that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain **UNKNOWN**.
The identity binding and fail-closed mechanics above are unchanged.

A Codex Desktop probe on 2026-09-28 observed `wait_agent` return
`{"message":"Wait completed.","timed_out":false}` after the child completed.
Call `wait_agent` only for a known unfinished child whose result remains
necessary. After Scanner FINAL, its parent uses the result and does not wait
on that Scanner again. Repeat a timed-out wait only while the same dependency
remains unfinished and necessary.
That response contains no child identity or terminal status. Desktop
`list_agents` responses have supplied an exact `agent_name` and an
`agent_status` with a `completed` result. After a child finishes, the
Controller calls `list_agents` once before `task-close`; lifecycle accepts
only the exact name-bound status for its managed child. If it is unavailable,
completion remains UNKNOWN and closure remains denied. End-to-end Desktop
`list_agents`/`task-close` closure has not yet been observed.

Task-close requires the latest Controller-direct handoff's matching Start,
Stop, and native Completed observation, with no pending or active descendants.
A later Scanner neither displaces that handoff nor supplies its completion
proof. Core task-close, record producer labels, retrieval, and Artifact rules
are unchanged. Previous flat lifecycle version 11 is not upgraded into nested
authority; current managed work requires version 12 records.

Correction routing is semantic and Controller-owned. A Reviewer finding that
overturns an accepted invariant, depends on an unproved external capability,
makes feasibility uncertain, or changes a Controller boundary/contract first
reopens the decision. Missing factual information goes to Investigator. When an
independent challenge may materially change direction, the Controller can route
the selected framing and evidence to Reasoning Specialist, including coherent
framing, hidden assumptions, causal models, decomposition, boundaries, decision
basis, premature convergence, and unexpected outcomes. The Specialist reports
critical missing facts for the Controller to route and does not make the final
task decision. Do not select it for broad fact gathering, implementation,
routine review, or ordinary hard-problem solving; difficulty alone is not a
trigger. Only a local implementation defect with the accepted design unchanged may go
directly to a fresh Implementer. An Implementer that encounters an unverified
external fact, an invalidated invariant, or a changed decision basis returns it
as a decision-changing unknown without expanding scope.

Verifier compatibility does not replace independent review when authority, provenance,
Host lifecycle, identity, trust, migration, or bootstrap semantics still
warrant independent challenge. Workspace anomalies are observations, not
candidate defects, unless the candidate introduced them, the modification
boundary owns them, or acceptance requires changing them. Historical/generated
ownership must come from exact independent historical evidence; current HEAD
must not establish its own historical authority.
