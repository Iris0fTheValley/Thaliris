# Native Separation Pool - 2026-09-03

This is a fresh external-provider, Luna-first screening. No Thaliris C/D or ABCD run was performed. The local auditable metadata cache contained 10 candidates, not the requested 15-25; no additional candidates were invented.

| Task | Readiness | B1 Luna | A1 Sol | Classification |
| --- | --- | --- | --- | --- |
| `reata__sqllineage-524` | `SEALED_PASS` | FAIL; scope violation | FAIL; scope violation | `VALID_SEALED_BOTH_FAIL` |
| `mozilla-services__cliquet-203` | `SEALED_PASS` | not run | not run | excluded by instruction |
| `editorconfig-checker__editorconfig-checker-360` | `SEALED_PASS` | FAIL | FAIL | `VALID_SEALED_BOTH_FAIL` |
| `reata__sqllineage-565` | `SEALED_PASS` | PASS | not run | `VALID_SEALED_NO_DISCRIMINATION` |
| `databacker__mysql-backup-266` | `SEALED_PASS` | PASS | not run | `VALID_SEALED_NO_DISCRIMINATION` |

Readiness exclusions were `FIXTURE_NOT_SEALED` for fluent-bit, copy-webpack-plugin, and privacyidea; `EVALUATOR_INCONCLUSIVE` for synthetics and sphinx. Go readiness required the prepared Go toolchain path. Network and installation enforcement remain `UNVERIFIED`.

## Results

`sqllineage-524` Luna and Sol both left F2P failures and changed a file outside the gold allowlist. `editorconfig-360` Luna and Sol both failed the injected F2P evaluator while remaining in scope. These are not separation evidence. The two passing Luna runs are retained as Luna-sufficient controls.

`SEPARATION_POOL = []`.

The current external provider therefore produced no new reproducible Sol > Luna capability separation. The earlier cliquet separation calibration is historical only and was excluded because its current-provider B1 passed. No ABCD authorization follows from this report.

Run artifacts and full telemetry are in `native_20260903_*.json`; unavailable telemetry fields are explicitly recorded as `UNAVAILABLE` in the summary JSON.
