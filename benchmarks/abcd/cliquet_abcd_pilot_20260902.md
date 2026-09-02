# Cliquet ABCD pilot — 2026-09-02

## Verdict

`PILOT_INVALID_ENVIRONMENT`. The two fresh native attempts reached `SEALED_PASS`, but the configured custom provider returned HTTP 404 for both requested model IDs (`gpt-5.6-luna` and `gpt-5.6-sol`). No model response, product patch, evaluator run, or managed-routing trajectory was produced. C and D fixtures independently reached `SEALED_PASS` and were stopped before model execution once this objective capability was unavailable.

This is not a Native A/B quality result and must not be counted as a Luna failure, Sol pass, escalation result, or attention-protection result.

## Arms

| Arm | Models | Result | F2P/P2P | Sol input | Total input | Root peak | Control calls |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| A | Sol | ENVIRONMENT_INVALID | UNAVAILABLE / UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| B | Luna | ENVIRONMENT_INVALID | UNAVAILABLE / UNAVAILABLE | n/a | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| C | Luna Controller + Luna child | ENVIRONMENT_INVALID | UNAVAILABLE / UNAVAILABLE | n/a | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| D | Luna -> possible Sol -> Luna | ENVIRONMENT_INVALID | UNAVAILABLE / UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

Run order was B, A, C, D. A and B each used a fresh synthetic single-commit workspace and passed the pre-model sealed gate. Their telemetry contains one started turn and zero successful model calls; all token fields are `UNAVAILABLE`. C and D each used a separate fresh fixture and passed the same gate. Since no model session could start, D Sol invocation, escalation policy behavior, Decision Context boundedness, quality retention, and all derived ratios are not interpretable.

## Readiness authority

The trusted evaluator readiness for base revision `41a48da66062b4e948ef1f6ce5183d2752304ecf` was already established independently: baseline `1 F2P failure / 27 P2P passes`, gold `28/28`, and gold repeat `3/3 PASS`. Network and installation enforcement remain `UNVERIFIED`.

The only code change in this milestone is a benchmark-harness compatibility fix for `Path.write_text`; no Thaliris product architecture, isolation, Controller guard, or routing policy was changed.

## Required questions

1. A Sol PASS? **Not measurable; environment invalid.**
2. B Luna FAIL? **Not measurable; environment invalid.**
3. C Luna-only FAIL? **Not measurable; model not started.**
4. D invoked Sol? **UNAVAILABLE; D not started.**
5. D PASS? **Not measurable.**

No new product defect can be inferred. Do not proceed to `ABCD x3` until both requested model IDs are available through the execution provider; then repeat the exact protocol from fresh sealed workspaces.
