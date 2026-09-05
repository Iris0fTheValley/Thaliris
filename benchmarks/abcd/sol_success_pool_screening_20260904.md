# T4 Sol-success pool screening — 2026-09-04

Provider was official OpenAI/ChatGPT authentication. Models were
`gpt-5.6-luna` and `gpt-5.6-sol`, both at high reasoning effort. No Thaliris
product, routing, guard, isolation, or escalation source was changed.

## Native screening

`aio-libs__aiohttp-8823` at exact revision
`1d9620cd8789cdf60434fa3bd73a32f2ec2a96d1` is a reproducible sealed
separation:

| Arm | Result | F2P | P2P | Scope | Input | Cached | Output | Reasoning | Calls |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| B1 Native Luna | FAIL | FAIL | PASS | PASS | 2,738,280 | 2,626,816 | 10,128 | 4,089 | 1 |
| A1 Native Sol | PASS | PASS | PASS | PASS | 2,168,590 | 2,045,568 | 8,405 | 2,584 | 1 |
| B2 Native Luna | FAIL | FAIL | PASS | PASS | 1,330,514 | 1,259,264 | 11,036 | 5,708 | 1 |
| A2 Native Sol | PASS | PASS | PASS | PASS | 4,428,894 | 4,265,856 | 13,486 | 5,302 | 1 |

Readiness was `SEALED_PASS`: BASE/NO_EDIT failed, GOLD and three independent
repeats passed. Each arm used an independent parentless fixture and session;
trusted evaluator materialization occurred after model exit.

Luna made a plausible Cython-parser fix but omitted the compatibility invariant
between the C/llhttp and pure-Python parser paths. Sol preserved the shared
Transfer-Encoding contract, including request/response framing differences.
This is a plausible semantic failure (cross-module compatibility), not a
syntax, dependency, timeout, or scope failure.

## Managed validation

Fresh Thaliris-initialized workspaces were used for C, D, and a hook-path D2
retry. Independent trusted evaluators gave all three model patches PASS,
NO_EDIT expected FAIL, GOLD PASS, and GOLD repeat 1/2/3 PASS.

| Arm | Model | Evaluator | Sol calls | Decision Context | Result |
| --- | --- | --- | ---: | ---: | --- |
| C Luna-only | Luna | PASS | 0 | n/a | PASS (unexpected control) |
| D Hybrid | Luna | PASS | 0 | n/a | PASS, no escalation |
| D2 Hybrid hook retry | Luna | PASS | 0 | n/a | PASS, no escalation |

D/D2 performed investigation, one fresh child dispatch and a bounded wait, then
implemented and verified the fix directly. The current routing policy did not
invoke Sol. Consequently this is **not** `HYBRID_RESCUE_PASS`; there is no
evidence that bounded escalation rescued this task. Runtime hook markers for
root guard/post-dispatch observation remained `UNKNOWN` in the standalone CLI
run, despite managed hook configuration being present, so no stronger guard
claim is made.

Native A1 Sol input was 2,168,590 tokens. D Sol input was zero because Sol was
not invoked; the arithmetic exposure ratio is 0, but it is not a rescue-mode
comparison. C/D wall times and child token telemetry were not emitted by the
standalone managed runner and are recorded as `UNAVAILABLE`, not estimated.

```text
SEALED_TASKS = [aio-libs__aiohttp-8823]
SEPARATION_POOL = [aio-libs__aiohttp-8823]
PROVISIONAL_SEPARATION = []
UNSTABLE_SEPARATION = []
LUNA_SUFFICIENT_CONTROLS = [d0c-s4vage__pfp-128, aaugustin__websockets-543,
  aaugustin__websockets-641, asdf-format__asdf-1907,
  amaranth-lang__amaranth-912]
BOTH_WEAK = [bashtage__arch-752]
ENVIRONMENT_INCONCLUSIVE = []
```

The single-issue capability boundary is productive: a new reproducible
Luna-fail/Sol-pass task was found. The task is suitable for a future bounded
escalation pilot, but this run does not support the stronger attention-
protection hypothesis because managed routing did not call Sol and C already
passed.
