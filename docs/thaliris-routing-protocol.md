# Thaliris Routing Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v2 -->

## Single semantic path

```text
Controller --explicit native handoff--> Investigator / Curator / Reasoning Specialist / Implementer / Focused Implementer / Verifier / Reviewer
Role session --distilled result + optional Artifact pointer--> Controller
Controller --next explicit handoff--> next selected role session
Implementer / Focused Implementer / Reviewer --explicit fresh handoff--> Investigator (Scanner)
Scanner --distilled evidence--> requesting Executor / Reviewer
```

The Controller owns task-specific semantic routing. It chooses the Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, or Reviewer,
task, facts, constraints, decisions, unknowns, and pointers to send. A missing
fact is a Controller/model error; Core must not infer or append it.

For every task, the Controller selects the minimum necessary fresh role
sessions. One top-level child may delegate one Scanner at a time, at maximum
managed depth two. Roles are capabilities, not mandatory workflow stages.
This policy is identical for ACTIVE and degraded work; degraded mode does not
define a second routing flow. A straightforward, bounded, low-risk task with
confirmed facts may take the Controller -> fresh Implementer -> done path: the
Implementer may do necessary bounded local reading, implementation, and
deterministic verification. Decision-changing investigation belongs to
Investigator. The Investigator/Scanner also handles broad scanning and factual
compression of large working sets, without architecture decisions. For a broad
task whose semantic slice is unclear, the Controller first uses a standard Luna
Investigator for facts and coupling. The Scanner batches a few searches and
reads, returns compact facts, and ends once the handoff has enough evidence.
Bounded local reading
needed for implementation may stay inside either Executor. Reviewer is conditional, not a mechanical post-implementation gate;
select it only when independent semantic review adds real value, such as
for architecture or cross-module changes, lifecycle, Host, identity, or
authority boundaries, compatibility invariants, multiple plausible
implementations, complex semantic repairs, or remaining correctness
uncertainty. Curator and Reasoning Specialist are optional and selected only
when they add actual value.

With INVALID_STATE, the PreToolUse guard denies only mechanically recognized
Controller-owned state mutations: direct Thaliris task/lifecycle mutations and
obvious writes to `.context/state.json` or lifecycle state. Unknown tools,
coordination, diagnostics, and reads remain transparent. This does not prove
managed enforcement. Damaged state does not transfer child semantic duties
to Root. If Investigator or Implementer is unavailable, Root may diagnose
the managed failure, read the evidence needed for that diagnosis, coordinate,
and report; it does not take over substantial repository investigation,
implementation, or testing.

At task end, the Controller makes one short semantic judgment about whether
a concise conclusion could change a future decision and needs durable
maintenance. It selects a fresh Curator only for that purpose and supplies
the selected material in a concise handoff. Curator maintains the selected
documents and relevant index links as a small, current, non-conflicting,
traceable corpus. It may modify, merge, split, supersede, or delete entries;
it does not scan the full corpus or decide architecture. Detailed evidence
stays in Artifacts, Git, or rollout records rather than memory. `CHANGED`
reports an evidence change, not semantic invalidation. The Controller may
request revalidation when a decision depends on changed evidence and has
become unreliable.

For divisible work, the Controller chooses bounded semantic slices instead of
handing an entire multi-slice stage to a higher-capability Executor. Define
slice boundaries by semantic dependencies, decision coupling, implementation
uncertainty, and independent closure, not by token, file, or task-count
thresholds. Prefer slices that can each be independently understood,
implemented, verified, committed, and closed. A completed slice returns
distilled state, its commit reference, and verification evidence; discard its
working set when closed.

When a broad task has an unclear semantic slice, the Controller first selects
the standard Luna Investigator to establish facts and coupling. After a Focused
Implementer delegates broad collection, it waits for compact distilled evidence
and reads only bounded immediate files; it does not duplicate the Scanner's
working set. When high-difficulty semantic closure is complete, the Focused
Implementer reports the deterministic patch, test, format, documentation, and
residual-reference tail to the Controller. The Controller owns closure of the
Focused slice and may authorize a fresh standard Luna Implementer handoff for
that deterministic tail. Model choice follows the difficulty of the current
slice, not the parent task.

Controller has no fixed model, effort, or native profile. The Host/user selects
its model. Investigator, Curator, and standard Implementer use
`gpt-6-luna/xhigh`; Focused Implementer, Reasoning Specialist, and Reviewer use
`gpt-6-sol/high`. Verifier remains read-only `gpt-6-luna/xhigh` for
compatibility and is not recommended. Only Controller may explicitly choose
static Astra medium or xhigh profiles before spawn for exceptional reasoning.
These profiles map to the same stable IDs; defaults remain Luna or Sol. Per-spawn
model/effort overrides are denied. Role sessions cannot choose their own
model/effort. Reasoning Specialist reframes ill-defined
problems; normal design and implementation belong to the Executors.
Choose the model per handoff and semantic slice difficulty. Deterministic
documentation, test, configuration, or reference cleanup and small defined
implementations default to standard Implementer on Luna, even within a large
project. Use Focused Implementer on Sol only when the current slice itself
requires complex lifecycle, ownership, compatibility, or multi-option reasoning.
Use Reasoning Specialist on Sol only when problem framing or slice decomposition
is unclear; it does not implement. Astra is an escalation for an already small,
unusually demanding slice or an evidenced Sol failure. Astra medium is the
default escalation; xhigh requires a clear reason.

