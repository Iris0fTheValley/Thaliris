# Managed CLI Execution Path - 2026-09-02

## Result

`MANAGED_CLI_PATH_STILL_BLOCKED`

No SWE task or ABCD rerun was run. The current CC Switch-selected external provider was used throughout; official Codex OAuth was not used.

## Root Cause

The earlier temporary `CODEX_HOME` was assembled from the CC Switch official Codex OAuth profile, not from the current selected external provider. It therefore lost the external auth/config pairing. The original native launcher additionally used `--ignore-user-config`, which bypassed the active provider configuration.

The C/D managed sessions had a separate startup-order failure: `context init` ran after `codex exec` had already started. Workspace `AGENTS.md` and `.codex/hooks.json` were therefore created too late for that session's startup-time instruction/hook loading. Those sessions also used standalone CLI `0.146.0`, while the current desktop runner is `0.151.0`.

The new benchmark-only builder projects only the active external provider configuration, `auth.json`, and optional global `AGENTS.md` into an otherwise empty per-run home. It excludes sessions, cache, logs, state, SQLite databases, plugins, and prompts. Repository-scoped managed hooks remain in the workspace and must be installed before launching the fresh model session.

## Smoke Results

| Check | Result | Evidence |
| --- | --- | --- |
| External Luna | FAIL | Normal current home and fresh selected-profile home both received external account-group HTTP 404. |
| External Sol | PASS | Fresh minimal home returned `EXTERNAL_SOL_OK`. |
| managed config loaded | PASS_DIAGNOSTIC | Pre-initialized workspace under CLI 0.151 recorded hook startup, PreToolUse, and PostToolUse. |
| root investigation blocked | UNAVAILABLE | Required external Luna controller could not start. |
| root mutation blocked | UNAVAILABLE | Required external Luna controller could not start. |
| fresh child spawned | PASS_DIAGNOSTIC | Runtime audit recorded `collaborationspawn_agent` and `successful_spawn_observed=true`. |
| fork_turns none | PASS_DIAGNOSTIC | Captured delegation recorded `fork_turns=NONE`, required and passing. |
| child mutation allowed | PASS_DIAGNOSTIC | Child `apply_patch` changed `target.txt` from `before` to `after`. |
| bounded handoff | UNAVAILABLE | The diagnostic parent remained in wait; no bounded Controller consumption was observed. |

The Sol diagnostic is not a substitute for the required Luna Controller smoke and is not evidence that the managed Luna path is ready.

## Changes

- Benchmark-only: [prepare_benchmark_codex_home.py](prepare_benchmark_codex_home.py) creates an auditable minimal external-provider home without persistent history contamination.
- Benchmark-only regression test: verifies the helper excludes sessions, plugins, and other state.
- Product: none.

Do not resume ABCD. The selected external provider must first expose `gpt-5.6-luna`, or the user must select an already-configured external Luna route. Then rerun the required fresh pre-initialized managed Luna smoke before any real benchmark.
