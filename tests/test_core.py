from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from thaliris import core
from thaliris.cli import main
from thaliris.markdown import parse


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def input_file(root: Path, payload: dict[str, object], name: str = "input.json") -> str:
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_core_roles_are_semantic() -> None:
    assert core._PACK_ROLES == {"controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer"}


def test_controller_packet_is_bounded(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert main(["--root", str(root), "init"]) == 0
    assert main(["--root", str(root), "task-start", "bounded task"]) == 0
    packet = core.task_status(root)
    encoded = json.dumps(packet)
    assert "Investigation Findings" not in encoded
    assert "Evidence refs" not in encoded
    assert "Artifact Refs" in packet


def test_artifact_registration_is_explicit_and_missing_is_loadable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    main(["--root", str(root), "init"])
    main(["--root", str(root), "task-start", "artifact"])
    artifact = root / "notes.md"
    artifact.write_text("large notes\n", encoding="utf-8")
    assert core.task_artifact(root, 1, "notes", "notes.md", "bounded notes")["revision"] == 2
    artifact.unlink()
    assert core.task_status(root)["Task"]["revision"] == 2


def test_close_checks_task_identity_and_revision(tmp_path: Path) -> None:
    root = repo(tmp_path)
    main(["--root", str(root), "init"])
    started = core.task_start(root, "cas", None, None)
    with pytest.raises(ValueError, match="task revision conflict"):
        core.task_close(root, started["revision"], expected_task_id="00000000-0000-0000-0000-000000000001")


def test_legacy_memory_audience_is_normalized_on_read(tmp_path: Path) -> None:
    root = repo(tmp_path)
    path = root / "entry.md"
    path.write_text(
        '---\nEvidence: NONE\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: UNVERIFIED\nAudience: ["sol-high", "terra-reviewer"]\n---\n\n# Entry\n\nBody.\n',
        encoding="utf-8",
    )
    assert parse(path).meta["Audience"] == ["reasoning-specialist", "reviewer"]


def test_role_projections_keep_working_set_bounded(tmp_path: Path) -> None:
    root = repo(tmp_path)
    main(["--root", str(root), "init"])
    core.task_start(root, "projection", None, None)
    investigator = core.prepare(root, None, "investigator")
    curator = core.prepare(root, None, "curator")
    specialist = core.prepare(root, None, "reasoning-specialist")
    assert investigator["role"] == "investigator"
    assert curator["Current Investigation Snapshot"] == []
    assert "Investigation Findings" not in json.dumps(specialist)


def test_reviewer_sees_git_changed_paths_without_artifact_contents(tmp_path: Path) -> None:
    root = repo(tmp_path)
    main(["--root", str(root), "init"])
    core.task_start(root, "review", None, None)
    changed = root / "changed.txt"
    changed.write_text("private contents", encoding="utf-8")
    pack = core.prepare(root, None, "reviewer")
    assert "changed.txt" in pack["Changed Surface"]
    assert "private contents" not in json.dumps(pack)


def test_evidence_freshness_demotes_changed_confirmed_fact(tmp_path: Path) -> None:
    root = repo(tmp_path)
    main(["--root", str(root), "init"])
    source = root / "fact.txt"
    source.write_text("v1", encoding="utf-8")
    digest = hashlib.sha256(b"v1").hexdigest()
    evidence = {"id": "fact", "kind": "file", "locator": f"file:fact.txt#{digest}", "summary": "fact", "confidence": "CONFIRMED"}
    state_input = root / "start.json"
    state_input.write_text(json.dumps({"evidence_refs": [evidence], "confirmed_facts": [{"text": "v1", "evidence_refs": ["fact"]}]}), encoding="utf-8")
    core.task_start(root, "freshness", None, str(state_input))
    source.write_text("v2", encoding="utf-8")
    pack = core.prepare(root, None, "implementer")
    assert pack["Confirmed Facts"] == []


def test_task_promote_requires_explicit_fresh_evidence(tmp_path: Path) -> None:
    root = repo(tmp_path)
    main(["--root", str(root), "init"])
    source = root / "decision.txt"
    source.write_text("decision", encoding="utf-8")
    digest = hashlib.sha256(b"decision").hexdigest()
    evidence = {"id": "decision", "kind": "file", "locator": f"file:decision.txt#{digest}", "summary": "decision", "confidence": "CONFIRMED"}
    start_input = root / "start.json"
    start_input.write_text(json.dumps({"evidence_refs": [evidence]}), encoding="utf-8")
    started = core.task_start(root, "promotion", None, str(start_input))
    promote_input = root / "promote.json"
    promote_input.write_text(json.dumps({"records": [{"type": "decision", "id": "D-1", "title": "Use decision", "text": "Adopt it.", "evidence_refs": ["decision"], "confidence": "CONFIRMED"}]}), encoding="utf-8")
    result = core.task_promote(root, "controller", started["revision"], str(promote_input))
    assert result["ok"] and (root / ".agent-memory/decisions/D-1.md").is_file()


def test_task_state_write_ingress_and_role_ownership_are_enforced(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    blocked = input_file(root, {"artifact_refs": [{"id": "bad", "path": "x", "summary": "x"}]})
    with pytest.raises(ValueError, match="forbidden"):
        core.task_start(root, "ingress", None, blocked)
    started = core.task_start(root, "ingress", None, None)
    with pytest.raises(ValueError, match="not allowed"):
        core.task_update(root, "controller", started["revision"], blocked)
    with pytest.raises(ValueError, match="not allowed"):
        core.task_update(root, "implementer", started["revision"], input_file(root, {"unknowns": []}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("investigation_findings", []),
        ("investigation_snapshot", []),
        ("review_findings", []),
        ("investigation_covered_through", 0),
        ("review_handled_through", 0),
    ],
)
def test_task_start_rejects_role_owned_execution_outputs(tmp_path: Path, field: str, value: object) -> None:
    root = repo(tmp_path)
    core.init(root)
    with pytest.raises(ValueError, match="forbidden"):
        core.task_start(root, "role provenance", None, input_file(root, {field: value}))


def test_task_start_keeps_semantic_bootstrap_inputs(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "bootstrap", None, input_file(root, {
        "constraints": [{"text": "preserve public API", "evidence_refs": []}],
        "unknowns": [{"text": "test coverage", "evidence_refs": []}],
        "modification_boundary": {"status": "UNVERIFIED", "includes": ["src"], "excludes": [], "evidence_refs": []},
        "verification_target": "pytest -q tests",
        "architectural_intent": "keep Core runtime-neutral",
    }))
    packet = core.task_status(root)
    assert started["revision"] == 1
    assert packet["Accepted Constraints"] == ["preserve public API"]
    assert packet["Verification Target"] == "pytest -q tests"


def test_findings_and_evidence_ids_are_append_only_with_revision_cas(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "investigate", None, None)
    finding = {"kind": "UNKNOWN", "text": "needs inspection", "evidence_refs": []}
    addition = input_file(root, {"investigation_findings": [finding]})
    updated = core.task_update(root, "investigator", started["revision"], addition)
    with pytest.raises(ValueError, match="append-only"):
        core.task_update(root, "investigator", updated["revision"], addition)
    with pytest.raises(ValueError, match="controller-writable"):
        core.task_update(root, "controller", updated["revision"], addition)
    with pytest.raises(ValueError, match="revision conflict"):
        core.task_update(root, "investigator", started["revision"], input_file(root, {"evidence_refs": []}))


def test_curator_cannot_turn_unknown_raw_finding_into_supported_snapshot(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    source = root / "source.txt"
    source.write_text("observed", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {"id": "e1", "kind": "file", "locator": f"file:source.txt#{digest}", "summary": "source", "confidence": "SUPPORTED"}
    started = core.task_start(root, "curate", None, input_file(root, {"evidence_refs": [evidence]}))
    finding = {"kind": "UNKNOWN", "text": "uncertain", "evidence_refs": ["e1"]}
    updated = core.task_update(root, "investigator", started["revision"], input_file(root, {"investigation_findings": [finding]}))
    snapshot = {"id": "S-1", "kind": "SUPPORTED", "text": "not justified", "derived_from": [0], "supersedes": [], "evidence_refs": ["e1"]}
    with pytest.raises(ValueError, match="cannot promote epistemic status"):
        core.task_update(root, "curator", updated["revision"], input_file(root, {"investigation_snapshot": [snapshot]}))


@pytest.mark.parametrize("producer_role", ["terra-implementer", "sol-high", "random-worker", "controller"])
def test_artifact_registration_rejects_nonsemantic_producer_roles(tmp_path: Path, producer_role: str) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "artifact", None, None)
    (root / "notes.md").write_text("bounded", encoding="utf-8")
    with pytest.raises(ValueError, match="semantic execution role"):
        core.task_artifact(root, started["revision"], "notes", "notes.md", "bounded notes", producer_role=producer_role)


def test_artifact_registration_writes_semantic_producer_and_legacy_alias_remains_readable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "artifact", None, None)
    (root / "notes.md").write_text("bounded", encoding="utf-8")
    result = core.task_artifact(root, started["revision"], "notes", "notes.md", "bounded notes", producer_role="implementer")
    assert result["revision"] == 2
    state_path = root / ".context/state.json"
    legacy = json.loads(state_path.read_text(encoding="utf-8"))
    legacy["artifact_refs"][0]["producer_role"] = "terra-implementer"
    state_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert core.task_status(root)["Artifact Refs"][0]["producer_role"] == "terra-implementer"


@pytest.mark.parametrize("path", [".git/config", ".context/state.json", ".agent-memory/INDEX.md", ".milestones/INDEX.md"])
def test_artifact_registration_rejects_private_control_paths(tmp_path: Path, path: str) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "artifact", None, None)
    with pytest.raises(ValueError, match="private control data"):
        core.task_artifact(root, started["revision"], "artifact", path, "bounded")


def test_controller_packet_excludes_private_findings_reviews_and_evidence_registry(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "private", None, None)
    source = root / "source.txt"
    source.write_text("private observation", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {"id": "private-e1", "kind": "file", "locator": f"file:source.txt#{digest}", "summary": "private evidence", "confidence": "SUPPORTED"}
    finding = {"kind": "UNKNOWN", "text": "raw private investigation", "evidence_refs": ["private-e1"]}
    core.task_update(root, "investigator", started["revision"], input_file(root, {"evidence_refs": [evidence], "investigation_findings": [finding]}))
    packet = json.dumps(core.task_status(root))
    assert "raw private investigation" not in packet
    assert "investigation_findings" not in packet
    assert "private-e1" not in packet


def test_test_evidence_is_demoted_when_its_native_source_changes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    source = root / "source.txt"
    source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    native = {"id": "src", "kind": "file", "locator": f"file:source.txt#{digest}", "summary": "source", "confidence": "SUPPORTED"}
    test = {"id": "test", "kind": "test", "locator": "pytest tests/test_source.py", "summary": "passed", "confidence": "SUPPORTED", "source_refs": ["src"]}
    claim = {"text": "targeted test passed", "evidence_refs": ["test"]}
    core.task_start(root, "verify", None, input_file(root, {"evidence_refs": [native, test], "supported_evidence": [claim]}))
    assert core.prepare(root, None, "reasoning-specialist")["Supported Evidence"] == [claim]
    source.write_text("two", encoding="utf-8")
    pack = core.prepare(root, None, "reasoning-specialist")
    assert pack["Supported Evidence"] == []
    assert any("stale supported evidence" in item["text"] for item in pack["Unknowns"])
