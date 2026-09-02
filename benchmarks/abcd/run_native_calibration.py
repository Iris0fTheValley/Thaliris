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
from prepare_benchmark_codex_home import build_minimal_home
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
CODEX_CANDIDATES = (
    Path(r"C:\Users\12298\AppData\Local\OpenAI\Codex\bin\87e5fb3433dabab1\codex.exe"),
    Path(r"C:\Users\12298\AppData\Local\codex-cli\codex.exe"),
)
EXTERNAL_CODEX_HOME = Path(os.environ.get(
    "THALIRIS_EXTERNAL_CODEX_HOME",
    r"C:\Users\12298\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\ThalirisBench\managed-cli-builder-external-home-r3",
))
CODEX_HOME_ROOT = Path(os.environ.get("THALIRIS_CODEX_HOME_ROOT", r"C:\thaliris-codex"))
GO_BIN = Path(r"I:\AI PROJECT\abcd-screening\readiness-20260902\tools\go\bin")
PY38 = Path(r"C:\Users\12298\AppData\Local\Programs\Python\Python38\python.exe")
READINESS_ROOT = Path(r"I:\AI PROJECT\abcd-screening\readiness-20260902")
TRUSTED_PATCH_ROOT = READINESS_ROOT / "evaluator-patches"


def _codex_executable() -> Path:
    configured = os.environ.get("CODEX_EXE")
    candidates = (Path(configured),) if configured else CODEX_CANDIDATES
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("no usable Codex CLI executable; set CODEX_EXE to codex.exe")


