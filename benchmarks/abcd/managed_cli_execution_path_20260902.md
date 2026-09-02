# Managed CLI Execution Path - 2026-09-02

## Result

`MANAGED_CLI_PATH_STILL_BLOCKED`

No SWE task or ABCD rerun was run. The current CC Switch-selected external provider was used throughout; official Codex OAuth was not used. A fresh rerun was performed after the provider recovered.

## Root Cause

The earlier temporary `CODEX_HOME` was assembled from the CC Switch official Codex OAuth profile, not from the current selected external provider. It therefore lost the external auth/config pairing. The original native launcher additionally used `--ignore-user-config`, which bypassed the active provider configuration.

The C/D managed sessions had a separate startup-order failure: `context init` ran after `codex exec` had already started. Workspace `AGENTS.md` and `.codex/hooks.json` were therefore created too late for that session's startup-time instruction/hook loading. Those sessions also used standalone CLI `0.146.0`, while the current desktop runner is `0.151.0`. The fresh rerun pre-initialized the workspace and used CLI `0.151.0`.

The new benchmark-only builder projects only the active external provider configuration, `auth.json`, and optional global `AGENTS.md` into an otherwise empty per-run home. It excludes sessions, cache, logs, state, SQLite databases, plugins, and prompts. Repository-scoped managed hooks remain in the workspace and must be installed before launching the fresh model session. The earlier Luna 404 did not recur: both model smoke calls now resolve through the external endpoint.

## Smoke Results

| Check | Result | Evidence |
| --- | --- | --- |
| External Luna | PASS | Fresh minimal selected-profile home returned `LUNA_SMOKE_OK` through the external Responses endpoint with CLI 0.151.0. |
| External Sol | PASS | Fresh minimal home returned `EXTERNAL_SOL_OK`. |
| managed config loaded | PASS_DIAGNOSTIC | Pre-initialized workspace under CLI 0.151 recorded hook startup, PreToolUse, and PostToolUse. |
| root investigation blocked | FAIL | Fresh Luna controller read `target.txt` with a shell command; output was `before`, exit code 0. |
| root mutation blocked | FAIL | Fresh Luna controller directly changed `target.txt` to `after`. |
| fresh child spawned | PASS | JSONL recorded one `collaborationspawn_agent` with a fresh child receiver. |
| fork_turns none | PASS | Spawn event carried `fork_turns="none"` and an isolation reason. |
| child mutation allowed | PASS | Child completed with bounded result; it found `target.txt` already `after` because root mutation had been allowed. |
| bounded handoff | PASS | One blocking `wait` completed and the Controller consumed the child's bounded result. |

The rerun proves provider resolution and child dispatch, but it also leaves a reproducible integration failure: root action guards are not enforced in the current CLI path. Therefore the managed path is still blocked.

## Changes

- Benchmark-only: [prepare_benchmark_codex_home.py](prepare_benchmark_codex_home.py) creates an auditable minimal external-provider home without persistent history contamination.
- Benchmark-only regression test: verifies the helper excludes sessions, plugins, and other state.
- Product: none.

Do not resume ABCD. Preserve this failing smoke as the regression case and repair only the CLI integration/guard loading needed to block root investigation and mutation. No routing or escalation policy was changed.
