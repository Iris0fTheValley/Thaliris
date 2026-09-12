from __future__ import annotations

import json
from pathlib import Path
import subprocess

from thaliris import codex_adapter, core


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    return tmp_path


def write_json(path: Path, value: object) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_execution_role_prepare_never_projects_task_memory_milestone_or_artifact(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task_input = write_json(root.parent / "input.json", {"records": [
        {"id": "fact", "kind": "fact", "text": "UNSELECTED_FACT"},
        {"id": "decision", "kind": "decision", "text": "OLD_DECISION"},
        {"id": "unknown", "kind": "unknown", "text": "OLD_UNKNOWN"},
        {"id": "review", "kind": "review", "text": "OLD_REVIEW"},
    ]})
    started = core.task_start(root, "explicit handoff only", "MILESTONE_TEXT", task_input)
    artifact = root / "artifact.md"
    artifact.write_text("ARTIFACT_PRIVATE_SENTINEL", encoding="utf-8")
    core.task_artifact(root, started["revision"], "details", "artifact.md", "details", producer_role="investigator")
    memory = root / ".agent-memory" / "private.md"
    memory.write_bytes(core._entry("Private", "MEMORY_TEXT", audience=["reviewer"], kind="record"))

    child_context = json.dumps(core.prepare(root, None, "reviewer"))
    assert "CONTROLLER_HANDOFF_ONLY" in child_context
    for forbidden in (
        "UNSELECTED_FACT", "OLD_DECISION", "OLD_UNKNOWN", "OLD_REVIEW",
        "MILESTONE_TEXT", "MEMORY_TEXT", "ARTIFACT_PRIVATE_SENTINEL",
    ):
        assert forbidden not in child_context


def test_artifact_freshness_is_observation_only(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "freshness", None, write_json(root.parent / "input.json", {
        "records": [{"id": "decision", "kind": "decision", "text": "keep model conclusion", "status": "accepted"}],
    }))
    artifact = root / "evidence.md"
    artifact.write_text("before", encoding="utf-8")
    registered = core.task_artifact(root, started["revision"], "evidence", "evidence.md", "evidence", producer_role="investigator")
    artifact.write_text("after", encoding="utf-8")

    status = core.task_status(root)
    assert status["Artifact Refs"][0]["freshness"] == "CHANGED"
    assert status["Records"][0]["text"] == "keep model conclusion"
    assert status["Records"][0]["status"] == "accepted"
    serialized = json.dumps(status)
    assert "REVALIDATION_REQUIRED" not in serialized and "STALE_PROVENANCE" not in serialized
    assert registered["revision"] == status["Task"]["revision"]


def test_verification_and_task_surface_are_observations_not_close_authority(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "completion belongs to Controller", None, None)
    changed = root / "unattributed.py"
    changed.write_text("changed", encoding="utf-8")
    observed = core.task_record_verification(
        root,
        started["revision"],
        "test-run",
        "test",
        "FAILED",
        "mechanical observation",
        observed_by="native-tool",
        source_paths=["unattributed.py"],
    )
    shown = core.task_show(root)
    assert shown["task_surface_delta"]["paths"] == ["unattributed.py"]
    assert shown["state"]["verification_results"][0]["outcome"] == "FAILED"

    closed = core.task_close(root, observed["revision"], expected_task_id=started["task_id"])
    assert closed["status"] == "DONE"


def test_promotion_stores_controller_selection_without_confidence_gate(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "promotion", None, None)
    promotion = write_json(root.parent / "promotion.json", {"records": [{
        "id": "selected",
        "kind": "decision",
        "title": "Selected record",
        "text": "MODEL_SELECTED_TEXT",
        "confidence": "WHATEVER_THE_MODEL_AUTHORED",
        "source_refs": [],
    }]})
    result = core.task_promote(root, "controller", started["revision"], promotion)
    assert result["promoted"] == [".agent-memory/promoted/selected.md"]

    candidates = core.recall(root, "MODEL_SELECTED_TEXT", "investigator")["candidates"]
    assert candidates[0]["path"] == ".agent-memory/promoted/selected.md"
    fetched = core.memory_get(root, candidates[0]["path"])
    assert "MODEL_SELECTED_TEXT" in fetched["body"]


def test_memory_audience_is_search_metadata_not_access_control(tmp_path: Path) -> None:
    root = repo(tmp_path)
    path = root / ".agent-memory" / "review-only.md"
    path.write_bytes(core._entry("Review hint", "EXPLICIT_MEMORY_SENTINEL", audience=["reviewer"], kind="record"))

    candidates = core.recall(root, "EXPLICIT_MEMORY_SENTINEL", "investigator")["candidates"]
    assert candidates and candidates[0]["audience"] == ["reviewer"]
    assert "body" not in candidates[0]
    assert "EXPLICIT_MEMORY_SENTINEL" in core.memory_get(root, candidates[0]["path"])["body"]

