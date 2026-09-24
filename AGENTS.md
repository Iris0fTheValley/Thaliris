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
Use Investigator/Scanner for missing facts, large working sets, broad scans,
and factual compression, without transferring architecture decisions. Use a Reviewer only when independent semantic review adds real
value; it is not a default gate. Curator and Reasoning Specialist remain
optional and are selected only when they add actual value.

When Thaliris routing, roles, bootstrap, trust boundaries, or Controller
contracts change, check and synchronize both the repository-managed
instruction and the currently effective Codex global instruction.

Fresh Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer sessions use `fork_turns="none"`
and receive their tasks plus selected information in
their authorized parent's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter an Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, or Reviewer automatically.

The persistent root Controller has no fixed model, reasoning effort, or native
profile; Host/user selection applies. The native child profiles are Investigator (`gpt-6-luna`, `xhigh`), Curator (`gpt-6-luna`, `xhigh`), Reasoning Specialist (`gpt-6-sol`, `high`), Implementer (`gpt-6-luna`, `xhigh`), Focused Implementer (`gpt-6-sol`, `high`), Verifier (`gpt-6-luna`, `xhigh`), and Reviewer (`gpt-6-sol`, `high`).
Only Controller may explicitly select static Astra medium or xhigh profiles for
Focused Implementer or Reasoning Specialist before spawn for exceptional reasoning.
These fixed profiles retain the same stable role IDs; default profiles remain
on Luna or Sol. Per-spawn model/effort overrides are denied;
role sessions never select their own model or effort.
Route low-difficulty, high-certainty slices to standard Implementer on Luna,
even within a large project. Use Focused Implementer on Sol for complex,
creative lifecycle, ownership, or compatibility work. Use Reasoning Specialist
on Sol only when problem framing or slice decomposition is unclear; it does not
implement. Astra is an escalation for an already small, unusually demanding
slice or an evidenced Sol failure. Astra medium is the default escalation;
xhigh requires a clear reason.
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
When a promotion changes durable navigation, the Controller should include its
own optional `index_update` in the same `task-promote` call. Core does not
generate INDEX content; it validates the CAS, references, and atomic commit.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. During an ACTIVE managed task the persistent Controller uses only
native spawn/wait/list/interrupt operations and an explicit allow-set of
trusted direct `thaliris` runtime commands. `init`, `uninstall`, `rollback`, a
second `task-start`, and `task-show` are blocked for ACTIVE Root. `task-status`
is bounded; `task-get`, `artifact-get`, `catalog`, and `document-get`
retrieve explicitly selected objects.
If `task-start` was attempted but managed enforcement is unavailable or
rejected, label the run unmanaged/degraded. Diagnose only the bootstrap cause:
Codex version, host capability, task schema, git/worktree identity,
hook/profile presence, and the `task-start` error are allowed reads. Use only
the direct canonical `thaliris` command or an absolute executable with an
explicit exact SHA-256 pin; never recommend or use a shell-wrapper fallback.
If neither trusted direct route is available, check canonical availability, the
explicit executable SHA-256 pin, and hook/install state, then report bootstrap
unavailable. Once the cause is known, do not read user-task repository source,
tests, docs, or search results. If work continues, apply the same minimum-role
routing policy defined above; degraded mode does not define a separate role
sequence. The Controller must not take over repository
investigation, implementation, or testing merely because NO_TASK applies. The
final report must not claim managed enforcement was verified.
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
identity. Grandchild Host hook identity behavior remains UNKNOWN until observed
on that Host; fixture verification is not live managed activation proof.
Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. When blocked on an
authorized managed child, use one blocking `wait_agent` call with `timeout_ms`
equal to the maximum advertised in the current turn's `wait_agent` tool
definition. The current turn's tool definition is the authority; never infer a
maximum from release defaults, configuration, history, or capability tables.
Early return on mailbox activity is expected; if the child remains pending,
inspect the relevant new state and wait again using the current turn's
advertised maximum. Do not use short periodic polling. If no usable current
maximum is advertised, do not invent one.
Task closure requires the last
Controller-direct handoff's completed lifecycle and no pending or active
descendants; a later Scanner does not replace that top-level completion.
The Controller interprets Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.

Startup contract: determine project initialization only from these explicit
project facts: a managed Thaliris block in the effective root instruction and
a current managed `.codex/hooks.json`. If either fact is absent, invoke
`thaliris --root <repo> init` directly, or invoke the absolute executable
named by the Host's exact SHA-256 pin. Project `init` does not create native
role identities. Stable Thaliris native role definitions are one-time Host
integration installed with `thaliris codex-install` under the user's
`CODEX_HOME/agents`; run it before starting a session that will use them. It
installs only Thaliris-owned profiles and preserves user files. A profile
filename added after SessionStart fails closed as
`NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE`. SessionStart's project and Host profile
file snapshots are disk-presence evidence only; missing snapshot or missing
Host-native catalog evidence remains `HOST_ROLE_CATALOG_UNKNOWN`, never PASS.
Updating content at an already-known filename does not add a role identity.
Read the canonical managed text and SHA-256 returned by `init` or
`bootstrap-check`. Explicitly acknowledge that digest with
`--controller-bridge-sha256` when calling `task-start`; the loaded current-ABI
PreToolUse hook binds that receipt to its session attestation. This is
Controller activation only: CLI output does not become Host developer
instruction, and Host instruction activation remains UNKNOWN. Project hook
activation is separate: use only a supported current-session Host refresh
route; when unavailable, report `PROJECT_HOOK_REFRESH_UNAVAILABLE` and do not
globalize lifecycle hooks. If neither trusted direct executable route is
available, report bootstrap unavailable and do not continue.
If all facts are present, read `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` (creating only a minimal missing map as instructed),
then proceed to normal managed startup.
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
