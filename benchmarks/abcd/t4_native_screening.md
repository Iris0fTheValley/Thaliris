# Native A-lite/B-lite screening

## Control protocol

- CLI: `codex-cli 0.146.0-alpha.3.1`.
- Models: `gpt-5.6-sol` (A-lite) and `gpt-5.6-luna` (B-lite).
- Reasoning effort: `medium` for both; this was selected because it exists for
  both models and keeps the candidate screen bounded.
- Tool protocol: local checkout and local tests only; no web search, GitHub
  API, remote refs, installs, or dependency-cache exploration.
- Each model used a fresh shallow checkout at the exact task base commit. No
  Codex session, child, patch, answer, or failure reason was reused.
- Same task wording, acceptance criteria, focused tests, and relevant test
  suite. Run order was randomized operationally as B-lite then A-lite.

## xarray-9636 (valid clean pair)

Task source: SWE-bench-Live lite, `pydata/xarray`, base
`8f6e45ba63941316b630e4c94ee2063395aa2b63`.

The task requires DataTree binary operations to match nodes by relative path
even when sibling insertion order differs, while preserving the existing
different-name/isomorphism behavior. It is a real multi-file investigation,
but the focused evaluator is reliable and the final patch is narrow.

| Metric | A-lite Native Sol | B-lite Native Luna |
| --- | ---: | ---: |
| Result | PASS | PASS |
| Focused regression | 1 passed | 4 passed |
| Relevant DataTree/mapping tests | 39 passed, 4 xfailed | 146 passed, 1 skipped, 10 xfailed |
| CLI input tokens | 412,648 | 408,698 |
| Cached input tokens | 360,960 | 353,792 |
| Uncached input tokens | 51,688 | 54,906 |
| Output tokens | 4,756 | 5,576 |
| Reasoning output tokens | 2,418 | 2,459 |
| Root model turns reported by CLI | 1 | 1 |
| File changes | 2 | 2 |
| Scope | PASS: only mapper + regression test | PASS: only mapper + regression test |

The CLI emitted an existing local `requests` dependency-version warning. It
did not change the result. Both patches aligned nodes by relative path and
retained positional fallback for intentionally differently named isomorphic
trees. The clean pair therefore shows **no model-quality discrimination**:
both models solved the task under the same controls. It should not be promoted
to T4 solely because its static complexity score is high.

The JSONL `turn.completed` usage is the available CLI aggregate for this
screen. It is not a substitute for a full ABCD telemetry ledger; peak context,
per-tool context, and wall-clock are `UNAVAILABLE` here.

## Flask-5637 (runtime-inconclusive attempt)

Task source: SWE-bench-Live lite, `pallets/flask`, base
`10bdf61a0f751f3cb000f8f8ac5ac5b4bb535677`.

Two Luna attempts were started from fresh copies with the same offline prompt.
Both spent the bounded window inspecting dependency/cache details and made no
patch. No Sol run was started, so this is **INCONCLUSIVE**, not `Luna FAIL`.
The first attempt also demonstrated why dependency setup must be treated as a
separate reproduction-cost field rather than folded into model quality.

## Screening decision

No valid Sol-pass/Luna-fail separation has been observed yet. The current
screen therefore does **not** authorize a T4 ABCD run. The next candidate to
screen is `python-telegram-bot__python-telegram-bot-4617`; if it also passes
for both models, expand the candidate pool rather than forcing a Luna failure.
