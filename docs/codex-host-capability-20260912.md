# Codex host capability record — 2026-09-12

This is a version-bound maintenance observation for the local Codex host. It
does not claim that another CLI, Desktop, app-server, or rollout surface has
the same behaviour.

## Host

- executable: `codex-cli 0.153.4`
- matching upstream release: `rust-v0.153.4` (`3d2ee51c…`)
- V2 wait defaults in that release: minimum `10000`, default `30000`, maximum
  `3600000` milliseconds
- explicit `wait_agent(timeout_ms=...)`: accepts values in the release's
  min/max range and blocks natively until activity, input, or timeout;
  `HOST_EXPLICIT_BLOCKING_WAIT=PASS` is independent of project config loading

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
activation. It does demonstrate that a single explicit native wait can return normally
without a timer/retry loop. The release source establishes that the wait occurs
inside tool execution; no intermediate Root model activation was observed by
the probe, but no model-activation counter is exposed by this Host.

On 2026-09-13, a second disposable Git probe used a separate `CODEX_HOME` with
an explicit trusted-project entry, project `hooks = true`, and a distinct
60-second project wait default. That fresh process could not sample because
the isolated home had no transferable authentication (`401` before any tool
call). A normal authenticated process with hooks enabled started, but did not
call the requested `list_agents` tool and wrote no capture. Neither attempt is
live evidence of effective project configuration or PostToolUse payload shape.

A third fresh process used the existing authenticated Codex home, a disposable
Git root, minimal `PostToolUse` capture configured for `Bash`, and explicitly
enabled hook execution for that invocation. It performed one ordinary native
command execution, but no project capture was written. Its command failed in
the local Windows Bash service, which is immaterial to hook delivery. Therefore
`PROJECT_POST_TOOL_HOOK_ACTIVE = LIVE_NOT_OBSERVED`; no collaboration payload
probe was attempted.

## Reconciliation surface

The release's V2 public tool schemas define structured PostToolUse results:

- `interrupt_agent`: `previous_status`
- `list_agents`: `agents[].agent_name` plus `agent_status`
- terminal status encodings: `{ "completed": ... }`, `{ "errored": ... }`,
  `interrupted`, and `shutdown`; `not_found` remains non-terminal.

The adapter treats these shapes as version-pinned fixtures only. Live hook
payload fidelity is still `LIVE_NOT_OBSERVED` until a project hook receives one; the
adapter therefore consumes them only when the current PostToolUse payload
actually contains the exact identity-bound structured fields.

`SubagentStop` has no AgentStatus result field. It attests only a matching stop
hook; it cannot create or overwrite a native `completed` status. Native terminal
reconciliation releases execution capacity but never accepts a child result.
