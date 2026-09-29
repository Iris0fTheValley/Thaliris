# Codex Adapter

The Codex adapter is a mechanical bridge between native Codex lifecycle events
and the runtime-neutral Core.

## Handoff boundary

The authorized parent's native `spawn_agent` message is the only task-specific
semantic handoff. An allowed spawn records a bounded reservation containing
task/revision, role, producer, handoff ID, payload hash, and creation time.

The matching `SubagentStart` verifies authorization and binds the native agent
identity. It returns no task-specific `additionalContext` and never invokes a
Core context-construction API. System/developer instructions, AGENTS, native role profile,
tools, and environment remain native context and are outside this regression.

## Lifecycle

Managed root native Codex child sessions must use `fork_turns="none"`, a supported native role
profile, and an explicit non-empty message. One top-level role session and one
nested Investigator session doing Scanner discovery work may be active, at
maximum depth two. Only Implementer, Focused Implementer, and Reviewer may
delegate that work. Matching SubagentStart/Stop events bind identity and
timestamps; bounded native terminal reconciliation handles missing stop
observations without treating reconciliation as successful work.

Investigator, Implementer, and Focused Implementer are semantic roles. Scanner
is a nested Investigator discovery working pattern, not a separate role.
Executor is a category covering Implementer and Focused Implementer, not a
selectable or spawnable role. A native execution profile selects model and
effort for a semantic role and does not create another role.

