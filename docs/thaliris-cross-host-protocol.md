# Thaliris cross-host managed children

This is the contract the Claude Code adapter and the Codex adapter both implement so that a
Controller on one Host can run a managed child on the other Host's model, recorded in the shared
Core ledger. Core (task schema 12) owns the ledger fields and transitions described here; the
adapters own the launcher, the relay and FOREIGN_CHILD recognition.

Status markers used below:

- **confirmed by probe**: established by a live probe on 2026-11-18 (Claude Code `claude -p`, Codex
  `app-server` and `exec`, Windows host, subscription auth).
- **pending**: designed, not yet probe-confirmed. An adapter must verify it before relying on it.

## 1. Model

Neither Host runs the other vendor's models natively. A foreign model runs as a **separate process**:
`claude -p` for a Claude child and `codex app-server` for a Codex child.

| Piece | Lives on | Authority |
|---|---|---|
| Controller | dispatching Host | the task's Controller authority, unchanged |
| Relay subagent | dispatching Host, a cheap native subagent | none; a notification shim for native background completion and UI |
| Launcher (`xhost-run`) | dispatching adapter, deterministic code | writes only the Core fields of section 3, for one handoff |
| Foreign child | foreign Host process | FOREIGN_CHILD: read-only role, no Controller authority, cannot delegate |
| Foreign adapter | foreign Host's Thaliris hooks | recognises the session and lowers its authority |

No secret travels in the environment. An environment marker may only **lower** authority; nothing
read from the environment, from the child's output or from a foreign field can raise it.

The first version ships **read-only foreign roles only** (investigator, reviewer, reasoning
specialist). Foreign children cannot delegate further.

## 2. Handoff fields (Core, schema 12)

Every field is assigned by Core. A model-authored registration or observation that carries one is
refused (`continuity field is assigned by Core`). All fields are kept on the handoff, survive
eviction and re-hydration unchanged, and a handoff stays hot while its run is live.

| Field | Set by | Meaning |
|---|---|---|
| `executor_host` | `reserve_foreign_handoff` | `claude` or `codex`: the Host whose model runs the child |
| `prompt_sha256` | `reserve_foreign_handoff` | sha256 of the prompt body (UTF-8) |
| `run_state` | every step | see section 2.1 |
| `transport_agent_id_hash` | reservation or launch, once | sha256 of the relay's native agent id |
| `foreign_session_hash` | `register_foreign_launch`, once | sha256 of the pre-registered foreign session id |
| `result_sha256`, `result_source` | `record_foreign_result`, once | digest of the result text; `result_source` is always `foreign-runner` |
| `cancel_reason` | `cancel_foreign_run` | bounded single-line reason, present exactly on `cancelled` |

Usage on a foreign-runner handoff is the ordinary usage record (`model, effort, input_tokens,
output_tokens, total_tokens, cost_usd, duration_ms, tool_uses, outcome`) plus the optional
`cost_basis`: `metered`, `subscription-notional` or `unknown`. Claim observations ingested from the
foreign result carry `provenance: foreign-runner`.

The prompt and result **bodies** are content-addressed sidecar files
`.context/tasks/<task id>/bodies/<sha256>.txt` (at most 1 MiB each), written before the state that
names them. Eviction never moves them, so the prompt stays retrievable for as long as the handoff
exists. `task_foreign_body(root, handoff_id, "prompt"|"result")` returns a body after verifying its
digest; a missing or altered body gives `FOREIGN_BODY_UNAVAILABLE`.

### 2.1 Run-state machine

```
reserved ──launch──▶ launched ──bind──▶ bound ──result──▶ completed | failed
   │                    │                 │       (result from launched is allowed too)
   └──────cancel────────┴──────cancel─────┴──▶ cancelled
```

- Transitions are one-way and each happens once. `register_foreign_launch` refuses a second launch;
  `record_foreign_result` refuses a second result; a settled run (`completed`, `failed`) cannot be
  cancelled; cancelling a cancelled run is a no-op (`already_cancelled: true`).
- Static coherence is validated on every load and write: no session hash before the launch; session
  and relay hashes from the launch on; a result exactly on `completed`/`failed`; claims only after the
  result; a cancel reason exactly on `cancelled`.
- A `foreign_session_hash` is unique among live runs (`reserved`, `launched`, `bound`).
- `bound` records the dispatcher's pre-workload binding. It carries no evidence that the
  foreign model has started or that a receiving hook has run.

