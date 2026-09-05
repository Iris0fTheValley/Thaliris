# T4 candidate screening progress

This is an adaptive screening record, not a formal T4 ABCD run.  The
screening protocol is B-first: an independent Native Luna run is required
before spending a Native Sol run, and a fixed public evaluator is the quality
authority.  Candidates were taken from [SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live)
lite metadata.

## Environment and controls

- Branch: `codex/abcd-benchmark-20260901`.
- Product ancestry: `a03db1a`; benchmark records are committed after that
  point.  No product architecture, isolation, guard, or routing policy was
  changed during this screening round.
- Codex: `codex-cli 0.146.0-alpha.3.1`.
- Models: `gpt-5.6-luna` and `gpt-5.6-sol`, both `reasoning_effort=high` for
  model runs.
- `context doctor --pretty`: routing ready `YES`; post-dispatch observation
  `YES`; pre-dispatch enforcement remains `UNKNOWN`.
- Global and repository `AGENTS.md` were loaded consistently.  Native runs
  used no Thaliris workflow.  Runs did not intentionally reuse a Codex
  session, worktree, child, answer, patch, log, or historical fix from another
  run; the DSPy fixture audit below found that historical objects and sibling
  artifacts were nevertheless accessible.
- Each candidate used an exact-revision checkout and an isolated venv.
  The DSPy fixture entry review below found that its model-side isolation was
  not sufficient: origin refs/object history and parent-directory artifacts
  remained readable.  Therefore DSPy model results are invalidated rather
  than treated as evidence.  Windows evaluator-only compatibility changes
  are called out in the tox record and are not product behavior.
- Model-turn counts and wall clocks are `UNAVAILABLE` where the CLI result did
  not expose them.  They are not estimated from token totals.

## Telegram-4617 readiness gate

`python-telegram-bot__python-telegram-bot-4617` at
`f57dd52100aafc4640891493ba43ad527433232f` is `ENVIRONMENT_INCONCLUSIVE`.
Checkout, imports, evaluator startup, and no-archaeology controls passed, but
the fixed FAIL_TO_PASS test reaches Telegram and receives `401 Unauthorized`
from the embedded fallback credential.  Pure local PASS_TO_PASS checks run,
while network-backed checks share the same blocker.  No B1 Luna run was
started, so A1/B2 are `NOT_RUN`; this is not a Luna failure.

## Fixed-evaluator screening results

| Candidate (exact base) | Readiness | B1 Native Luna | A1 Native Sol | B2 Native Luna | Fixed evaluator result | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `tox-dev__tox-3409` (`f919d0d0d512a755f0f85af540ed75f73140a685`) | PASS | FAIL, 0/9 F2P | FAIL, 0/9 F2P | NOT_RUN | Both models failed dependency-group/error-contract semantics; selected P2P ran | No separation |
| `modelcontextprotocol__python-sdk-167` (`08042c3307bdd0d4a66b0dd3200f38222f447b1e`) | PASS | FAIL, 0/2 F2P; issue regression PASS | FAIL, 0/2 F2P; issue regression PASS | NOT_RUN | Both models failed the same in-flight/cancellation contracts | No separation |
| `stanfordnlp__dspy-1609` (`16ceaba5f7126ca86e5b50b669975c926b9f8f55`) | INVALIDATED | OBSERVED FAIL, 0/4 | OBSERVED PASS, 4/4 | OBSERVED FAIL, 0/4 | Fixture leaked upstream history and parent-side evaluator artifacts; observations are not quality evidence | Invalidated solution leakage |

### Token accounting

Counts are the completed model-turn usage returned by the CLI.  `uncached` is
`input - cached input`; cached input is retained and is not treated as free.

| Run | Model | Input | Cached input | Uncached input | Output | Reasoning |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| tox B1 | Luna | 4,476,572 | 4,327,424 | 149,148 | 18,487 | 11,850 |
| tox A1 | Sol | 4,418,393 | 4,299,264 | 119,129 | 15,204 | 6,244 |
| MCP B1 (valid rerun) | Luna | 4,451,793 | 4,313,088 | 138,705 | 30,970 | 20,145 |
| MCP A1 | Sol | 1,202,931 | 1,124,608 | 78,323 | 12,696 | 7,394 |
| DSPy B1 (invalid) | Luna | 2,426,283 | 2,321,152 | 105,131 | 18,157 | 10,532 |
| DSPy A1 (invalid) | Sol | 1,616,720 | 1,533,696 | 83,024 | 14,223 | 8,383 |
| DSPy B2 (invalid) | Luna | 4,251,775 | 4,118,272 | 133,503 | 26,633 | 17,444 |
| DSPy A2 (invalid) | Sol | 1,459,158 | 1,138,064 | 321,094 | 8,102 | 4,111 |

The first MCP B1 attempt is retained as invalid-protocol cost data (input
2,541,492; cached 2,436,608; uncached 104,884; output 23,990; reasoning
16,190), but is excluded from quality because it installed/downloaded through
`uv`.  An early DSPy setup attempt shadowed the third-party `datasets` package,
made no source change, and had no completed usage record; it is excluded.

