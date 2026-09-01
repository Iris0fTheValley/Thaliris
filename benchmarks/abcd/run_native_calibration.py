"""Run isolated Native Luna/Sol calibration for sealed benchmark fixtures.

This module is benchmark-only.  It intentionally keeps model workspaces free
of evaluator assets, runs the fixed evaluator only after the model exits, and
stores telemetry outside every workspace.  It does not enable the Thaliris
router and never runs C/D orchestration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from build_sealed_fixture import build_fixture
from run_external_readiness import _commands, _load_tasks
from validate_sealed_fixture import validate_fixture


TASKS = (
    "reata__sqllineage-524",
    "mozilla-services__cliquet-203",
    "editorconfig-checker__editorconfig-checker-360",
    "reata__sqllineage-565",
    "databacker__mysql-backup-266",
)
MODELS = ("luna", "sol")
KNOWN_GOLD_COMMIT = "2349c84b5489bb792edbedc81acfaf9bf2488ce0"
CODEX = Path(os.environ.get("CODEX_EXE", r"C:\Users\12298\AppData\Local\codex-cli\codex.exe"))
GO_BIN = Path(r"I:\AI PROJECT\abcd-screening\readiness-20260902\tools\go\bin")
PY38 = Path(r"C:\Users\12298\AppData\Local\Programs\Python\Python38\python.exe")
READINESS_ROOT = Path(r"I:\AI PROJECT\abcd-screening\readiness-20260902")
TRUSTED_PATCH_ROOT = READINESS_ROOT / "evaluator-patches"


def _calibration_commands(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return the fixed evaluator command, excluding a known archive-only check.

    sqllineage's drawing test serves ``sqllineage/build/index.html``.  That
    frontend build is intentionally absent from a parentless git-archive
    fixture, so the check fails before exercising the parser task.  The
    remaining full suite (including the injected FAIL_TO_PASS tests) is the
    preservation evaluator for calibration.
    """
    install, test, toolchain = _commands(row)
    if row["task"].startswith("reata__sqllineage") and test:
        test = f"{test} --ignore=tests/core/test_drawing.py"
    return install, test, toolchain


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int, stdin: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            process.kill()
        stdout, stderr = process.communicate()
        return {
            "exit_code": 124,
            "timeout": True,
            "duration_seconds": round(time.monotonic() - started, 2),
            "stdout": (stdout or error.stdout or "")[-12000:] if isinstance(stdout or error.stdout, str) else "",
            "stderr": (stderr or error.stderr or "")[-12000:] if isinstance(stderr or error.stderr, str) else "",
        }
    return {
        "exit_code": process.returncode,
        "timeout": False,
        "duration_seconds": round(time.monotonic() - started, 2),
        "stdout": stdout[-12000:],
        "stderr": stderr[-12000:],
    }


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(workspace), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def _apply(workspace: Path, patch: Path) -> dict[str, Any]:
    result = _git(workspace, "apply", "--whitespace=nowarn", str(patch))
    return {"path": str(patch), "exit_code": result.returncode, "stderr": result.stderr[-4000:]}


def _reset(workspace: Path, baseline: str) -> None:
    result = _git(workspace, "reset", "--hard", baseline)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git reset failed")
    _git(workspace, "clean", "-fd")


def _patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git a/"):
            fields = line.split()
            if len(fields) >= 4 and fields[3].startswith("b/"):
                paths.append(fields[3][2:])
    return sorted(set(paths))


def _model_patch(workspace: Path, baseline: str, destination: Path) -> tuple[str, list[str]]:
    diff = _git(workspace, "diff", "--binary", baseline, "--", ".")
    destination.write_text(diff.stdout, encoding="utf-8", newline="\n")
    status = _git(workspace, "status", "--porcelain", "--untracked-files=all").stdout
    untracked = [line[3:] for line in status.splitlines() if len(line) >= 3 and line[:2] == "??"]
    return diff.stdout, untracked


