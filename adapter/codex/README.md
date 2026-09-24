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
profile, and an explicit non-empty message. One top-level role session and its
one Investigator/Scanner may be active, at maximum depth two. Only Implementer,
Focused Implementer, and Reviewer may delegate that Scanner. Matching SubagentStart/Stop events bind identity and
timestamps; bounded native terminal reconciliation handles missing stop
observations without treating reconciliation as successful work.

For ACTIVE and degraded work alike, the Controller selects only the minimum
necessary fresh roles. Roles are capabilities rather than mandatory workflow
stages, so a straightforward bounded task may go directly from Controller to a
fresh Implementer and then finish. Decision-changing investigation belongs to
Investigator; bounded local reading needed for implementation may stay inside
Implementer. Reviewer is an optional independent semantic check, not a default
gate. Curator and Reasoning Specialist are likewise used only when valuable.
An Executor handoff should close one decision-complete semantic slice without
routine Controller steering. If decision-changing information invalidates the
slice, let the child return a distilled state and create a fresh correction
slice. Reviewers challenge converged slices after implementation stops; their
findings return to Controller, which decides on fresh correction work.
Decision-changing uncertainty routes to Investigator; broad grep and exhaustive
call-site or residual-reference scans route to Scanner under an Executor or
Reviewer.

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
Specialist let only Controller explicitly escalate before spawn, retaining the
same stable role IDs and Luna or Sol defaults. Per-spawn model/effort overrides
are denied; no dynamic role exists.

When native event-driven continuation is unavailable, `wait_agent` is
automatically normalized to a long wait only when an actual pending reservation
or managed native Codex child exists and a current-session effective maximum is mechanically
verified. When that maximum is unavailable, the requested timeout is preserved;
there is no automatic expansion. Thaliris provides no scheduler or polling
loop.

The installed `thaliris --root <repo> codex-bootstrap` command is the
project-external zero-state boundary. It uses a read-only definition probe,
then at most one trusted direct `thaliris init` call. Native role identities
and the stable hook ABI trampoline are installed separately in `CODEX_HOME`
with `thaliris codex-install`; that command safely merges global hooks and
preserves user-owned files. On Windows the trampoline checks only the static
`.codex/thaliris.json` project activation marker, then dispatches directly to
the current executable. Inactive repositories skip the Thaliris runtime. The
project `init` command writes the marker and managed project definitions; it
does not install project lifecycle hooks or project-local native roles. It returns
`MANUAL_ACTION_REQUIRED` when initialization leaves explicit manual work, and
never task-starts or retries initialization. A trusted executable that lacks
the current managed hook ABI, adapter protocol, or valid Controller bridge,
or emits the obsolete `session_restart_required` field, returns
`EXECUTABLE_PROTOCOL_SKEW`. SessionStart records role filenames as disk
presence only, not as Host catalog evidence. Without a native Host catalog
signal, readiness reports `HOST_ROLE_CATALOG_UNKNOWN`; a profile filename
added after the startup snapshot fails closed with
`NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE`. Updating the content of an existing
filename does not imply a restart. Host registration files on disk do not prove
that a current session loaded them. `task-start`
then requires the exact Controller bridge SHA-256 and a one-shot
current-session, current-ABI `PreToolUse` attestation; a missing or mismatched
bridge or attestation remains an explicit admission blocker. Project init does
not claim same-session activation unless that live hook attestation is observed.

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
