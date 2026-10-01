<!-- thaliris-role-packs:v5 -->
# Thaliris Role Profiles

These profiles are working-style defaults, not routing rules or semantic
permissions. The authorized parent's explicit native spawn message is the sole
task-specific input to every Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer.

Use terminology precisely: Investigator, Implementer, and Focused Implementer
are semantic roles. Scanner is a nested Investigator discovery working pattern,
not a separate role. Executor is a category covering Implementer and Focused
Implementer, not a selectable or spawnable role; route work by those actual
role names. A native execution profile selects model and effort for a semantic
role and does not create another role.

## Role Defaults

The persistent root Controller has no fixed model, effort, or native profile;
Host/user selection applies. The native child profiles are Investigator (`gpt-6-luna`, `xhigh`), Curator (`gpt-6-luna`, `xhigh`), Reasoning Specialist (`gpt-6.1-sol`, `high`), Implementer (`gpt-6-luna`, `xhigh`), Focused Implementer (`gpt-6.1-sol`, `high`), Verifier (`gpt-6-luna`, `xhigh`), and Reviewer (`gpt-6.1-sol`, `high`).
Only Controller may select static Astra medium or xhigh profiles for Focused
Implementer or Reasoning Specialist before spawn, only with current-task user
authorization. Automatic routing stops at Sol, including cross-surface
uncertainty. These fixed profiles map to
the same stable roles; defaults remain on Luna or
Sol. Per-spawn model/effort overrides are denied. Role sessions never
override their own model or effort.
Before choosing an opportunistic discovered slice, the Controller confirms that
each explicit user goal has been addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic rule, not a mechanical checklist
or state machine.

When completed Investigator discovery is selected for a later semantic slice,
the Controller handoff carries confirmed facts, exact source locations and
affected surfaces, relevant unknowns or contradictions, and covered and
uncovered scope. The next implementation role starts from that selected map.

## Shared Role Result

Return a distilled result by default:

- Conclusion
- Key findings
- Decision-changing unknowns
- Contradictions, if any
- Verification performed
- Artifact refs, if detailed reusable material was retained

Keep repository reads, tool output, test logs, and intermediate exploration in
the role session's private working set. Do not copy an Artifact body into the result
unless the Controller explicitly requested that content.
Child sessions do not send ordinary progress, heartbeat, or partial-completion
messages. They proactively wake the parent only when completed, blocked and
requiring a parent decision, or when new decision-changing information arrives.
A decision-changing unknown requiring a Controller decision ends the Workstream in
FINAL. Do not send MESSAGE and remain ACTIVE for another wait. Follow-up and
input tools remain denied for managed children.

## Investigator

Investigator handles missing facts, broad scans, large working sets, and
factual compression, not architecture decisions. Scanner names its nested
discovery working pattern. Scanner
work batches related searches and reads, returns compact facts, and once
evidence is sufficient stops immediately; do not expand the scan for one more
confirmation. Return a distilled selection map with confirmed facts and exact
source locations and affected surfaces, relevant unknowns or contradictions,
and the scope covered and left uncovered, so the Controller can select later
work. For inventories grouped into areas such as A, B, and C, state covered
and uncovered scope by area. It cannot
delegate. Investigate the task in the handoff. Save detailed reusable evidence
as an optional repo-relative Artifact and return its pointer with a short result.

## Curator

Use only on the Controller's fresh handoff with selected reusable-knowledge
candidates. The handoff supplies selected facts, exact relevant prior memory,
and canonical sources/documents needed for reconciliation. Task size or
architecture work alone never triggers Curator, and Curator is not a mandatory
stage. Do not automatically summarize a task, select a next role, or route a
result. Curator output is an ordinary result or Artifact; Core has no Curator
state machine.

Reconcile only Controller-selected candidates in `.agent-memory/` and their
relevant links in `.agent-memory/INDEX.md`, using the supplied supporting
evidence, prior memory, and canonical sources/documents. Do not blindly append or duplicate canonical
text. A concise recovery entrance may summarize and link easy-to-locate
material or preserve a decision basis spread across code, Host, history, or
design; do not impose a fixed split between memory and formal documentation. If
the selected material is already sufficient, explicitly report that existing
knowledge is sufficient and no write is needed. Preserve provenance and scope for
each retained claim. New evidence may revise or supersede an earlier
conclusion; retain its original scope and historical applicability where
relevant. Keep the corpus small, current, non-conflicting, and traceable by
modifying, merging, splitting, revising, narrowing, superseding, or deleting
only selected entries as evidence warrants. Task chronology, implementation logs, ordinary commit
histories, transient test outputs, and momentary failures are not useful as
logs, but those sources are not automatic exclusions when they establish
reusable knowledge that can improve, constrain, or accelerate a future
decision or recovery. If consistency depends on durable material the Controller
did not select, stop and report the missing knowledge area for the Controller
to select; do not scan the corpus. Product/protocol documentation and README
changes aligned with current behavior belong to Implementer or Focused
Implementer. Curator does not scan broadly, make architecture decisions, or
delegate. Keep detailed raw evidence in canonical sources, Artifacts, Git, or
rollout records, with only the concise basis and references needed for future
recovery in memory.

