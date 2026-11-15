# Thaliris Routing Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v3 -->

The historical routing marker is retained for benchmark compatibility. This
document explains shared semantics; Host mechanics and native profiles belong
to adapters. Core stores observations and selected intent, not semantic decisions.

Thaliris is a Git-native context orchestration controller. Its guards prevent
ordinary agents from acting outside their selected task, role or lifecycle;
they are not an authentication or privilege framework for malicious actors
with the same OS access. Selected human intent and its persistent task contract
authorize work. Native session, Hook and runtime observations describe execution
and association; missing observation is not itself a violation and never becomes
a universal PASS. Known child and readonly restrictions, fences, retired tasks,
exact Workstream association, conflicting evidence, user-owned bytes and separate
Host-maintenance authority remain binding.

Tasks have explicit Task IDs. State, authority, reservations and recovery evidence
belong to that task; a shared workspace's old ACTIVE record does not select a new
session's task or prove a write conflict. Preserve old evidence for explicit recovery.
Missing Host fields are UNKNOWN, distinct from actual identity conflict or role
violation. Damaged authority restricts the managed controls and certifications that
depend on it; ordinary diagnostics and independent work retain their role boundaries.
Preserve user-owned unknown bytes, file CAS, immutable raw contracts and history.
Authorized independent tasks may establish current baselines; software/configuration
evolution does not permanently bind ordinary work to an old runtime baseline.

## Ownership and handoff

Controller retains the full original goal, direction, scope and acceptance criteria, global facts and hard
invariants, distilled child conclusions, contradictions and UNKNOWN, current candidate
judgments, context selection and next routing. The child owns the delegated investigation,
implementation and local verification working set. Executor owns implementation design
and methods within that boundary. A decision-complete handoff carries selected local goal/acceptance,
confirmed facts, authoritative source and derived relationships, affected surfaces,
hard invariants/decided boundaries, usable verification entry and decision-changing
unknowns. Include source locations and covered/uncovered scope from selected discovery.
Resolve ambiguity from the request and confirmed facts; bound the transformation in
cleanup, synchronization or migration. Recommendations are non-binding.

Use a stable narrative base language and preserve precision-bearing original terms,
quotations, distinctions and user formulations when translation would materially
blur, broaden, narrow or expand meaning. Avoid forced monolingual translation,
random language switching and bilingual repetition. Output language requirements
still govern. Compression and handoff retain this precision-bearing representation.
For operational artifact or installation acceptance, Controller selects the
authoritative artifact, source, revision and provenance before delegation, or
explicitly assigns that selection to a later Workstream before its operational
acceptance.

Fresh children receive only the authorized parent's native handoff and explicitly
selected material, not an automatic task-state/memory projection. Their private
working set is larger than the distilled result sent back. Reuse established
inventory; reopening decision-critical originals is part of execution. A Scanner
collects only an independent uncovered discovery gap, not a duplicate inventory.

Controller owns the full user requirements and global acceptance; children receive only
selected local goals, acceptance, facts and source pointers. Carry opaque related requirement
refs and handoff/workchain provenance without projecting global task history into children.
When an already discovered fact changes a child's local conclusion, local acceptance or a
critical UNKNOWN, the child records it with source refs and selected handoff/requirement provenance.
This creates no additional search duty or global-importance judgment, model call or acceptance gate.

A child ends its final message with one fenced `thaliris-claims` block: the literal `none`,
or at most five claims `{requirement, polarity: supports|contradicts|unknown, text, evidence,
basis: check|read|inference}`, where `evidence` is a declared check id or `path:line`. The
adapter ingests it. `contradicts` and `unknown` become ordinary observations with the handoff's
provenance. `supports` are counted per requirement on the handoff and create no obligation. A
claim about a requirement outside the handoff's refs becomes an unassigned observation. A
missing or malformed block is recorded as a marker and listed as a handoff without typed
claims. Claims carry no confidence value.

Attribute evidence to its source: facts established by Controller, imported historical child
results and independent review remain distinct. This provenance distinction does not change
execution mode, tool permissions or child authority.

