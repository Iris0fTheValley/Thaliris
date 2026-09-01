# T4 proposal and entry gate

## Recommended task

The strongest current candidate is `pydata__xarray-9636`, because it has a
large enough working set (DataTree mapping, path/isomorphism helpers, and
multiple regression semantics), a hidden node-path/order invariant, and a
reliable focused evaluator. However, the clean A-lite/B-lite pair passed for
both models, so it is **not yet an approved T4**. The task is useful as a
negative control for a future T4 pool, not as evidence that Sol escalation is
needed.

The next screening candidate is
`python-telegram-bot__python-telegram-bot-4617` at
`f57dd52100aafc4640891493ba43ad527433232f`. It has a broad conversion
surface and subclass-dispatch invariant, but must first pass the same clean
A-lite/B-lite protocol.

## Entry gate

Promote a task to T4 only when all conditions hold:

1. Native A-lite (Sol) reaches PASS on the original evaluator and preserves
   scope.
2. Native B-lite (Luna) reaches FAIL or materially unstable quality on the
   same evaluator, with a recorded failure mode; do not manufacture a failure
   by withholding ordinary tools or injecting noise.
3. The problem statement does not expose the solution, a public workaround,
   exact file/line hints, or the historical fix in the checkout.
4. The task has a reproducible fixture and a semantically justified hidden
   invariant. Setup/reproduction cost is recorded separately.

## Proposed ABCD hypothesis

For a qualifying task, compare:

- A: Native Sol, full unrestricted investigation.
- B: Native Luna, full unrestricted investigation.
- C: Thaliris Luna-only, current routing policy and bounded child context.
- D: Thaliris Hybrid, Luna investigation and bounded unresolved Decision
  Context, with Sol escalation only if the current routing policy selects it.

Primary hypothesis: D will preserve A's root-cause and evaluator quality while
reducing Sol input exposure, because Sol receives only evidence-backed
Decision Context rather than the full investigation working set. Secondary
hypotheses are that C may retain isolation but fail on the hard decision, and
that D's extra Luna/control-plane work may increase total compute.

## Required T4 measurements

Record per model: input, cached input, uncached input, output, reasoning, and
model calls. Record root peak/cumulative input, largest child context,
child count, Decision Context size, excluded raw-history size, evidence
pointer count, root/child model turns, control calls, wall-clock, and quality
scope. If telemetry is unavailable, write `UNAVAILABLE` or `estimate` rather
than an invented exact value.

Derive:

```text
Sol Exposure Ratio = D Sol input / A Sol input
Total Compute Ratio = D all-model input+output / A all-model input+output
Quality Retention = an evidence-backed comparison of root cause, constraints,
                    patch scope, regressions, and evaluator results
```

The optional recovery ablation should compare full trajectory, bounded packet,
and no history on the same failed-task set. It is a mechanism probe, not a
replacement for A/B separation.

## Confounds to report, not hide

- Cached-input churn and prompt-cache reuse.
- Different model capability or reasoning support.
- Image/dependency setup and Windows permissions.
- Any remote/history access or leaked task artifacts.
- Tasks where both Native models pass (no discrimination).
- Tasks where all four pass but patch quality or hidden-risk evidence differs.

No architecture change, scheduler, worker manager, forced Sol call, forced
Luna failure, or full T1--T3 rerun is part of this stage.