def _scope(model_paths: list[str], gold_patch: str, untracked: list[str]) -> dict[str, Any]:
    gold_paths = set(_patch_paths(gold_patch))
    forbidden = ("test", "tests/", "evaluator", ".git/")
    violations = [path for path in model_paths if path not in gold_paths or path.lower().startswith(forbidden)]
    violations.extend(untracked)
    return {
        "status": "PASS" if not violations else "FAIL",
        "changed_files": model_paths,
        "untracked_files": untracked,
        "gold_file_allowlist": sorted(gold_paths),
        "violations": sorted(set(violations)),
    }


def _parse_jsonl(path: Path) -> tuple[dict[str, int], list[dict[str, Any]], str | None]:
    totals = {key: 0 for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")}
    timeline: list[dict[str, Any]] = []
    model: str | None = None
    preceding = "initial"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if not payload and isinstance(row.get("item"), dict):
            payload = row["item"]
        if row.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            model = payload["model"]
        if row.get("type") == "response_item" or row.get("type", "").startswith("item."):
            kind = payload.get("type")
            if kind in {"function_call", "custom_tool_call"}:
                preceding = str(payload.get("name") or "tool")
            elif kind in {"function_call_output", "custom_tool_call_output"}:
                preceding = "tool_result"
        # 0.146 emits usage directly on turn.completed.  Older snapshots used
        # event_msg/token_count, so accept both without counting either form
        # twice when a mixed stream is encountered.
        if row.get("type") == "turn.completed" and isinstance(row.get("usage"), dict):
            last = row["usage"]
        elif row.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
        else:
            continue
        if not isinstance(last.get("input_tokens"), int):
            continue
        values = {
            "input_tokens": int(last.get("input_tokens", 0)),
            "cached_input_tokens": int(last.get("cached_input_tokens", 0)),
            "output_tokens": int(last.get("output_tokens", 0)),
            "reasoning_tokens": int(last.get("reasoning_output_tokens", last.get("reasoning_tokens", 0))),
        }
        for key, value in values.items():
            totals[key] += value
        timeline.append({"call": len(timeline) + 1, **values, "preceding_action": preceding})
        preceding = "model_turn"
    totals["uncached_input_tokens"] = totals["input_tokens"] - totals["cached_input_tokens"]
    return totals, timeline, model


def _python_env(task: str, dependency: Path, workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(workspace) + os.pathsep + env.get("PYTHONPATH", "")
    if task == "mozilla-services__cliquet-203":
        python = dependency / "Scripts" / "python.exe"
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    return env


def _prepare_dependency(task: str, source: Path, dependency: Path) -> dict[str, Any]:
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.mkdir(parents=True, exist_ok=True)
    if task == "mozilla-services__cliquet-203":
        python = dependency / "Scripts" / "python.exe"
        if not python.exists():
            if not PY38.exists():
                return {"status": "FAIL", "reason": f"missing Python 3.8: {PY38}"}
            made = _run([str(PY38), "-m", "venv", str(dependency)], cwd=source, env=os.environ.copy(), timeout=300)
            if made["exit_code"]:
                return {"status": "FAIL", "reason": made["stderr"]}
            packages = ["pytest<8", "WebTest==1.4.3", "nose", "nose-cov", "mock", "Sphinx", "sphinx_rtd_theme", "SQLAlchemy", "tox", "werkzeug==0.16.1", "wheel", "newrelic", "pyramid==1.10.8", "WebOb==1.8.11", "structlog==19.2.0", "colander", "cornice", "python-dateutil", "pyfxa", "pyramid_multiauth", "redis", "requests", "six", "ujson"]
            installed = _run([str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check", *packages], cwd=source, env=os.environ.copy(), timeout=1200)
            if installed["exit_code"]:
                return {"status": "FAIL", "reason": installed["stderr"][-4000:]}
            # Install only distribution metadata into the external venv.  The
            # model/evaluator imports still resolve from their own workspace
            # through PYTHONPATH, while legacy pkg_resources version lookups
            # (used by Cliquet) remain functional.
            metadata = _run([str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-deps", "-e", str(source)], cwd=source, env=os.environ.copy(), timeout=300)
            if metadata["exit_code"]:
                return {"status": "FAIL", "reason": metadata["stderr"][-4000:]}
        else:
            metadata_probe = _run([str(python), "-c", "import pkg_resources; pkg_resources.get_distribution('cliquet')"], cwd=source, env=os.environ.copy(), timeout=60)
            if metadata_probe["exit_code"]:
                metadata = _run([str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-deps", "-e", str(source)], cwd=source, env=os.environ.copy(), timeout=300)
                if metadata["exit_code"]:
                    return {"status": "FAIL", "reason": metadata["stderr"][-4000:]}
        return {"status": "PASS", "kind": "python3.8", "python": str(python)}
    if task.startswith("reata__sqllineage"):
        probe = _run([sys.executable, "-c", "import pytest,sqlfluff,sqlparse,networkx,sqlalchemy"], cwd=source, env=os.environ.copy(), timeout=60)
        return {"status": "PASS" if probe["exit_code"] == 0 else "FAIL", "kind": "python3.11-global", "reason": probe["stderr"][-2000:]}
    if task in {"editorconfig-checker__editorconfig-checker-360", "databacker__mysql-backup-266"}:
        go = GO_BIN / ("go.exe" if os.name == "nt" else "go")
        if not go.exists():
            return {"status": "FAIL", "reason": f"missing Go toolchain: {go}"}
        gomod = dependency / "gomodcache"
        gomod.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PATH"] = str(GO_BIN) + os.pathsep + env.get("PATH", "")
        env["GOTOOLCHAIN"] = "local"
        env["GOMODCACHE"] = str(gomod)
        download = _run([str(go), "mod", "download"], cwd=source, env=env, timeout=1200)
        return {"status": "PASS" if download["exit_code"] == 0 else "FAIL", "kind": "go", "gomodcache": str(gomod), "reason": download["stderr"][-4000:]}
    return {"status": "FAIL", "reason": f"unsupported task dependency: {task}"}


def _model_env(task: str, dependency: Path, workspace: Path) -> dict[str, str]:
    if task.startswith("reata__sqllineage") or task == "mozilla-services__cliquet-203":
        return _python_env(task, dependency, workspace)
    env = os.environ.copy()
    env["PATH"] = str(GO_BIN) + os.pathsep + env.get("PATH", "")
    env["GOTOOLCHAIN"] = "local"
    env["GOMODCACHE"] = str(dependency / "gomodcache")
    return env


def _evaluate(row: dict[str, Any], model_workspace: Path, evaluator: Path, dependency: Path, model_patch_path: Path, test_patch: Path, gold_patch: Path, timeout: int) -> dict[str, Any]:
    source = Path(row["source"])
    baseline = row["base_commit"]
    if evaluator.exists():
        shutil.rmtree(evaluator)
    eval_build = build_fixture(source=source, revision=baseline, issue_text=Path(row["issue_path"]), dependency_reference=str(dependency), workspace=evaluator, report=None)
    install, test_command, toolchain = _calibration_commands(row)
    env = _model_env(row["task"], dependency, evaluator)
    if row["task"] == "mozilla-services__cliquet-203":
        python = dependency / "Scripts" / "python.exe"
        test_command = test_command.replace("python", f'"{python}"', 1)
    if toolchain == "go":
        env["GOTOOLCHAIN"] = "local"
        test_command = test_command.replace("go test", f'"{GO_BIN / "go.exe"}" test', 1)
    if install:
        # Dependencies were prepared before model execution; evaluator only
        # verifies the fixed test command and never installs during this stage.
        pass

    def stage(kind: str, include_model: bool, include_gold: bool) -> dict[str, Any]:
        _reset(evaluator, eval_build["synthetic_commit"])
        actions: list[dict[str, Any]] = []
        if include_model:
            actions.append({"model_patch": _apply(evaluator, model_patch_path)})
        actions.append({"test_patch": _apply(evaluator, test_patch)})
        if include_gold:
            actions.append({"gold_patch": _apply(evaluator, gold_patch)})
        if any(next(iter(item.values()))["exit_code"] for item in actions):
            return {"kind": kind, "status": "PATCH_APPLY_FAIL", "actions": actions}
        # All fixed commands use paths without spaces in this fixture root;
        # removing the optional Windows quoting preserves the executable as a
        # single argv item without POSIX shlex interpreting backslashes.
        result = _run(test_command.replace('"', "").split(), cwd=evaluator, env=env, timeout=timeout)
        return {"kind": kind, "status": "PASS" if result["exit_code"] == 0 else "FAIL", "run": result, "actions": actions}

    model_result = stage("model", True, False)
    no_edit = stage("no_edit", False, False)
    gold = stage("gold", False, True)
    repeats = [stage(f"gold_repeat_{index}", False, True) for index in range(1, 4)]
    return {
        "model": model_result,
        "no_edit": no_edit,
        "gold": gold,
        "gold_repeat": repeats,
        "model_pass": model_result.get("status") == "PASS",
        "no_edit_expected_fail": no_edit.get("status") == "FAIL",
        "gold_pass": gold.get("status") == "PASS" and all(item.get("status") == "PASS" for item in repeats),
        "test_command": test_command,
    }


def run_one(row: dict[str, Any], model_name: str, index: int, root: Path, timeout: int) -> dict[str, Any]:
    task = row["task"]
    run_id = f"{task}-{model_name.upper()}{index}"
    # Keep each model workspace in a unique temporary one-entry directory.
    # Telemetry, evaluator workspaces and trusted overlays live elsewhere, so
    # no previous benchmark artifact is reachable by walking its parent.
    isolated_parent = Path(tempfile.mkdtemp(prefix=f"thaliris-{run_id}-"))
    workspace = isolated_parent / "workspace"
    evaluator = root / "evaluators" / run_id
    dependency = root / "dependencies" / task
    telemetry = root / "telemetry" / f"{run_id}.jsonl"
    final = root / "final" / f"{run_id}.txt"
    model_patch = root / "model-patches" / f"{run_id}.patch"
    patch_dir = TRUSTED_PATCH_ROOT / task
    test_patch = patch_dir / "test.patch"
    gold_patch = patch_dir / "gold.patch"
    for path in (workspace, evaluator):
        if path.exists():
            shutil.rmtree(path)
    for path in (telemetry, final, model_patch):
        path.unlink(missing_ok=True)
    telemetry.parent.mkdir(parents=True, exist_ok=True)
    final.parent.mkdir(parents=True, exist_ok=True)
    model_patch.parent.mkdir(parents=True, exist_ok=True)
    patch_dir.mkdir(parents=True, exist_ok=True)
    # Keep trusted evaluator overlays in memory until the model has exited.
    # This prevents a full-access model process from discovering test/gold
    # patches through an absolute path, while still keeping them outside the
    # model workspace when the evaluator is materialized.
    dep = _prepare_dependency(task, Path(row["source"]), dependency)
    record: dict[str, Any] = {"task": task, "model": model_name, "index": index, "run": run_id, "dependency": dep, "network_enforcement": "UNVERIFIED", "installation_enforcement": "UNVERIFIED"}
    if dep.get("status") != "PASS":
        record["classification"] = "ENVIRONMENT_INVALID"
        record["failure_mode"] = dep.get("reason")
        return record
    build = build_fixture(source=Path(row["source"]), revision=row["base_commit"], issue_text=Path(row["issue_path"]), dependency_reference=str(dependency), workspace=workspace, report=None)
    record["fixture"] = {"synthetic_commit": build["synthetic_commit"], "source_tree": build["source_tree"]}
    gate = validate_fixture(workspace=workspace, source=Path(row["source"]), revision=row["base_commit"], dependency_reference=str(dependency), baseline_status="PASS", known_gold_commit=KNOWN_GOLD_COMMIT, scan_root=workspace, forbidden_roots=[evaluator, patch_dir], evaluator_path=evaluator, max_scan_files=10000)
    record["gate"] = gate["status"]
    if gate["status"] != "SEALED_PASS":
        record["classification"] = "ENVIRONMENT_INVALID"
        record["failure_mode"] = "pre-model sealed fixture gate failed"
        return record
    prompt = Path(row["issue_path"]).read_text(encoding="utf-8") + "\n\nSolve this issue in the current repository. Investigate source and tests as needed, implement the smallest correct fix, and run relevant tests. Do not access git history, remotes, parent directories, benchmark/evaluator artifacts, or the network. Do not modify tests or unrelated files."
    env = _model_env(task, dependency, workspace)
    command = [str(CODEX), "exec", "--ignore-user-config", "--ignore-rules", "--cd", str(workspace), "--model", "gpt-5.6-luna" if model_name == "luna" else "gpt-5.6-sol", "-c", "model_reasoning_effort=high", "--sandbox", "danger-full-access", "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust", "--json", "--ephemeral", "--output-last-message", str(final), "-"]
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=telemetry.open("w", encoding="utf-8"), stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    try:
        _stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            process.kill()
        _stdout, stderr = process.communicate()
        record["model_process"] = {"exit_code": 124, "timeout": True, "duration_seconds": round(time.monotonic() - started, 2), "stderr_tail": stderr[-4000:]}
    else:
        record["model_process"] = {"exit_code": process.returncode, "timeout": False, "duration_seconds": round(time.monotonic() - started, 2), "stderr_tail": stderr[-4000:]}
    if "usage limit" in record["model_process"].get("stderr_tail", "").lower() or "hit your usage limit" in record["model_process"].get("stderr_tail", "").lower():
        record["model_process"]["failure_reason"] = "USAGE_LIMIT"
    totals, timeline, actual_model = _parse_jsonl(telemetry)
    record["telemetry"] = {"model_reported": actual_model, "usage": totals, "model_calls": len(timeline), "peak_context": max((item["input_tokens"] for item in timeline), default=0), "timeline": timeline}
    diff, untracked = _model_patch(workspace, build["synthetic_commit"], model_patch)
    record["scope"] = _scope(_patch_paths(diff), (row.get("patch") or ""), untracked)
    if record["model_process"].get("failure_reason") == "USAGE_LIMIT":
        record["evaluation"] = {"status": "NOT_RUN", "reason": "Codex usage limit; no model attempt completed"}
        record["quality"] = "ENVIRONMENT_INVALID"
        record["failure_mode"] = "usage_limit"
    elif process.returncode == 0 and model_patch.exists():
        patch_dir.mkdir(parents=True, exist_ok=True)
        test_patch.write_text((row.get("test_patch") or "").replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        gold_patch.write_text((row.get("patch") or "").replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        evaluator_report = _evaluate(row, workspace, evaluator, dependency, model_patch, test_patch, gold_patch, timeout=timeout)
        record["evaluation"] = evaluator_report
        record["quality"] = "PASS" if evaluator_report["model_pass"] and evaluator_report["no_edit_expected_fail"] and evaluator_report["gold_pass"] and record["scope"]["status"] == "PASS" else "FAIL"
    else:
        record["evaluation"] = {"status": "NOT_RUN", "reason": "model process failed or produced no patch"}
        record["quality"] = "FAIL"
    record["failure_mode"] = None if record["quality"] == "PASS" else ("scope_violation" if record["scope"]["status"] != "PASS" else "evaluator/model failure")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-metadata", required=True, type=Path)
    parser.add_argument("--v2-metadata", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--only", action="append", choices=TASKS)
    parser.add_argument("--luna-runs", type=int, default=3)
    parser.add_argument("--sol-runs", type=int, default=3)
    parser.add_argument("--luna-start", type=int, default=1)
    parser.add_argument("--sol-start", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    # Use the already prepared trusted source and issue roots from readiness;
    # no evaluator material is placed beside a model workspace.
    rows = _load_tasks(args.live_metadata, args.v2_metadata, args.root, READINESS_ROOT / "trusted-sources", READINESS_ROOT / "issues")
    selected = tuple(args.only or TASKS)
    all_results: list[dict[str, Any]] = []
    for task in selected:
        row = rows[task]
        luna_results = []
        for index in range(args.luna_start, args.luna_start + args.luna_runs):
            result = run_one(row, "luna", index, args.root, args.timeout)
            luna_results.append(result)
            all_results.append(result)
            # Adaptive rule: only run Sol if Luna is already 0/3 or 1/3 after
            # all independent Luna attempts.  This loop intentionally does
            # not leak earlier result details into later model prompts.
        luna_passes = sum(item.get("quality") == "PASS" for item in luna_results)
        if luna_passes <= 1:
            for index in range(args.sol_start, args.sol_start + args.sol_runs):
                all_results.append(run_one(row, "sol", index, args.root, args.timeout))
    payload = {"schema_version": 1, "protocol": "native_calibration_luna_first", "tasks": selected, "runs": all_results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
