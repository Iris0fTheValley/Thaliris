"""Frozen formal gate for the D-sakiko behavior-contract evaluator."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

FORMAL_SCHEMA_VERSION = 2
CONTRACT_VERSION = "d-sakiko-live2d-behavior-v2"


def _run(evaluator: Path, workspace: Path) -> dict:
    proc = subprocess.run([sys.executable, str(evaluator), str(workspace)], capture_output=True, text=True, check=False)
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "ERROR", "detail": f"invalid evaluator output: {exc}: {proc.stderr[-1000:]}"}
    report["process_returncode"] = proc.returncode
    return report


def evaluate(candidate: Path, baseline: Path, evaluator: Path, expected_hash: str, manifest: Path | None) -> dict:
    actual_hash = hashlib.sha256(evaluator.read_bytes()).hexdigest()
    hash_match = actual_hash == expected_hash.lower()
    candidate_report = _run(evaluator, candidate)
    baseline_report = _run(evaluator, baseline)
    candidate_pass = candidate_report.get("quality_profile") == "FULL_PASS"
    baseline_fail = baseline_report.get("quality_profile") == "FAIL"
    report = {
        "schema_version": FORMAL_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "evaluator": str(evaluator.resolve()),
        "evaluator_sha256": actual_hash,
        "expected_evaluator_sha256": expected_hash.lower(),
        "evaluator_frozen": hash_match,
        "manifest": str(manifest.resolve()) if manifest else None,
        "known_good": {"workspace": str(candidate.resolve()), "status": "PASS" if candidate_pass else "FAIL", "report": candidate_report},
        "untouched_base": {"workspace": str(baseline.resolve()), "status": "FAIL" if baseline_fail else "UNEXPECTED_PASS", "report": baseline_report},
        "calibration": {"gold_pass": candidate_pass, "untouched_base_fail": baseline_fail, "no_edit_fail": baseline_fail},
        "formal_status": "SEALED_PASS" if hash_match and candidate_pass and baseline_fail else ("EVALUATOR_NOT_FROZEN" if not hash_match else "FAIL"),
        "independent_of_model_authored_tests": True,
    }
    if manifest:
        manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, default=Path(__file__).with_name("d_sakiko_quality_evaluator_v4.py"))
    parser.add_argument("--expected-evaluator-sha256", required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    report = evaluate(args.candidate, args.baseline, args.evaluator, args.expected_evaluator_sha256, args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["formal_status"] == "SEALED_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
