# Sol-success Pool Screening (2026-09-03)

This benchmark-only screen used the configured external CC Switch provider;
official OAuth was not used. The Native runner now uses the current
`codex-cli 0.152.1` executable and a fresh minimal provider-only `CODEX_HOME`
for every run. No Thaliris C/D or ABCD run was performed.

| Task | Readiness | B1 Luna | A1 Sol | B2 Luna | A2 Sol | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `asdf-format__asdf-1907` | SEALED_PASS | ENVIRONMENT_INVALID | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `aaugustin__websockets-543` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `aaugustin__websockets-641` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `aio-libs__aiohttp-8823` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `bashtage__arch-752` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `dask-contrib__dask-expr-901` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `d0c-s4vage__pfp-128` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `alteryx__woodwork-1300` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `amaranth-lang__amaranth-912` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `d0c-s4vage__pfp-126` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |

```text
SEALED_TASKS = [asdf-format__asdf-1907]
SEPARATION_POOL = []
PROVISIONAL_SEPARATION = []
UNSTABLE_SEPARATION = []
LUNA_SUFFICIENT_CONTROLS = []
BOTH_WEAK = []
ENVIRONMENT_INCONCLUSIVE = [all candidates except asdf-format__asdf-1907]
```

The fresh asdf B1 reached the external provider through the correct CLI and
minimal home, then received `403 INSUFFICIENT_BALANCE` before a model turn;
telemetry therefore contains zero model calls and the run is not a Luna
failure. The first attempt also exposed a long Windows plugin-materialization
path; the runner now places per-run homes below `C:\thaliris-codex` to avoid
that unrelated path-length artifact.

No candidate produced an interpretable Luna/Sol separation. The pool remains
blocked by provider account state and legacy evaluator feasibility, so no
plausible semantic Luna failure can be claimed and no task is authorized for
ABCD. If the provider is restored, rerun asdf B1 first with this runner; only
a real B1 semantic failure should trigger A1. If a repaired pool remains
empty, pivot to the attention-exposure benchmark rather than expanding this
single-issue search.

Network and installation enforcement remain `UNVERIFIED`. No Thaliris
product, routing, guard, isolation, or escalation code was changed.