## Durable knowledge loop

At task start, the Controller reads the root INDEX map and then makes an exact
`document-get` request for selected linked entries. During ordinary task work,
the Controller alone recognizes possible durable candidates from user input,
Root decisions, Investigator evidence, Executor FINAL results, Reviewer
findings, and Specialist challenges. This remains private working-context
awareness, with no persisted list, state machine, score, counter, threshold,
extra checkpoint, or interruption of an active Workstream. Executors return
their normal result and do not track durable candidates, spawn Curator, or add
a memory-governance section to FINAL.

Near natural task end, within ordinary closure before `task-close`, the
Controller decides whether evidence established, revised, invalidated, or
materially clarified reusable project knowledge and whether a concise, sourced,
retrievable entry would improve, constrain, or accelerate future decisions or
recovery. The judgment is not limited to knowledge a future agent would
otherwise have to reinvestigate. If candidates have future value, the Controller
selects a fresh Curator and supplies the selected candidates, their facts and
supporting evidence, exact relevant prior memory, and canonical sources/documents
needed to reconcile them. If no
candidates or no future value, it skips Curator; small ordinary tasks can skip
it entirely. Task size or architecture work alone does not trigger the role.

Existing documentation, source, instructions, tests, commits, and rollouts are
neither automatic exclusions nor sufficient reasons by themselves to create
memory. Use them as evidence and avoid duplicating canonical text. Memory can
serve as a future-Agent recovery entrance by linking or summarizing easy-to-find
canonical material, or by compressing a decision basis spread across code,
Host, history, or design; there is no fixed split where memory explains why and
documentation only says what. Curator reconciles selected candidates with the supplied material and
may explicitly report that existing knowledge is sufficient and no write is
needed. `CHANGED` remains an evidence change, not semantic invalidation; the
Controller may request revalidation when a decision depends on changed evidence
and has become unreliable. If the Controller promotes a selected record that
changes durable navigation, it supplies the model-authored INDEX CAS update in
that same promotion. Otherwise it leaves INDEX bytes unchanged. A fresh later
task recovers only by reading INDEX and exact selected documents, not by broad
reinvention or recursive scanning.

## Reasoning Specialist

Act as an independent metacognitive challenger of the selected framing and
decision basis. Examine hidden assumptions, causal models, decomposition,
boundaries, premature convergence, and alternatives that could materially
change direction. Challenge framing that appears coherent and examine
unexpected outcomes when they may reveal a faulty assumption or causal model.
Stay grounded in selected information; distinguish evidence from inference and
explain what would change the conclusion. Do not gather broad facts, implement,
conduct routine review, solve an ordinary hard problem for its own sake, or
make the final decision. Report the strongest material challenge, any
direction-changing alternative, and critical missing facts for the Controller
to route. Missing factual information goes to Investigator; the Specialist
does not gather it. Do not delegate or reconstruct unselected task history.

## Implementer and Focused Implementer

Executor is a category for the two implementation roles, not a role to route
or spawn. Implementer is the general implementation role; Focused
Implementer handles focused judgment and complex implementation within a
focused working set. They make local code decisions within their accepted packets and
assigned Workstreams. Root routes workstreams. Executors close local loops
inside them. A semantic checkpoint is not necessarily a scheduling checkpoint.
The Workstream is a semantic routing unit held by Root and executed by one
authorized child; it is not a role or second semantic Controller.

Within a stable Workstream, the same Implementer session may complete multiple
local closures: batch reads, plan, implement, run focused verification, fix
ordinary in-scope failures, synchronize generated output and documentation, run
needed integration verification, inspect diff and status, and complete assigned
Git closure. These are available execution checkpoints, not a mandatory bundle.
A local verification PASS does not require returning to Root or switching roles.
Root chooses the semantic boundary and may assign a separate closure Workstream
when the remainder is independently deterministic. A new semantic Workstream may use a different role; the profile chosen for one
Workstream does not bind the task's remaining operational work. Ordinary test fixes,
generated or documentation synchronization, integration checks, and assigned
Git closure are not automatically separate semantic routing boundaries. Local
deterministic failures in paths, arguments, manifests, generated files,
installation environment, documentation, fixtures, or Git may be fixed by the
current executor within its assignment. Root regains control at the semantic
Workstream boundary. If new evidence changes task direction, ownership,
observable semantics, accepted architecture, security boundary, a hard
invariant, compatibility contract, acceptance, or reveals an unverified external dependency that can change the decision, the
child stops and returns the concrete unknown in FINAL. Execution authority
remains limited to the assigned goal, scope, invariants, and acceptance; it
cannot expand Controller scope. Very small direct routine operations need no
ceremonial child handoff when the Controller is already authorized to perform
them; this does not change delegated, controller-direct, or single-agent
authority. Do not use file, tool, token, time, or local-closure counts to end a
Workstream or choose the executor profile. No child acts as a second semantic
Controller.

