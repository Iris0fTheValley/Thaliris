"""Acceptance tests for the benchmark-only sealed fixture harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


BENCHMARK_TOOLS = Path(__file__).parents[1] / "benchmarks" / "abcd"
sys.path.insert(0, str(BENCHMARK_TOOLS))

from build_sealed_fixture import build_fixture  # noqa: E402
from validate_sealed_fixture import validate_fixture  # noqa: E402


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


@pytest.fixture
def source_repo(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "trusted-source"
    source.mkdir()
    _git(source, "init", "--quiet")
    _git(source, "config", "user.name", "fixture-test")
    _git(source, "config", "user.email", "fixture-test@invalid.local")
    (source / "README.md").write_text("sealed fixture test\n", encoding="utf-8")
    _git(source, "add", "--all", "--force")
    _git(source, "commit", "--quiet", "-m", "base")
    revision = _git(source, "rev-parse", "HEAD")
    return source, revision


def test_builder_and_gate_round_trip(source_repo: tuple[Path, str], tmp_path: Path) -> None:
    source, revision = source_repo
    issue = tmp_path / "issue.md"
    issue.write_text("public issue only\n", encoding="utf-8")
    dependency = tmp_path / "venv"
    dependency.mkdir()
    run_root = tmp_path / "sealed-run"
    workspace = run_root / "workspace"
    result = build_fixture(
        source=source,
        revision=revision,
        issue_text=issue,
        dependency_reference=str(dependency),
        workspace=workspace,
        report=tmp_path / "build-report.json",
    )
    assert result["source_tree"] == result["synthetic_tree"]

    gate = validate_fixture(
        workspace=workspace,
        source=source,
        revision=revision,
        dependency_reference=str(dependency),
        baseline_status="PASS",
        known_gold_commit="f" * 40,
        scan_root=run_root,
        forbidden_roots=[],
        evaluator_path=run_root / "evaluator",
        max_scan_files=100,
    )
    assert gate["status"] == "SEALED_PASS"


def test_gate_fails_for_parent_side_channel(source_repo: tuple[Path, str], tmp_path: Path) -> None:
    source, revision = source_repo
    issue = tmp_path / "issue.md"
    issue.write_text("public issue only\n", encoding="utf-8")
    dependency = tmp_path / "venv"
    dependency.mkdir()
    run_root = tmp_path / "sealed-run"
    workspace = run_root / "workspace"
    build_fixture(
        source=source,
        revision=revision,
        issue_text=issue,
        dependency_reference=str(dependency),
        workspace=workspace,
        report=None,
    )
    (run_root / "test.patch").write_text("not visible to a sealed model\n", encoding="utf-8")
    gate = validate_fixture(
        workspace=workspace,
        source=source,
        revision=revision,
        dependency_reference=str(dependency),
        baseline_status="PASS",
        known_gold_commit="f" * 40,
        scan_root=run_root,
        forbidden_roots=[],
        evaluator_path=run_root / "evaluator",
        max_scan_files=100,
    )
    assert gate["status"] == "FIXTURE_NOT_SEALED"
    assert gate["checks"]["filesystem_parent_traversal"]["status"] == "FAIL"
