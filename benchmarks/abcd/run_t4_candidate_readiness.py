"""Run sealed readiness for the current T4 candidate batch.

Candidate metadata and trusted repositories live outside this repository and
are never copied into a model workspace by this adapter.  This command does
not invoke a model.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

import run_external_readiness as readiness


TIER_S = {
    "aaugustin__websockets-543", "aaugustin__websockets-641",
    "aio-libs__aiohttp-8823", "bashtage__arch-752",
    "dask-contrib__dask-expr-901", "d0c-s4vage__pfp-128",
}
TIER_A = {
    "asdf-format__asdf-1907", "alteryx__woodwork-1300",
    "amaranth-lang__amaranth-912", "d0c-s4vage__pfp-126",
}
ALL_CANDIDATES = TIER_S | TIER_A


def _commands(row: dict[str, Any]) -> tuple[str, str, str]:
    task = row["task"]
    if task.startswith("aaugustin__websockets"):
        # websockets 7 passes ``loop=`` into asyncio helpers.  On Python 3.8+
        # asyncio emits a host-runtime DeprecationWarning which this legacy
        # suite captures as an assertion failure.  Filter only that exact
        # asyncio warning; task-specific deprecation assertions remain active.
        return ('python -m pip install -q -e . "pytest<8"',
                'python -m pytest -q -W "ignore:The loop argument is deprecated since Python 3.8"',
                "python/pip")
    if task == "aio-libs__aiohttp-8823":
        return 'python -m pip install -q -e . "pytest<8"', "python -m pytest -q", "python/pip"
    if task == "bashtage__arch-752":
        return ('python -m pip install -q -e . "pytest<8" '
                'numpy==1.26.4 pandas==1.5.3 scipy==1.11.4 statsmodels==0.14.4'), "python -m pytest -q", "python/pip"
    if task == "dask-contrib__dask-expr-901":
        return 'python -m pip install -q -e . "pytest<8" dask pandas pyarrow', "python -m pytest -q", "python/pip"
    if task == "d0c-s4vage__pfp-128":
        return 'python -m pip install -q -e . "pytest<8"', "python -m pytest -q", "python/pip"
    if task == "d0c-s4vage__pfp-126":
        return 'python -m pip install -q -e . "pytest<8"', "python -m pytest -q", "python/pip"
    if task == "asdf-format__asdf-1907":
        return 'python -m pip install -q -e . "pytest<9" psutil pytest-remotedata', "python -m pytest -q", "python/pip"
    if task == "alteryx__woodwork-1300":
        return 'python -m pip install -q -e . "pytest<9" pandas==1.5.3 scikit-learn', "python -m pytest -q", "python/pip"
    if task == "amaranth-lang__amaranth-912":
        return 'python -m pip install -q . "pytest<9" coverage', "python -m pytest -q", "python/pip"
    raise ValueError(f"no readiness command for {task}")


def _load_rows(metadata: Path, trusted_root: Path, issue_root: Path, prep_root: Path) -> list[dict[str, Any]]:
    records = json.loads(metadata.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in records:
        task = item["instance_id"]
        if task not in ALL_CANDIDATES:
            continue
        repo_name = task if (trusted_root / task).exists() else item["repo"].split("/", 1)[1]
        row = dict(item)
        selection = list(item.get("FAIL_TO_PASS", [])) + list(item.get("PASS_TO_PASS", []))
        # A few parquet rows contain truncated parametrized node ids (the
        # closing bracket and parameter value were lost during dataset export).
        # File-level selection is the only honest fallback; it preserves the
        # task's test module without inventing a test name.
        if any("[" in test and "]" not in test for test in selection):
            selection = sorted({test.split("::", 1)[0] for test in selection})
        row.update({
            "task": task,
            "dataset": "SWE-rebench-V2-Filtered-Verified",
            "source": str(trusted_root / repo_name),
            "issue_path": str(issue_root / f"{task}.md"),
            "model_workspace": str(prep_root / "model" / task),
            "evaluator_workspace": str(prep_root / "eval" / task),
            "dependency_reference": str(prep_root / "deps" / task),
            "future_evaluator_path": str(prep_root / "future-evaluator" / task),
            "FAIL_TO_PASS": item.get("FAIL_TO_PASS", []),
            "PASS_TO_PASS": item.get("PASS_TO_PASS", []),
            "test_selection": selection,
        })
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--trusted-root", required=True, type=Path)
    parser.add_argument("--issue-root", required=True, type=Path)
    parser.add_argument("--prep-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--only", action="append")
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args(argv)
    args.prep_root.mkdir(parents=True, exist_ok=True)
    rows = _load_rows(args.metadata, args.trusted_root, args.issue_root, args.prep_root)
    if args.only:
        rows = [row for row in rows if row["task"] in set(args.only)]
    for row in rows:
        if row["task"] not in ALL_CANDIDATES:
            raise ValueError(f"unexpected candidate outside first batch: {row['task']}")
    readiness._commands = _commands
    py37 = Path(r"C:\thaliris-toolchains\python37\python.exe")
    py38 = Path(r"C:\Users\12298\AppData\Local\Programs\Python\Python38\python.exe")
    py39 = Path(r"C:\Users\12298\AppData\Roaming\uv\python\cpython-3.9-windows-x86_64-none\python.exe")
    py311 = Path(r"C:\Users\12298\AppData\Local\Programs\Python\Python311\python.exe")
    original_base_python = readiness._venv_base_python
    def base_python(task: str) -> str:
        if task.startswith("aaugustin__websockets"):
            # websockets-641's shutdown tests rely on Python 3.7 asyncio
            # cancellation semantics. Python 3.8+ changes the relevant
            # scheduling behavior and produces unrelated P2P failures.
            if task == "aaugustin__websockets-641" and py37.exists():
                return str(py37)
            if py39.exists():
                return str(py39)
            if py38.exists():
                return str(py38)
        # arch-752 declares Python >=3.9 and its build requires NumPy 2,
        # which cannot be installed on Python 3.8.  Keep this environment
        # choice local to readiness; it never changes the model fixture.
        if task in {"bashtage__arch-752", "asdf-format__asdf-1907", "alteryx__woodwork-1300"} and py311.exists():
            return str(py311)
        return original_base_python(task)

    readiness._venv_base_python = base_python
    results = []
    for row in rows:
        try:
            results.append(readiness.evaluate_task(row, args.prep_root, args.timeout))
        except Exception as error:
            results.append({"task": row["task"], "final": "EVALUATOR_INCONCLUSIVE", "blocker": f"harness exception: {error}"})
    selected_tiers = {"S" if row["task"] in TIER_S else "A" for row in rows}
    payload = {
        "schema_version": 1,
        "model_runs": 0,
        "candidate_tier": next(iter(selected_tiers)) if len(selected_tiers) == 1 else "S+A",
        "tasks": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