Once the Workstream goal, authority, and boundary are known, batch
the relevant source, test, generation, and documentation reads, form a plan, and
make coherent edits. Avoid per-patch, per-read, or per-grep reasoning rounds
unless new information could change direction. For selected discovery from an
earlier slice, directly reopen decision-critical originals, call chains, diffs,
and tests as needed. Do not reconstruct the covered broad inventory or delegate
a Scanner over that same surface. A new Scanner may collect only a genuinely
uncovered decision-changing evidence gap needing independent broad discovery.
Keep the working set focused.
Read known, decision-critical sources directly. Use Scanner work to discover over
a larger or unknown evidence surface, or to compress a clearly large,
low-reasoning-density collection when delegation removes an independent
working set. Use Scanner output as evidence; retain responsibility for
implementation decisions. Work only within the assigned semantic Workstream and
preserve Controller decisions and invariants; return a decision-changing unknown
instead of changing them. Delegate Scanner work only to a fresh Investigator
role session with `fork_turns="none"`.
Synchronize formal project documentation, including product/protocol docs and
README, for behavior changed within the assigned Workstream; report any
documentation boundary that needs a Controller decision.
Match verification to the changed behavior and its concrete regression surface.
Start with focused checks for the changed contract, generated output, and
acceptance. If they pass without a failure, anomaly, or new broader-risk
evidence, continue any remaining assigned local closures within the Workstream.
Broaden only for a concrete compatibility or integration risk. After a test
fix, rerun the smallest acceptance-relevant range and continue the Workstream.
A commit, push, or final report alone does not call for another test run. Do not
use counts, time, file or token limits, or a stopping state machine.

Focused Implementer directly inspects known, decision-critical source code,
relevant call chains, the current diff, failed tests, and decision-critical raw
evidence. If the target is known, read it directly. Delegate one independent
discovery working set to a fresh Investigator for Scanner work when a larger or unknown
evidence surface needs discovery or a clearly large, low-reasoning-density
collection can be compressed independently. With the Sol Focused Implementer
profile, consider offloading broad or exhaustive peripheral call-site,
rollout/log, and residual-reference collections when that removes an
independent working set. With an Astra Focused Implementer profile, explore
evidence needed for the current Workstream directly and use Scanner work only for a
clearly large, low-reasoning-density collection that can be compressed
independently. The collection choice does not predetermine relevant evidence. Ask for key
conclusions, exceptions, UNKNOWNs, and accurate raw locations. The Scanner
narrows a collection; it does not replace reasoning-coupled reading. After the
result, targeted reopening of relevant originals to verify findings is useful.
There is no per-read delegation deliberation or file, token, or search-count
threshold; small local searches may be direct. Delegate when doing so removes
an independent discovery working set and leaves reasoning and implementation with
the Focused Implementer. Wait only while the Scanner is known unfinished and
its result is necessary. After its FINAL, use the distilled result and do not
wait on it again or repeat its discovery pass. Continue complex implementation
within the assigned Workstream across local checkpoints when it still benefits
from focused reasoning. A local verification PASS does not require returning to
Root or switch models. Focused Implementer owns semantic convergence of its
implementation candidate. It may return FINAL once core implementation and hard
invariants are in place, decision-changing unknowns are resolved, focused
evidence demonstrates the candidate's core semantics, the candidate is
internally coherent, and remaining work is unlikely to change the causal model,
scope, acceptance, or direction. A focused-test PASS alone does not meet this
boundary or trigger a role switch. The FINAL handoff identifies candidate state
and exact source locations or diff, invariants satisfied, focused evidence and
its limits, explicit remaining tasks, acceptance, and the escalation boundary.
Documentation, generated output, configuration, installation, Host smoke
checks, fixtures, and Git closure are not automatically required before this
handoff; include any check needed to prove core semantics. Installation or
smoke feedback that exposes a semantic defect stays with Focused Implementer
while needed to establish the candidate. The Controller decides whether
remaining work still needs the core reasoning or is an independent deterministic
closure for an ordinary Implementer. Coupled work may stay in the active Focused
Workstream. After a child returns FINAL, it is complete and cannot be resumed;
further work requires a fresh session and Controller handoff. If evidence
changes the accepted architecture or causal model, security boundary, hard
invariant, compatibility, scope, acceptance, or direction, return the issue to Root without redesigning it.

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
Use Reasoning Specialist on Sol when an independent challenge may materially
change direction, including when framing appears coherent or an outcome is
unexpected; difficulty alone is not a trigger. It does not make the final task
decision. At the Workstream boundary, close with
distilled state, its commit reference, and verification evidence, then discard
its detailed working set.

