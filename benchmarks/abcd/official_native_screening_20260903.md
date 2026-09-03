# Official Native Capability Screening (2026-09-03)

This benchmark-only follow-up used official OpenAI ChatGPT authentication for
Native Luna. It did not run Thaliris C/D or ABCD, and did not modify product,
routing, guard, isolation, escalation, or Decision Context code.

## Controls

- Branch: `codex/abcd-benchmark-20260901`; benchmark baseline:
  `871a2dfc611767a1b11e4f4839337f899c0e994d`.
- Provider: official OpenAI / ChatGPT authentication. Each run copied only
  `auth.json` to a fresh `CODEX_HOME`; `codex exec --ignore-user-config`
  prevented loading the configured third-party provider settings.
- Luna: `gpt-5.6-luna`, `reasoning_effort=high`; Sol was intentionally not
  launched because no eligible real Luna semantic failure was produced.
- Each model run used a fresh sealed workspace and home. The evaluator was
  materialized only after model exit. The three actual fixture gates returned
  `SEALED_PASS`.
- The official Luna smoke returned `OK`. Its telemetry was 12,870 input,
  8,960 cached input, 19 output, and 12 reasoning tokens.
- Network, installation, and whole-machine path isolation remain
  `UNVERIFIED`; this is not a claim of hermetic host isolation.

## Candidate Status

| Task | Readiness | B1 Luna | A1 Sol | B2 Luna | A2 Sol | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `aaugustin__websockets-543` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `aaugustin__websockets-641` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `aio-libs__aiohttp-8823` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `bashtage__arch-752` | `SEALED_PASS` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `dask-contrib__dask-expr-901` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `d0c-s4vage__pfp-128` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `asdf-format__asdf-1907` | `SEALED_PASS` | `INVALID_SCOPE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `INVALID_SCOPE` |
| `alteryx__woodwork-1300` | `ENVIRONMENT_INCONCLUSIVE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `ENVIRONMENT_INCONCLUSIVE` |
| `amaranth-lang__amaranth-912` | `SEALED_PASS` | `INVALID_SCOPE` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `INVALID_SCOPE` |
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
ENVIRONMENT_INCONCLUSIVE = [
  aaugustin__websockets-543,
  aaugustin__websockets-641,
  aio-libs__aiohttp-8823,
  bashtage__arch-752,
  dask-contrib__dask-expr-901,
  d0c-s4vage__pfp-128,
  alteryx__woodwork-1300,
  d0c-s4vage__pfp-126
]
```

## Native Evidence

- `arch-752` (`2c8e9ef56ece657f741e187c0149683280503350`): official B1
  completed one Luna call in 318.09 seconds (1,107,603 input; 1,031,168
  cached; 12,703 output; 8,431 reasoning) without a model patch. The final
  evaluator baseline and gold both failed because the exact archived source
  imports packaging-generated `arch._version`, which is absent from the
  archive. This is an environment artifact, so no Sol run was authorized.
- `asdf-1907` (`74fdcd96540049e4824b4da2bbe3ffdf42d23cfc`): official B1 made
  one real Luna call (521,020 input; 481,024 cached; 3,989 output; 1,327
  reasoning; 148.11 seconds). Its code change was a plausible recursive
  YAML-constructor fix, but it also altered `asdf/_tests/test_util.py`; the
  trusted evaluator test patch therefore could not apply. Gold and gold
  repeats pass on a clean fixture, but this model run is `INVALID_SCOPE`, not
  an eligible semantic failure.
- `amaranth-912` (`11d5bb19eb34463918c07dc5e2e0eac7dbf822b0`): official B1
  made one real Luna call (848,751 input; 762,880 cached; 8,800 output; 5,585
  reasoning; 277.06 seconds). The model patch passed the target evaluator,
  and no-edit failed as expected; gold passed 3/3. It also modified
  `tests/test_hdl_ast.py`, which is disallowed hidden-test manipulation, so
  the run is `INVALID_SCOPE` rather than a Luna sufficient control.

The first official B1 attempt for all three tasks is retained as external raw
evidence only: its evaluator selector was removed by the evaluator reset
before execution. The runner now rematerializes that trusted selector after
each reset; those first results are `ENVIRONMENT_INCONCLUSIVE` and were not
used for any classification.

## Conclusions

1. No new current-provider reproducible separation was found.
2. No task is suitable for an ABCD x1 pilot from this evidence. `asdf-1907`
   has the most interesting plausible semantic approach but must first be
   rerun under a protocol that treats any test edit as an immediate invalid
   run; it is not an ABCD candidate now.
3. The only plausible semantic Luna behavior was `asdf-1907`'s recursive
   constructor approach. It cannot be credited because it also changed tests.
   `amaranth-912` is functionally passing but invalid for the same reason.
4. It is not yet justified to expand single-issue screening: only three
   previously sealed tasks were eligible, and none yielded a valid B1
   semantic outcome that could authorize Sol. Repairing the archive adapter
   would require generated-package metadata work, which is out of scope.
5. `SINGLE_ISSUE_CAPABILITY_BOUNDARY_NOT_PRODUCTIVE` is **not established**:
   the ten-candidate pool was not validly measured to completion. If a future
   clean eligible set again yields only Luna/Sol both-pass or both-fail, stop
   expanding SWE issues and pivot to the attention-exposure benchmark: a real
   large-working-set task, Luna investigation/curation, bounded high-value
   Decision Context, then Sol decision.

Structured telemetry and raw artifact pointers are in
`official_native_screening_20260903.json`; external run artifacts remain under
`I:\AI PROJECT\abcd-screening\t4-20260903`.
