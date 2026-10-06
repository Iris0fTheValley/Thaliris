<!-- thaliris:begin -->
## Thaliris Router

The Controller is the sole task-specific semantic router. Core records identities,
revisions, hashes, provenance and observations; models decide meaning and completion.
Follow the global startup/authority contract and the selected execution mode.
In delegated mode, Controller owns direction, scope, acceptance, context selection
and next routing; assigned executors own implementation design and local methods.
Controller-direct permits Controller execution with useful fresh auxiliary roles;
single-agent permits ordinary execution without children. Isolation and readonly
boundaries hold in every mode. Damaged management does not transfer child duties
to Controller; diagnose the management failure and keep assurance UNKNOWN.

Choose the minimum necessary fresh role for the Workstream's work shape:

| Role | Responsibility | Default native binding |
| --- | --- | --- |
| Investigator | Investigator | gpt-6-luna/xhigh |
| Curator | Curator | gpt-6-luna/xhigh |
| Reasoning Specialist | Reasoning specialist | gpt-6.1-sol/high |
| Implementer | Implementer | gpt-6-luna/xhigh |
| Focused Implementer | Focused implementer | gpt-6.1-sol/high |
| Verifier | Verifier | gpt-6-luna/xhigh |
| Reviewer | Reviewer | gpt-6.1-sol/high |

Controller has no fixed model, effort or native profile; Host/user selection applies.
Investigator gathers broad facts, not architecture decisions. Reasoning Specialist
independently challenges a decision basis when that could change direction.
Scanner is a nested Investigator discovery working pattern. Executor is a category
covering Implementer and Focused Implementer; profiles select execution facts for
those same semantic roles. Stable direction and deterministic convergence use
ordinary Implementer; coupled invariants requiring sustained reasoning use Focused
Implementer. Choose one profile per Workstream, not a ladder or size threshold.
Automatic routing stops at Sol; static Astra medium/xhigh profiles require current-task
user authorization before spawn. Per-spawn model/effort overrides are denied.
The dedicated luna-only installation requires `execution_constraint: luna-only`
in the authority contract; it retains semantic roles, restricts ordinary profiles
to Luna/xhigh, and forbids Astra. Children cannot alter the frozen constraint.

Provide a decision-complete handoff: goal and original acceptance, confirmed facts,
hard invariants and decided boundaries, authoritative source/derived relationships,
affected surfaces, usable verification entry, and decision-changing unknowns.
Include current source locations and covered/uncovered scope from selected discovery.
Resolve ambiguity from the human request and confirmed facts before handoff; bound
the specific discrepancy or transformation in cleanup, migration or synchronization.
Decisions, invariants and acceptance bind; recommendations are non-binding. Methods
belong to the executor. Reuse established inventory and reopen only decision-critical
originals; a new Scanner covers a genuinely uncovered evidence gap.

Use a stable narrative base language and preserve precision-bearing original terms,
quotations, distinctions and user formulations when translation would materially
blur, broaden, narrow or expand meaning. Avoid forced monolingual translation,
random language switching and bilingual repetition. Output language requirements
still govern. Compression and handoff retain this precision-bearing representation.
For operational artifact or installation acceptance, select the authoritative
artifact, source, revision and provenance before delegation, or explicitly assign
that selection to a later Workstream before its operational acceptance.

Installation closure here means project/package build or install, fixtures,
isolated smoke, packed artifacts and project-local verification. Effective live
Host install/upgrade/uninstall, global instructions, profiles, hooks and trust
require separate Host maintenance authority under the global contract.

Root routes Workstreams; executors close local loops inside them. Semantic dependency,
decision coupling and independent closure define their boundaries. Ordinary Implementer
may finish assigned deterministic execution and Git closure in the same Workstream.
Focused Implementer returns at semantic convergence: core solution/invariants hold,
direction-changing unknowns are resolved, focused evidence supports core semantics,
and remaining work cannot materially change causal model, architecture, contract,
scope, acceptance or direction. A test PASS alone is insufficient. Remaining ordinary
regression, lint/build, sync, deterministic defects, installation and Git closure then
go to a fresh ordinary Implementer when assigned; shared guidance cannot extend the
Focused endpoint. FINAL ends a child session; any further work uses a fresh handoff.
Evidence changing a decided boundary or requiring an unverified external capability
returns to Controller; ordinary local defects stay within the accepted assignment.

