# Codex host capability record — 2026-09-12

This is a version-bound maintenance observation for the local Codex host. It
does not claim that another CLI, Desktop, app-server, or rollout surface has
the same behaviour.

## Host

- executable: `codex-cli 0.153.4`
- matching upstream release: `rust-v0.153.4` (`3d2ee51c…`)
- V2 wait defaults in that release: minimum `10000`, default `30000`, maximum
  `3600000` milliseconds
- trusted project `.codex/config.toml`: implemented by the release config
  loader; live activation remains `UNKNOWN` until the Host loads the project
  layer for the session

The release's child-completion path sends its inter-agent completion message
with `trigger_turn = false`. Therefore this release records
`NATIVE_CHILD_COMPLETION_REENTERS_ROOT = UNSUPPORTED`; it must not select
EVENT_DRIVEN mode without a later contrary live probe.

## Disposable native wait probe

A fresh temporary Git root ran `codex exec` and asked one root to dispatch one
short child and make exactly one 60-second native wait. The CLI displayed one
`collab: Wait` execution and the root then reported completion. The probe used
no Thaliris hooks, task state, Controller, or child profile.

The temporary project's PostToolUse capture hook did not receive an event.
Consequently it is not payload evidence for `spawn_agent`, `wait_agent`,
`interrupt_agent`, or `list_agents`, and it does not prove project hook/config
activation. It does demonstrate that a single native wait can return normally
without a timer/retry loop. The release source establishes that the wait occurs
inside tool execution; no intermediate Root model activation was observed by
the probe, but no model-activation counter is exposed by this Host.

## Reconciliation surface

The release's V2 public tool schemas define structured PostToolUse results:

- `interrupt_agent`: `previous_status`
- `list_agents`: `agents[].agent_name` plus `agent_status`
- terminal status encodings: `{ "completed": ... }`, `{ "errored": ... }`,
  `interrupted`, and `shutdown`; `not_found` remains non-terminal.

The adapter treats these shapes as version-pinned fixtures only. Live hook
payload fidelity is still `UNKNOWN` until a project hook receives one; the
adapter therefore consumes them only when the current PostToolUse payload
actually contains the exact identity-bound structured fields.
