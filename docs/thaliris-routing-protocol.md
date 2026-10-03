# Thaliris Routing Protocol

<!-- thaliris-routing-protocol: thaliris-routing-v3 -->

The marker identifies this routing contract for D11. Version 3 records the
effective native agent-profile rule below as part of the semantic contract;
native lifecycle schemas are independent of this marker.

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

Durable-knowledge admission belongs to the Controller alone. During normal
task work, Root notices reusable candidates in the human instruction, its own
architecture or governance decisions, Investigator evidence, Executor FINAL
results, Reviewer findings, and Specialist challenges. Keep this awareness in
the Controller's working context. Do not create a candidate register or
persisted admission state, add scores, counters, or thresholds, make an extra
checkpoint, or interrupt an active Workstream for memory review. Executors
return their normal distilled results, evidence, and decision-changing
information. They do not track memory candidates, spawn Curator, maintain
durable INDEX navigation, or add a separate durable-governance product to FINAL.

Near the task's natural end, as ordinary closure before `task-close`, the
Controller decides whether evidence established, revised, invalidated, or
materially clarified reusable project knowledge and whether a concise, sourced,
retrievable memory entry would improve, constrain, or accelerate future
decisions or recovery. This does not require that a future agent would
otherwise need to reinvestigate the knowledge. If selected candidates have
future value, Root hands Curator those candidates, facts and supporting
evidence, exact relevant prior memory and INDEX navigation, and the canonical
sources/documents needed to reconcile them. If
no candidates or no future value, it skips Curator; small ordinary tasks can
skip it entirely. Task size or architecture work alone never triggers a
Curator stage.

Existing documentation, source, project instructions, tests, commits, and
rollout records are neither automatic exclusions nor reasons by themselves to
create memory. Treat them as evidence and do not duplicate canonical text. A
future-Agent recovery entrance may link or summarize easy-to-locate canonical
material or compress the decision basis spread across code, Host, history, or
design. Do not impose a fixed split between memory and formal documentation.
Curator reconciles the selected candidates with supplied prior memory and
canonical sources; if existing material is sufficient, it explicitly reports
that no write is needed. Before selecting recovery documents, Root uses the
root INDEX's concise semantic descriptions of what linked knowledge covers,
when it is useful to read, and current or historical applicability where
useful. INDEX is navigation, not a bare file listing; keep current knowledge
discoverable first and retain historical links when they help explain earlier
scope or decisions. Models choose natural paths, hierarchy, and wording without
a fixed schema, taxonomy, status classifier, or state machine.

Curator maintains only Controller-selected knowledge under `.agent-memory/`
and relevant links in INDEX entries explicitly supplied in the handoff.
When adding, revising, merging, splitting, narrowing, superseding, or deleting
selected memory, Curator also judges whether the relevant INDEX navigation
needs a semantic update and updates it when needed. Keep INDEX entries concise
and semantic: what linked knowledge covers, when it is useful to read, and
current versus historical or superseded applicability where useful. Keep
currently relevant knowledge discoverable first and retain historical links
when they help explain earlier scope or decisions. Curator chooses natural
paths, hierarchy, and wording; there is no fixed schema, taxonomy, status
classifier, or state machine. Do not rebuild a directory listing or catalog,
write comprehensive history, or duplicate memory bodies in INDEX files. Core
performs only mechanical path, compare-and-swap, size, link, and atomic-write
checks; it never interprets or generates INDEX content. Preserve provenance
and scope for each retained claim; when new evidence revises or supersedes a
conclusion, preserve its original scope and historical applicability where
relevant. Keep the corpus small, current, non-conflicting, and traceable. Do not preserve task
chronology, implementation logs, ordinary commit histories, transient test
outputs, or momentary failures as logs; those sources are not automatic
exclusions when they establish reusable knowledge that can improve, constrain,
or accelerate future decisions or recovery. If consistency depends on durable
material the Controller did not select, stop and report the missing knowledge
area for Root to select; do not scan the corpus. Product/protocol docs and
README aligned with current behavior belong to Implementer or Focused
Implementer. Curator does not make architecture decisions or delegate. Keep
detailed raw evidence in canonical sources, Artifacts, Git, or rollout records,
with only the concise basis and references needed for future recovery in memory.
`CHANGED` reports an evidence change, not semantic invalidation. The Controller
may request revalidation when a decision depends on changed evidence and has
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
acceptance; this authority never expands Controller-assigned scope. Very small
direct routine operations need no ceremonial child handoff when the Controller
is already authorized to perform them; this does not change delegated,
controller-direct, or single-agent authority.

Root regains control at the semantic Workstream boundary. A child returns
distilled state, its commit reference, and verification evidence after its
assigned Workstream is complete. If new evidence changes task direction,
ownership, observable semantics, an accepted architecture or security boundary,
a hard invariant, compatibility contract, or
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
originals is useful. The collection choice does not
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

When routing or shared role contracts change, synchronize shared guidance and
the affected adapter instructions. Bootstrap, trust, Host maintenance, native
spawn reconciliation and offline administration are adapter-owned; see
[Codex lifecycle and recovery](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/docs/thaliris-runtime-recovery.md).

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

Core stores opaque actor labels and explicit observations. An adapter must prove
its own native identities, isolation, profile binding and completion evidence.
Core does not invoke a Host, choose a model or authenticate a Controller. The
[Codex adapter](https://github.com/Iris0fTheValley/Thaliris-Codex) and
[DSH adapter](https://github.com/Iris0fTheValley/Thaliris-DSH) implement separate
Host contracts around these shared mechanical APIs.