Keep the working set focused. Delegate broad repository scanning, exhaustive
call-site search, residual-reference checks, and other large mechanical
investigation to the Scanner. Use Scanner output as evidence; retain
responsibility for implementation decisions. Only Implementer, Focused
Implementer, and Reviewer may delegate Investigator. The remaining child roles
cannot delegate. Fresh children always use `fork_turns="none"`. Executors work
only within their assigned semantic slice, preserve Controller decisions and
invariants, and return a decision-changing unknown rather than changing them.
They synchronize formal project documentation for behavior changed within
their slice. After a Focused Implementer delegates broad collection, it waits
for the distilled evidence and reads only bounded immediate files; it does not
duplicate the Scanner's broad working set. When high-difficulty semantic
closure is complete, it reports the deterministic patch, test, format,
documentation, and residual-reference tail to the Controller. The Controller
owns closure of the Focused slice and may authorize a fresh standard Luna
Implementer handoff for that deterministic tail. Reviewer challenges semantic
drift between a candidate and its formal project documentation when selected.

When Thaliris routing, roles, bootstrap, trust boundaries, or Controller
contracts change, check and synchronize both the repository-managed instruction
and the currently effective Codex global instruction.

`thaliris codex-install` also maintains one marker-owned startup block in
`CODEX_HOME/AGENTS.md`. For substantive Git repository changes, including a
README task, without an explicit
opt-out, that block directs the Controller through a trusted one-shot
`bootstrap-check` even when no project marker exists, then `init` if the
definition or activation marker is missing. Chatting, informational questions,
read-only work, and non-Git directories are excluded; confirmed readiness is
not rechecked, and ACTIVE tasks do not run `init`. The installed instruction
includes the exact executable path and SHA-256 used for Host integration, so
the Controller can verify and invoke that direct route even if an ordinary PATH
command is stale. It requires the explicit bridge digest at same-session
`task-start`; the loaded hook's bearer check is described below. It does not
carry task routing policy or mutate repositories from a hook. Install replaces
only the well-formed `thaliris:global` span; uninstall removes only that span.
Text outside the span remains byte-for-byte intact, and damaged, duplicate, or
conflicting Thaliris markers require manual resolution. A newly saved global
instruction does not prove what the current session loaded.

The `task-start` bridge also requires a one-shot PreToolUse bearer attestation
from the loaded current-ABI hook. The token embeds a hash of the hook payload's
session id; the adapter checks that hash, bridge digest, hook ABI, expiry, and
one-time local record. This is an adapter-side hook-path check inside the
selected same-Windows-user local trust boundary. It does not authenticate Host
provenance, and another local process under that user could replay the bearer
while it remains valid.

The scoped live sequence is recorded in the [admission proof probe report](codex-admission-live-20260926.md).

`SubagentStart` is lifecycle-only. It validates the authorized native Codex child and binds
identity, role, session, start time, provenance, handoff ID, and payload hash.
It does not construct a role packet or inject task state.

## Private work and return

The Scanner absorbs large mechanical working sets; Executors and Reviewer
retain a focused private working set. The default result is a concise
conclusion, key findings, decision-changing unknowns, contradictions,
verification performed, and optional Artifact references. The detailed working
set does not automatically re-enter the Controller.
Child sessions do not send ordinary progress, heartbeat, or partial-completion
messages to the parent. They proactively wake the parent only when completed,
blocked or needing a decision, or when a decision-changing fact arrives. Direct
`send_message` to the exact bound parent remains
available for genuine decision-changing information, with no automatic wake
filter. Follow-up and input tools remain denied for managed children.
Scanner results return to their requesting Executor/Reviewer.

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

Task-close requires the latest Controller-direct handoff's matching Start,
Stop, and native Completed observation, with no pending or active descendants.
A later Scanner neither displaces that handoff nor supplies its completion
proof. Core task-close, record producer labels, retrieval, and Artifact rules
are unchanged. Previous flat lifecycle version 11 is not upgraded into nested
authority; current managed work requires version 12 records.

Correction routing is semantic and Controller-owned. A Reviewer finding that
overturns an accepted invariant, depends on an unproved external capability,
makes feasibility uncertain, or changes a Controller boundary/contract first
reopens the decision; the Controller then chooses Investigator for missing
facts or Reasoning Specialist to reframe an ill-defined problem from known facts. Only
a local implementation defect with the accepted design unchanged may go
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