Keep critical observations globally visible across later handoffs until Controller explicitly
reassesses each related USER REQUIREMENT for the current candidate: satisfied, unknown,
repair, or a reason it no longer affects that candidate. Reading, retrieving, acknowledging,
or forwarding evidence is not disposition. Neither test PASS, Reviewer READY, native
Completed nor mechanical DONE substitutes for this requirement judgment. Incorporated
unknown/repair judgments remain visible as unresolved requirements; an incorporation record
alone does not mean satisfaction. Preserve previous observations and judgments as history;
an old handoff observation is not automatically current truth. The immutable `candidate`
on a handoff/observation is a logical workstream label, not a repository snapshot. Repair
may change files within that label. Source refs and optional producer-selected
`observed_state` distinguish local observations; absent state identity remains UNKNOWN.
Matching candidate labels do not establish identical actual states. The existing
verification-result `candidate_identity` describes its dedicated verification snapshot;
it is not an automatic identity for every observation.

Nested delegation retains parent provenance without inferring global relevance. A nested
handoff may have empty requirement refs; its observation stays visible as unassigned
until Controller cites it in a selected requirement judgment. Children never select
global relevance. A subsequent satisfied judgment citing fresh positive evidence alone
does not remove an earlier unaddressed repair/unknown basis from the bounded view.
Controller explicitly addresses that basis through prior `judgment_refs` and reasoning,
or its complete observation refs. These append-only mechanical links avoid repeating
the full history and create no semantic acceptance or task-close gate.

An adapter whose native dispatch text is opaque may let Controller preselect exact
role/profile and opaque evidence association through its existing registration operation.
Bind the generated handoff during the existing reservation before native execution so
the child's first observation and nested lineage do not depend on a later Controller
acknowledgement. Consume that selection only for its matching owning top-level dispatch;
children cannot select global relevance or consume the Controller's next selection.
Keep append and protected checkpoint operations under the existing task lock so concurrent
child observations and reservations retain all evidence. Core supplies only the shared
append contract; adapter authority and native identity remain adapter responsibilities.

Adapters should reintroduce bounded evidence during ordinary Controller result delivery,
before its next broad completion/requirement judgment, rather than relying on the
task-close response. This requires no extra Agent, mandatory stage, polling or heartbeat.

Core stores model-authored observations and judgments with opaque requirement and handoff
references, provenance and append-only history. It does not classify importance, infer
acceptance, route work or prescribe approval, roles, stages, model calls or polling.

Mechanism may withhold; only a model may grant. The Controller may give a requirement a kind
(`compiled`, `partial`, default `judgment-only`) and declare checks for it: an argv command,
cwd, timeout and check files whose content hashes Core records. Any task actor runs a declared
check with `task-verify`; Core executes it and records the outcome against the current tree
identity. A result is fresh only for the tree it ran on and the declared check content, and an
UNKNOWN tree is never fresh. While a requirement's declared check is red, unrun or stale, a
`satisfied` judgment for it is refused as `VERIFICATION_WITHHELD`. The Controller either makes
the check green or judges with an override reason, which is stored with the checks it overrode
and shown in status. A fresh PASS marks nothing satisfied. A changed check file becomes one
open observation from producer `mechanism` per new content; re-declaring the check with
`--supersede` is how the Controller accepts the change.

To keep Controller round trips small, Core accepts batched judgments
(`{"judgments": [...]}`) and observations (`{"observations": [...]}`) as one
all-or-nothing append, returns a compact evidence summary (open-item totals always,
items paged by `next_offset`) on request, and offers a compact `task-status` view with
an optional `--since-revision` hint. A stale write is still refused under strict CAS;
the `TASK_REVISION_CONFLICT` details carry a bounded, non-exact `changes_since` hint
(`exact: false`: revision gap, records newer than the base, the last k handoffs,
observations and judgments, which may predate the base, and the open evidence summary)
so the Controller knows what to review before retrying. It is a hint, not a delta:
persisted state carries no per-item revision.

## Context frequency, waiting and observation

Keep normal Controller routing, handoffs, evidence reuse, Workstream endpoints,
acceptance and causal diagnosis directly available in its normal task context.
Retrieve exceptional recovery, Host maintenance and historical migration procedures
when needed. Shared instructions carry genuinely cross-role boundaries; role-owned
methods stay with the role. Judge complete task context plus retrieval/reconstruction
cost and delivered quality, not the shortest prompt or number of calls alone.

