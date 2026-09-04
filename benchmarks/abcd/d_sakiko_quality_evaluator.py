"""Trusted, behavior-oriented quality evaluation for the D_sakiko pilot.

This adapter deliberately scores contract capabilities instead of comparing a
model patch with the gold diff.  Model workspaces are supplied after model
exit; the evaluator itself remains outside sealed fixtures.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


CONTRACTS = {
    "shared_behavior": {
        "tests": "GPT_SoVITS/test/test_live2d_shared_behavior.py",
        "entry_points": [
            "live2d_support.shared_behavior.SharedLive2DBehavior",
            "live2d_support.contract.SharedLive2DBehavior",
            "live2d_support.runtime_contract.SharedLive2DBehavior",
        ],
    },
    "renderer": {
        "tests": "GPT_SoVITS/test/test_renderer_contract.py",
        "entry_points": [
            "live2d_support.renderer_contract",
            "live2d_support.contract",
            "live2d_support.runtime_contract",
        ],
    },
    "runtime_ingress": {
        "tests": "GPT_SoVITS/test/test_runtime_ingress.py",
        "entry_points": [
            "live2d_support.runtime_ingress",
            "live2d_support.runtime_contract",
            "live2d_support.runtime_adapter",
        ],
    },
}


def _module_available(root: Path, dotted: str) -> bool:
    module, _, symbol = dotted.rpartition(".")
    path = root / "GPT_SoVITS" / (module.replace(".", "/") + ".py")
    if path.exists():
        if not symbol:
            return True
        return symbol in path.read_text(encoding="utf-8", errors="replace")
    package = root / "GPT_SoVITS" / module.replace(".", "/")
    return package.exists()


def discover_entry_points(root: Path) -> dict[str, list[str]]:
    return {
        name: [entry for entry in spec["entry_points"] if _module_available(root, entry)]
        for name, spec in CONTRACTS.items()
    }


def run_contract(root: Path, name: str) -> dict:
    test_path = root / CONTRACTS[name]["tests"]
    if not test_path.exists():
        return {"status": "UNAVAILABLE", "tests": 0, "passed": 0, "returncode": None}
    python = sys.executable
    if sys.platform == "win32":
        probe = subprocess.run(["py", "-3.11", "-c", "import sys; print(sys.executable)"], capture_output=True, text=True)
        if probe.returncode == 0:
            python = probe.stdout.strip()
    proc = subprocess.run(
        [python, "-m", "pytest", "-q", str(test_path)],
        cwd=root / "GPT_SoVITS",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = proc.stdout + proc.stderr
    match = re.search(r"(?P<count>\d+) passed", output)
    passed = int(match.group("count")) if match else 0
    failed = re.search(r"(?P<count>\d+) failed", output)
    failed_count = int(failed.group("count")) if failed else 0
    collected = passed + failed_count
    return {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "tests": collected,
        "passed": passed if proc.returncode == 0 else 0,
        "returncode": proc.returncode,
        "output_tail": output[-2000:],
    }


def evaluate(root: Path) -> dict:
    entries = discover_entry_points(root)
    contracts = {name: run_contract(root, name) for name in CONTRACTS}
    total = sum(item["tests"] for item in contracts.values())
    passed = sum(item["passed"] for item in contracts.values())
    return {
        "workspace": str(root),
        "entry_points": entries,
        "contracts": contracts,
        "trusted_test_pass_rate": (passed / total) if total else 0.0,
        "quality_profile": "FULL_PASS" if total and passed == total else (
            "PARTIAL" if passed else "LOW_VALUE_PROGRESS"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.workspace.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
