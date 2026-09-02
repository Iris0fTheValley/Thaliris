# Sol-success Pool Screening (2026-09-03)

This benchmark-only screen used the configured external CC Switch provider. No official OAuth was used. No Native Luna or Native Sol model run was started because no candidate completed the sealed readiness contract.

| Task | Readiness | B1 Luna | A1 Sol | B2 Luna | A2 Sol | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `aaugustin__websockets-543` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `aaugustin__websockets-641` | FIXTURE_NOT_SEALED | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `aio-libs__aiohttp-8823` | FIXTURE_NOT_SEALED | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `bashtage__arch-752` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `dask-contrib__dask-expr-901` | FIXTURE_NOT_SEALED | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `d0c-s4vage__pfp-128` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `asdf-format__asdf-1907` | FIXTURE_NOT_SEALED | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `alteryx__woodwork-1300` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `amaranth-lang__amaranth-912` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |
| `d0c-s4vage__pfp-126` | ENVIRONMENT_INCONCLUSIVE | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | ENVIRONMENT_INCONCLUSIVE |

## Sets

```text
SEALED_TASKS = []
SEPARATION_POOL = []
PROVISIONAL_SEPARATION = []
UNSTABLE_SEPARATION = []
LUNA_SUFFICIENT_CONTROLS = []
BOTH_WEAK = []
ENVIRONMENT_INCONCLUSIVE = [
  websockets-543, websockets-641, aiohttp-8823, arch-752, dask-expr-901,
  pfp-128, asdf-1907, woodwork-1300, amaranth-912, pfp-126
]
```

## Findings

The sealed gate itself rejected exact revisions containing symlinks, a submodule, or `git archive` export substitution. The candidates that did seal were blocked by legacy third-party runtime requirements: removed Python APIs, scientific-package ABI/API drift, missing `cpp`/`yosys`, or invalid upstream packaging metadata. These are environment artifacts, not model failures, so no Luna-first funnel or Sol confirmation is interpretable this round.

The current-provider Sol/Luna separation question is therefore unanswered. There is no new reproducible separation task and no plausible Luna semantic failure to analyze. It is not worth expanding the single-issue search until evaluator environments are made deterministic. If a repaired readiness pool remains empty, the next experiment should directly test the attention-exposure hypothesis using a large working set, Luna curation, bounded Decision Context, and a Sol decision.

No Thaliris product, routing, guard, isolation, or escalation code was changed. Network and installation enforcement remain `UNVERIFIED`.