For ACTIVE and degraded work alike, the Controller selects only the minimum
necessary fresh roles. Roles are capabilities rather than mandatory workflow
stages, so a straightforward bounded task may go directly from Controller to a
fresh Implementer and then finish. Decision-changing investigation belongs to
Investigator; bounded local reading needed for implementation may stay inside
Implementer. Reviewer is an optional independent semantic check, not a default
gate. Curator and Reasoning Specialist are likewise used only when valuable.
The Controller owns the complete user objective, its decomposition, role and
context choice, overall invariants, boundaries and acceptance, interpretation
of child results, and task-level decisions to reopen, review, continue, or end.
It may do bounded reading to frame a handoff and interpret evidence, but does
not perform broad repository scans, implementation, or the full task test
suite. The Investigator role gathers broad evidence, including through the
Scanner working pattern. Implementer and Focused Implementer make local code
decisions within their accepted packets and Workstreams. Root routes workstreams.
Executors close local loops inside them. A semantic checkpoint is not
necessarily a scheduling checkpoint. A Workstream is the semantic routing unit,
not a role or second Controller, and one authorized child session owns its
execution. Within a stable Workstream, that same session may perform relevant
reads, plan, implement, verify, fix ordinary in-scope failures, synchronize
generated output and docs, run needed integration checks, inspect diff/status,
and complete assigned Git closure. A local verification PASS does not require
returning to Root; these local closures do not create semantic routing boundaries.
Root regains control at a semantic Workstream boundary. If evidence changes task
direction, ownership, observable semantics, a hard invariant, compatibility,
acceptance, or reveals an unverified external dependency that could change the
decision, the child stops and returns the concrete unknown in FINAL. Execution
authority cannot expand Controller-assigned scope. Reviewers challenge
converged candidates after implementation stops; their findings return to
Controller, which decides on follow-on work.
Use Reasoning Specialist when an independent challenge may materially change
direction, including when framing appears coherent or an outcome is unexpected.
It tests hidden assumptions, causal models, decomposition, boundaries, decision
basis, premature convergence, and direction-changing alternatives. Difficulty
alone is not a trigger; the Specialist does not gather broad facts, implement,
conduct routine review, or make the final decision. Missing factual information
goes to Investigator.
Before choosing an opportunistic discovered slice, the Controller confirms that
each explicit user goal has been addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic rule, not a mechanical checklist
or state machine. Focused Implementer can complete complex implementation as
well as focused reasoning. It directly inspects known, decision-critical
sources, including source code, relevant call chains, the current diff, failed
tests, and raw evidence. When the target is known, it reads it directly. A
Scanner is a nested Investigator discovery working pattern, not a separate
role. It can discover, enumerate, filter, and classify a larger or unknown
evidence surface, or compress a clearly large, low-reasoning-density
collection. It returns key conclusions, exceptions, UNKNOWNs, and accurate raw
locations. Its collection choice does not predetermine relevant evidence and
does not replace reasoning-coupled reading. Targeted reopening of
relevant originals after its result is useful. Implementer and Focused Implementer directly read known,
decision-critical sources. With the Sol Focused Implementer profile, consider
offloading broad or exhaustive peripheral call-site, rollout/log, and
residual-reference collections when this removes an independent working set.
With an Astra Focused Implementer profile, explore evidence needed for the
current Workstream directly and use Scanner work only for a clearly large,
low-reasoning-density collection that can be compressed independently. Small
local searches may be direct. There is no per-read delegation deliberation or
file, token, or search-count threshold. Delegate when doing so removes an
independent working set.
When completed Investigator discovery is selected for a later Workstream, the
Controller handoff supplies its facts, exact source locations and affected
surfaces, relevant unknowns or contradictions, and covered and uncovered
scope. The implementation role starts from that map and directly reopens
decision-critical originals, call chains, diffs, and tests as needed. It does
not repeat the covered broad inventory or delegate a Scanner over that surface.
A fresh Scanner can collect a genuinely uncovered decision-changing evidence
gap that needs independent broad discovery, limited to that gap.
Focused Implementer continues complex implementation within its assigned
Workstream across local checkpoints when it still benefits from focused
reasoning. A local verification PASS does not force a return to Root. Close the
Workstream at its semantic boundary or when assigned acceptance is complete. A
deterministic remainder goes to Controller routing only when it is outside the
Workstream or independently closable without the Focused model's reasoning. A Scanner batches
related searches and reads, returns compact facts, and once evidence is
sufficient stops immediately; do not expand the scan for one more confirmation.
Once the Workstream goal, authority, and boundary are known, Implementer and Focused Implementer batch the
relevant source, test, generation, and documentation reads, form a plan, and
make coherent edits. Avoid per-patch, per-read, or per-grep reasoning rounds
unless new information could change direction. Match verification to the changed
behavior and its concrete regression surface; start with focused checks for
the changed contract, generated output, and acceptance. If those pass without
a failure, anomaly, or new broader-risk evidence, continue any remaining assigned
local closures within the Workstream. Broaden only for a concrete compatibility or
integration risk. After a test fix, rerun the smallest acceptance-relevant
range and continue the Workstream. A commit, push, or final report alone does
not call for another test run. Do not use counts, time, file or token limits,
or a stopping state machine.

The ACTIVE root Controller uses only bounded control-plane commands and
explicit retrieval. Execution, mutation, and testing belong to fresh
Implementer or Focused Implementer sessions. Read-only inspection is prompt policy, not a shell-regex
semantic classifier.

Nested PreToolUse requires the exact bound parent agent, role, session, and
turn. Start consumes the unique reservation and binds the Scanner's own
identity. Missing/conflicting fields deny tool execution. Grandchild Host hook
identity remains UNKNOWN; tests use explicit contract-shaped fixtures. The
last Controller-direct handoff supplies task-close completion proof, with no
active or pending descendants. Scanner completion does not replace it.

Controller has no fixed model or effort. Default model/profile facts are in
the generated [role registry](../../docs/thaliris-role-registry.md). The two
static Astra medium and xhigh profiles for Focused Implementer and Reasoning
Specialist let only Controller choose before spawn with current-task user
authorization. Automatic routing stops at Sol, including cross-surface
uncertainty. These profiles retain the same
semantic role identities and Luna or Sol defaults. Astra medium and xhigh are
execution profiles of a semantic role, never separate roles. Per-spawn
model/effort overrides are denied; no dynamic role exists.