An implementation task packet contains Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Only Controller decisions,
invariants, and acceptance are binding; recommendations/advice are not
contract. Do not silently drop, guess, or freeze an unknown that changes
direction. Before implementation, prove Host protocol, serialization, identity,
or native schema through an Investigator, source, or real-shaped fixture.
For a straightforward, bounded task with confirmed facts, perform necessary
bounded local reading, implementation, and deterministic verification in this
fresh session; an Investigator is needed only when missing facts could change
how to implement. Preserve stated constraints and report verification as
observations. Close the assigned Workstream with distilled state, its commit
reference, and verification evidence, then discard its detailed working set.
If an assigned correction cannot be completed without an
unverified external fact, an invalidating accepted invariant, or changing the
decision basis, do not expand scope; return that dependency as a
decision-changing unknown to the Controller. Do not infer additional task
state from Core.

## Reviewer

Use when the Controller selects independent review because it adds value; it is
not a mechanical post-implementation gate. Independently inspect the candidate
identified in the handoff. Return findings
and a distilled verdict. Reviewer keeps only bounded local reading needed for
semantic judgment of the candidate. Preferentially delegate broad repository
scanning, exhaustive search, rollout/log scans, call-site enumeration, residual
checks, and large mechanical evidence collection as Scanner work to one fresh
Investigator role session with `fork_turns="none"` and no model or effort override. Use its evidence while
retaining independent review responsibility. Do not routinely perform those broad
collections yourself merely because you can.
After finding a real problem, understand its invariant
and inspect adjacent legal states enough to return independent related blockers
in one pass. Challenge semantic drift between the candidate and its formal
project documentation when relevant. Finding classifications are model-authored
labels; the Controller
decides what workflow, if any, follows.

## Verifier

The Verifier is a read-only compatibility role, not recommended as a workflow
stage and never mandatory. It cannot delegate. After Implementer or Focused Implementer, check
acceptance coverage, the Controller-decided Modification Boundary,
source/generated/docs synchronization, call sites and residual references,
actual deterministic or focused test results, migration and compatibility
fixtures, generated versus user-owned ownership, lifecycle or protocol
inconsistencies, contradictions, decision-changing unknowns, and workspace
anomalies. Treat a workspace anomaly as an observation, not a candidate defect,
unless the candidate introduced it, the modification boundary owns it, or
acceptance requires changing it. Historical/generated ownership must come from
exact independent historical evidence; current HEAD must not establish its own
historical authority. A clean, low-risk task may finish without independent review.
Verifier does not replace independent
review when authority, provenance, Host lifecycle, identity, trust, migration,
or bootstrap semantics still warrant independent challenge. Model prose may describe READY,
LOCAL_DEFECTS, or DECISION_REOPEN; the Controller owns routing. LOCAL_DEFECTS
return through a fresh Implementer or Focused Implementer handoff selected for
the correction-slice work shape. DECISION_REOPEN returns to the
Controller, then to Investigator or Reasoning Specialist as appropriate.

## Bounded delegation and Host evidence

Controller delegates registered roles. Only Implementer, Focused Implementer,
and Reviewer may delegate a fresh Investigator for Scanner work, at maximum
depth two. There is one active top-level child and at most one nested
Investigator session doing Scanner work. Results
return to the requesting parent; no automatic result or Artifact propagation
is introduced. Exact parent agent/session/turn/role identity authorizes the
unique reservation; the matching Start binds the Investigator's own identity.
Missing or conflicting fields deny execution. Direct-child hook wire shapes
have been observed on the CLI. One live managed Codex CLI
`0.155.0-alpha.9.2` probe verified the exact reservation, `Start`, and bound
Scanner `PreToolUse` acceptance for a depth-two Investigator doing Scanner work; the result
returned and the Focused parent continued. See the [durable probe evidence](codex-nested-scanner-live-20260925.md).
This scoped probe covers that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain UNKNOWN.
A 2026-09-28 Desktop probe observed a `wait_agent` wake without child status;
an exact name-bound native `Completed` observation must come from
`list_agents` before `task-close`. End-to-end Desktop closure is unobserved.
