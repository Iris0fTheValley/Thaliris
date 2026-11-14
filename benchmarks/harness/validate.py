#!/usr/bin/env python3
"""Self-validate every task in tasks/. Exit code 0 only if all checks hold.

Per task:
  * meta.json is schema-valid and required files exist;
  * hidden tests FAIL on the seed repo/;
  * visible tests FAIL on the seed repo/ (so a no-op never looks finished);
  * visible AND hidden tests PASS on repo/ + reference/;
  * traps: visible PASS and hidden FAIL on repo/ + decoy/ (non-traps have no decoy/);
  * the number of tasks (8-12) and traps (>= 4) is within the design bounds.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness_common as hc  # noqa: E402

MIN_TASKS, MAX_TASKS, MIN_TRAPS = 8, 12, 4


def _outcome(task_dir: Path, scratch: Path, label: str, overlays: tuple[str, ...], test_dir: str) -> hc.TestOutcome:
    workdir = scratch / label
    hc.build_workdir(task_dir, workdir, overlays=overlays, visible=True, hidden=True)
    return hc.run_unittests(workdir, test_dir)


def validate_task(task_dir: Path) -> list[str]:
    """Return a list of problems for one task (empty list = valid)."""
    task_dir = Path(task_dir)
    task_id = task_dir.name
    problems: list[str] = []
    required = ["repo", "visible_tests", "hidden_tests", "reference", "task.md", "meta.json"]
    for name in required:
        if not (task_dir / name).exists():
            problems.append(f"missing {name}")
    if problems:
        return [f"{task_id}: {p}" for p in problems]
    try:
        meta = hc.load_meta(task_dir)
    except ValueError as exc:
        return [f"{task_id}: meta.json is not valid JSON: {exc}"]
    problems += hc.validate_meta(meta, task_id)
    trap = bool(meta.get("trap")) if isinstance(meta, dict) else False
    has_decoy = (task_dir / "decoy").is_dir()
    if trap and not has_decoy:
        problems.append("trap task has no decoy/ overlay")
    if not trap and has_decoy:
        problems.append("non-trap task must not have a decoy/ overlay")
    if not (task_dir / "task.md").read_text(encoding="utf-8").strip():
        problems.append("task.md is empty")
    for sub in ("visible_tests", "hidden_tests"):
        if not list((task_dir / sub).glob("test_*.py")):
            problems.append(f"{sub}/ has no test_*.py file")
    if problems:
        return [f"{task_id}: {p}" for p in problems]

    with tempfile.TemporaryDirectory(prefix=hc.WORKDIR_PREFIX + "val-") as tmp:
        scratch = Path(tmp)
        plan = {
            "seed-hidden": ((), "hidden_tests", False),
            "seed-visible": ((), "visible_tests", False),
            "reference-visible": (("reference",), "visible_tests", True),
            "reference-hidden": (("reference",), "hidden_tests", True),
        }
        if trap and has_decoy:
            plan["decoy-visible"] = (("decoy",), "visible_tests", True)
            plan["decoy-hidden"] = (("decoy",), "hidden_tests", False)
        outcomes = {
            label: _outcome(task_dir, scratch, label, overlays, test_dir)
            for label, (overlays, test_dir, _expect_pass) in plan.items()
        }
    for label, (_overlays, _test_dir, expect_pass) in plan.items():
        out = outcomes[label]
        if out.passed != expect_pass:
            want = "PASS" if expect_pass else "FAIL"
            problems.append(f"{label}: expected {want} but got {'PASS' if out.passed else 'FAIL'} (ran={out.ran}, rc={out.returncode})\n{out.output[-600:]}")
    return [f"{task_id}: {p}" for p in problems]


def validate_all(tasks_dir: Path = hc.TASKS_DIR, jobs: int = 8) -> list[str]:
    """Validate every task; return all problems (empty list = everything holds)."""
    tasks_dir = Path(tasks_dir)
    ids = hc.list_task_ids(tasks_dir)
    problems: list[str] = []
    if not MIN_TASKS <= len(ids) <= MAX_TASKS:
        problems.append(f"suite: expected {MIN_TASKS}-{MAX_TASKS} tasks, found {len(ids)}")
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for result in pool.map(lambda tid: validate_task(tasks_dir / tid), ids):
            problems += result
    traps = 0
    for tid in ids:
        try:
            traps += bool(hc.load_meta(tasks_dir / tid).get("trap"))
        except (OSError, ValueError, AttributeError):
            pass
    if traps < MIN_TRAPS:
        problems.append(f"suite: expected at least {MIN_TRAPS} trap tasks, found {traps}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks-dir", type=Path, default=hc.TASKS_DIR)
    args = parser.parse_args(argv)
    problems = validate_all(args.tasks_dir)
    ids = hc.list_task_ids(args.tasks_dir)
    if problems:
        print(f"VALIDATION FAILED ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: {len(ids)} tasks validated (seed fails, reference passes, decoys fool visible tests only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
