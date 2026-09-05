# External benchmark readiness — 2026-09-02

This benchmark-only run used clean trusted worktrees at the exact revisions
below. No model was run (`model_runs=0`); all patches and test overlays stayed
in evaluator-only directories. OS-level network isolation could not be
mechanically proven, so `network_enforcement=UNVERIFIED` is retained.

| Task | Source | Exact base revision | F2P/P2P | Model fixture | BASE / NO_EDIT | GOLD | GOLD repeat | Final |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `fluent__fluent-bit-10563` | SWE-bench-Live | `c872957b57b2a8704e3b8cbc7f3994b430f96140` | 1 / 71 | FIXTURE_NOT_SEALED | not run | not run | — | FIXTURE_NOT_SEALED |
| `elastic__synthetics-316` | SWE-rebench-V2 | `f52f0bf3d18ca418d1eec4afd1370751fdd914ce` | 1 / 83 | SEALED_PASS | test patch did not apply | not run | 0/3 | EVALUATOR_INCONCLUSIVE |
| `reata__sqllineage-524` | SWE-bench-Live | `4adcc8f46fe9c5f919c9d942e1e1a0cf7d342cc2` | 4 / 376 | SEALED_PASS | 4 F2P fail; P2P pass / same | 381 pass | 3/3 | SEALED_PASS |
| `mozilla-services__cliquet-203` | SWE-rebench-V2 | `41a48da66062b4e948ef1f6ce5183d2752304ecf` | 1 / 13 | SEALED_PASS | 1 F2P fail; 27 pass / same | 28 pass | 3/3 | SEALED_PASS |
| `editorconfig-checker__editorconfig-checker-360` | SWE-rebench-V2 | `6116ec6685b33652e9e25def9b8897ed4b015c7d` | 13 / 28 | SEALED_PASS | F2P compile/test failures; P2P pass / same | PASS | 3/3 | SEALED_PASS |
| `webpack-contrib__copy-webpack-plugin-590` | SWE-rebench-V2 | `a9b06a635a7d3458c8e2ed2b10cc3fd1e02b5f37` | 21 / 197 | FIXTURE_NOT_SEALED | not run | not run | — | FIXTURE_NOT_SEALED |
| `privacyidea__privacyidea-3852` | SWE-bench-Live | `969e5f55d603ea86b3f0832e23a69e0c58621d3e` | 1 / 1562 | FIXTURE_NOT_SEALED | not run | not run | — | FIXTURE_NOT_SEALED |
| `reata__sqllineage-565` | SWE-bench-Live | `4c6c65e7c94b87b50f26ad7f35ac26ed26a54cee` | 2 / 380 | SEALED_PASS | 2 F2P fail; P2P pass / same | 383 pass | 3/3 | SEALED_PASS |
| `databacker__mysql-backup-266` | SWE-rebench-V2 | `738a5d651d8501f6b17bcd4d1ed9df481eb8f557` | 6 / 13 | SEALED_PASS | 6 F2P fail; P2P pass / same | PASS | 3/3 | SEALED_PASS |
| `sphinx-doc__sphinx-11888` | SWE-bench-Live | `882a174e48a4dfd22d4fab4b2e3b74f091b3f98e` | 1 / 1997 | SEALED_PASS | 30.23s timeout / not established | 30.20s timeout | not run | EVALUATOR_INCONCLUSIVE |

## VALID_SEALED_TASKS

```text
[
  "reata__sqllineage-524",
  "mozilla-services__cliquet-203",
  "editorconfig-checker__editorconfig-checker-360",
  "reata__sqllineage-565",
  "databacker__mysql-backup-266"
]
```

The three `FIXTURE_NOT_SEALED` tasks contain source symlink/submodule entries
that the fail-closed archive builder intentionally refuses to materialize.
Cliquet required a prepared Python 3.8 legacy dependency set; WebTest 1.4.3
was required for the trusted evaluator to pass. Sphinx remains evaluator
inconclusive because its full preservation suite is large and exceeded the
bounded Windows run window. None of these classifications is a model-quality
result.