## DSPy fixture freeze and leakage review

The frozen fixture is recorded in
[`dspy_1609_t4_manifest.json`](./dspy_1609_t4_manifest.json), with the exact
revision, verbatim issue wording hash, four fixed FAIL_TO_PASS tests, 257-test
PASS_TO_PASS population, explicit non-F2P preservation selectors, scope rules,
and evaluator/model checkout separation requirements.  The issue wording file
contains only the public `problem_statement`; no `hints_text` was supplied.

The entry gate nevertheless failed after the model runs:

- `dspy-1609-A2-sol` retained `origin` and `--all` objects exposing upstream
  fix `2349c84b5489bb792edbedc81acfaf9bf2488ce0` (`Fix TypedPredictor
  formatting with list output values (#1609)`).
- The sibling `dspy-1609-test.patch` and complete `swe-live-lite.parquet`
  (including test patch/hints fields) were readable from the parent directory
  of the model checkout under the full-access runtime.
- The current A2 prompt did not directly contain the solution, but the
  cross-run prompt/history and side-channel isolation cannot be proven clean.

Accordingly, the fixed evaluator results are retained only as contaminated
observations: B1 Luna `0/4`, A1 Sol `4/4`, B2 Luna `0/4`, and A2 Sol `0/4`
(the A2 failure was `TypeError: _format_field_value() got an unexpected
keyword argument 'field_info'`).  The independent overlay was applied after
the A2 model run, but that does not repair model-side leakage.  A2 is therefore
not `UNSTABLE_SOL_SEPARATION`; the entire candidate is
`INVALIDATED_SOLUTION_LEAKAGE` and no A1/A2 or B1/B2 consistency claim is
valid.

## Candidate-pool expansion

The initial static survey found additional potentially useful cross-module or
invariant-heavy candidates:

- `pdm-project__pdm-3374`
- `geopandas__geopandas-3471`
- `streamlink__streamlink-6338`
- `pylint-dev__pylint-10089`

These are shortlist entries only; readiness and B1 screening are pending.  The
pool will be readiness-filtered before any further model run, with preference
for multiple plausible fixes, strong PASS_TO_PASS preservation, lifecycle or
concurrency invariants, and a large but disposable investigation set.  Raw
LOC, file count, visible solution pointers, and setup cost alone are not used
as evidence of a Luna/Sol capability boundary.

## Classification

- Negative controls: `pydata__xarray-9636` (Native Sol and Native Luna both
  pass; no observed discrimination).
- Environment-inconclusive: `pallets__flask-5637` (dependency/runtime
  truncation), `python-telegram-bot__python-telegram-bot-4617` (invalid
  network fixture).
- Unstable separations: none so far.
- Legacy unaudited screens: none among the four audited historical fixtures;
  each has either confirmed history/artifact exposure or an unprovable clean
  boundary.
- Invalidated candidates: `pydata__xarray-9636` (A-Sol queried git history and
  remote), `tox-dev__tox-3409` (origin/full history and issue-related upstream
  commits were available), `modelcontextprotocol__python-sdk-167` (origin and
  remote refs remained in the worktrees), and `stanfordnlp__dspy-1609`
  (confirmed upstream fix objects plus parent-side evaluator artifacts).
- Provisional T4 candidates: none.
- Screened with no separation because both models failed the fixed semantic
  evaluator: `tox-dev__tox-3409`,
  `modelcontextprotocol__python-sdk-167`.
- Excluded before fair screening: `tox-dev__tox-3388`, `urllib3__urllib3-3527`,
  and `jupyterlab__jupyter-ai-1022` for visible solution/setup or unstable
  environment reasons documented in `t4_candidate_screening.json`.

## Decision

`NO QUALIFYING T4 FOUND YET`.

DSPy-1609 is downgraded from provisional to
`INVALIDATED_SOLUTION_LEAKAGE`.  Do not run B3 or formal ABCD from these
fixtures.  A future qualification requires a newly isolated, offline fixture
with no remote refs/gold objects and no parent-side test patch/parquet access,
then fresh reproducible A/B screening.

## Frozen protocol if a clean DSPy fixture is rebuilt

Only after the leakage gate passes, use the same exact issue/evaluator for:

`A Native Sol` · `B Native Luna` · `C Thaliris Luna-only` · `D Thaliris Hybrid`.

Do not prompt D to invoke Sol.  If D invokes Sol, record Sol input,
serialized Decision Context size, evidence/artifact pointer count, raw
investigation size excluded from Sol, Luna investigation input, root
cumulative/peak context, largest child context, all model turns, and
spawn/wait/list/status/send counts.  Derive `Sol Exposure Ratio = D Sol input /
A Sol input` and `Total Compute Ratio = D all-model input+output / A all-model
input+output`; a zero Sol invocation is not evidence of attention protection.
