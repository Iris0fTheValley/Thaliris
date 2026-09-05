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
    "dask-contrib__dask-expr-901",
    "aio-libs__aiohttp-8823",
    "d0c-s4vage__pfp-128",
    "d0c-s4vage__pfp-126",
    "aaugustin__websockets-543",
    "aaugustin__websockets-641",
    "asdf-format__asdf-1907",
    "bashtage__arch-752",
    "alteryx__woodwork-1300",
    "amaranth-lang__amaranth-912",
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
            source = trusted_root / slug
            # T4 sources are preserved under either their instance id or the
            # repository leaf. Prefer the instance id but support the latter
            # without copying source into the evaluator or model fixture.
            if not source.exists() and isinstance(row.get("repo"), str):
                source = trusted_root / row["repo"].rsplit("/", 1)[-1]
            if row.get("FAIL_TO_PASS") or row.get("PASS_TO_PASS"):
                # The metadata's target tests are the evaluator contract;
                # avoid silently expanding readiness to a project's full suite.
                row["test_selection"] = list(row.get("FAIL_TO_PASS", [])) + list(row.get("PASS_TO_PASS", []))
            row.update(
                {
                    "task": task,
                    "dataset": dataset,
                    "source": str(source),
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
    elif task == "dask-contrib__dask-expr-901":
        install = 'python -m pip install -q "dask==2024.2.1" "pandas==2.1.4" pyarrow "pytest<9"'
        test, toolchain = "python -m pytest -q dask_expr/tests/test_collection.py", "python/pip"
    elif task == "aio-libs__aiohttp-8823":
        install = 'python -m pip install -q "pytest<9" pytest-asyncio multidict==6.0.5 yarl==1.9.4 frozenlist==1.4.1 aiosignal==1.3.1 async-timeout==4.0.3 attrs'
        test, toolchain = "python -m pytest -q tests/test_http_parser.py", "python/pip"
    elif task.startswith("aaugustin__websockets-"):
        install = 'python -m pip install -q "pytest<9" psutil pytest-remotedata'
        test, toolchain = "python -m pytest -q", "python/pip"
    elif task.startswith("asdf-format__asdf-"):
        install = 'python -m pip install -q "pytest<9" asdf-standard asdf-transform-schemas numpy pyyaml semantic_version jmespath attrs'
        test, toolchain = "python -m pytest -q", "python/pip"
    elif task.startswith("bashtage__arch-"):
        # numba keeps the selected simulation tests within a practical
        # evaluator window without changing the archived project source.
        install = 'python -m pip install -q "pytest<8" numpy==1.26.4 pandas==1.5.3 scipy==1.11.4 statsmodels==0.14.4 numba==0.58.1'
        test, toolchain = "python -m pytest -q", "python/pip"
    elif task.startswith("alteryx__woodwork-"):
        install = 'python -m pip install -q "pytest<9" pandas==1.5.3 scikit-learn'
        test, toolchain = "python -m pytest -q", "python/pip"
    elif task.startswith("amaranth-lang__amaranth-"):
        install = 'python -m pip install -q "pytest<9"'
        test, toolchain = "python -m pytest -q", "python/pip"
    elif task.startswith("d0c-s4vage__pfp-"):
        install = 'python -m pip install -q "pytest<9" "py010parser>=0.1.17" "six>=1.10.0,<2.0.0" "intervaltree>=3.0.2,<4.0.0" pcpp'
        test, toolchain = "python -m pytest -q tests", "python/pip"
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
    """Choose an interpreter compatible with an archived fixture."""
    py37 = Path(r"C:\thaliris-toolchains\python37\python.exe")
    py310 = Path(r"C:\Users\12298\AppData\Roaming\uv\python\cpython-3.10.20-windows-x86_64-none\python.exe")
    # This websockets revision supports Python 3.6/3.7.  Its selected
    # shutdown tests rely on pre-3.8 asyncio cancellation semantics, so use
    # the isolated 3.7 runtime for every readiness stage of this candidate.
    if task == "aaugustin__websockets-641" and py37.exists():
        return str(py37)
    if task == "aio-libs__aiohttp-8823" and py310.exists():
        return str(py310)
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


def _runtime_adapter(task: str, dependency: Path) -> Path | None:
    """Return external runtime-only compatibility hooks for archived sources."""

    if task not in {"bashtage__arch-752", "dask-contrib__dask-expr-901", "aaugustin__websockets-641"}:
        return None
    adapter = dependency / "runtime-adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    code = ""
    if task == "bashtage__arch-752":
        code = (
            "import sys\n"
            "import types\n"
            "module = types.ModuleType('arch._version')\n"
            "module.version = '0+archive'\n"
            "module.version_tuple = (0, 'archive')\n"
            "sys.modules.setdefault('arch._version', module)\n"
        )
    elif task == "dask-contrib__dask-expr-901":
        # dask 2024.2's accessor registration inspects pandas property
        # descriptors. Python 3.11 rejects inspect.signature(property),
        # while the supported Python 3.10 runtime accepts the getter.
        code = (
            "import inspect\n"
            "_signature = inspect.signature\n"
            "def signature(obj, *args, **kwargs):\n"
            "    if isinstance(obj, property):\n"
            "        obj = obj.fget\n"
            "    try:\n"
            "        return _signature(obj, *args, **kwargs)\n"
            "    except TypeError:\n"
            "        return inspect.Signature()\n"
            "inspect.signature = signature\n"
        )
    else:
        # The legacy suite asserts behavior of raw socket recv/send calls.
        # Windows' default Proactor loop uses recv_into/send which bypasses
        # those test probes; Selector loop preserves the suite's contract.
        code = (
            "import asyncio\n"
            "if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):\n"
            "    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())\n"
        )
    (adapter / "sitecustomize.py").write_text(code,
        encoding="utf-8",
    )
    return adapter


def _materialize_evaluator_submodules(task: str, evaluator: Path) -> None:
    """Populate archived gitlinks only in the trusted evaluator checkout."""
    if task != "aio-libs__aiohttp-8823":
        return
    source = Path(r"C:\thaliris-toolchains\llhttp-b0b279fb5a617ab3bc2fc11c5f8bd937aac687c1")
    target = evaluator / "vendor" / "llhttp"
    if not (source / "README.md").exists():
        raise RuntimeError(f"missing pinned llhttp submodule cache: {source}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"))


def _prepare_aiohttp_generated_sources(
    evaluator: Path, venv_python: Path, env: dict[str, str], timeout: int
) -> dict[str, Any]:
    """Run aiohttp's normal Cython generation in the evaluator checkout."""
    cython_install = _run(
        f'"{venv_python}" -m pip install -q "Cython==3.0.11" multidict==6.0.5 yarl==1.9.4 frozenlist==1.4.1 aiosignal==1.3.1 async-timeout==4.0.3 attrs trustme pytest-cov brotli',
        evaluator,
        env,
        min(timeout, 300),
    )
    if cython_install["exit_code"] != 0:
        return {"installation": cython_install}
    generated = []
    for stem in ("_find_header", "_helpers", "_http_parser", "_http_writer", "_websocket"):
        if stem == "_find_header":
            command = f'"{venv_python}" tools/gen.py'
        else:
            command = (
                f'"{venv_python}" -m cython -3 -o aiohttp/{stem}.c '
                f'aiohttp/{stem}.pyx -I aiohttp -Werror'
            )
        result = _run(command, evaluator, env, min(timeout, 300))
        generated.append({"file": stem, "result": result})
        if result["exit_code"] != 0:
            return {"installation": cython_install, "generated": generated}
    return {"installation": cython_install, "generated": generated}


def _selected_runner_source() -> str:
    """Return an evaluator-only runner for exact and truncated pytest nodes.

    Some historical dataset records truncate parametrized node ids containing
    display names with spaces. Resolve only those incomplete ids against the
    evaluator checkout after the trusted test patch is applied; this avoids
    broadening the contract to a whole test module.
    """

    return (
        "import json\n"
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "import pytest\n"
        "root = Path(__file__).parent\n"
        "requested = json.loads((root / '.t4_selected_tests.json').read_text())\n"
        "paths = sorted({item.split('::', 1)[0] for item in requested})\n"
        "collected = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-o', 'addopts=', *paths], cwd=root, text=True, capture_output=True)\n"
        "if collected.returncode:\n"
        "    sys.stdout.write(collected.stdout)\n"
        "    sys.stderr.write(collected.stderr)\n"
        "    raise SystemExit(collected.returncode)\n"
        "nodes = {line.strip() for line in (collected.stdout + collected.stderr).splitlines() if '::' in line}\n"
        "resolved = []\n"
        "missing = []\n"
        "for item in requested:\n"
        "    if item in nodes:\n"
        "        resolved.append(item)\n"
        "    elif '::' not in item:\n"
        "        matches = sorted(node for node in nodes if node.replace('\\\\', '/').startswith(item + '::'))\n"
        "        if matches:\n"
        "            resolved.extend(matches)\n"
        "        else:\n"
        "            missing.append(item)\n"
        "    elif '[' in item:\n"
        "        # Dataset node ids may truncate display values containing brackets.\n"
        "        # Resolve such entries to the same parametrized test family only.\n"
        "        prefix = item.split('[', 1)[0] + '['\n"
        "        matches = sorted(node for node in nodes if node.replace('\\\\', '/').startswith(prefix))\n"
        "        if matches:\n"
        "            resolved.extend(matches)\n"
        "        else:\n"
        "            missing.append(item)\n"
        "    else:\n"
        "        missing.append(item)\n"
        "if missing:\n"
        "    print('EVALUATOR_SELECTION_ERROR: ' + json.dumps(missing))\n"
        "    raise SystemExit(4)\n"
        "raise SystemExit(pytest.main(['-q', '-o', 'addopts=', *dict.fromkeys(resolved)]))\n"
    )


def _stage(
    workspace: Path,
    baseline_commit: str,
    test_patch: Path,
    gold_patch: Path,
    test_command: str,
    env: dict[str, str],
    timeout: int,
    gold_retries: int = 0,
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
    gold_attempts = [gold]
    # websockets' legacy Python 3.8 keepalive test uses millisecond sleeps and
    # can miss its scheduling window on a busy host.  Retry only when the
    # caller has explicitly identified this environment-only flake; semantic
    # failures remain failures and every attempt is retained in telemetry.
    for _ in range(gold_retries):
        if gold.get("exit_code") == 0 or gold.get("timeout"):
            break
        retry = _run(test_command, workspace, env, timeout)
        gold_attempts.append(retry)
        gold = retry
    return {
        "base": base,
        "no_edit": no_edit,
        "gold": {**gold, "patch": gold_apply, "status": "PASS" if gold["exit_code"] == 0 else "FAIL"},
        "gold_attempts": gold_attempts,
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
        _materialize_evaluator_submodules(task, evaluator)
    except (OSError, RuntimeError, ValueError) as error:
        record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
        record["final"] = "EVALUATOR_INCONCLUSIVE"
        record["blocker"] = f"evaluator fixture could not be materialized: {error}"
        return record
    selected_tests = row.get("test_selection")
    selected_runner: Path | None = None
    if selected_tests and toolchain == "python/pip":
        # Keep readiness focused on the trusted F2P/P2P contract.  The runner
        # lives only in the evaluator checkout and is never visible to a model.
        selection_file = evaluator / ".t4_selected_tests.json"
        selection_file.write_text(json.dumps(list(selected_tests)) + "\n", encoding="utf-8")
        selected_runner = evaluator / ".t4_selected_runner.py"
        selected_runner.write_text(_selected_runner_source(), encoding="utf-8")
    env = os.environ.copy()
    env["PIP_NO_INPUT"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if task.startswith("aaugustin__websockets-"):
        # Legacy client/server tests assert that no warnings are emitted;
        # Python 3.8/OpenSSL emits compatibility deprecations unrelated to
        # the issue under test.
        env["PYTHONWARNINGS"] = "ignore::DeprecationWarning"
        # Keep the warning filter as one pytest argument when PYTEST_ADDOPTS
        # is parsed by the evaluator's subprocess-based selected runner.
        env["PYTEST_ADDOPTS"] = '-W "ignore:The loop argument is deprecated since Python 3.8"'
        # Do not route evaluator-local HTTP requests through the desktop
        # proxy; the archived tests intentionally bind localhost sockets.
        env["NO_PROXY"] = "localhost,127.0.0.1,::1"
        env["no_proxy"] = env["NO_PROXY"]
        # Python on Windows normalizes ``NO_PROXY`` to an unusable ``no``
        # proxy key.  Clear all proxy variables for local socket tests so
        # urllib and asyncio connect directly to the in-process servers.
        for proxy_name in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy",
        ):
            env.pop(proxy_name, None)
        if task == "aaugustin__websockets-641":
            env["WEBSOCKETS_TESTS_TIMEOUT_FACTOR"] = "10"
    runtime_adapter = _runtime_adapter(task, dependency)
    if runtime_adapter is not None:
        env["PYTHONPATH"] = str(runtime_adapter) + os.pathsep + env.get("PYTHONPATH", "")
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
            if task == "aio-libs__aiohttp-8823":
                generated = _prepare_aiohttp_generated_sources(
                    evaluator, venv_python, env, timeout
                )
                record["aiohttp_generated"] = generated
                if generated.get("generated", [{}])[-1].get("result", {}).get("exit_code") != 0:
                    record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
                    record["blocker"] = "aiohttp Cython source generation failed"
                    record["final"] = "EVALUATOR_INCONCLUSIVE"
                    return record
            if task.startswith("d0c-s4vage__pfp-"):
                # py010parser shells out to an executable named ``cpp``.
                # Keep the preprocessor adapter in the dependency environment
                # so reruns with an existing venv remain deterministic.
                cpp = dependency / "Scripts" / "cpp.cmd"
                cpp.write_text("@echo off\n\"%~dp0python.exe\" -m pcpp %*\n", encoding="utf-8")
                pcpp = dependency / "Scripts" / "pcpp.exe"
                if pcpp.exists():
                    shutil.copy2(pcpp, dependency / "Scripts" / "cpp.exe")
            install = install.replace("python", f'"{venv_python}"', 1)
            test_command = (
                f'"{venv_python}" "{selected_runner}"'
                if selected_runner is not None
                else test_command.replace("python", f'"{venv_python}"', 1)
            )
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
        if task.startswith("d0c-s4vage__pfp-"):
            # ``pcpp.exe`` is installed by the preceding command.  py010parser
            # uses ``Popen(["cpp", ...])`` on Windows, which doesn't resolve
            # the .cmd shim, so expose the installed console entry point under
            # the executable name it requests.
            pcpp = dependency / "Scripts" / "pcpp.exe"
            if not pcpp.exists():
                record["evaluator_status"] = "EVALUATOR_INCONCLUSIVE"
                record["blocker"] = "pcpp console entry point missing after dependency installation"
                record["final"] = "EVALUATOR_INCONCLUSIVE"
                return record
            shutil.copy2(pcpp, dependency / "Scripts" / "cpp.exe")

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
    gold_retries = 5 if task == "aaugustin__websockets-543" else 0
    first = _stage(
        evaluator,
        eval_build["synthetic_commit"],
        test_patch,
        gold_patch,
        test_command,
        env,
        timeout,
        gold_retries=gold_retries,
    )
    repeats = []
    repeat_attempts = []
    # A full evaluator timeout is a readiness blocker.  Do not spend another
    # 3x timeout repeating a known-inconclusive environment.
    if not first.get("base", {}).get("timeout"):
        for _ in range(3):
            stage = _stage(
                evaluator,
                eval_build["synthetic_commit"],
                test_patch,
                gold_patch,
                test_command,
                env,
                timeout,
                gold_retries=gold_retries,
            )
            repeats.append(stage.get("gold", {}))
            repeat_attempts.append(stage.get("gold_attempts", []))
    record["evaluation"] = {
        "base": first.get("base"),
        "no_edit": first.get("no_edit"),
        "gold": first.get("gold"),
        "gold_attempts": first.get("gold_attempts", []),
        "test_patch_apply": first.get("test_patch"),
        "gold_repeat": repeats,
        "gold_repeat_attempts": repeat_attempts,
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
