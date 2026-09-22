# Codex Adapter

The Codex adapter is a mechanical bridge between native Codex lifecycle events
and the runtime-neutral Core.

## Handoff boundary

The Controller's native `spawn_agent` message is the only task-specific
semantic handoff. An allowed spawn records a bounded reservation containing
task/revision, role, producer, handoff ID, payload hash, and creation time.

The matching `SubagentStart` verifies authorization and binds the native agent
identity. It returns no task-specific `additionalContext` and never invokes a
Core context-construction API. System/developer instructions, AGENTS, native role profile,
tools, and environment remain native context and are outside this regression.

## Lifecycle

Managed root native Codex child sessions must use `fork_turns="none"`, a supported native role
profile, and an explicit non-empty message. Reservations and started managed native Codex child sessions are serial. Matching SubagentStart/Stop events bind identity and
timestamps; bounded native terminal reconciliation handles missing stop
observations without treating reconciliation as successful work.

For ACTIVE and degraded work alike, the Controller selects only the minimum
necessary fresh roles. Roles are capabilities rather than mandatory workflow
stages, so a straightforward bounded task may go directly from Controller to a
fresh Implementer and then finish. Decision-changing investigation belongs to
Investigator; bounded local reading needed for implementation may stay inside
Implementer. Reviewer is an optional independent semantic check, not a default
gate. Curator and Reasoning Specialist are likewise used only when valuable.

The ACTIVE root Controller uses only bounded control-plane commands and
explicit retrieval. Execution, mutation, and testing belong to fresh
Implementer sessions. Read-only inspection is prompt policy, not a shell-regex
semantic classifier.

When native event-driven continuation is unavailable, `wait_agent` is
automatically normalized to a long wait only when an actual pending reservation
or managed native Codex child exists and a current-session effective maximum is mechanically
verified. When that maximum is unavailable, the requested timeout is preserved;
there is no automatic expansion. Thaliris provides no scheduler or polling
loop.

The installed `thaliris --root <repo> codex-bootstrap` command is the
project-external zero-state boundary. It uses a read-only definition probe,
then at most one trusted direct `thaliris init` call. Manual action or a
restart requirement is terminal for that Controller session; it never
task-starts or retries initialization. No automatic Codex Host hook is assumed
or claimed by this command.

## Role results

Role profiles ask each Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer to keep its working set private and return a distilled
result plus optional Artifact pointers. This is a prompt convention, not a Core
result schema. Artifact bodies, memory, milestone text, task history, and prior
reviews are never automatically added to another role session.

## Telemetry

Production hooks may record bounded hashes and lifecycle identities for the
root prompt, delegation, native Codex child, and result. They do not invoke a model auditor,
block completion based on model judgment, or inject corrections into the
Controller. Model-based intent evaluation belongs in explicit offline/debug
work only.
