# Thaliris DSH plugin MVP

This out-of-tree Cordis plugin uses DSH's Loader, Agent, fresh in-process
subagents and subprocess service with the same Python Thaliris Core. The
Controller explicitly selects human intent, a Workstream, a configured role,
the child's bounded handoff, and the final completion decision. Thaliris does
not run a second Agent loop or choose semantic roles or models.

The [capability map](CAPABILITIES.md) identifies the reused source APIs. The
verified DSH baseline is `639ed015397290b3745d163aafe02ffee4aa3f84`, version
`0.2.0-rc.2`, with Cordis `4.0.4`. Other revisions require compatibility
verification. This is an MVP, without framework or Host feature parity.

## Deployment

Make this package available alongside the DSH runtime with its peer packages
resolving to that runtime's copies. A source checkout can load `index.mjs` by
module URL; an installed local package exposes the same entry point. Keep the
package directory and `core_bridge.py` together. Package replacement follows
native DSH restart behavior; configuration unload/reload uses Loader normally.

Use the [example patch](cordis.patch.example.yml) beside `index.mjs`, with a
native DSH profile already providing `agents`, `tools`, `subagents`, the
`spawn` provider and `subprocess` (the local provider is verified). Mount the
plugin on the deployment's global tool plane, outside individual Agent presets.
Configure these explicit absolute paths in your local deployment:

- `root`: existing Git repository root, matching the native Controller's cwd.
- `pythonExecutable`: Python 3.11 or newer in your chosen environment.
- `corePath`: directory containing the `thaliris` Python package, e.g. the
  Thaliris checkout's `src` directory. The plugin does not use the Codex CLI.
- `authorityDirectory`: external storage outside the workspace, without
  symlink/reparse traversal. Closed ledgers remain here after unload.

The example uses `THALIRIS_DSH_ROOT`, `THALIRIS_DSH_PYTHON`,
`THALIRIS_DSH_CORE_PATH`, and `THALIRIS_DSH_AUTHORITY_DIRECTORY` to populate
these fields via native Loader expressions. No personal paths or credentials
are included. `bridgeTimeoutMs` defaults to 30000 and accepts up to 300000.

`roles` is an explicit deployment map from Controller-selected names to native
`agentOptions` (`provider/model/reasoningEffort/maxTokens`), optional `persona`,
and a required global tool `tools` allowlist. Omitted `agentOptions` inherit
the native parent route. Use configured DSH routes; there are no Codex model
names, complexity rules or automatic profile selection. Native restrictions
apply to global tools and intersect; scoped registrations follow DSH's native
semantics. Review your preset composition when configuring capabilities. This
plugin always excludes its four Controller tools and denies them again in
their execution bodies, including when a caller bypasses schema visibility.

## Controller tools

1. `thaliris_task_start`: supply `goal` and the selected `contract`, containing
   exactly `human_instruction`, `boundary`, `invariants`, `acceptance`, and
   `execution_mode`. This explicit Controller assertion records intent; it
   does not mechanically authenticate the human. Core initialization creates
   its ignored task state, configuration and navigation templates if absent.
   It installs no Codex instructions or runtime components.
2. `thaliris_workstream`: supply the returned `task_id/base_revision`,
   `workstream`, configured `role`, and `handoff` containing exactly `goal`,
   `scope`, `invariants`, `acceptance`, and `context`. The delegated execution
   mode is required. Only these selected values enter the child's prompt.
   Native `spawn` runs a fresh one-shot child with depth cap 1 and explicit
   tool filtering. Seeding or remote providers are rejected. The response
   contains the native child ID, stop reason, output, and current revision.
3. Interpret the result yourself. A normal native completion is an observation,
   not semantic acceptance. A noncompleted result records its native status
   and raises a native tool error carrying the observation and partial output;
   the task remains ACTIVE. Infrastructure failure/cancellation before a native
   result preserves the selected Workstream reservation in `active_work` for
   diagnosis.
4. `thaliris_task_close`: supply the current `task_id/base_revision` and an
   explicit `decision` (up to 3500 characters). When no Workstream reservation
   is unresolved, Core records the decision and marks the task DONE. Nothing
   automatically calls this tool.

