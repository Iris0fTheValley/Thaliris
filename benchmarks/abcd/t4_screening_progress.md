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
  used no Thaliris workflow.  No run reused a Codex session, worktree, child,
  answer, patch, log, or historical fix from another run.
- Each candidate used an exact-revision clean checkout and an isolated venv.
  Dependencies were prepared before model execution; model runs had no
  network, install, remote/history, or cache archaeology access.  Windows
  evaluator-only compatibility changes are called out in the tox record and
  are not product behavior.
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
| `stanfordnlp__dspy-1609` (`16ceaba5f7126ca86e5b50b669975c926b9f8f55`) | PASS | FAIL, 0/4 F2P | PASS, 4/4 F2P | FAIL, 0/4 F2P | Luna failures are the same typed-list bootstrap contract class; Sol passes | Provisional T4 candidate |

### Token accounting

Counts are the completed model-turn usage returned by the CLI.  `uncached` is
`input - cached input`; cached input is retained and is not treated as free.

| Run | Model | Input | Cached input | Uncached input | Output | Reasoning |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| tox B1 | Luna | 4,476,572 | 4,327,424 | 149,148 | 18,487 | 11,850 |
| tox A1 | Sol | 4,418,393 | 4,299,264 | 119,129 | 15,204 | 6,244 |
| MCP B1 (valid rerun) | Luna | 4,451,793 | 4,313,088 | 138,705 | 30,970 | 20,145 |
| MCP A1 | Sol | 1,202,931 | 1,124,608 | 78,323 | 12,696 | 7,394 |
| DSPy B1 | Luna | 2,426,283 | 2,321,152 | 105,131 | 18,157 | 10,532 |
| DSPy A1 | Sol | 1,616,720 | 1,533,696 | 83,024 | 14,223 | 8,383 |
| DSPy B2 | Luna | 4,251,775 | 4,118,272 | 133,503 | 26,633 | 17,444 |

The first MCP B1 attempt is retained as invalid-protocol cost data (input
2,541,492; cached 2,436,608; uncached 104,884; output 23,990; reasoning
16,190), but is excluded from quality because it installed/downloaded through
`uv`.  An early DSPy setup attempt shadowed the third-party `datasets` package,
made no source change, and had no completed usage record; it is excluded.

## DSPy separation review

The fixed four-test overlay is identical for B1, A1, and B2.  B1 and B2 each
failed because typed list demonstrations were reused in the adapter's numbered
passage format without satisfying the typed parser's contract.  A1 selected a
narrow adapter normalization and passed all four tests.  B2 independently
failed the same evaluator contract (`_format_field_value` compatibility), so
this is reproducible Luna semantic failure rather than an environment or
timeout failure.  The candidate also has 257 PASS_TO_PASS tests, clean exact
fixtures, no solution leakage, and preservation subsets passing in local
verification.  It is therefore a `PROVISIONAL_T4_CANDIDATE`, not approval to
start the formal ABCD workload.

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
- Unstable separations: none so far.  DSPy is reproducible separation across
  B1/B2, not unstable.
- Provisional T4 candidates: `stanfordnlp__dspy-1609` only.
- Screened with no separation because both models failed the fixed semantic
  evaluator: `tox-dev__tox-3409`,
  `modelcontextprotocol__python-sdk-167`.
- Excluded before fair screening: `tox-dev__tox-3388`, `urllib3__urllib3-3527`,
  and `jupyterlab__jupyter-ai-1022` for visible solution/setup or unstable
  environment reasons documented in `t4_candidate_screening.json`.

## Decision

`NO QUALIFYING T4 FOUND YET`.

DSPy-1609 is the first provisional candidate because it satisfies the
observed A1 PASS / B1+B2 same semantic FAIL gate.  A formal T4 ABCD run still
requires a final entry review and a fresh reproducibility check; this round
does not start it.