def _calibration_commands(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return the fixed evaluator command, excluding a known archive-only check.

    sqllineage's drawing test serves ``sqllineage/build/index.html``.  That
    frontend build is intentionally absent from a parentless git-archive
    fixture, so the check fails before exercising the parser task.  The
    remaining full suite (including the injected FAIL_TO_PASS tests) is the
    preservation evaluator for calibration.
    """
    install, test, toolchain = _commands(row)
    if install is None and row.get("exact_issue_only"):
        return None, "python -m pytest -q", "python/pip"
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
    # Keep Git's LF patch stream intact on Windows.  ``Path.write_text`` did
    # not gain ``newline=`` until Python 3.10, while this harness supports
    # the Cliquet Python 3.8 environment.
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(diff.stdout)
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
        python = dependency / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        if not python.exists():
            made = _run([sys.executable, "-m", "venv", str(dependency)], cwd=source, env=os.environ.copy(), timeout=300)
            if made["exit_code"]:
                return {"status": "FAIL", "kind": "python-venv", "reason": made["stderr"][-2000:]}
            installed = _run([str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", str(source), "pytest", "sqlfluff", "sqlparse", "networkx", "sqlalchemy"], cwd=source, env=os.environ.copy(), timeout=1200)
            if installed["exit_code"]:
                return {"status": "FAIL", "kind": "python-venv", "reason": installed["stderr"][-2000:]}
        probe = _run([str(python), "-c", "import pytest,sqlfluff,sqlparse,networkx,sqlalchemy"], cwd=source, env=os.environ.copy(), timeout=60)
        return {"status": "PASS" if probe["exit_code"] == 0 else "FAIL", "kind": "python-venv", "python": str(python), "reason": probe["stderr"][-2000:]}
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
    if task.startswith(("aaugustin__websockets-", "asdf-format__asdf-", "alteryx__woodwork-", "amaranth-lang__amaranth-", "bashtage__arch-")):
        python = dependency / "Scripts" / "python.exe"
        if not python.exists():
            base = Path(r"C:\Users\12298\AppData\Local\Programs\Python\Python311\python.exe")
            if task.startswith("aaugustin__websockets-"):
                base = PY38
            if not base.exists():
                return {"status": "FAIL", "reason": f"missing Python runtime: {base}"}
            made = _run([str(base), "-m", "venv", str(dependency)], cwd=source, env=os.environ.copy(), timeout=300)
            if made["exit_code"]:
                return {"status": "FAIL", "reason": made["stderr"][-4000:]}
            packages = ["pytest<9", "psutil", "pytest-remotedata"]
            if task.startswith("asdf-format__asdf-"):
                packages += ["asdf-standard", "asdf-transform-schemas", "numpy", "pyyaml", "semantic_version", "jmespath", "attrs"]
            elif task.startswith("alteryx__woodwork-"):
                packages += ["pandas==1.5.3", "scikit-learn"]
            elif task.startswith("bashtage__arch-"):
                packages += ["numpy==1.26.4", "pandas==1.5.3", "scipy==1.11.4", "statsmodels==0.14.4"]
            installed = _run([str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check", *packages], cwd=source, env=os.environ.copy(), timeout=1200)
            if installed["exit_code"]:
                return {"status": "FAIL", "reason": installed["stderr"][-4000:]}
        return {"status": "PASS", "kind": "python", "python": str(python)}
    return {"status": "FAIL", "reason": f"unsupported task dependency: {task}"}


def _model_env(task: str, dependency: Path, workspace: Path) -> dict[str, str]:
    if task.startswith("reata__sqllineage"):
        env = _python_env(task, dependency, workspace)
        python = dependency / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
        env["THALIRIS_BENCHMARK_PYTHON"] = str(python)
        return env
    if task == "mozilla-services__cliquet-203":
        return _python_env(task, dependency, workspace)
    if task.startswith(("aaugustin__websockets-", "asdf-format__asdf-", "alteryx__woodwork-", "amaranth-lang__amaranth-", "bashtage__arch-")):
        env = _python_env(task, dependency, workspace)
        python = dependency / "Scripts" / "python.exe"
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
        return env
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
    test_argv: list[str] | None = None
    if row.get("exact_issue_only") and toolchain == "python/pip":
        selection = list(row.get("test_selection") or row.get("FAIL_TO_PASS", []) + row.get("PASS_TO_PASS", []))
        if any("[" in test and "]" not in test for test in selection):
            selection = sorted({test.split("::", 1)[0] for test in selection})
        selection_file = evaluator / ".t4_selected_tests.json"
        selection_file.write_text(json.dumps(selection) + "\n", encoding="utf-8")
        runner = evaluator / ".t4_selected_runner.py"
        runner.write_text(
            "import json\nfrom pathlib import Path\nimport pytest\n"
            "tests = json.loads((Path(__file__).with_name('.t4_selected_tests.json')).read_text())\n"
            "raise SystemExit(pytest.main(['-q', *tests]))\n",
            encoding="utf-8",
        )
        test_argv = [str(dependency / "Scripts" / "python.exe"), str(runner)]
    if row["task"].startswith("reata__sqllineage"):
        python = dependency / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        test_command = test_command.replace("python", f'"{python}"', 1)
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
        command = test_argv if test_argv is not None else test_command.replace('"', "").split()
        result = _run(command, cwd=evaluator, env=env, timeout=timeout)
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
    patch_dir = Path(row.get("patch_dir", str(TRUSTED_PATCH_ROOT / task)))
    test_patch = Path(row.get("test_patch_path", str(patch_dir / "test.patch")))
    gold_patch = Path(row.get("gold_patch_path", str(patch_dir / "gold.patch")))
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
    prompt = Path(row["issue_path"]).read_text(encoding="utf-8") if row.get("exact_issue_only") else Path(row["issue_path"]).read_text(encoding="utf-8") + "\n\nSolve this issue in the current repository. Investigate source and tests as needed, implement the smallest correct fix, and run relevant tests. Do not access git history, remotes, parent directories, benchmark/evaluator artifacts, or the network. Do not modify tests or unrelated files."
    env = _model_env(task, dependency, workspace)
    # Native runs must not inherit the desktop app's sessions, databases,
    # plugins, or user instructions. Project only the configured provider and
    # auth into a fresh home; credentials never enter telemetry or reports.
    # Keep the home path short: Codex may materialize bundled plugin assets
    # below CODEX_HOME, and Windows MAX_PATH otherwise masks provider/model
    # failures before the first request.
    CODEX_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    codex_home = CODEX_HOME_ROOT / f"r-{os.getpid()}-{task.split('__', 1)[0][:8]}-{model_name[0]}{index}"
    if codex_home.exists():
        shutil.rmtree(codex_home, ignore_errors=True)
    try:
        home_manifest = build_minimal_home(EXTERNAL_CODEX_HOME, codex_home)
    except Exception as error:
        record["classification"] = "ENVIRONMENT_INVALID"
        record["failure_mode"] = f"minimal CODEX_HOME: {error}"
        return record
    env["CODEX_HOME"] = str(codex_home)
    for key in ("CODEX_SESSION_ID", "CODEX_THREAD_ID", "CODEX_APP_SERVER", "CODEX_DESKTOP"):
        env.pop(key, None)
    record["codex"] = {"executable": str(_codex_executable()), "home": home_manifest}
    command = [str(_codex_executable()), "exec", "--ignore-rules", "--cd", str(workspace), "--model", "gpt-5.6-luna" if model_name == "luna" else "gpt-5.6-sol", "-c", "model_reasoning_effort=high", "--sandbox", "danger-full-access", "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust", "--json", "--ephemeral", "--output-last-message", str(final), "-"]
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
    stderr_lower = record["model_process"].get("stderr_tail", "").lower()
    if "usage limit" in stderr_lower or "hit your usage limit" in stderr_lower:
        record["model_process"]["failure_reason"] = "USAGE_LIMIT"
    elif "insufficient_balance" in stderr_lower or "insufficient account balance" in stderr_lower:
        # Provider/account state is not a model result. Keep this run out of
        # the capability funnel and make the environment blocker explicit.
        record["model_process"]["failure_reason"] = "PROVIDER_INSUFFICIENT_BALANCE"
    elif "503 service unavailable" in stderr_lower or "service temporarily unavailable" in stderr_lower:
        record["model_process"]["failure_reason"] = "PROVIDER_UNAVAILABLE"
    totals, timeline, actual_model = _parse_jsonl(telemetry)
    record["telemetry"] = {"model_reported": actual_model, "usage": totals, "model_calls": len(timeline), "peak_context": max((item["input_tokens"] for item in timeline), default=0), "timeline": timeline}
    diff, untracked = _model_patch(workspace, build["synthetic_commit"], model_patch)
    record["scope"] = _scope(_patch_paths(diff), (row.get("patch") or ""), untracked)
    if record["model_process"].get("failure_reason") in {"USAGE_LIMIT", "PROVIDER_INSUFFICIENT_BALANCE", "PROVIDER_UNAVAILABLE"}:
        reason = record["model_process"]["failure_reason"]
        record["evaluation"] = {"status": "NOT_RUN", "reason": "external provider unavailable before model attempt" if reason in {"PROVIDER_INSUFFICIENT_BALANCE", "PROVIDER_UNAVAILABLE"} else "Codex usage limit; no model attempt completed"}
        record["quality"] = "ENVIRONMENT_INVALID"
        record["failure_mode"] = reason.lower()
    elif process.returncode == 0 and model_patch.exists():
        patch_dir.mkdir(parents=True, exist_ok=True)
        with test_patch.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write((row.get("test_patch") or "").replace("\r\n", "\n"))
        with gold_patch.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write((row.get("patch") or "").replace("\r\n", "\n"))
        evaluator_report = _evaluate(row, workspace, evaluator, dependency, model_patch, test_patch, gold_patch, timeout=timeout)
        record["evaluation"] = evaluator_report
        record["quality"] = "PASS" if evaluator_report["model_pass"] and evaluator_report["no_edit_expected_fail"] and evaluator_report["gold_pass"] and record["scope"]["status"] == "PASS" else "FAIL"
    else:
        record["evaluation"] = {"status": "NOT_RUN", "reason": "model process failed or produced no patch"}
        record["quality"] = "FAIL"
    if record["quality"] == "PASS":
        record["failure_mode"] = None
    elif record["scope"]["status"] != "PASS":
        record["failure_mode"] = "scope_violation"
    elif record.get("model_process", {}).get("failure_reason"):
        record["failure_mode"] = record["model_process"]["failure_reason"].lower()
    else:
        record["failure_mode"] = "evaluator/model failure"
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-metadata", required=True, type=Path)
    parser.add_argument("--v2-metadata", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--only", action="append")
    parser.add_argument("--t4-metadata", type=Path)
    parser.add_argument("--t4-trusted-root", type=Path)
    parser.add_argument("--t4-issue-root", type=Path)
    parser.add_argument("--t4-patch-root", type=Path)
    parser.add_argument("--luna-runs", type=int, default=3)
    parser.add_argument("--sol-runs", type=int, default=3)
    parser.add_argument("--luna-start", type=int, default=1)
    parser.add_argument("--sol-start", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    # Use the already prepared trusted source and issue roots from readiness;
    # no evaluator material is placed beside a model workspace.
    if args.t4_metadata:
        trusted_root = (args.t4_trusted_root or READINESS_ROOT / "trusted-sources").resolve()
        issue_root = (args.t4_issue_root or READINESS_ROOT / "issues").resolve()
        patch_root = (args.t4_patch_root or READINESS_ROOT / "patches").resolve()
        rows = {}
        for item in json.loads(args.t4_metadata.read_text(encoding="utf-8")):
            task = item["instance_id"]
            source = trusted_root / (task if (trusted_root / task).exists() else item["repo"].split("/", 1)[1])
            rows[task] = {**item, "task": task, "dataset": "SWE-rebench-V2-Filtered-Verified",
                          "source": str(source), "issue_path": str(issue_root / f"{task}.md"),
                          "model_workspace": "", "evaluator_workspace": "", "dependency_reference": "",
                          "future_evaluator_path": "", "exact_issue_only": True,
                          "patch_dir": str(patch_root / task),
                          "test_patch_path": str(patch_root / f"{task}.test.patch"),
                          "gold_patch_path": str(patch_root / f"{task}.patch"),
                          "FAIL_TO_PASS": item.get("FAIL_TO_PASS", []), "PASS_TO_PASS": item.get("PASS_TO_PASS", [])}
        selected = tuple(args.only or rows.keys())
    else:
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