Choose waiting from available capability, expected meaningful event and necessary
dependency; prefer native notifications. A tool maximum is capacity, not a recommended
duration. Higher-level limits take precedence; neither a universal maximum nor a fixed
wait duration is the shared policy. Give each necessary dependency one observation
owner: executors run/wait on their tests, processes and CI and report substantive
changes or terminal evidence; Controller waits for the necessary child result without
rechecking the same job. Do not create status-only reasoning rounds for unchanged
state or poll completed work. A timeout alone supplies no new decision or evidence.

At decision boundaries, reuse the task's existing Active Work, Pending Results and selected
evidence refs to recover decisions, hard constraints, current evidence, UNKNOWNs and the
precise next event. Refresh Git HEAD or environment facts only when a relevant change or
decision-changing uncertainty could affect the choice. This is task continuity, not a
parallel persistent-memory workflow; no fixed time or call quota applies.

After user/model steering or turn interruption, an earlier dependency view may be stale.
Take one exact current status snapshot when needed before another wait, and wait only if the
necessary dependency remains unfinished. Do not wait on an interrupted, ended or no-longer-
needed child or repeat confirmation. A missed wake remains UNKNOWN without Host evidence;
prompt guidance alone cannot establish or fix native wake behavior.

`ASSOCIATION_UNKNOWN` for the wait helper does not block authorized source work or tests.
Observe your own process with native exec/write_stdin; this does not bypass managed guards.

For expensive native fixtures, first verify the exact source and lockfile, package identity,
and normal dependency path. A `--no-deps` fixture may isolate packaging behavior but is not
ordinary release/install proof; use this ordering where relevant, not as a universal gate.
After `EADDRINUSE` or `EBUSY`, inspect resource ownership and health before an equivalent
retry; never kill an unknown owner or delete an unknown lock. Truncated CI output, or a
`ready` result paired with exit 1, needs one targeted structured terminal/health
reconciliation; do not poll or treat readiness as completion.

After interruption, verify the known artifact path, provenance and current bytes, then finish
the remaining requested delivery instead of restarting all work.

Native capacity never expands adapter-managed authorization. A simultaneous
active/pending delegation slot is not a lifetime quota; after proved terminal
completion it may serve another necessary uncovered gap within the accepted boundary,
where the adapter supports that shape. Unknown overlap evidence does not authorize
bypassing admission or disabling all future supported delegation. Core does not set
Host concurrency limits.

Independent investigation and workstreams with isolated writes may run in parallel.
Parallel dispatch is user-directed: the program imposes no count of its own beyond a
number the user states, and when the user asks for large-scale parallelism the
Controller carries it out. The only mechanical boundary is that live write
workstreams may not overlap (equal or prefix-nested write scopes are refused,
whatever their domain label); read workstreams are never refused for overlap. The
Controller partitions work into non-overlapping domains, such as different research
areas, partitioned material or independent modules, not limited to these.
Coordinate known shared-file overlap or use separate worktrees before dispatch;
file CAS detects lost updates, not semantic overlap. An adapter may retain one
task-local unbound dispatch while precise native identity is unavailable, without
blocking other tasks or already bound independent siblings. Native execution,
product acceptance and task/dependency disposition are separate facts. Explicit
management abandonment may release a dependency while native execution and writing
risk remain UNKNOWN; fence its grants and reject late reactivation, without claiming
the process stopped. Unknown actual writes still need isolation or coordination.

## Role selection and Workstreams

Roles are capabilities, not mandatory stages. Choose one profile for the Workstream's
work shape, not a ladder, importance score or file/tool/token/time threshold.
Investigator gathers broad facts without architecture decisions. Scanner is its
nested discovery working pattern, not a role. Executor covers Implementer and
Focused Implementer, not a spawnable identity. Reasoning Specialist independently
challenges framing when that may change direction. Curator maintains selected reusable
knowledge and linked INDEX entries: edit, merge, split, replace, supersede or delete using
exact selected material. No corpus scan, delegation, architecture/product acceptance or
real-time evidence duty belongs to Curator. Concise future decision value belongs in memory;
raw detail stays in canonical Artifacts, Git or rollout records. Core supports CAS document
maintenance and validates paths/links; models choose semantic reconciliation.
Verifier remains read-only compatibility, not a recommended stage.
Native role/model bindings, readonly enforcement, execution modes and delegation
capabilities are adapter-owned. Profiles do not alter semantic responsibilities.

