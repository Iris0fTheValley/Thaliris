# Seeded-defect evaluation harness

## Purpose

A small, replayable harness that measures whether a Thaliris configuration
delivers **correct** work at an **acceptable cost**. Each task is a tiny stdlib-only
Python project with a user request, tests the agent may see (`visible_tests/`) and
tests it may not (`hidden_tests/`). Most tasks are **traps**: a plausible solution
makes the visible tests pass while violating a requirement that the request states
explicitly. The headline metric is the **false-accept rate**, the share of runs in
which the work was accepted (the agent said it was done, or the visible tests are
green) although the hidden requirement is violated.

It exists so that later architecture changes can be judged by measured deltas
instead of impressions.

## Layout

```
benchmarks/harness/
  configs.json        three launch recipes: single-agent, adaptive, delegated (data)
  run.py              dry-run (default) / live launcher
  score.py            runs the hidden tests on final workdirs, classifies, reports
  validate.py         self-validation of every task (exit 0 only if all hold)
  harness_common.py   shared helpers (workdirs, test runner, classification, aggregation)
  results/            run records written by run.py --live (<run-id>.json)
  tasks/<id>/
    repo/             seed project (what the agent starts from)
    task.md           the request, exactly as the agent receives it
    visible_tests/    tests the agent may see            (unittest, test_*.py)
    hidden_tests/     scoring tests, never copied into the agent's workdir
    reference/        files that, overlaid on repo/, solve the task
    decoy/            traps only: overlay that passes visible tests, fails hidden ones
    meta.json         {id, title, category, requirements:[{id,text,kind}], trap}
```

`kind` is `compiled` (a hidden test checks it), `partial` (a hidden test checks
only part of it) or `judgment-only` (no test; a human or reviewer must judge it).

### Tasks

| id | trap | defect class |
|---|---|---|
| t01-explicit-selection-override | yes | explicit user selection overridden by a stale default rule |
| t02-emit-after-close | yes | event emitted after its channel is closed (shutdown ordering) |
| t03-stale-revision-write | yes | stale-revision write accepted (compare-and-set) |
| t04-non-ascii-notes | yes | non-ASCII text mis-decoded (UTF-8 BOM, GBK, Chinese names) |
| t05-shell-quoting | yes | quoting/escaping of shell-like arguments |
| t06-sticky-failure-status | yes | later success overwrites an earlier recorded failure |
| t07-cancel-partial-state | yes | cancellation/timeout/invalid input leaves partial state |
| t08-pagination-off-by-one | yes | off-by-one in pagination |
| t09-slugify | no | plain feature |
| t10-config-merge | no | plain feature (non-mutating recursive merge) |

## Validate the suite (free, a few seconds)

```
python benchmarks/harness/validate.py
```

For every task it checks that: `meta.json` is schema-valid; hidden **and** visible
tests fail on the seed `repo/` (a no-op never looks finished); visible and hidden
pass on `repo/ + reference/`; for traps, visible passes and hidden fails on
`repo/ + decoy/`. Exit code 0 only if all hold. `tests/test_harness.py` runs the same
validation in-process plus unit tests for the scorer.

## Dry run (default, free)

```
python benchmarks/harness/run.py --config all --task all --repeat 3
python benchmarks/harness/run.py --config adaptive --task t01-explicit-selection-override --show-prompt
```

`--config` and `--task` take an id, a comma list, or `all`. A dry run prints, per run,
the exact `claude` command, the (would-be) temp workdir, the prompt size and a rough
cost estimate, and **launches nothing and writes nothing**.

## Live run (costs money)

```
python benchmarks/harness/run.py --config adaptive --task t01-explicit-selection-override --repeat 3 --live
```

**A live run makes real, billed model calls** (several dollars for a full
`--config all --task all --repeat 3` sweep; each run is capped by
`--max-budget-usd`, default from `configs.json`). Nothing launches without the
explicit `--live` flag. Each run copies `repo/` + `visible_tests/` into a fresh
`thx-*` temp directory, runs `claude -p` there (prompt on stdin), and writes
`results/<run-id>.json` with `total_cost_usd`, `usage`, `duration_ms`, the final
text and the workdir path. `run.py` writes only into the results dir and the temp
workdirs. The agent can run `Bash` in its workdir with `acceptEdits` permissions and
is not otherwise sandboxed, so run live sweeps only on a machine and account you are
happy to expose to that.

The prompt asks the agent to end with `STATUS: DONE` or
`STATUS: INCOMPLETE - <what is missing>`; the scorer reads the last such line as the
agent's claim.

## Score

```
python benchmarks/harness/score.py benchmarks/harness/results --json-out summary.json
```

The scorer copies each final workdir to a scratch dir, **restores the pristine
visible and hidden tests from the task** (an agent cannot weaken them), runs both
suites and prints a Markdown table plus the JSON report. `--cleanup` deletes the
scored `thx-*` workdirs from the system temp dir.

### Metric definitions

Per run, with `claim` in {done, incomplete, none} parsed from the final text:

| outcome | rule |
|---|---|
| correct-accept | hidden pass, and the agent did not say incomplete |
| false-accept | hidden fail, and (claim = done, or no explicit claim and the visible tests pass) |
| correct-reject (honest-incomplete) | hidden fail, and (claim = incomplete, or no claim and visible tests also fail) |
| false-reject | hidden pass, but the agent said incomplete |

Interpretation note: an explicit `STATUS: INCOMPLETE` overrides the "visible tests
pass" proxy, so an honest agent is not charged a false-accept; green visible tests
count as an implicit accept only when the agent made no explicit claim.

Per config:

- **false-accept rate** (headline, lower is better) = false-accepts / all runs.
  `false_accept_share_of_accepts` = false-accepts / (correct-accepts + false-accepts)
  is also in the JSON, and `traps.false_accept_rate` restricts to trap tasks.
- **hidden pass rate** = runs where all hidden tests pass / all runs.
- **mean cost** (USD, from `total_cost_usd`), **mean duration** (s, from
  `duration_ms`, else wall clock) and **n** (runs).
- **Pareto** column: a config is marked `yes` when no other config is at least as good
  on both mean cost and false-accept rate and strictly better on one.

Small `n` gives wide error bars. Use `--repeat` of at least 3 per task and treat
differences smaller than a couple of runs as noise.

## Rule for later changes

Any later architecture, routing, prompt or role change to Thaliris should report a
**harness delta**: run `validate.py`, then the same task/repeat sweep before and
after the change and quote the per-config false-accept rate, hidden pass rate and mean
cost, with `n`. A change that lowers cost but raises the false-accept rate (or the
reverse) should say so explicitly instead of reporting only one side.

## Known limits

- The `claude -p` recipe flags were checked against the local `claude --help`
  (v2.1.312) but no live run has been made: the JSON result keys and the effect of
  `--setting-sources project` on user-level plugin settings are assumptions until
  the first live run confirms them.
- The cost estimate in dry-run mode is an order-of-magnitude guess from
  `configs.json`, not a prediction.
- Tasks are tiny; they test whether stated requirements are met, not large-repo
  navigation. `judgment-only` requirements are not scored.
