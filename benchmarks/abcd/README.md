# Thaliris ABCD benchmark

This directory records the strict ABCD rerun performed on the `86cc7e7`
baseline with real `codex-cli 0.146.0-alpha.3.1`.

## Workloads

- **T1**: a micro negative-control task with one obvious version regression.
- **T2**: a medium investigation covering bounded Controller artifact
  projection and a multi-file test path.
- **T3**: a noisy investigation with legacy payload handling, flattened
  collaboration naming, hook-observation semantics, source history, logs, and
  multiple candidate failures.

The acceptance standard was identical across A, B, C, and D: fix only the
seeded regression, pass its focused tests and the relevant full suite, keep the
diff minimal, and avoid changes to tests or benchmark evidence.

## Workflows

- **A — Native Sol**: no Thaliris managed router; Sol owns the complete task.
- **B — Native Luna**: no Thaliris managed router; Luna owns the complete task.
- **C — Thaliris Luna-only**: managed router; Controller and child use Luna.
- **D — Thaliris Hybrid**: managed router; current policy may escalate, but it
  did not invoke Sol for these three workloads.

Each run used an independent clean clone. Native clones used an empty local
`.codex/hooks.json` and a Native baseline `AGENTS.md`; C/D retained the managed
router. Root/session identifiers were cleared between invocations. The final
statistics exclude earlier shared-worktree/session-contaminated attempts.

## Reproduction notes

The model run itself is intentionally not automated by this repository: it
requires the installed Codex CLI, account state, and the configured MCP tools.
The workload acceptance tests are checked in under `tests/test_abcd_workload_acceptance.py`.
The sanitized run ledger is `results.json`. The benchmark-only
`analyze_orchestration.py` reconstructs control-call classifications from
exported session JSONL using `clean_run_manifest.json`; its baseline output is
`orchestration_baseline.json`. The benchmark-only `summarize_sessions.py` and
`build_rerun_report.py` summarize the four orchestration-economy reruns listed
in `clean_run_manifest_v7.json`, `orchestration_v7.json`,
`session_metrics_v7.json`, and `rerun_v7_report.json`. Raw Codex session
telemetry and external clone contents are not committed.

The policy-only experiment is on `codex/abcd-benchmark-20260901` after
`247abc4`. It changes only the managed instruction surface: use a realistic
single blocking wait after spawn, avoid normal-path topology/status chatter,
and reserve `send_message` for material updates. It does not change routing
or isolation implementation.

For external candidate screening, `build_sealed_fixture.py` creates a
model-only workspace from an exact source revision and a synthetic baseline
commit. Run `validate_sealed_fixture.py` before every model invocation; it is
fail-closed and returns `SEALED_PASS` or `FIXTURE_NOT_SEALED`. Evaluator assets
are materialized only after model completion. The DSPy-1609 acceptance and
legacy fixture audit are recorded in `sealed_fixture_v2.md`.

## Result headline

Isolation behavior was observed end to end, and D matched A on the three
fixture qualities. D reduced root peak context by about 29% on average, but D
used 2.88x A's total input+output and never escalated to Sol. Therefore this
rerun does not establish total-token saving or Sol-attention protection in the
intended Sol-needed regime.