Respect the human's delegated, controller-direct, single-agent or adaptive selection; omitted
selection defaults to delegated. In adaptive mode the Controller may execute directly and may
also dispatch children, and the contract may leave `boundary` and `invariants` unspecified.
Controller strategy may change through authorized
task/revision CAS without expanding the original goal, scope or hard constraints.
Existing child role and readonly boundaries remain fixed. Ordinary Controller reads,
Git and diagnostics are legal within the task boundary. Legal capability is separate
from cognitive responsibility. In delegated mode, delegate broad repository investigation,
searches and call-site collection, log cleaning, tests, local analysis and implementation
to suitable fresh roles. A direct Controller read is a precise source spot-check for a
pending immediate decision, not an alternate investigation. After complete dispatch,
reading, searching, testing, diff review, runtime probing and implementation analysis
within that Workstream remain the child's work, even when useful to global acceptance;
they are not independent global decision work. Finish genuinely independent global
decision work first; when none remains and a necessary child is unfinished, wait normally.
Do not invent busywork to delay waiting. Integrate the distilled result with retained
global facts and acceptance; reopen a precise original for a pending immediate decision.
Controller-direct, single-agent and adaptive permit direct execution. No file, line, token, query
or tool-count quota or privilege denial enforces cognitive ownership. In adaptive mode Core
surfaces lane advisories in status: a check failing twice on distinct trees, a task surface
beyond the declared `write_surface` or the size thresholds, a `judgment-only` or contract-surface
requirement, and heavy Controller tool output. They are facts for the Controller's lane choice
and never block. Prefer
bounded catalog/document/task/artifact retrieval and exact instruction sections
when useful. Hooks cannot prove cumulative semantic scope or all third-party MCP behavior.
An active child may receive selected supplemental evidence and factual corrections
inside its accepted goal and role. Communication cannot change authorization. After
FINAL, new work uses a fresh child.

Stable accepted direction and deterministic convergence use ordinary Implementer.
Coupled invariants or nonlocal constraints needing sustained reasoning use Focused
Implementer. Controller routes Workstreams by semantic dependencies, decision coupling
and independent closure. Executors close local loops inside them; a semantic checkpoint
is not necessarily a scheduling checkpoint. Count-based thresholds do not route work.

Substantive frontend work has a strong-model quality bar: new UI or layout, component
architecture, responsive behavior, interaction, animation, creative SVG work or
nontrivial visual design needs a strong executor even when the diff or code is small.
A light model fits only genuinely trivial, fully specified text/color changes or
equivalent mechanical edits, all of which require no design or behavior decisions.
This is a semantic Controller routing decision, not a Core keyword or diff-size classifier;
native model and profile policy belongs to the Host-specific Controller instructions.

Remaining work is independently deterministic only when the accepted contract
uniquely determines the behavior to preserve. Compatibility authority ambiguity
remains semantic. When production behavior and historical fixtures leave authority
undecided, Focused supplies representative evidence or returns the dependency to
Controller; full regression is not mandatory by default. Controller may reroute the
same semantic closure to a fresh ordinary session when explicit inputs and independent
acceptance suffice and accumulated debugging state adds no benefit. Its handoff carries
distilled invariants, exact candidate, green evidence, provenance, remaining acceptance
and blockers, not raw history. FINAL ends the prior child session.

## Mutation and evidence