### 2.2 Core API

State-level functions take a locked state (the caller writes it), mirroring `ingest_claims` and
`set_handoff_usage`. Adapters select the exact task and compose these functions inside their
existing checked transaction. The root-level forms acquire the task lock themselves. Reservation
requires an exact `base_revision` (`TASK_REVISION_CONFLICT`); other writes enforce it when supplied.
Every refusal leaves the state unchanged.

| Function | Root-level form | Effect |
|---|---|---|
| `reserve_foreign_handoff(state, record, executor_host=, prompt=, transport_agent_id_hash=None, root=)` | `task_foreign_reserve(root, actor, base_revision, handoff, executor_host=, prompt=, ...)` | register the handoff, store the prompt, `reserved` |
| `register_foreign_launch(state, handoff_id, foreign_session_hash, transport_agent_id_hash)` | `task_foreign_launch(...)` | `reserved → launched` |
| `bind_foreign_session(state, foreign_session_hash)` → `(binding or None, changed)` | `task_foreign_bind(root, hash)` | first bind `launched → bound`; idempotent |
| `record_foreign_result(state, handoff_id, result_text, claims_block, usage, outcome=, root=)` | `task_foreign_result(...)` | store result, ingest claims, record usage, `completed`/`failed` |
| `cancel_foreign_run(state, handoff_id, reason)` → `(response, changed)` | `task_foreign_cancel(...)` | `→ cancelled` |
| `foreign_body(root, state, handoff_id, kind="prompt")` | `task_foreign_body(root, handoff_id, kind="prompt")` | read a digest-verified body |
| `foreign_session_hash(session_id)` | | sha256 hex of the session id |

Error codes: `FOREIGN_RUN_INVALID` (malformed input, not a foreign handoff, relay mismatch, a session
hash already live), `FOREIGN_RUN_STATE_CONFLICT` (out of order or repeated), `FOREIGN_DELEGATION_REFUSED`
(a handoff whose parent is a foreign-runner handoff), `FOREIGN_BODY_UNAVAILABLE`.

**No nested delegation.** Any handoff registration (foreign or ordinary) whose parent has
`executor_host` is refused with `FOREIGN_DELEGATION_REFUSED`.

**Claims are ingested once, from the foreign result.** `ingest_claims` on a foreign-runner handoff
(for example from the relay's own SubagentStop) changes nothing and returns `changed: false`,
`ingested_by: foreign-runner`, and `already_ingested: true` with reason
`already ingested by foreign runner` once the result is recorded (before it, `already_ingested:
false`). Likewise `set_handoff_usage` / `task_handoff_usage` do not overwrite a foreign-runner
handoff's usage (`ignored` in the response); the relay's own token use is not recorded in v1.

## 3. Launcher CLI contract

```
xhost-run --handoff <handoff id>
```

The relay is told to run exactly this command and nothing else. The dispatching adapter's PreToolUse
hook recognises the command and **injects the relay's native identity** (its agent id, from the hook
payload; never from the model's text or the environment) and the task id. The launcher then:

1. Loads the task, refuses unless the handoff exists, has `executor_host`, is `reserved`, and (if
   the reservation carried one) its `transport_agent_id_hash` equals sha256 of the injected relay id.
2. Reads the digest-verified prompt and acquires the foreign session id (section 4).
3. Before releasing the workload, uses one checked dispatch-side transaction to call
   `register_foreign_launch` with the session and relay hashes, then `bind_foreign_session` with
   the registered session hash. It verifies the binding, commits the `bound` ledger and
   checkpoints the dispatching Host's authority. It also publishes the deny-only selector
   from section 6 before releasing the workload.
4. Runs the workload with the capability shape of section 5 and the lowering environment marker
   from section 6. It collects the final result and usage.
5. Calls `record_foreign_result(state, handoff, result_text, None, usage, outcome=..., root=root)`
   inside a checked dispatch-side transaction. The result, claims and usage reach Core whether
   or not the relay survives. The dispatching Host checkpoints the result write.
6. Prints a short summary for the relay (handoff id, run state, result digest, claim counts). The
   relay returns that summary as its final message, which carries no claims of its own.

One run per handoff: the launch step is one-shot in Core, so a second `xhost-run` for the same
handoff fails with `FOREIGN_RUN_STATE_CONFLICT` before any process starts.

## 4. Pre-registering the foreign session id

| Host | Mechanism | Status |
|---|---|---|
| Claude child | The launcher generates a UUID and passes `claude -p --session-id <uuid>`. The same `session_id` appears in the JSON output and in every hook payload. | confirmed by probe |
| Codex child (preferred) | `codex app-server --listen stdio://`: `initialize`, `initialized`, then `thread/start {cwd, model, sandbox: "read-only", approvalPolicy: "never", config: {...}}`. The response returns `thread.id` (equal to the hook `sessionId`) before any `turn/start`, so the launcher registers `sha256(thread id)` and only then sends `turn/start`. Race-free. | confirmed by probe |
| Codex `exec` | `codex exec --json` emits `thread.started` with the thread id as its first line, but the turn starts with no gap, so registration races the first hooks. It cannot satisfy the version-1 pre-workload binding requirement. | confirmed by probe (the race) |

The hook session id hash equals `sha256(thread id)` for Codex and `sha256(session_id)` for Claude
(confirmed by probe). Core's `foreign_session_hash(session_id)` computes it.

## 5. Capability shaping per role and Host

Only read-only roles in v1. The allowed tool set per role is the role's read-only set (Read, Grep,
Glob for Claude; the read-only sandbox for Codex). Shaping happens at launch time; the child cannot
widen it.

