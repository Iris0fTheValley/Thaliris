"""Behavior-contract evaluator independent of gold private APIs."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CONTRACTS = {
    "shared_behavior": "GPT_SoVITS/test/test_live2d_shared_behavior.py",
    "renderer": "GPT_SoVITS/test/test_renderer_contract.py",
    "runtime_ingress": "GPT_SoVITS/test/test_runtime_ingress.py",
}

def _public_modules(root: Path) -> list[str]:
    package = root / "GPT_SoVITS" / "live2d_support"
    if not package.is_dir():
        return []
    return sorted(str(p.relative_to(root / "GPT_SoVITS")).replace("\\", "/") for p in package.rglob("*.py"))

def discover_entry_points(root: Path) -> dict[str, list[str]]:
    modules = _public_modules(root)
    return {name: modules[:] for name in CONTRACTS}

def _python_for_tests() -> str:
    if sys.platform == "win32":
        probe = subprocess.run(["py", "-3.11", "-c", "import sys; print(sys.executable)"], capture_output=True, text=True)
        if probe.returncode == 0:
            return probe.stdout.strip()
    return sys.executable

def _pytest_contract(root: Path, name: str) -> dict:
    path = root / CONTRACTS[name]
    if not path.exists():
        return {"status": "UNAVAILABLE", "tests": 0, "passed": 0, "returncode": None, "source": "trusted_behavior_tests"}
    proc = subprocess.run([_python_for_tests(), "-m", "pytest", "-q", str(path)], cwd=root / "GPT_SoVITS", capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = proc.stdout + proc.stderr
    pm, fm = re.search(r"(\d+) passed", output), re.search(r"(\d+) failed", output)
    passed, failed = (int(pm.group(1)) if pm else 0), (int(fm.group(1)) if fm else 0)
    return {"status": "PASS" if proc.returncode == 0 else "FAIL", "tests": passed + failed, "passed": passed, "returncode": proc.returncode, "source": "trusted_behavior_tests", "output_tail": output[-2000:]}

def run_contract(root: Path, name: str) -> dict:
    return _pytest_contract(root, name)

def evaluate(root: Path) -> dict:
    contracts = {name: run_contract(root, name) for name in CONTRACTS}
    total, passed = sum(v["tests"] for v in contracts.values()), sum(v["passed"] for v in contracts.values())
    return {"workspace": str(root), "entry_points": discover_entry_points(root), "contracts": contracts, "trusted_test_pass_rate": passed / total if total else 0.0, "quality_profile": "FULL_PASS" if total and passed == total else ("PARTIAL" if passed else "LOW_VALUE_PROGRESS"), "implementation_independent": False}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("workspace", type=Path); parser.add_argument("--output", type=Path); args = parser.parse_args()
    rendered = json.dumps(evaluate(args.workspace.resolve()), ensure_ascii=False, indent=2) + "\n"
    if args.output: args.output.write_text(rendered, encoding="utf-8")
    else: print(rendered, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
