"""Run offline readiness checks for a fixed external benchmark task set.

This is benchmark-only plumbing.  It never invokes a model.  Trusted source
metadata and evaluator patches stay outside the model workspace; the model
workspace is produced by ``build_sealed_fixture`` and gated before use.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from build_sealed_fixture import build_fixture
from validate_sealed_fixture import validate_fixture


TASKS = (
    "fluent__fluent-bit-10563",
    "elastic__synthetics-316",
    "reata__sqllineage-524",
    "mozilla-services__cliquet-203",
    "editorconfig-checker__editorconfig-checker-360",
    "webpack-contrib__copy-webpack-plugin-590",
    "privacyidea__privacyidea-3852",
    "reata__sqllineage-565",
    "databacker__mysql-backup-266",
    "sphinx-doc__sphinx-11888",
)


def _run(command: str, cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return {
            "command": command,
            "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 2),
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }
    except subprocess.TimeoutExpired as error:
        # ``shell=True`` is retained for the small command strings (notably
        # chained package installs), so explicitly reap the shell's child tree
        # on Windows instead of leaving pytest/npm descendants behind.
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            process.kill()
        stdout, stderr = process.communicate()
        return {
            "command": command,
            "exit_code": 124,
            "duration_seconds": round(time.monotonic() - started, 2),
            "stdout_tail": (stdout or error.stdout or "")[-4000:] if isinstance(stdout or error.stdout, str) else "",
            "stderr_tail": (stderr or error.stderr or "")[-4000:] if isinstance(stderr or error.stderr, str) else "",
            "timeout": True,
        }


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _apply_patch(workspace: Path, patch_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "-C", str(workspace), "apply", "--whitespace=nowarn", str(patch_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "patch": str(patch_path),
        "exit_code": result.returncode,
        "stderr": result.stderr[-4000:],
    }


def _cleanup_patch_paths(workspace: Path, patch_path: Path) -> None:
    """Remove untracked files created by a previous overlay, preserving deps."""
    if not patch_path.exists():
        return
    paths: set[str] = set()
    for line in patch_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("diff --git a/"):
            fields = line.split()
            if len(fields) >= 4 and fields[3].startswith("b/"):
                paths.add(fields[3][2:])
    for path in sorted(paths):
        subprocess.run(
            ["git", "-C", str(workspace), "clean", "-fd", "--", path],
            capture_output=True,
            text=True,
            check=False,
        )


def _reset(workspace: Path, commit: str) -> None:
    result = _git(workspace, "reset", "--hard", commit)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git reset failed")


def _load_tasks(
    live_path: Path,
    v2_path: Path,
    prep_root: Path,
    trusted_root: Path,
    issue_root: Path,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path, dataset in ((live_path, "SWE-bench-Live"), (v2_path, "SWE-rebench-V2")):
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        for task, row in raw.items():
            slug = task.replace("/", "_")
            row = dict(row)
            row.update(
                {
                    "task": task,
                    "dataset": dataset,
                    "source": str(trusted_root / slug),
                    "issue_path": str(issue_root / f"{slug}.md"),
                    "model_workspace": str(prep_root / "model" / slug),
                    "evaluator_workspace": str(prep_root / "eval" / slug),
                    "dependency_reference": str(prep_root / "deps" / slug),
                    "future_evaluator_path": str(prep_root / "future-evaluator" / slug),
                }
            )
            records[task] = row
    return records


def _commands(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    task = row["task"]
    install = None
    test = None
    toolchain = None
    if task == "elastic__synthetics-316":
        install, test, toolchain = "npm ci --quiet", "npm run test:unit -- --verbose --no-color", "node/npm"
    elif task == "webpack-contrib__copy-webpack-plugin-590":
        install, test, toolchain = "npm ci", "npm run test:only -- --verbose --no-color", "node/npm"
    elif task == "mozilla-services__cliquet-203":
        install = "python -m pip install -q -e . WebTest==1.4.3 nose nose-cov nose-mocha-reporter mock Sphinx sphinx_rtd_theme SQLAlchemy kinto tox werkzeug==0.16.1 wheel zest.releaser pytest newrelic pyramid==1.10.8 WebOb==1.8.11 structlog==19.2.0"
        test, toolchain = "python -m pytest --no-header -rA --tb=line --color=no -p no:cacheprovider -W ignore::DeprecationWarning cliquet/tests/test_initialization.py", "python/pip"
    elif task in {"reata__sqllineage-524", "reata__sqllineage-565"}:
        install = "python -m pip install -q -e . pytest"
        test, toolchain = "python -m pytest -rA", "python/pip"
    elif task == "privacyidea__privacyidea-3852":
        install = "python -m pip install -q -e . pytest responses testfixtures"
        test, toolchain = "python -m pytest -v -rA tests/", "python/pip"
    elif task == "sphinx-doc__sphinx-11888":
        install = "python -m pip install -q .[test]"
        test, toolchain = "python -X dev -X warn_default_encoding -m pytest -v -rA", "python/pip"
    elif task in {"editorconfig-checker__editorconfig-checker-360", "databacker__mysql-backup-266"}:
        install, test, toolchain = "go mod download", "go test -v ./...", "go"
    elif task == "fluent__fluent-bit-10563":
        test, toolchain = "ctest --test-dir build --output-on-failure", "cmake+ninja+docker"
    return install, test, toolchain


def _toolchain_ready(toolchain: str) -> tuple[bool, str | None]:
    checks = {
        "node/npm": ("node", "npm"),
        "python/pip": (sys.executable,),
        "go": ("go",),
        "cmake+ninja+docker": ("cmake", "ninja", "docker"),
    }
    for executable in checks[toolchain]:
        if os.path.isabs(executable):
            continue
        if shutil.which(executable) is None:
            return False, f"missing executable: {executable}"
    return True, None


def _venv_base_python(task: str) -> str:
    """Use Python 3.8 for the legacy Cliquet fixture when available."""
    if task == "mozilla-services__cliquet-203" and os.name == "nt" and shutil.which("py"):
        probe = subprocess.run(
            ["py", "-3.8", "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return probe.stdout.strip()
    return sys.executable


def _stage(
    workspace: Path,
    baseline_commit: str,
    test_patch: Path,
    gold_patch: Path,
    test_command: str,
    env: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    _cleanup_patch_paths(workspace, test_patch)
    _cleanup_patch_paths(workspace, gold_patch)
    _reset(workspace, baseline_commit)
    test_apply = _apply_patch(workspace, test_patch)
    if test_apply["exit_code"]:
        return {"test_patch": test_apply, "status": "PATCH_APPLY_FAIL"}
    base = _run(test_command, workspace, env, timeout)
    no_edit = {**base, "status": "PASS" if base["exit_code"] == 0 else "FAIL"}
    gold_apply = _apply_patch(workspace, gold_patch)
    if gold_apply["exit_code"]:
        return {"base": base, "no_edit": no_edit, "gold": {"patch": gold_apply, "status": "PATCH_APPLY_FAIL"}}
    gold = _run(test_command, workspace, env, timeout)
    return {
        "base": base,
        "no_edit": no_edit,
        "gold": {**gold, "patch": gold_apply, "status": "PASS" if gold["exit_code"] == 0 else "FAIL"},
    }


def evaluate_task(row: dict[str, Any], prep_root: Path, timeout: int) -> dict[str, Any]:
    task = row["task"]
    source = Path(row["source"])
    issue = Path(row["issue_path"])
    model = Path(row["model_workspace"])
    evaluator = Path(row["evaluator_workspace"])
    dependency = Path(row["dependency_reference"])
    dependency.mkdir(parents=True, exist_ok=True)
    model.parent.mkdir(parents=True, exist_ok=True)
    evaluator.parent.mkdir(parents=True, exist_ok=True)
    install, test_command, toolchain = _commands(row)
    record: dict[str, Any] = {
        "task": task,
        "source_dataset": row["dataset"],
        "repo": row["repo"],
        "revision": row["base_commit"],
        "f2p": row.get("FAIL_TO_PASS", []),
        "p2p_count": len(row.get("PASS_TO_PASS", [])),
        "toolchain": toolchain,
        "network_enforcement": "UNVERIFIED",
        "installation_enforcement": "UNVERIFIED",
    }
    ready, blocker = _toolchain_ready(toolchain)
    record["toolchain_ready"] = ready
    if blocker:
        record["blocker"] = blocker

    # Always materialize the model fixture, even if the evaluator cannot run.
    if model.exists():
        shutil.rmtree(model)
    dependency_ref = str(dependency)
    try:
        build = build_fixture(source=source, revision=row["base_commit"], issue_text=issue, dependency_reference=dependency_ref, workspace=model, report=None)
    except (OSError, RuntimeError, ValueError) as error:
        record["model_fixture"] = {"status": "FIXTURE_NOT_SEALED", "error": str(error)}
        record["gate_status"] = "FIXTURE_NOT_SEALED"
        record["evaluator_status"] = "NOT_RUN"
        record["final"] = "FIXTURE_NOT_SEALED"
        record["blocker"] = f"sealed fixture builder rejected source tree: {error}"
        return record
    record["model_fixture"] = {"workspace": str(model), "synthetic_commit": build["synthetic_commit"], "source_tree": build["source_tree"]}

    patch_dir = prep_root / "evaluator-patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    test_patch = patch_dir / f"{task}.test.patch"
    gold_patch = patch_dir / f"{task}.gold.patch"
    # pathlib.Path.write_text gained the ``newline`` parameter after the
    # Python 3.8 runtime used by several candidate projects.  Use an
    # explicit text handle so patch bytes remain normalized on all runners.
    with test_patch.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write((row.get("test_patch") or "").replace("\r\n", "\n"))
    with gold_patch.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write((row.get("patch") or "").replace("\r\n", "\n"))
    # The future evaluator path is intentionally absent for the model gate.
    future_evaluator = Path(row["future_evaluator_path"])
    if future_evaluator.exists():
        shutil.rmtree(future_evaluator)

    if not ready:
        gate = validate_fixture(
            workspace=model,
            source=source,
            revision=row["base_commit"],
            dependency_reference=dependency_ref,
            baseline_status="UNVERIFIED",
            known_gold_commit="2349c84b5489bb792edbedc81acfaf9bf2488ce0",
            scan_root=model,
            forbidden_roots=[evaluator, patch_dir],
            evaluator_path=future_evaluator,
            max_scan_files=10000,
        )
        record["gate_status"] = gate["status"]
        record["evaluator_status"] = "NOT_RUN"
        record["final"] = "READINESS_FAIL"
        return record

    if evaluator.exists():
        shutil.rmtree(evaluator)
    try:
        eval_build = build_fixture(source=source, revision=row["base_commit"], issue_text=issue, dependency_reference=dependency_ref, workspace=evaluator, report=None)
    except (OSError, RuntimeError, ValueError) as error:
        record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
        record["final"] = "EVALUATOR_INCONCLUSIVE"
        record["blocker"] = f"evaluator fixture could not be materialized: {error}"
        return record
    env = os.environ.copy()
    env["PIP_NO_INPUT"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if install:
        if toolchain == "python/pip":
            venv_python = dependency / "Scripts" / "python.exe"
            if not venv_python.exists():
                venv = subprocess.run(
                    [_venv_base_python(task), "-m", "venv", str(dependency)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if venv.returncode:
                    record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
                    record["blocker"] = f"python venv creation failed: {venv.stderr[-2000:]}"
                    record["final"] = "EVALUATOR_INCONCLUSIVE"
                    return record
            env["PATH"] = str(venv_python.parent) + os.pathsep + env.get("PATH", "")
            install = install.replace("python", f'"{venv_python}"', 1)
            test_command = test_command.replace("python", f'"{venv_python}"', 1)
        elif toolchain == "node/npm":
            env["npm_config_ignore_scripts"] = "1"
        elif toolchain == "go":
            env["GOTOOLCHAIN"] = "local"
        record["installation"] = _run(install, evaluator, env, min(timeout, 900))
        if record["installation"]["exit_code"] != 0:
            record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
            record["blocker"] = "dependency installation failed"
            record["final"] = "EVALUATOR_INCONCLUSIVE"
            return record

    # Independent model gate after evaluator readiness is externally known.
    gate = validate_fixture(
        workspace=model,
        source=source,
        revision=row["base_commit"],
        dependency_reference=dependency_ref,
        baseline_status="PASS",
        known_gold_commit="2349c84b5489bb792edbedc81acfaf9bf2488ce0",
        scan_root=model,
        forbidden_roots=[evaluator, patch_dir],
        evaluator_path=future_evaluator,
        max_scan_files=10000,
    )
    record["gate_status"] = gate["status"]
    if gate["status"] != "SEALED_PASS":
        record["evaluator_status"] = "FIXTURE_NOT_SEALED"
        record["final"] = "FIXTURE_NOT_SEALED"
        return record

    if test_command is None:
        record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
        record["blocker"] = "no evaluator command"
        record["final"] = "EVALUATOR_INCONCLUSIVE"
        return record
    first = _stage(evaluator, eval_build["synthetic_commit"], test_patch, gold_patch, test_command, env, timeout)
    repeats = []
    # A full evaluator timeout is a readiness blocker.  Do not spend another
    # 3x timeout repeating a known-inconclusive environment.
    if not first.get("base", {}).get("timeout"):
        for _ in range(3):
            stage = _stage(evaluator, eval_build["synthetic_commit"], test_patch, gold_patch, test_command, env, timeout)
            repeats.append(stage.get("gold", {}))
    record["evaluation"] = {
        "base": first.get("base"),
        "no_edit": first.get("no_edit"),
        "gold": first.get("gold"),
        "test_patch_apply": first.get("test_patch"),
        "gold_repeat": repeats,
    }
    base_ok = first.get("base", {}).get("exit_code") not in (None, 0)
    no_edit_ok = first.get("no_edit", {}).get("exit_code") not in (None, 0)
    gold_ok = first.get("gold", {}).get("exit_code") == 0
    repeat_ok = len(repeats) == 3 and all(item.get("exit_code") == 0 for item in repeats)
    record["evaluator_status"] = "PASS" if base_ok and no_edit_ok and gold_ok and repeat_ok else "EVALUATOR_INCONCLUSIVE"
    record["final"] = "SEALED_PASS" if record["evaluator_status"] == "PASS" else "EVALUATOR_INCONCLUSIVE"
    if record["final"] != "SEALED_PASS":
        record["blocker"] = "base/no-edit/gold or gold-repeat acceptance did not meet required exit-status contract"
        if first.get("status") == "PATCH_APPLY_FAIL":
            record["blocker"] = "test patch did not apply to exact base revision"
        elif first.get("base", {}).get("timeout"):
            record["blocker"] = "base evaluator timed out before fixed acceptance could be established"
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-metadata", required=True, type=Path)
    parser.add_argument("--v2-metadata", required=True, type=Path)
    parser.add_argument("--prep-root", required=True, type=Path)
    parser.add_argument("--trusted-root", type=Path)
    parser.add_argument("--issue-root", type=Path)
    parser.add_argument("--only", action="append", choices=TASKS)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    trusted_root = args.trusted_root or (args.prep_root / "trusted-sources")
    issue_root = args.issue_root or (args.prep_root / "issues")
    rows = _load_tasks(args.live_metadata, args.v2_metadata, args.prep_root, trusted_root, issue_root)
    selected = tuple(args.only or TASKS)
    missing = [task for task in selected if task not in rows]
    if missing:
        raise SystemExit(f"metadata missing: {missing}")
    results = []
    for task in selected:
        try:
            results.append(evaluate_task(rows[task], args.prep_root, args.timeout))
        except Exception as error:  # readiness must remain auditable per task
            results.append({"task": task, "final": "EVALUATOR_INCONCLUSIVE", "blocker": f"harness exception: {error}"})
    payload = {"schema_version": 1, "model_runs": 0, "tasks": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Keep CLI output portable on Windows consoles whose code page is not UTF-8;
    # the UTF-8 report file above remains the authoritative artifact.
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
