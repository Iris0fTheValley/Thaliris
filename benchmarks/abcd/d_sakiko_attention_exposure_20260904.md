# D_sakiko attention-exposure benchmark readiness — 2026-09-04

## Source provenance

The target repository is `Iris0fTheValley/D_sakiko`; its exact sealed base is
merge-base `cdb3f5d591e831b503ce53dfd73489d2207b3040` (tree
`92ad9a822dc1ea93cfb5559df3f5e224f9d52240`). The repository README and
`pyproject.toml` identify two relevant upstream projects. Each was cloned in
full, independently, before any model fixture was built:

| Project | Authoritative URL | Revision | Tree | Files |
| --- | --- | --- | --- | ---: |
| GPT-SoVITS | `https://github.com/RVC-Boss/GPT-SoVITS` | `48b1a0169a28582a8984402f82cf438d3bfa6aca` | `f24ae1c9e2af77c985eb8a7e691a4660b05ad0dc` | 241 |
| live2d-py | `https://github.com/EasyLive2D/live2d-py` | `f9512a458e7b67365cd504f94a6d17e419533050` | `fed42be8a2a95ad16fef90cfe7f3a9fb584025d5` | 660 |

The complete trees are outside the model fixture at
`I:\AI PROJECT\abcd-screening\d-sakiko-20260904\trusted\upstream\`. No
files were copied from the gold branch into the model baseline.

## Sealed baseline and contract

The model fixture was constructed from the exact D_sakiko merge-base using
`git archive`, with raw UTF-8 path handling for the repository's non-ASCII
asset names. The original `.git` was removed and replaced by one synthetic
parentless commit (`bc32d93bfb1b1a059a03948d248bb16a4bfa64e5`); remotes,
remote refs, tags, future commits, benchmark files and evaluator files are
absent. `validate_sealed_fixture.py` returned `SEALED_PASS` after an isolated
Python 3.11 environment was prepared.

The hidden contract is behavior-focused rather than a gold diff:

- shared behavior scheduling and audio/motion lifecycle;
- renderer command normalization and failure handling;
- runtime ingress fanout and state transitions.

Gold-side contract tests are the three pure Python suites
`test_live2d_shared_behavior.py`, `test_renderer_contract.py`, and
`test_runtime_ingress.py` (15 tests, 15 passed). Running those tests against
the base checkout fails during collection because the shared modules do not
exist. The WebUI presentation suite requires the native Torch/Live2D runtime
and is not used as the primary medium contract on this Windows host.

## Arms

The medium task statement preserves the full repository and asks for shared
renderer ownership, runtime ingress, behavior scheduling, lifecycle/bye
handling, backend/frontend compatibility, and regression tests. It does not
name files, commits, branches, expected model outcomes, or escalation.

The first Native Sol attempt was invalidated by an official usage limit before
sampling. After the quota recovered, a fresh Sol A2, Luna B2, managed Luna C3,
and managed Hybrid D3 were run under the same one-turn, high-reasoning pilot
rule. This is a comparable execution rule, not equal token usage: each arm had
the same original task, full repository, fresh isolation, and no fixed token
cap, so natural investigation depth differs.

| Arm | Input tokens | Output | Focused tests | Final quality profile | Sol calls |
| --- | ---: | ---: | ---: | --- | ---: |
| A2 Native Sol | 7,717,195 | 21,443 | 3 Python contract tests | `PARTIAL`: shared contract started, but hidden shared behavior/ingress modules remained absent | 1 |
| B2 Native Luna | 13,634,124 | 45,443 | 3 Python contract tests; frontend self-tests/build reported pass | `HIGH_QUALITY_PARTIAL`: desktop/backend/frontend contract work plus deterministic frontend scheduling; full regression not collected | 0 |
| C3 managed Luna-only | 14,409,860 | 35,608 | 4 Python tests; frontend self-tests/lint/build reported pass | `HIGH_QUALITY_PARTIAL`: broad three-layer progress, fresh child and bounded wait | 0 |
| D3 managed Hybrid | 13,918,652 | 42,986 | 4 Python tests; frontend self-tests/lint/build reported pass | `HIGH_QUALITY_PARTIAL`: broad three-layer progress, fresh child and bounded wait; no Sol escalation | 0 |

The trusted contract evaluator contains 15 gold-derived behavioral tests. The
benchmark-only adapter `d_sakiko_quality_evaluator.py` discovers equivalent
entry points and runs the same contract suites after model exit. Gold
validation is 15/15 PASS; sealed base/no-edit is the expected collection
failure because the shared modules do not exist at merge-base. Scoring is
behavior-oriented and does not require changed-file or gold-diff equality.

D3 JSONL mechanically records one fresh `spawn_agent` and one bounded `wait`;
no `send_message`-to-Sol or Sol model turn occurred. Thus D3's arithmetic Sol
exposure is zero, but `INTERPRETABLE=false`: it is not an attention-saving
rescue comparison because the arm did not invoke Sol. The current routing made
the same decision as C3 for this pilot.

```text
SEALED_TASKS = [d_sakiko_shared_live2d_medium]
NATIVE_A = HIGH_QUALITY_PARTIAL (A2; hidden-contract completeness gap)
NATIVE_B = HIGH_QUALITY_PARTIAL
MANAGED_C = HIGH_QUALITY_PARTIAL
MANAGED_D = HIGH_QUALITY_PARTIAL_NO_SOL_ESCALATION
SOL_EXPOSURE_RATIO = 0 (arithmetic only)
INTERPRETABLE = false
ATTENTION_PROTECTION_HYPOTHESIS = NOT_SUPPORTED_BY_THIS_PILOT
```

The aiohttp task is complete separately: Native Luna B1/B2 failed, Native Sol
A1/A2 passed, and managed C2 passed as `LUNA_ORCHESTRATION_RESCUE`. Its managed
smoke evidence mechanically records root investigation/mutation guard,
fresh-child dispatch, `fork_turns=none`, bounded wait, and child mutation
allowed. No aiohttp D3 Sol escalation was run.

The D_sakiko medium pilot is useful as a quality-baseline run, but it does not
justify a full large-workload run yet. First normalize evaluator entry points,
then repeat A/B/C/D under an explicit wall-time or model-call budget. Proceed
to the full shared-live2d-upstream task only if that pilot produces a stable
quality comparison and an interpretable Sol invocation.
