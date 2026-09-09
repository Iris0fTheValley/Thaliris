"""Frozen, independent behavior-contract gate for the D-sakiko fixture.

The contract checks are implemented in ``d_sakiko_quality_evaluator_v3`` and
exercise public behavior only; they never import model-authored tests or read
self-reports.  This wrapper makes the formal gate explicit: a known-good
candidate must pass and the untouched sealed base must fail under the same
frozen evaluator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

FORMAL_SCHEMA_VERSION = 1
CONTRACT_VERSION = "d-sakiko-live2d-behavior-v1"


def _run(evaluator: Path, workspace: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(evaluator), str(workspace)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "ERROR", "detail": f"invalid evaluator output: {exc}: {proc.stderr[-1000:]}"}
    report["process_returncode"] = proc.returncode
    return report


def evaluate(candidate: Path, baseline: Path, evaluator: Path) -> dict:
    candidate_report = _run(evaluator, candidate)
    baseline_report = _run(evaluator, baseline)
    evaluator_hash = hashlib.sha256(evaluator.read_bytes()).hexdigest()
    candidate_pass = candidate_report.get("quality_profile") == "FULL_PASS"
    baseline_fail = baseline_report.get("quality_profile") == "FAIL"
    return {
        "schema_version": FORMAL_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "evaluator": str(evaluator.resolve()),
        "evaluator_sha256": evaluator_hash,
        "known_good": {"workspace": str(candidate.resolve()), "status": "PASS" if candidate_pass else "FAIL", "report": candidate_report},
        "untouched_base": {"workspace": str(baseline.resolve()), "status": "FAIL" if baseline_fail else "UNEXPECTED_PASS", "report": baseline_report},
        "formal_status": "SEALED_PASS" if candidate_pass and baseline_fail else "FAIL",
        "independent_of_model_authored_tests": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, default=Path(__file__).with_name("d_sakiko_quality_evaluator_v3.py"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate(args.candidate, args.baseline, args.evaluator)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["formal_status"] == "SEALED_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
