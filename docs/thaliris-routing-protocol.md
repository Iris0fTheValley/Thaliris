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
Investigator/Scanner also handles broad scanning and factual compression of
large working sets, without architecture decisions. Bounded local reading
needed for implementation may stay inside either Executor. Reviewer is conditional, not a mechanical post-implementation gate;
select it only when independent semantic review adds real value, such as
for architecture or cross-module changes, lifecycle, Host, identity, or
authority boundaries, compatibility invariants, multiple plausible
implementations, complex semantic repairs, or remaining correctness
uncertainty. Curator and Reasoning Specialist are optional and selected only
when they add actual value.

For divisible work, the Controller chooses bounded semantic slices instead of
handing an entire multi-slice stage to a higher-capability Executor. Define
slice boundaries by semantic dependencies, decision coupling, implementation
uncertainty, and independent closure, not by token, file, or task-count
thresholds. Prefer slices that can each be independently understood,
implemented, verified, committed, and closed. A completed slice returns
distilled state, its commit reference, and verification evidence; discard its
working set when closed.

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
Route low-difficulty, high-certainty slices to standard Implementer on Luna,
even within a large project. Use Focused Implementer on Sol for complex,
creative lifecycle, ownership, or compatibility work. Use Reasoning Specialist
on Sol only when problem framing or slice decomposition is unclear; it does not
implement. Astra is an escalation for an already small, unusually demanding
slice or an evidenced Sol failure. Astra medium is the default escalation;
xhigh requires a clear reason.

Keep the working set focused. Delegate broad repository scanning, exhaustive
call-site search, residual-reference checks, and other large mechanical
investigation to the Scanner. Use Scanner output as evidence; retain
responsibility for implementation decisions. Only Implementer, Focused
Implementer, and Reviewer may delegate Investigator. The remaining child roles
cannot delegate. Fresh children always use `fork_turns="none"`. Executors work
only within their assigned semantic slice, preserve Controller decisions and
invariants, and return a decision-changing unknown rather than changing them.

When Thaliris routing, roles, bootstrap, trust boundaries, or Controller
contracts change, check and synchronize both the repository-managed instruction
and the currently effective Codex global instruction.

`thaliris codex-install` also maintains one marker-owned startup block in
`CODEX_HOME/AGENTS.md`. That block only discovers a project's activation marker
or managed instruction and directs the Controller through `bootstrap-check`,
`init` when needed, and the explicit bridge digest at `task-start`. It does not
carry task routing policy or mutate repositories from a hook. Install replaces
only the well-formed `thaliris:global` span; uninstall removes only that span.
Text outside the span remains byte-for-byte intact, and damaged, duplicate, or
conflicting Thaliris markers require manual resolution. A newly saved global
instruction does not prove what the current session loaded.

`SubagentStart` is lifecycle-only. It validates the authorized native Codex child and binds
identity, role, session, start time, provenance, handoff ID, and payload hash.
It does not construct a role packet or inject task state.

## Private work and return

The Scanner absorbs large mechanical working sets; Executors and Reviewer
retain a focused private working set. The default result is a concise
conclusion, key findings, decision-changing unknowns, contradictions,
verification performed, and optional Artifact references. The detailed working
set does not automatically re-enter the Controller.
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

Direct-child wire fields were observed in an isolated Codex CLI
`0.155.0-alpha.9.2` probe on 2026-09-23. Native desktop depth-two creation and
parent-directed result delivery were observed, but no desktop hook payload
was captured; nested CLI creation failed with `no thread with id`.
Grandchild hook identity equality therefore remains **UNKNOWN**. The shaped
fixtures test the fail-closed contract, not live managed activation.

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
