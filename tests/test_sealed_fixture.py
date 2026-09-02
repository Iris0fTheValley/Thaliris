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
from prepare_benchmark_codex_home import build_minimal_home  # noqa: E402


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


def test_minimal_codex_home_projects_provider_without_history(tmp_path: Path) -> None:
    source = tmp_path / "source-codex"
    source.mkdir()
    (source / "config.toml").write_text(
        "model_provider = \"custom\"\nmodel = \"gpt-5.6-sol\"\nmodel_reasoning_effort = \"high\"\n"
        "[model_providers.custom]\nname = \"external\"\nbase_url = \"https://example.invalid\"\n"
        "wire_api = \"responses\"\nrequires_openai_auth = true\n"
        "[projects.'c:\\\\machine']\ntrust_level = \"trusted\"\n",
        encoding="utf-8",
    )
    (source / "auth.json").write_text('{"OPENAI_API_KEY":"test-secret"}\n', encoding="utf-8")
    (source / "sessions").mkdir()
    (source / "sessions" / "old.jsonl").write_text("old session\n", encoding="utf-8")
    agents = tmp_path / "AGENTS.md"
    agents.write_text("global benchmark policy\n", encoding="utf-8")

    destination = tmp_path / "fresh-codex"
    result = build_minimal_home(source, destination, global_agents=agents)

    assert result["auth_projected"] is True
    assert result["global_agents_projected"] is True
    assert not (destination / "sessions").exists()
    assert not (destination / "plugins").exists()
    assert (destination / "auth.json").read_text(encoding="utf-8") == (source / "auth.json").read_text(encoding="utf-8")
    config = (destination / "config.toml").read_text(encoding="utf-8")
    assert "base_url" in config and "[projects" not in config
