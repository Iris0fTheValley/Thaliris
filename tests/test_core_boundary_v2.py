from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from thaliris import core
from thaliris import codex_adapter
from thaliris.intent_audit import handle_hook


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def completed_child(root: Path) -> None:
    assert handle_hook(root, "PreToolUse", {"session_id": "boundary", "turn_id": "boundary", "tool_name": "spawn_agent", "tool_input": {"fork_turns": "none", "agent_type": "worker"}}) == ""
    assert handle_hook(root, "SubagentStart", {"session_id": "boundary", "turn_id": "boundary", "agent_id": "child", "agent_type": "worker"})
    assert handle_hook(root, "SubagentStop", {"session_id": "boundary", "turn_id": "boundary", "agent_id": "child"}) == ""


def test_core_has_no_codex_adapter_import() -> None:
    source = Path(core.__file__).read_text(encoding="utf-8")
    assert "from .intent_audit" not in source
    assert "import codex_adapter" not in source


def test_core_close_checks_expected_task_identity(tmp_path: Path) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    started = core.task_start(root, "cas", None, None)
    with pytest.raises(ValueError, match="task revision conflict"):
        core.task_close(root, started["revision"], expected_task_id="00000000-0000-0000-0000-000000000000")
    assert json.loads((root / ".context/state.json").read_text(encoding="utf-8"))["status"] == "ACTIVE"


def test_codex_init_is_one_backup_for_core_and_adapter(tmp_path: Path) -> None:
    root = repo(tmp_path)
    result = codex_adapter.init(root)
    assert result["ok"] and len(list((root / ".context/backups").glob("*.json"))) == 1


def test_codex_uninstall_is_one_backup_for_core_and_adapter(tmp_path: Path) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    result = codex_adapter.uninstall(root)
    assert result["ok"] and len(list((root / ".context/backups").glob("*.json"))) == 2


def test_adapter_close_rejects_task_identity_change_during_audit(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    started = codex_adapter.task_start(root, "race", None, None)
    completed_child(root)

    def audit_with_task_switch(*_args, **_kwargs):
        state = json.loads((root / ".context/state.json").read_text(encoding="utf-8"))
        state["task_id"] = "00000000-0000-0000-0000-000000000001"
        state["revision"] = 1
        (root / ".context/state.json").write_text(json.dumps(state), encoding="utf-8")
        return {"status": "UNKNOWN"}

    monkeypatch.setattr(codex_adapter, "task_close_audit", audit_with_task_switch)
    with pytest.raises(ValueError, match="task revision conflict"):
        codex_adapter.task_close(root, started["revision"])


def test_adapter_close_does_not_treat_model_test_report_as_execution_result(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    source = root / "subject.py"
    source.write_text("subject", encoding="utf-8")
    start_input = tmp_path.parent / "adapter-start.json"
    start_input.write_text(json.dumps({
        "changed_surface": ["subject.py"],
        "verification_target": {"description": "run subject tests", "artifact_refs": [], "changed_surface": ["subject.py"]},
    }), encoding="utf-8")
    started = codex_adapter.task_start(root, "verification", None, str(start_input))
    completed_child(root)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    fake_input = tmp_path.parent / "adapter-fake.json"
    fake_input.write_text(json.dumps({"evidence_refs": [
        {"id": "src", "kind": "file", "locator": f"file:subject.py#{digest}", "summary": "source", "confidence": "SUPPORTED"},
        {"id": "fake", "kind": "test", "locator": "pytest -q", "summary": "passed", "confidence": "SUPPORTED", "source_refs": ["src"]},
    ]}), encoding="utf-8")
    configured = core.task_update(root, "controller", started["revision"], str(fake_input))
    monkeypatch.setattr(codex_adapter, "task_close_audit", lambda *_args, **_kwargs: {"status": "UNKNOWN"})
    with pytest.raises(ValueError, match="trusted successful verification result"):
        codex_adapter.task_close(root, configured["revision"])


def test_child_bootstrap_loads_projection_inside_child_boundary(tmp_path: Path) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    codex_adapter.task_start(root, "child ingress", None, None)
    instruction = codex_adapter.child_bootstrap("terra-implementer")
    assert "context prepare --role implementer" in instruction
    pack = codex_adapter.prepare_child(root, "terra-implementer")
    assert pack["role"] == "implementer"
    assert "Investigation Snapshot" not in json.dumps(pack)


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    source = str(Path(__file__).parents[1] / "src")
    environment = os.environ | {"PYTHONPATH": source + os.pathsep + os.environ.get("PYTHONPATH", "")}
    return subprocess.run(
        [sys.executable, "-m", "thaliris.cli", "--root", str(root), *args],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_child_bootstrap_semantic_command_passes_real_cli_parser(tmp_path: Path) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    codex_adapter.task_start(root, "child ingress", None, None)

    implementer_instruction = codex_adapter.child_bootstrap("terra-implementer")
    assert "context prepare --role implementer" in implementer_instruction
    semantic = _cli(root, "prepare", "--role", "implementer")
    assert semantic.returncode == 0
    assert json.loads(semantic.stdout)["role"] == "implementer"

    alias = _cli(root, "prepare", "--role", "terra-implementer")
    assert alias.returncode == 0
    assert json.loads(alias.stdout)["role"] == "implementer"

    specialist_instruction = codex_adapter.child_bootstrap("sol-high")
    assert "context prepare --role reasoning-specialist" in specialist_instruction
    specialist = _cli(root, "prepare", "--role", "reasoning-specialist")
    assert specialist.returncode == 0
    assert json.loads(specialist.stdout)["role"] == "reasoning-specialist"


def test_cli_normalizes_role_inputs_for_updates_artifacts_and_promotion(tmp_path: Path) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    codex_adapter.task_start(root, "role ingress", None, None)
    update_input = root / "update.json"
    update_input.write_text(json.dumps({"investigation_findings": [{"kind": "UNKNOWN", "text": "inspect", "evidence_refs": []}]}), encoding="utf-8")
    update = _cli(root, "task-update", "--role", "investigator", "--base-revision", "1", "--input", str(update_input))
    assert update.returncode == 0 and json.loads(update.stdout)["revision"] == 2

    (root / "notes.md").write_text("bounded", encoding="utf-8")
    artifact = _cli(root, "task-artifact", "--base-revision", "2", "--id", "notes", "--path", "notes.md", "--summary", "bounded", "--producer-role", "terra-implementer")
    assert artifact.returncode == 0
    assert core.task_show(root)["state"]["artifact_refs"][0]["producer_role"] == "implementer"

    promotion_input = root / "promotion.json"
    promotion_input.write_text(json.dumps({"records": []}), encoding="utf-8")
    denied = _cli(root, "task-promote", "--role", "terra-implementer", "--base-revision", "3", "--input", str(promotion_input))
    assert denied.returncode == 2
    assert "only the Controller" in json.loads(denied.stdout)["error"]