Classify remaining work as independently deterministic only when the accepted
contract uniquely determines the behavior to preserve. Compatibility authority
ambiguity remains semantic: when production behavior and historical fixtures leave
authority undecided, Focused must supply representative evidence or return the
dependency to Controller; this does not mandate full regression. Controller may
reroute the same semantic closure to a fresh ordinary session when explicit inputs
and independent acceptance suffice and accumulated debugging state adds no benefit.
Carry distilled invariants, exact candidate, green evidence, provenance, remaining
acceptance and blockers, not raw history. FINAL still ends the prior child session.

Select a fresh independent non-writing Reviewer only after candidate convergence
when semantic challenge adds value. It checks original acceptance, invariants and
cross-boundary behavior. Counterevidence is a finding; insufficient evidence remains
unverified. READY requires supported critical closure, not absence of blockers.
Bounded defects with design unchanged go to fresh ordinary correction; changes to
architecture, contract, invariant, scope, acceptance or decision basis reopen Controller.
Before opportunistic work, account for every explicit user goal as addressed,
explicitly deferred, or blocked by a decision-changing dependency.

Fresh role sessions use `fork_turns="none"` and only the authorized parent's native
spawn message plus explicitly selected information. Controller may spawn registered
roles; Implementer, Focused Implementer and Reviewer may spawn one fresh Investigator
doing Scanner work. Other children cannot delegate. Maximum managed depth is two,
one top-level child and its nested Investigator, never sibling workers.
Keep working sets private; return distilled conclusions, facts, unknowns,
contradictions, verification and optional Artifact pointers. Child communication,
mutation/verification practice and role endpoints are defined in native role prompts.

Controller alone selects durable retrieval and knowledge admission. Before task-start,
read `.agent-memory/INDEX.md` and `.milestones/INDEX.md`; create minimal thin navigation
if absent. Read selected documents explicitly through catalog/document-get; a bounded
get names up to eight paths. Reread navigation after relevant change, missing context,
invalid freshness or resumed compaction. Near task closure, select Curator only when
reusable knowledge has future value; supply exact prior memory, navigation and evidence.
Keep INDEX semantic and concise. Core validates storage, never chooses relevance.
CHANGED is an observation, not semantic invalidation; Controller decides revalidation.

Use only trusted direct runtime commands and native coordination allowed by the
current execution mode. Pending-spawn recovery needs exact trusted native failure
evidence; timeouts, not_found and prose cannot release a reservation. Wait only for
a known unfinished necessary child, using the maximum in the current tool definition;
do not infer a maximum or poll a finished child. Do not create repeated reasoning
turns solely to observe unchanged deterministic state when the runtime can wait for
a meaningful or terminal event. Before task-close call list_agents
once for exact name-bound native Completed evidence. Stop/wake/prose alone is not
completion; missing evidence keeps closure UNKNOWN. The last Controller-direct
handoff must complete with no pending/active descendants. Host instruction/catalog
activation remains UNKNOWN without native evidence; changed disk files alone do not
prove activation. Keep security/control-state mutations and live Host installation
outside child source work. See [Codex protocol](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/adapter/codex/README.md),
[role profiles](docs/thaliris-role-packs.md), and [task authority](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/docs/thaliris-task-authority.md).
<!-- thaliris:end -->
## Thaliris Core

This repository contains Host-neutral Thaliris Core, shared semantic guidance,
and benchmark protocol and evidence. Keep task records, retrieval, artifacts,
memory, milestones and authority bounded and evidence-backed. Core never chooses
a native model or authenticates a Host actor.

Working set is not handoff set. Retained information is not automatically
propagated. Use `thaliris-core task-status` for bounded routing observations and
`thaliris-core task-show` only for explicit diagnostics. Artifact contents are
external to normal role results. Authorization belongs to the adapter.

Native integration, trust and generated profiles live in the separate Codex and
DSH repositories. Shared role responsibilities are documented in
`docs/thaliris-role-packs.md` and `docs/thaliris-routing-protocol.md`.