Before first mutation, executor establishes acceptance-relevant current mutation
surfaces, authoritative/derived relationships and a working verification entry.
Observe enough, make a coherent semantic mutation, verify acceptance-relevant behavior,
and repair from new evidence. Use the smallest tests for independently verifiable
semantic slices; keep coupled work together. Update authoritative source and use the
existing generator/sync for derived outputs. Stale structure calls for refreshing the
bounded authoritative region and reconstructing the edit; an unsuitable method calls
for changing methods. Cwd, quoting and known environment command mistakes are mechanical
recovery, not reasons to restart semantic inquiry. No retry or tool/token/time threshold
decides convergence. External Host protocol/schema/identity dependencies need source or
real-shaped proof; unresolved direction-changing dependencies return to Controller.
Authority ambiguity affecting compatibility, ownership, security, lifecycle or
contract also returns to Controller. Many failures, many files or long regression
alone do not require escalation.

Reuse the original failure and smallest local reproduction before changing behavior.
Distinguish actual failed boundaries (transport, decoding, shape, dispatch, contract,
identity) from an inferred deeper root cause. Keep secrets, payloads, raw contracts
and unbounded exception objects out of diagnostics. Preserve actual refusal, identity,
ownership and acceptance behavior when repairing CI; tests must not weaken it.

## Endpoints and review

Ordinary Implementer may finish assigned verification, deterministic fixes,
generated/documentation sync, integration checks, project/package install-smoke checks and Git closure in the
same Workstream. Stop at original acceptance. Focused Implementer owns the full reasoning,
implementation, runtime-feedback and revision loop. It returns FINAL when core solution
and invariants hold, decision-changing unknowns are resolved, focused evidence supports
core semantics, and remaining tasks cannot materially change causal model, architecture,
contract, scope, acceptance or direction. A focused-test PASS alone is insufficient.
Before that endpoint, project/package install or smoke feedback that exposes a semantic defect stays
in its loop. Afterward, ordinary regression/lint/build/sync, mechanical compatibility,
deterministic defects, project/package install-smoke checks and Git closure go to a fresh ordinary Implementer
when assigned. Shared Executor guidance never extends the Focused endpoint. Its result
identifies exact candidate sources/diff, invariants, evidence and limits, remaining
tasks, acceptance and escalation boundary. FINAL ends the child; further work is fresh.

Project/package install-smoke closure covers builds, installs, fixtures, isolated smoke,
packed artifacts and project-local verification. Effective live Host installation,
upgrade or uninstall, global instructions, profiles, hooks and trust require separate
Host authority under the adapter's maintenance contract. Project operational acceptance
does not grant that authority.

Reviewer is an optional fresh, independent and non-writing challenge after candidate
convergence. It challenges the original criteria, invariants and affected cross-boundary
behavior, not only the diff. Counterevidence is a finding; inadequate evidence remains
unverified/insufficient; READY requires supported critical closure for the selected
review. No blocker found is not verified acceptance. Accepted design unchanged and
bounded defect supports fresh ordinary correction; architecture/contract/invariant/
scope/acceptance or decision-basis changes reopen Controller.

Controller owns product acceptance. It integrates the user's original objective,
acceptance criteria, candidate, criterion-linked evidence and UNKNOWN from the
Implementer or Focused Implementer, and existing evidence, then decides whether the
product meets the request. Implementer and Focused Implementer implement, verify and
report within their assigned boundaries.
Controller may request additional verification or route repair when a criterion is
unmet or a decision-changing UNKNOWN remains; no fixed closing handoff, lifecycle
stage or new Agent is required. Preserve the user's selected execution mode.

Keep execution, review, product acceptance and mechanical closure distinct: test PASS
reports the checks run; native child Completed reports execution termination; Reviewer
READY reports supported critical closure for its selected review; Core task-close DONE
records mechanical closure. None alone decides semantic product acceptance.

`task-close` is withheld while any declared check is red, unrun or stale for the current tree,
unless the Controller closes with an override reason, which is recorded. The close response
lists every `judgment-only` and `partial` requirement with its latest judgment, so what no
check decided stays in front of the Controller at closure.
Choose fresh sessions by remaining independence and total context reconstruction cost,
never by a mechanical duration/call threshold or a local PASS alone.

Before opportunistic work, Controller accounts for every explicit user goal as addressed,
explicitly deferred or blocked by a decision-changing dependency. Near natural task closure
Controller decides whether selected evidence has reusable future value and warrants fresh
Curator reconciliation. No durable candidate register, extra stage or automatic corpus scan
is required. INDEX navigation stays concise, semantic, selected and model-maintained.