`thaliris_task_inspect` explicitly retrieves the ACTIVE task and selected
contract. It injects nothing into child context. Goal, scope and intent are
immutable for an ACTIVE task; this MVP exposes no expansion or recovery tool.
Restart with an ACTIVE task requires the same native Controller identity;
an identity replacement is not silently authorized.

The plugin authorizes against the exact live `exec.agent`, native registry root
ownership, durable ancestry/depth, and configured cwd. It binds the Controller
object after an authorized successful call and checks the persisted native ID
on later bridge operations, including after reload. It accepts no caller actor
or session-ID field. Known native children cannot start, inspect, route or close
tasks. Shared OS access and direct Python invocation remain governance, not a
security sandbox; Host actor assurance remains UNKNOWN.

## Bridge and lifecycle

`core_bridge.py` reads one bounded protocol-1 JSON envelope from stdin, imports
only neutral `thaliris.core/authority`, executes one operation, and writes one
JSON response. The plugin supplies native identity from execution context and
launches the configured interpreter with `-I` through `ctx.subprocess`, with
bounded output, a deadline, cancellation and managed exit. Internal operations
are `start/inspect/begin/finish/close`; they are transport mechanics, not model
policy. Core owns task identity, revision checks, immutable intent, protected
configuration and external authority anchors. The bridge is not an independent
identity or ledger service. A failure between a Core mutation and its authority
checkpoint leaves evidence for diagnosis rather than inventing recovery.

Core task operations serialize within one plugin instance. Native run objects
supply identity and terminal facts; child prose supplies neither. Runs always
dispose through DSH. Cordis effects own tool registrations and operation cleanup.
If a native result is observed, `finish` records that observation in
`pending_results` and clears its `active_work` reservation. Cancellation,
infrastructure failure, or unload before `run.result` leaves the reservation in
`active_work` for diagnosis. While `active_work` is nonempty, a new
`thaliris_workstream` fails with `UNRESOLVED_ACTIVE_WORK_CANNOT_BEGIN`, and
`thaliris_task_close` fails with `UNRESOLVED_ACTIVE_WORK_CANNOT_CLOSE`. These
rejections leave the Core ledger and external authority anchor unchanged.
`thaliris_task_inspect` can retrieve the ACTIVE record after reload. The MVP has
no recovery or reconciliation operation; a missing native terminal observation
must remain unresolved. Unload cancels and drains active child/process work,
removes registrations, and preserves ACTIVE/DONE records and native parent
Agents. Reload starts with fresh plugin state and no duplicate registrations.
There are no plugin event listeners, so event registration count remains zero.

## Reproduce verification

Use an isolated DSH source clone at the pinned revision. Install its locked
dependencies with `pnpm install --frozen-lockfile --ignore-scripts`. The checked-in
runner requires Node 22.19+ or 24+, that clone in `DSH_SOURCE`, and an isolated
Python 3.11+ executable in `THALIRIS_TEST_PYTHON`. From the Thaliris root:

```text
python -m pytest adapters/dsh/tests/test_bridge.py -q
node adapters/dsh/tests/run-native.mjs
```

The Python tests exercise real JSON processes and Core authority, including
revision/identity conflicts, unsupported expansion/recovery, external storage,
security conflicts and neutral imports. The native suite imports the actual
out-of-tree module through Loader, creates real Agents, drives tool execution,
spawns real native children, invokes real Python through the local subprocess
provider, and explicitly closes the Core task. It verifies completed parent
conversation and unselected authority sentinels do not enter child context,
Controller tools disappear and refuse direct child execution, native failure
stays ACTIVE, seeding is rejected, unload drains an active child, ordinary native
turns continue while unloaded, and repeated reloads restore exactly four tools.

Only the LLM boundary is scripted, using upstream's `MockAdapter`. No Agent,
subagent manager, Loader, process or Core is mocked. This proves local composition
and mechanics on Windows with Node 24/Python 3.11; it does not establish live
provider quality, remote execution, cross-process Controller migration or
universal shared-OS authorization. No model credentials are required.