Choose one model/profile for the current Workstream from its work shape, not as
a ladder. Standard Implementer on Luna is the default for a
stable problem structure and direction, including remaining execution, local
code judgment, tests, synchronization, and mechanical consistency, regardless
of task size. Choose Focused Implementer on Sol when the smallest coherent
Workstream has a stable direction but inherently needs sustained reasoning
across coupled invariants, nonlocal effects, or constraints. Routine local
closures do not trigger another role or profile choice. Choose a Focused
Astra medium and xhigh remain exceptional profiles of the same Focused
Implementer role, available only with current-task user authorization.
Importance, file count, cross-module scope, number of local closures, or ordinary
alternatives alone do not determine the choice.
Do not use file, tool, token, time, or local-closure counts to end a Workstream.

When native event-driven continuation is unavailable, `wait_agent` is
automatically normalized to a long wait only when an actual pending reservation
or managed native Codex child exists and a current-session effective maximum is mechanically
verified. When that maximum is unavailable, the requested timeout is preserved;
there is no automatic expansion. Thaliris provides no scheduler or polling
loop.
Call `wait_agent` only for a known unfinished child whose result remains
necessary. After Scanner FINAL, the parent uses its result and does not wait
on that Scanner again. A decision-changing unknown ends the child Workstream in
FINAL for Controller decision.

The installed pinned `thaliris-run.cmd --root <repo> codex-bootstrap` command is
the one-shot project startup boundary for substantive Git work. It checks task
state first and performs project `init` only when needed. Native role identities
and the stable hook ABI trampoline are installed separately in `CODEX_HOME`
with `thaliris codex-install`; that command safely merges global hooks and
preserves user-owned files. On Windows the trampoline checks only the static
`.codex/thaliris.json` project activation marker, then dispatches directly to
the installed pinned runtime. Inactive repositories skip the Thaliris runtime. The
project `init` operation writes the marker and managed project definitions; it
does not install project lifecycle hooks or project-local native roles. It returns
`MANUAL_ACTION_REQUIRED` when initialization leaves explicit manual work, and
never task-starts or retries initialization. A trusted runtime that lacks
the current managed hook ABI, adapter protocol, or valid Controller bridge,
or emits the obsolete `session_restart_required` field, returns
`EXECUTABLE_PROTOCOL_SKEW`. SessionStart records role filenames as disk
presence only, not as Host catalog evidence. Without a native Host catalog
signal, readiness reports `HOST_ROLE_CATALOG_UNKNOWN`; a profile filename
added after the startup snapshot fails closed with
`NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE`. Updating the content of an existing
filename does not imply a restart. Host registration files on disk do not prove
that a current session loaded them. READY exposes one opaque
`task_start_receipt` for a direct `task-start --bootstrap-receipt` call; the
current Host Hook attaches one-shot current-session attestation. ACTIVE returns
owner and exact old-state evidence so the Controller can continue or explicitly
abandon the old task. Abandon preserves incomplete evidence and never creates a
completed child. Project initialization requires no Codex restart. A global
Host installation change may require one restart before its integration loads.
Host maintenance of source, tests, installed runtime, hooks, profiles, and the
global instruction can proceed in a separate checkout and Codex session while
another project's task is ACTIVE. The ACTIVE Controller guard admits only exact
identity-checked installed `codex-install` and `codex-uninstall` calls for Host
maintenance; ordinary project source and test commands retain the managed role
boundary. If uninstall runs from its own `thaliris-run.cmd`, it leaves that
launcher inert after removing the manifest and integration, reports
`UNINSTALLED_INERT_RUNNER_RETAINED`, and a later direct uninstall or reinstall
can clean it up. This avoids deleting a running Windows batch file.

## Role results

Role profiles ask each Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, and Reviewer to keep its working set private and return a distilled
result plus optional Artifact pointers. This is a prompt convention, not a Core
result schema. Artifact bodies, memory, milestone text, task history, and prior
reviews are never automatically added to another role session.

## Telemetry

Production hooks may record bounded hashes and lifecycle identities for the
root prompt, delegation, native Codex child, and result. They do not invoke a model auditor,
block completion based on model judgment, or inject corrections into the
Controller. Model-based intent evaluation belongs in explicit offline/debug
work only.
