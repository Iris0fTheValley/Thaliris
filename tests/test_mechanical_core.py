from __future__ import annotations

import json
import importlib.util
import hashlib
from pathlib import Path
import subprocess
import pytest

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

    shown = core.task_show(root)
    assert core._artifact_freshness(root, shown["state"]["artifact_refs"][0]) == "CHANGED"
    assert shown["state"]["records"][0]["text"] == "keep model conclusion"
    assert shown["state"]["records"][0]["status"] == "accepted"
    serialized = json.dumps(shown)
    assert "REVALIDATION_REQUIRED" not in serialized and "STALE_PROVENANCE" not in serialized
    assert registered["revision"] == shown["state"]["revision"]


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


def test_promoted_provenance_survives_task_state_and_round_trips(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "promotion provenance", None, write_json(root.parent / "sources.json", {
        "evidence_refs": [{
            "id": "source-1", "kind": "repository", "locator": "src/module.py#symbol", "summary": "source",
        }],
    }))
    artifact_path = root / "details.md"
    artifact_path.write_text("artifact details", encoding="utf-8")
    registered = core.task_artifact(
        root, started["revision"], "artifact-7", "details.md", "details",
        producer_role="investigator", evidence_refs=["source-1"],
    )
    promotion = write_json(root.parent / "durable.json", {"records": [{
        "id": "durable-decision",
        "kind": "decision",
        "title": "Durable decision",
        "text": "Keep this conclusion",
        "source_refs": ["artifact-7"],
        "status": "accepted",
        "confidence": "model-authored",
        "applicability": "project",
        "audience": ["controller", "reviewer"],
        "topics": ["routing"],
        "symbols": ["module.symbol"],
    }]})
    result = core.task_promote(root, "controller", registered["revision"], promotion)
    durable_path = result["promoted"][0]
    (root / ".context" / "state.json").unlink()

    fetched = core.memory_get(root, durable_path)
    assert fetched["metadata"]["Kind"] == "decision"
    assert fetched["metadata"]["Audience"] == ["controller", "reviewer"]
    assert "artifact-7" in fetched["body"]
    assert "details.md" in fetched["body"]
    assert hashlib.sha256(b"artifact details").hexdigest() in fetched["body"]
    assert started["task_id"] in fetched["body"]
    assert "source-1" in fetched["body"]
    assert "src/module.py#symbol" in fetched["body"]
    assert fetched["freshness"] == "FRESH"
    assert core.recall(root, "Durable decision", "controller")["candidates"][0]["path"] == durable_path
    artifact_path.write_text("changed artifact details", encoding="utf-8")
    assert core.memory_get(root, durable_path)["freshness"] == "CHANGED"


@pytest.mark.parametrize("field,value", [
    ("kind", "bad\nkind"),
    ("status", "bad\nstatus"),
    ("confidence", "bad\nconfidence"),
    ("applicability", "bad\napplicability"),
    ("audience", ["bad\naudience"]),
    ("topics", ["bad\ntopic"]),
    ("symbols", ["bad\nsymbol"]),
    ("title", "bad\ntitle"),
    ("kind", "x" * 129),
    ("audience", ["x" * 257]),
])
def test_invalid_promotion_metadata_is_rejected_without_writing(tmp_path: Path, field: str, value: object) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "invalid promotion", None, None)
    record = {"id": "invalid", "kind": "decision", "title": "Title", "text": "body", field: value}
    promotion = write_json(root.parent / "invalid.json", {"records": [record]})
    with pytest.raises(ValueError):
        core.task_promote(root, "controller", started["revision"], promotion)
    assert not (root / ".agent-memory" / "promoted" / "invalid.md").exists()


def test_memory_audience_is_search_metadata_not_access_control(tmp_path: Path) -> None:
    root = repo(tmp_path)
    path = root / ".agent-memory" / "review-only.md"
    path.write_bytes(core._entry("Review hint", "EXPLICIT_MEMORY_SENTINEL", audience=["reviewer"], kind="record"))

    candidates = core.recall(root, "EXPLICIT_MEMORY_SENTINEL", "investigator")["candidates"]
    assert candidates and candidates[0]["audience"] == ["reviewer"]
    assert "body" not in candidates[0]
    assert "EXPLICIT_MEMORY_SENTINEL" in core.memory_get(root, candidates[0]["path"])["body"]


