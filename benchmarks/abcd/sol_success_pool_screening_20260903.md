# Sol-success Pool Screening (2026-09-03)

This benchmark-only report records the first-stage sealed-feasibility and
Native Luna-first screening requested for the current-provider Sol-success
candidate pool. It used the configured external CC Switch route; official
OAuth was not used. No Thaliris C/D or ABCD run was performed, and no Thaliris
product, routing, guard, isolation, or escalation code was changed.

## Controls

- Former benchmark development branch (now deleted; policy experiment commit
  `247abc48eb9d057ff528c2f6998a9cc434dd7722`).
- Candidate base revisions were exact and sealed before any Native attempt.
- Sealed fixtures followed the required archive, synthetic parentless commit,
  no-remote/no-history, and evaluator-after-exit controls.
- Native Luna used `gpt-5.6-luna`, `reasoning_effort=high`, a fresh sealed
  workspace, and a fresh provider-only `CODEX_HOME` for each attempt.
- Sol was not run because no B1 attempt produced a real Luna semantic failure.
- CLI: `codex-cli 0.152.1`.

## Candidate status

| Task | Readiness | B1 Luna | A1 Sol | B2 Luna | A2 Sol | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `aaugustin__websockets-543` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `aaugustin__websockets-641` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `aio-libs__aiohttp-8823` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `bashtage__arch-752` | `SEALED_PASS` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `dask-contrib__dask-expr-901` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `d0c-s4vage__pfp-128` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `asdf-format__asdf-1907` | `SEALED_PASS` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `alteryx__woodwork-1300` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `amaranth-lang__amaranth-912` | `SEALED_PASS` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `d0c-s4vage__pfp-126` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |

```text
SEALED_TASKS = [
  bashtage__arch-752,
  asdf-format__asdf-1907,
  amaranth-lang__amaranth-912
]
SEPARATION_POOL = []
PROVISIONAL_SEPARATION = []
UNSTABLE_SEPARATION = []
LUNA_SUFFICIENT_CONTROLS = []
BOTH_WEAK = []
ENVIRONMENT_INCONCLUSIVE = [all 10 candidates]
```

The seven other candidates were stopped at readiness because their evaluator
or dependency setup was inconclusive. They were not promoted to model runs.
The three `SEALED_PASS` candidates reached the correct external Luna route,
but every B1 attempt received `503 SERVICE_UNAVAILABLE` before sampling;
`model_calls=0`, with F2P/P2P therefore `UNAVAILABLE`. Scope was vacuously
`PASS` because no model changed the workspace. These are provider failures,
not Luna failures, so the B1-fail funnel did not authorize A1 Sol.

An independent smoke using the same external CC Switch configuration returned
`OK` for `gpt-5.5` and `503 SERVICE_UNAVAILABLE` for `gpt-5.6-luna`; neither
used official OAuth. This identifies the current blocker as the Luna route at
the provider rather than the sealed fixture or authentication setup.

Detailed per-run telemetry, including unavailable fields recorded as
`UNAVAILABLE`, is in
`benchmarks/abcd/sol_success_pool_screening_20260903.json`. External artifacts
are under `I:\AI PROJECT\abcd-screening\t4-20260903`.

## Required conclusions

1. No new current-provider reproducible separation was found. The
   `SEPARATION_POOL` is empty because no valid Luna sample was produced.
2. No task is ready for ABCD x1. After the provider is restored, rerun B1 on
   `arch-752`, `asdf-1907`, and `amaranth-912`; run Sol only after a real Luna
   semantic failure, then apply B2/A2 only to a provisional separation.
3. No plausible Luna semantic failure can be classified in this round:
   there were zero model calls and no evaluator result for every Native
   attempt.
4. It remains reasonable to retry these sealed candidates after the provider
   route is healthy. If the repaired pool still yields no Luna-fail/Sol-pass
   pair, stop expanding single-issue SWE searches.
5. This round does not establish
   `SINGLE_ISSUE_CAPABILITY_BOUNDARY_NOT_PRODUCTIVE`, because provider
   unavailability prevented capability measurement. If the retry remains
   empty, record that verdict and pivot to the attention-exposure benchmark:
   a large working-set task with Luna investigation/curation and bounded
   high-value Decision Context followed by Sol decision.

Network and installation enforcement remain `UNVERIFIED`. The report does not
authorize C/D or ABCD execution.
