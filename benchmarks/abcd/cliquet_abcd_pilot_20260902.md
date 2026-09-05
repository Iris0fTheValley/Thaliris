# Cliquet ABCD pilot - 2026-09-02

## Verdict

This completed `cliquet-203 ABCD x1` run does **not** support the intended Hybrid hypothesis. Fresh official-provider native runs both passed, so the earlier Sol/Luna separation did not reproduce. Managed C/D runs passed the pre-model sealed gate and used independent evaluators, but neither produced the required fresh child. Both were a single Luna root turn with zero observed `spawn_agent` and `wait_agent` calls; C and D therefore violate the managed-arm protocol. D did not invoke Sol.

| Arm | Models | Result | F2P/P2P | Sol input | Total input | Root peak | Control calls |
| --- | ------ | ------ | ------: | --------: | ----------: | --------: | ------------- |
| A | Sol | PASS | 0 / 28 | 292,930 | 299,011 | 292,930 | 0 |
| B | Luna | PASS | 0 / 28 | n/a | 718,228 | 705,266 | 0 |
| C | Luna root | FAIL; arm protocol failure | 1 / 27 | n/a | 1,140,974 | 1,128,977 | `spawn=0`, `wait=0` |
| D | Luna root | Product PASS; arm protocol failure | 0 / 28 | n/a | 1,592,273 | 1,582,985 | `spawn=0`, `wait=0`, `task-status=4` |

Input includes cached input; total input is input plus output. Token telemetry is session-reported, not billing estimates.

## Protocol Facts

- Run order: B, A, C, D.
- Every counted arm used a fresh synthetic one-commit workspace at exact base `41a48da66062b4e948ef1f6ce5183d2752304ecf` and emitted `SEALED_PASS` before model startup.
- Dependencies were newly prepared Python 3.8 environments with WebTest 1.4.3, Pyramid 1.10.8, and Werkzeug 0.16.1.
- Evaluator assets were materialized only after model completion. The evaluator projected only `cliquet/` product diffs, then applied trusted test/gold overlays. It established no-edit failure and gold `3/3` before classification.
- Network and installation enforcement remain `UNVERIFIED`.
- Earlier custom-provider 404 runs and the first official A/B attempt (a CRLF model-patch serialization bug) are discarded and excluded.

## Required Answers

1. A Sol PASS: **yes**.
2. B Luna FAIL: **no; B PASS**. Native separation was not reproduced.
3. C Luna-only FAIL: **product FAIL (1 F2P, 27 P2P)**, but C was not a valid Luna-controller-plus-fresh-child arm.
4. D invoked Sol: **no**. This is not attention-protection evidence because D had no Sol decision point.
5. D PASS: **product evaluator PASS (28/28)**, but D is protocol-noncompliant because Controller-only/fresh-child execution did not occur.

## Decision Context And Exposure

D produced no Sol model call, no `sol-high` handoff, and no serialized Decision Context. Its Decision Context size and raw investigation excluded from Sol are `NOT_APPLICABLE`. `Sol Exposure Ratio` and `Total Compute Ratio` are both `NOT INTERPRETABLE`.

## Product Finding

The pilot exposed an integration defect: after `context init` in a fresh Codex CLI session, current managed routing did not produce an observed `spawn_agent` call and did not prevent root source investigation/mutation. This is reported only; routing, isolation, Controller guard, and product code were not changed.

Do not proceed to `A/B/C/D x3`. First validate a repair for managed CLI dispatch/guard integration, then establish a new current sealed task where Native Sol and Luna actually separate before retesting escalation.
