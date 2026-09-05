# Official Native Screening Status (2026-09-04)

This report records benchmark-only Native screening after the official
OpenAI/ChatGPT authentication route was selected. It supersedes no earlier
external-provider report. No Thaliris product, routing, guard, isolation, or
escalation source was changed, and no managed C/D or ABCD run was performed.

## Sealed Result

`aio-libs__aiohttp-8823` at
`1d9620cd8789cdf60434fa3bd73a32f2ec2a96d1` is `SEALED_PASS`:

- BASE and NO_EDIT fail as expected.
- GOLD and each of three independent GOLD repeats pass.
- The evaluator checkout is materialized only after model exit. It uses the
  project’s normal Cython generation and a pinned llhttp cache outside every
  model workspace.
- Each Native attempt uses a fresh parentless fixture, workspace, session, and
  official-auth projected `CODEX_HOME`.

| Task | Readiness | B1 Luna | A1 Sol | B2 Luna | A2 Sol | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `aio-libs__aiohttp-8823` | `SEALED_PASS` | `FAIL` | `PASS` | `FAIL` | `PROVIDER_USAGE_LIMIT_INVALID` | `PROVISIONAL_SEPARATION_PENDING_A2` |

`B1` and `B2` both made a plausible but incomplete Cython-parser change. The
trusted F2P tests exercise the Python parser, whose Transfer-Encoding contract
remained unchanged. This is a cross-parsing-path compatibility invariant
omission, rather than a lookup, syntax, timeout, dependency, or evaluator
failure.

`A1` changed `aiohttp/http_parser.py` and passed the trusted evaluator.
Visible test changes were reset before applying the trusted overlay; they were
not treated as a scope violation. Its new changelog file is a reasonable
related artifact, not evaluator or benchmark tampering.

`A2` made zero model calls and emitted no patch. The official CLI reported an
account usage limit with a next available time of 2026-09-07 12:45 PM. It is
therefore invalid for capability comparison and cannot confirm or refute A1.

## Telemetry

| Arm | Model | Result | Input | Cached | Uncached | Output | Reasoning | Calls | Wall time |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 | `gpt-5.6-luna` | FAIL | 2,738,280 | 2,626,816 | 111,464 | 10,128 | 4,089 | 1 | 335.55s |
| A1 | `gpt-5.6-sol` | PASS | 2,168,590 | 2,045,568 | 123,022 | 8,405 | 2,584 | 1 | 326.81s |
| B2 | `gpt-5.6-luna` | FAIL | 1,330,514 | 1,259,264 | 71,250 | 11,036 | 5,708 | 1 | 275.45s |
| A2 | `gpt-5.6-sol` | invalid | 0 | 0 | 0 | 0 | 0 | 0 | 20.64s |

All telemetry unavailable for A2 is recorded as `UNAVAILABLE`; no estimate was
made. Native run records remain outside model workspaces under
`I:\AI PROJECT\abcd-screening\t4-20260903`.

```text
SEALED_TASKS = [aio-libs__aiohttp-8823]
SEPARATION_POOL = []
PROVISIONAL_SEPARATION = [aio-libs__aiohttp-8823]
UNSTABLE_SEPARATION = []
LUNA_SUFFICIENT_CONTROLS = [d0c-s4vage__pfp-128, aaugustin__websockets-543,
  aaugustin__websockets-641, asdf-format__asdf-1907,
  amaranth-lang__amaranth-912]
BOTH_WEAK = [bashtage__arch-752]
ENVIRONMENT_INCONCLUSIVE = [A2 official provider usage limit only]
```

## Next Authorized Action

Retry only fresh official `A2` for `aio-libs__aiohttp-8823` after the official
usage limit clears. If it passes, the task becomes a reproducible separation
and authorizes C/D validation. Until then, C/D and ABCD remain intentionally
unrun. The observed Luna failure is suitable for bounded escalation because it
requires distinguishing the parser implementations’ differing compatibility
rules, but the attention-protection hypothesis is not yet tested.