def test_production_package_has_no_benchmark_authority_module() -> None:
    assert importlib.util.find_spec("thaliris.host_authority") is None
    assert importlib.util.find_spec("thaliris.protocol") is None
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(core.__file__).parent.glob("*.py")
    )
    for benchmark_only in ("D11", "formal authority registry", "receipt issuer"):
        assert benchmark_only not in production


def test_only_current_task_state_schema_is_accepted(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "current schema", None, None)
    path = root / ".context" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["schema_version"] -= 1
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid task state schema"):
        core.task_show(root)


def test_revision_cas_rejects_stale_writer_without_mutating_state(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "cas", None, None)
    update = write_json(root.parent / "update.json", {
        "records": [{"id": "r1", "kind": "note", "text": "first"}],
    })
    first = core.task_update(root, "controller", started["revision"], update)
    before = (root / ".context" / "state.json").read_bytes()

    try:
        core.task_update(root, "controller", started["revision"], update)
    except ValueError as exc:
        assert "revision conflict" in str(exc)
    else:
        raise AssertionError("stale CAS writer was accepted")

    assert (root / ".context" / "state.json").read_bytes() == before
    assert core.task_show(root)["state"]["revision"] == first["revision"]


def test_atomic_backup_and_rollback_restore_exact_bytes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    target = root / "tracked.txt"
    target.write_bytes(b"before\n")
    with core._lock(root):
        backup = core._apply_with_backup(root, {"tracked.txt": b"after\n"}, [], "test")
    assert target.read_bytes() == b"after\n"

    rolled_back = core.rollback(root, backup)
    assert rolled_back["ok"] is True
    assert target.read_bytes() == b"before\n"


def test_artifact_identity_provenance_supersession_and_history(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "artifacts", None, write_json(root.parent / "sources.json", {
        "evidence_refs": [{
            "id": "source-1", "kind": "repo", "locator": "src/example.py", "summary": "source",
        }],
    }))
    first_path = root / "first.md"
    first_path.write_text("first body", encoding="utf-8")
    first = core.task_artifact(
        root, started["revision"], "a1", "first.md", "first",
        producer_role="investigator", evidence_refs=["source-1"],
    )
    second_path = root / "second.md"
    second_path.write_text("second body", encoding="utf-8")
    second = core.task_artifact(
        root, first["revision"], "a2", "second.md", "replacement",
        producer_role="curator", supersedes=["a1"],
    )

    artifacts = core.task_show(root)["state"]["artifact_refs"]
    assert [item["id"] for item in artifacts] == ["a1", "a2"]
    assert artifacts[0]["content_sha256"] == hashlib.sha256(b"first body").hexdigest()
    assert artifacts[0]["producer"] == "investigator"
    assert artifacts[0]["source_refs"] == ["source-1"]
    assert artifacts[1]["supersedes"] == ["a1"]
    assert second["revision"] == first["revision"] + 1


def test_objective_freshness_reports_missing_without_semantic_mutation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "missing", None, write_json(root.parent / "state.json", {
        "records": [{"id": "d1", "kind": "decision", "text": "model keeps this", "status": "accepted"}],
    }))
    path = root / "disappears.md"
    path.write_text("present", encoding="utf-8")
    core.task_artifact(root, started["revision"], "gone", "disappears.md", "gone")
    path.unlink()

    shown = core.task_show(root)
    assert core._artifact_freshness(root, shown["state"]["artifact_refs"][0]) == "MISSING"
    assert shown["state"]["records"][0]["text"] == "model keeps this"
    assert shown["state"]["records"][0]["status"] == "accepted"
    assert shown["state"]["records"][0]["source_refs"] == []


