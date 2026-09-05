# Native model calibration (2026-09-02)

This is a benchmark-only calibration on the former (now deleted) benchmark
development branch; its policy experiment began at
`247abc48eb9d057ff528c2f6998a9cc434dd7722`.
No Thaliris C/D run and no product code change was made.

## Protocol and environment

- Product checkout: `6d44bd74c1658123248c0195769a2000886bdccf`; former
  benchmark development branch (now deleted).
- CLI: `codex-cli 0.146.0-alpha.3.1`; models:
  `gpt-5.6-luna`, `gpt-5.6-sol`; `model_reasoning_effort=high`.
- Every counted attempt used a fresh synthetic `git archive` fixture, an
  `--ephemeral` Codex session, and the same issue wording.  Evaluator files
  were outside each model workspace, and a post-run telemetry search found no
  model reference to evaluator, test-patch, gold-patch, history, or remote
  paths.  The committed harness now defers writing trusted evaluator overlays
  until model termination; the first runs were collected before that sequencing
  hardening, so strict no-leak proof for those historical processes is
  unavailable (no observed leakage was found).
- `validate_sealed_fixture.py` was `SEALED_PASS` before every counted model
  attempt.  Dependencies were prepared before the model run; network and
  installation enforcement remain `UNVERIFIED` (protocol-level only).
- For both sqllineage tasks the archive has no historical `sqllineage/build`
  frontend.  The benchmark-only evaluator therefore excludes only
  `tests/core/test_drawing.py` (an unrelated 404 caused by the absent build)
  and retains all parser F2P/P2P tests.  With that preservation subset,
  trusted gold was 3/3 PASS for each run.
- Two early attempts stopped at the provider usage limit (mysql Luna2/3 and
  editorconfig Sol3).  They are not counted as model failures; replacement
  runs are the numbered runs below.

## Calibration result

| Task | Base revision | F2P/P2P | Native Luna | Native Sol | Classification |
|---|---|---:|---:|---:|---|
| `reata__sqllineage-524` | `4adcc8f46fe9c5f919c9d942e1e1a0cf7d342cc2` | 4/376 | 0/3 | 0/3 | **BOTH_WEAK** |
| `mozilla-services__cliquet-203` | `41a48da66062b4e948ef1f6ce5183d2752304ecf` | 1/13 | 0/3 | 3/3 | **STRONG_SOL_LUNA_SEPARATION** |
| `editorconfig-checker__editorconfig-checker-360` | `6116ec6685b33652e9e25def9b8897ed4b015c7d` | 13/28 | 0/3 | 0/3 | **BOTH_WEAK** |
| `reata__sqllineage-565` | `4c6c65e7c94b87b50f26ad7f35ac26ed26a54cee` | 2/380 | 3/3 | not run | **LUNA_SUFFICIENT** |
| `databacker__mysql-backup-266` | `738a5d651d8501f6b17bcd4d1ed9df481eb8f557` | 6/13 | 3/3 | not run | **LUNA_SUFFICIENT** |

`PASS` means the independent evaluator reported model F2P PASS, required P2P
PASS, no-edit expected failure, gold PASS (including three gold repeats), and
scope PASS.  `sqllineage-524` additionally had the two F2P tests
`test_column_update_with_multi_tables` and `test_column_update_with_subquery`
failing in every Luna/Sol run; all Sol/Luna patches that touched
`sqlparse/analyzer.py` were also outside the trusted gold-file allowlist.

## Model cost breakdown (sum of three valid runs)

Token fields are `input / cached input / uncached input / output / reasoning`;
`peak` is the largest root input context in the three runs.  Each row has one
 0.146 usage record per model invocation (`model_calls=3`).

| Task | Model | Input | Cached | Uncached | Output | Reasoning | Root peak |
|---|---|---:|---:|---:|---:|---:|---:|
| sqllineage-524 | Luna | 4,620,110 | 4,368,128 | 251,982 | 33,316 | 14,912 | 1,678,100 |
| sqllineage-524 | Sol | 3,347,226 | 3,112,448 | 234,778 | 33,305 | 15,142 | 1,279,952 |
| cliquet-203 | Luna | 1,386,138 | 1,237,504 | 148,634 | 22,254 | 16,357 | 545,258 |
| cliquet-203 | Sol | 1,343,059 | 1,208,064 | 134,995 | 24,939 | 16,778 | 700,262 |
| editorconfig-360 | Luna | 1,399,120 | 1,214,208 | 184,912 | 19,605 | 12,901 | 643,986 |
| editorconfig-360 | Sol | 1,683,600 | 1,535,232 | 148,368 | 19,111 | 11,445 | 586,846 |
| sqllineage-565 | Luna | 2,106,858 | 1,906,432 | 200,426 | 17,349 | 5,363 | 900,429 |
| mysql-backup-266 | Luna | 696,756 | 622,080 | 74,676 | 7,950 | 3,354 | 272,188 |

Exact per-run usage, evaluator output, changed files, and fixture synthetic
commit IDs are retained in the raw run JSONL outside the model workspaces;
the compact machine-readable summary is `native_calibration_20260902.json`.

## Failure diversity and quality notes

- **cliquet-203:** Luna 1/2/3 made small variants in `cliquet/__init__.py`,
  all missed the typed `default_settings` contract and failed the same
  `test_overriden_default_settings` path (`TypeError: initialize() got an
  unexpected keyword argument 'default_settings'`).  Sol passed 3/3 with the
  same scope and preservation checks.  This is a reproducible semantic
  separation with multiple plausible but wrong Luna patches.
- **sqllineage-524:** Luna produced three different approaches (one also left
  an untracked sqlparse handler; two changed sqlparse analyzer); Sol produced
  three similar analyzer patches.  All failed the same two update-lineage F2P
  tests.  This is a same-class semantic failure plus scope non-compliance, not
  a Sol/Luna separation.
- **editorconfig-360:** all three Luna patches and all three Sol patches only
  changed `pkg/error/error.go`.  The evaluator consistently exposed the
  missing `go-snaps` dependency and logger API (`LogMessage`/
  `PrintLogMessages`); gold passed 3/3.  Both models are weak on the fixed
  semantic contract.
- **sqllineage-565:** identical one-file Luna solutions passed 3/3 (382
  preserved tests plus 2 F2P after the drawing check was excluded).
- **mysql-backup-266:** three independent Luna solutions passed 3/3 (6 F2P +
  13 P2P, gold repeats 3/3), with changes limited to `cmd/dump.go` and
  `pkg/core/timer.go`.

## Pools and interpretation

`SEPARATION_POOL = ["mozilla-services__cliquet-203"]`.

`NEGATIVE_CONTROLS = ["reata__sqllineage-565", "databacker__mysql-backup-266"]`.

`BOTH_WEAK = ["reata__sqllineage-524", "editorconfig-checker__editorconfig-checker-360"]`.

There were no remaining environment-invalid counted runs after replacement;
the usage-limit attempts are recorded as discarded infrastructure events.
Only cliquet-203 meets the requested strong separation rule (Luna 0/3,
Sol 3/3, same fixed evaluator, clean sealed fixture).  This is a calibration
pool result, not an approval to change Hybrid routing or to start ABCD.
