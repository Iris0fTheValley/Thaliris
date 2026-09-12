# Codex Adapter

The Codex adapter is a mechanical bridge between native Codex lifecycle events
and the runtime-neutral Core.

## Handoff boundary

The Controller's native `spawn_agent` message is the only task-specific
semantic handoff. An allowed spawn records a bounded reservation containing
task/revision, role, producer, handoff ID, payload hash, and creation time.

The matching `SubagentStart` verifies authorization and binds the native agent
identity. It returns no task-specific `additionalContext` and never invokes
`core.prepare()`. System/developer instructions, AGENTS, native role profile,
tools, and environment remain native context and are outside this regression.

## Lifecycle

Managed root children must use `fork_turns="none"`, a supported native role
profile, and an explicit non-empty message. Reservations and started managed
children are serial. Matching SubagentStart/Stop events bind identity and
timestamps; bounded native terminal reconciliation handles missing stop
observations without treating reconciliation as successful work.

The root Controller guard denies only deterministic boundaries such as direct
known source writes and invalid managed spawn parameters. Read-only inspection
is prompt policy, not a shell-regex semantic classifier.

When native event-driven continuation is unavailable, `wait_agent` is
normalized to the supported Host maximum only if an actual pending reservation
or managed Child exists. Thaliris provides no scheduler or polling loop.

## Child results

Role profiles ask a Child to keep its working set private and return a distilled
result plus optional Artifact pointers. This is a prompt convention, not a Core
result schema. Artifact bodies, memory, milestone text, task history, and prior
reviews are never automatically added to another Child.

## Telemetry

Production hooks may record bounded hashes and lifecycle identities for the
root prompt, delegation, Child, and result. They do not invoke a model auditor,
block completion based on model judgment, or inject corrections into the
Controller. Model-based intent evaluation belongs in explicit offline/debug
work only.