def test_task_start_does_not_echo_initial_ledger(tmp_path: Path) -> None:
    root = repo(tmp_path)
    sentinel = "INITIAL_RECORD_BODY_MUST_NOT_ECHO"
    started = core.task_start(root, "start", None, write_json(root.parent / "initial.json", {
        "records": [{"id": "initial", "kind": "note", "text": sentinel}],
    }))
    assert "controller_packet" not in started
    assert sentinel not in json.dumps(started)
    assert {"task_id", "revision", "status"} <= set(started)


def test_routing_state_has_one_small_total_byte_budget(tmp_path: Path) -> None:
    root = repo(tmp_path)
    concise = write_json(root.parent / "concise.json", {
        "active_work": ["implement bounded status"],
        "pending_results": ["targeted tests"],
    })
    started = core.task_start(root, "routing budget", None, concise)
    assert core.task_status(root)["Active Work"] == ["implement bounded status"]

    oversized = write_json(root.parent / "oversized.json", {
        "active_work": ["a" * 4096, "b" * 4096],
        "pending_results": ["c"],
    })
    with pytest.raises(ValueError, match="store long content as a Record or Artifact"):
        core.task_update(root, "controller", started["revision"], oversized)
    assert core.task_show(root)["state"]["revision"] == started["revision"]

    second_root = repo(tmp_path / "second")
    with pytest.raises(ValueError, match="store long content as a Record or Artifact"):
        core.task_start(second_root, "oversized start", None, oversized)
    assert not (second_root / ".context" / "state.json").exists()


def test_large_task_status_is_bounded_while_task_show_retains_full_ledger(tmp_path: Path) -> None:
    root = repo(tmp_path)
    body = "HISTORICAL_RECORD_BODY_" + "x" * 256
    started = core.task_start(root, "bounded status", None, write_json(root.parent / "large.json", {
        "active_work": ["bounded current work"],
        "pending_results": ["one concise pending result"],
        "records": [
            {"id": f"record-{index}", "kind": "note", "text": f"{body}{index}"}
            for index in range(500)
        ],
    }))
    with core._lock(root):
        state = core._load_state(root, active=True)
        for index in range(200):
            artifact_path = root / f"artifact-{index}.md"
            artifact_path.write_text(f"ARTIFACT_BODY_{index}", encoding="utf-8")
            state["artifact_refs"].append({
                "id": f"artifact-{index}",
                "path": f"artifact-{index}.md",
                "summary": f"summary {index}",
                "producer": "investigator",
                "registered_by": "controller",
                "source_refs": [],
                "supersedes": [],
                "task_id": state["task_id"],
                "revision": started["revision"],
                "content_sha256": hashlib.sha256(f"ARTIFACT_BODY_{index}".encode()).hexdigest(),
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            material = {
                "id": f"verification-{index}",
                "kind": "test",
                "outcome": "PASSED",
                "summary": f"VERIFICATION_BODY_{index}",
                "observed_by": "native-tool",
                "candidate_identity": "a" * 64,
                "observed_files": [],
            }
            state["verification_results"].append({
                **material,
                "observed_at": "2026-01-01T00:00:00+00:00",
                "observed_at_revision": started["revision"],
                "result_hash": hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest(),
            })
        core._write_state(root, state)

    status = core.task_status(root)
    serialized = json.dumps(status)
    assert status["Counts"] == {
        "records": 500, "sources": 0, "artifacts": 200, "verification_observations": 200,
    }
    assert len(status["Recent Artifact IDs"]) == 8
    assert len(serialized.encode()) < 8 * 1024
    for forbidden in ("HISTORICAL_RECORD_BODY", "ARTIFACT_BODY", "VERIFICATION_BODY", "Task Surface"):
        assert forbidden not in serialized

    shown = core.task_show(root)
    assert len(shown["state"]["records"]) == 500
    assert len(shown["state"]["artifact_refs"]) == 200
    assert len(shown["state"]["verification_results"]) == 200
    assert "HISTORICAL_RECORD_BODY" in json.dumps(shown)
