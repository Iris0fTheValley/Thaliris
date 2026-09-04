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

Native Sol A was started with the official OpenAI/ChatGPT provider and a fresh
sealed workspace, but the account usage limit was reached before the first
model sample (`turn.failed`, zero model turns and no valid model result). It is
therefore `PROVIDER_USAGE_LIMIT_INVALID`, not a capability failure. Native B,
managed C, and managed D were not started; no A/B/C/D quality conclusion is
claimed. A fresh A run is the next permitted action after the official quota
resets, followed by B only if A produces a valid result.

```text
SEALED_TASKS = [d_sakiko_shared_live2d_medium]
NATIVE_A = PROVIDER_USAGE_LIMIT_INVALID
NATIVE_B = NOT_RUN
MANAGED_C = NOT_RUN
MANAGED_D = NOT_RUN
SOL_EXPOSURE_RATIO = UNAVAILABLE
INTERPRETABLE = false
ATTENTION_PROTECTION_HYPOTHESIS = NOT_TESTED
```

The aiohttp task is complete separately: Native Luna B1/B2 failed, Native Sol
A1/A2 passed, and managed C2 passed as `LUNA_ORCHESTRATION_RESCUE`; no D3 Sol
escalation was run.