### Claude child (`claude -p`)

```
claude -p --session-id <uuid> \
  --tools "Read,Grep,Glob" \
  --strict-mcp-config --mcp-config <file containing {"mcpServers":{}}> \
  --permission-mode dontAsk \
  --output-format stream-json
```

| Key | Status |
|---|---|
| `--tools "Read,Grep,Glob"` as an **allowlist** (the role set) | confirmed by probe |
| `--strict-mcp-config` with an empty `{"mcpServers":{}}` config; `--tools` alone does not remove MCP tools | confirmed by probe |
| `--permission-mode dontAsk` | confirmed by probe |
| `--output-format stream-json` | confirmed by probe |
| Prompt on **stdin**: `--tools`, `--mcp-config` and `--allowedTools` are variadic and swallow a positional prompt | confirmed by probe |
| `--disallowedTools Agent,Task` as a denylist is **not** sufficient (a denylist leaks NotebookEdit); with the `--tools` allowlist, Agent/Task are already absent. Adapters may still add it as belt and braces. | confirmed by probe (leak) |
| Do **not** use `--bare`: it breaks subscription auth | confirmed by probe |
| Plugin hooks fire in `-p`: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse (the Thaliris plugin registers no Stop hook) | confirmed by probe |
| Hook subprocesses inherit env set on the `claude -p` process | confirmed by probe |

### Codex child (`codex app-server`)

`thread/start` with `sandbox: "read-only"`, `approvalPolicy: "never"` and config keys:

| Key | Status |
|---|---|
| `-s read-only` / sandbox `read-only` blocks file writes (Windows) | confirmed by probe |
| `agents.enabled=false` removes `spawn_agent` / `send_message` (no delegation) | confirmed by probe |
| `mcp_servers.<name>.enabled=false` **per server**; there is no global switch, so the launcher enumerates server names from config or app-server `mcpServerStatus/list` | confirmed by probe |
| `--disable apps --disable plugins` (or the equivalent thread config) removes `codex_apps` and plugin tools | confirmed by probe |
| These do **not** work: `mcp_servers={}`, `--disable multi_agent*`, `features.multi_agent_v2.enabled=false` | confirmed by probe |
| Hooks fire in app-server sessions: sessionStart (after `turn/start`), userPromptSubmit, preToolUse (also sees MCP calls), postToolUse, stop | confirmed by probe |
| Codex hooks create `.context/audit` in any cwd | confirmed by probe |

Both directions work with subscription auth (a Codex shell running `claude -p`, a Claude shell
running Codex), with or without the host environment scrubbed; a Codex `workspace-write` shell can
run `claude -p` (confirmed by probe).

## 6. FOREIGN_CHILD recognition on the foreign side

The launcher sets the lowering marker `THALIRIS_FOREIGN_CHILD=1`. Optional
`THALIRIS_TASK_ID` and `THALIRIS_HANDOFF_ID` environment values are hints. Before releasing the
workload, it atomically writes `~/.thaliris/xhost-sessions/<full session sha>.json` with
`root` (canonical absolute project path), `task_id` (UUID), and `handoff_id`. Both directions use
this selector. The environment and selector can only lower authority.

At SessionStart (and on every later hook) the foreign adapter:

1. Computes `sha256(session id)` from the **hook payload**, never from the environment.
2. Uses the exact hash to locate the selector. It reads the selected ledger and requires an
   already-bound handoff matching the native hash, `task_id`, `handoff_id` and the receiving
   adapter's `executor_host` before applying the read-only role. Receiving hooks never write or
   checkpoint the dispatching Host's ledger or authority. Using `bind_foreign_session` against a
   read-only in-memory state requires `changed: false` and a `bound` binding. Its `authority`
   value is always `none`.
3. Denies Controller operations, delegation (Agent/Task, `spawn_agent`) and tools outside the
   role's read-only boundary.
4. A foreign marker or selector entry without a matching live binding triggers unbound foreign
   handling. Missing, invalid, mismatched, cancelled, settled and evicted bindings provide no
   managed capability. When the marker is absent, a matching selector still enforces the same
   denial boundary. Neither source establishes a Controller association.

## 7. Result envelope and claims

The foreign child ends its final message with the ordinary `thaliris-claims` block (the same format
every Thaliris child uses; see the role packs). The launcher passes:

- `result_text`: the child's final message (for Claude stream-json, the **last** `result` event; a
  background Bash in `-p` keeps the process alive and produces a second `result`, confirmed by probe;
  for Codex, the final agent message of the turn);
- `claims_block`: `None` (Core parses the last block of `result_text`) or its equivalent fenced
  block. A block that differs from the result body is refused;
- `usage`: section 8;
- `outcome`: `completed` for a normal end, `failed` for an error, non-zero exit or timeout with a
  partial result.

Core stores the digest and body, ingests the claims with `provenance: foreign-runner` (adverse claims
become open observations of the handoff's producer and candidate, supports are counted), and sets
`run_state`. A missing or malformed block records the ordinary marker.

## 8. Usage mapping

| Core field | Codex (`turn.completed.usage` / app-server turn usage) | Claude (`result.usage`, `modelUsage`) |
|---|---|---|
| `model` | thread model | the `modelUsage` key with the most output tokens |
| `effort` | configured reasoning effort | configured effort, or null |
| `input_tokens` | `input_tokens` (includes cached input) | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` |
| `output_tokens` | `output_tokens` (includes reasoning output) | `output_tokens` |
| `total_tokens` | input + output | input + output |
| `cost_usd` | list-price estimate | `total_cost_usd` |
| `cost_basis` | `subscription-notional` under subscription auth, else `metered` | same rule |
| `duration_ms` | launcher wall clock | `duration_ms` |
| `tool_uses` | count of tool items | count of `tool_use` blocks |
| `outcome` | from the run outcome when null | same |

Status: the field names are pending until each adapter's probe records a real payload. Unknown
values are null; Core never invents them. `usage_summary` sums `cost_usd` across handoffs regardless
of `cost_basis`; readers that need billed cost must filter on `cost_basis`.

## 9. Timeout, cancel-on-dispose, kill-tree

- The launcher enforces a per-role wall-clock timeout. On timeout it kills the **whole process tree**
  (Windows: job object or `taskkill /T /F`; POSIX: process group), then records `outcome: failed`
  with whatever result text it has, or cancels if the run never produced output.
- When the relay is disposed, interrupted or its Host session ends, the dispatching adapter calls
  `task_foreign_cancel(root, handoff, reason)` and kills the launcher's tree. A result that arrives
  after the cancel is refused by Core (`FOREIGN_RUN_STATE_CONFLICT`) and discarded.
- One run per handoff: Core's one-shot launch makes a second launcher fail before it spawns anything.
  A retry is a new handoff.

## 10. What the relay may and may not do

May: run exactly `xhost-run --handoff <id>` once, wait for it, and return its summary verbatim.

May not: read or edit project files, run any other command, spawn agents, call Core, write claims
(its SubagentStop ingest is a no-op by design), report usage that overwrites the foreign model's,
or retry a failed run. Its PreToolUse hook refuses anything but the one launcher command, and its
model should be the cheapest one the Host offers.

## 11. Compatibility

Schema 12 adds only optional content, so schema 7 to 11 ledgers load unchanged and are written as 12
on their next write. A Core older than this one refuses a schema-12 ledger with
`STATE_SCHEMA_INCOMPATIBLE` (upgrade required). An adapter that does not implement this protocol
never creates foreign-runner handoffs and is unaffected, except that it must not treat
`task_ingest_claims` returning `changed: false` with `ingested_by: foreign-runner` as an error.
