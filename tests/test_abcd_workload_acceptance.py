from __future__ import annotations

import json
import subprocess
from pathlib import Path

from thaliris import doctor
from thaliris.cli import main
from thaliris.intent_audit import _delegation_input, _pre_tool_output


def _run(capsys, root, *args):
    assert main(["--root", str(root), *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_abcd_t1_exact_version(capsys):
    assert main(["version"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "version": "0.3.0"}


def test_abcd_t2_bounded_artifact_pointer(tmp_path, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "bench@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Bench"], cwd=root, check=True)
    _run(capsys, root, "init")
    _run(capsys, root, "task-start", "bounded status regression")
    artifact = root / "evidence.txt"
    artifact.write_text("fresh evidence\n", encoding="utf-8")
    _run(capsys, root, "task-artifact", "--base-revision", "1", "--id", "e1", "--path", "evidence.txt", "--summary", "focused evidence")
    packet = _run(capsys, root, "task-status")
    assert packet["Artifact Refs"] == [{"id": "e1", "path": "evidence.txt", "summary": "focused evidence"}]
    assert "evidence_refs" not in packet
    assert "investigation_findings" not in packet


def test_abcd_t3_real_flattened_spawn_requires_explicit_isolation():
    output = json.loads(_pre_tool_output({
        "tool_name": "collaborationspawn_agent",
        "tool_input": {"fork_turns": "all", "message": "inspect the bounded issue"},
    }))
    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"].startswith("THALIRIS_ISOLATION_REQUIRED:")
    assert "updatedInput" not in decision


def test_abcd_t3_legacy_input_payload_is_read():
    value = _delegation_input({"input": {"message": "legacy investigation", "id": "child-1"}})
    assert value["message"] == "legacy investigation"


def test_abcd_t3_doctor_does_not_infer_hook_support(tmp_path):
    hooks = tmp_path / ".codex"
    hooks.mkdir()
    (hooks / "hooks.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"hooks": [{"type": "command", "command": "context audit-hook PreToolUse"}]}],
        "PostToolUse": [{"hooks": [{"type": "command", "command": "context audit-hook PostToolUse"}]}],
    }}), encoding="utf-8")
    observed = doctor._context_isolation(tmp_path)["observed"]
    assert all(value == "UNKNOWN" for value in observed.values())


def test_abcd_result_ledger_has_complete_matrix():
    ledger = json.loads((Path(__file__).parents[1] / "benchmarks" / "abcd" / "results.json").read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in ledger["runs"]}
    assert ids == {f"{workflow}_T{workload}" for workflow in "ABCD" for workload in range(1, 4)}
    assert ledger["derived"]["total_compute_ratio"]["ratio"] > 1
    assert ledger["verdict"]["architecture_isolation"] == "SUPPORTED"
