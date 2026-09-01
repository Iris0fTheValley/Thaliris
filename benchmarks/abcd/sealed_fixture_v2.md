# Sealed screening fixture v2

This benchmark-only harness hardens the model/evaluator boundary after the
DSPy-1609 fixture was invalidated.  It does not change Thaliris product code,
routing, isolation, or Controller guards, and it does not run a model-quality
screen.

## A. Design

- `build_sealed_fixture.py` accepts a trusted repository, exact revision, issue
  text file, and dependency-environment reference.
- It materializes the exact tree with `git archive` (forced `core.autocrlf=false`),
  rejects symlink/submodule entries, removes any source `.git`, and initializes
  a fresh repository with one synthetic `sealed baseline` commit.
- Tracked ignored files are force-added, executable modes are preserved in the
  synthetic tree, and Windows mode-only working-tree noise is disabled after
  the commit.  The issue text and dependency reference are metadata only; no
  issue, dataset, patch, or evaluator file is copied into the workspace.
- Operator reports and evaluator assets must live outside the model workspace
  and its dedicated run-root scan scope.  The evaluator is materialized only
  after the model exits and its source diff has been captured.
- `validate_sealed_fixture.py` is fail-closed: the only successful outcome is
  `SEALED_PASS`; every required check failure returns `FIXTURE_NOT_SEALED` and
  exit code 1.

## B. Automated leakage gate

The validator checks exact source tree, clean working tree, one parentless
synthetic commit, empty remotes/remote refs/tags, reflog state, reachable-vs-
all Git objects, known gold commit absence, evaluator absence before model
execution, parent/run-root artifact traversal, evaluator/data separation, and
dependency plus externally verified baseline readiness.  Network and install
controls are reported as `UNVERIFIED` when the host only has protocol rules;
they are never represented as sandbox guarantees.  An ordinary Windows
process has no asserted global OS sandbox, so absolute-path access outside the
scanned run root remains explicitly `UNVERIFIED`.

The DSPy acceptance invocation produced `SEALED_PASS` with:

| Gate | Result |
| --- | --- |
| exact source tree | PASS |
| synthetic commit count / parent count | `1 / 0` |
| remote / remote refs / tags | `0 / 0 / 0` |
| reflog upstream entries | PASS: none |
| unexpected Git objects | PASS: none |
| `git cat-file -e 2349c84b...` | unavailable |
| `git log --all --grep=1609` | no output |
| `git remote -v` | empty |
| parent/run-root suspicious artifact scan | PASS |
| evaluator checkout before model | absent |
| dependencies + baseline evaluator status | PASS |
| network / installation enforcement | UNVERIFIED (protocol-only) |
| global OS sandbox | UNVERIFIED |

Machine-readable acceptance evidence is in
[`sealed_fixture_v2_acceptance.json`](./sealed_fixture_v2_acceptance.json).

## C. DSPy acceptance interpretation

The old leakage paths are mechanically absent from the new dedicated run root:
the model workspace has no origin, remote refs, tags, upstream object, test
patch, benchmark parquet, prior JSONL, sibling evaluator checkout, or evaluator
directory before model execution.  The known old artifacts still exist in a
separate operator directory on this host; the validator records that they are
outside the scanned model-visible scope, while making no false claim that a
full-access process cannot reach arbitrary absolute paths.

No new Sol/Luna quality run was started.  DSPy remains an invalidated
historical candidate until a future run uses a genuinely sealed workspace and
the same fixed evaluator after model exit.

## D. Legacy audit

| Task | Old result | Old fixture leakage risk | Actual suspicious access | New classification |
| --- | --- | --- | --- | --- |
| `pydata__xarray-9636` | Sol/Luna both passed | origin remained configured | A-Sol queried `git log` and `git remote` | `INVALIDATED_SOLUTION_LEAKAGE` |
| `tox-dev__tox-3409` | Sol/Luna both failed F2P | origin and broad history/refs remained | issue-related upstream commits were available; clean boundary unproven | `INVALIDATED_SOLUTION_LEAKAGE` |
| `modelcontextprotocol__python-sdk-167` | Sol/Luna both failed F2P | origin and remote refs remained | legacy checkout was not sealed; no clean-boundary proof | `INVALIDATED_SOLUTION_LEAKAGE` |
| `stanfordnlp__dspy-1609` | B1/B2 Luna failed; A1 Sol passed; A2 observed 0/4 | upstream fix object plus parent patch/parquet/JSONL were available | confirmed by checkout and parent traversal audit | `INVALIDATED_SOLUTION_LEAKAGE` |

These historical results remain useful as observations only.  None is
`VALID_SEALED_SCREEN`, and no audited task is promoted to formal T4 evidence.

## E. Next-step qualification gate

Do not screen `pdm-3374`, `geopandas-3471`, `streamlink-6338`, or
`pylint-10089` yet.  Resume B-first screening only after both the automated
gate and the DSPy sealed acceptance return `SEALED_PASS`; then materialize the
evaluator after model completion and re-run the fixed A/B protocol from clean
sealed workspaces.
