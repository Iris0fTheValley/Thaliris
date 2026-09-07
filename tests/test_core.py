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


def commit(root: Path, message: str = "baseline") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Thaliris", "-c", "user.email=thaliris@example.invalid", "commit", "-qm", message], cwd=root, check=True)


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


def _durable_lifecycle_memory(root: Path) -> Path:
    index = root / ".agent-memory" / "INDEX.md"
    index.write_text(index.read_text(encoding="utf-8").replace("- [Operator](operator.md)", "- [Operator](operator.md)\n- [Lifecycle](lifecycle.md)"), encoding="utf-8")
    evidence = root / "lifecycle-evidence.txt"
    evidence.write_text("lifecycle evidence", encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    memory = root / ".agent-memory" / "lifecycle.md"
    memory.write_text(
        f'---\nEvidence: file:lifecycle-evidence.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: CONFIRMED\nKind: MEMORY\nAudience: ["reasoning-specialist"]\nTopics: ["lifecycle", "XYZ"]\nSymbols: ["LifecycleXYZ"]\n---\n\n# Lifecycle invariant\n\npreserve lifecycle invariant XYZ\n',
        encoding="utf-8",
    )
    return memory


def test_durable_memory_requires_explicit_recall_and_recall_is_read_only(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    memory = _durable_lifecycle_memory(root)
    core.task_start(root, "preserve lifecycle XYZ", None, None)
    before_state = (root / ".context" / "state.json").read_bytes()
    before_memory = memory.read_bytes()

    pack = core.prepare(root, None, "reasoning-specialist")
    assert "preserve lifecycle invariant XYZ" not in json.dumps(pack)

    recalled = core.recall(root, "lifecycle XYZ", "reasoning-specialist")
    assert recalled["routing_errors"] == []
    assert len(recalled["candidates"]) == 1
    candidate = recalled["candidates"][0]
    assert candidate["source"] == ".agent-memory/lifecycle.md"
    assert candidate["confidence"] == "CONFIRMED"
    assert candidate["freshness"] == "FRESH"
    assert candidate["evidence_refs"] == ["memory:.agent-memory/lifecycle.md"]
    assert "preserve lifecycle invariant XYZ" in candidate["text"]
    assert (root / ".context" / "state.json").read_bytes() == before_state
    assert memory.read_bytes() == before_memory

    assert core.recall(root, "unrelated rendering issue", "reasoning-specialist")["candidates"] == []
    assert "preserve lifecycle invariant XYZ" not in json.dumps(core.prepare(root, None, "reasoning-specialist"))


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


def test_investigator_handoff_can_select_rich_semantic_constraints(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "rich handoff", None, None)
    selected = {
        "investigation_findings": [{
            "kind": "UNKNOWN",
            "text": (
                "Compatibility constraint: preserve the lifecycle invariant; "
                "architecture ambiguity remains an unresolved contradiction."
            ),
            "evidence_refs": [],
        }],
    }
    updated = core.task_update(root, "investigator", started["revision"], input_file(root, selected))
    assert updated["revision"] == 2
    assert "Compatibility constraint" in core.task_show(root)["state"]["investigation_findings"][0]["text"]


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


def test_legacy_anonymous_semantic_records_upgrade_without_loss(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    core.task_start(root, "legacy", None, input_file(root, {"constraints": [{"text": "keep API", "evidence_refs": []}]}))
    path = root / ".context/state.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy["constraints"] = [{"text": "keep API", "evidence_refs": []}]
    legacy.pop("verification_evidence")
    path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = core.task_show(root)["state"]
    assert loaded["schema_version"] == 4
    assert loaded["constraints"] == [{"id": "legacy-C-0001", "text": "keep API", "evidence_refs": [], "status": "ACTIVE"}]
    assert core.migrate(root)["changed"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 4
    assert persisted["constraints"] == loaded["constraints"]


def test_v2_verification_claims_remain_readable_but_are_not_trusted_results(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    source = root / "source.txt"
    source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    started = core.task_start(root, "legacy verification", None, input_file(root, {
        "evidence_refs": [
            {"id": "src", "kind": "file", "locator": f"file:source.txt#{digest}", "summary": "source", "confidence": "SUPPORTED"},
            {"id": "claim", "kind": "test", "locator": "pytest -q", "summary": "passed", "confidence": "SUPPORTED", "source_refs": ["src"]},
        ],
    }))
    path = root / ".context/state.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 2
    legacy["verification_evidence"] = ["claim"]
    legacy.pop("verification_results")
    legacy.pop("task_surface_baseline")
    path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = core.task_show(root)["state"]
    assert loaded["schema_version"] == 4
    assert loaded["verification_evidence"] == ["claim"]
    assert loaded["verification_results"] == []
    assert loaded["task_surface_baseline"] is None
    assert loaded["revision"] == started["revision"]


def test_semantic_transition_contracts_and_illegal_updates_fail_closed(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "semantics", None, input_file(root, {
        "constraints": [{"text": "preserve API", "evidence_refs": []}],
        "unknowns": [{"text": "coverage", "evidence_refs": []}],
        "decisions": [{"text": "use current API", "evidence_refs": []}],
    }))
    with pytest.raises(ValueError, match="not allowed"):
        core.task_update(root, "controller", started["revision"], input_file(root, {"constraints": []}))

    revision = started["revision"]
    operations = [
        {"op": "resolve", "type": "unknowns", "id": "legacy-U-0001"},
        {"op": "reopen", "type": "unknowns", "id": "legacy-U-0001"},
        {"op": "add", "type": "contradictions", "id": "X-1", "text": "two sources disagree", "evidence_refs": []},
    ]
    with pytest.raises(ValueError, match="contradictions require evidence"):
        core.task_update(root, "controller", revision, input_file(root, {"semantic_operations": operations}))

    source = root / "source.txt"
    source.write_text("evidence", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {"id": "src", "kind": "file", "locator": f"file:source.txt#{digest}", "summary": "source", "confidence": "SUPPORTED"}
    updated = core.task_update(root, "controller", revision, input_file(root, {"evidence_refs": [evidence], "semantic_operations": [
        {"op": "resolve", "type": "unknowns", "id": "legacy-U-0001"},
        {"op": "reopen", "type": "unknowns", "id": "legacy-U-0001"},
        {"op": "add", "type": "constraints", "id": "C-2", "text": "keep transition history", "evidence_refs": []},
        {"op": "add", "type": "contradictions", "id": "X-1", "text": "two sources disagree", "evidence_refs": ["src"]},
        {"op": "adjudicate", "type": "contradictions", "id": "X-1"},
        {"op": "supersede", "type": "decisions", "id": "D-2", "text": "use revised API", "evidence_refs": [], "supersedes": ["legacy-D-0001"]},
    ]}))
    state = core.task_show(root)["state"]
    assert state["unknowns"][0]["status"] == "OPEN"
    assert state["contradictions"][0]["status"] == "ADJUDICATED"
    assert state["decisions"][0]["status"] == "SUPERSEDED"
    assert state["decisions"][0]["superseded_by"] == "D-2"
    assert state["decisions"][1]["status"] == "ACTIVE"
    assert core.task_status(root)["Accepted Constraints"] == ["preserve API", "keep transition history"]
    assert core.task_status(root)["Accepted Decisions"] == ["use revised API"]
    with pytest.raises(ValueError, match="revision conflict"):
        core.task_update(root, "controller", revision, input_file(root, {"semantic_operations": [{"op": "resolve", "type": "unknowns", "id": "legacy-U-0001"}]}))
    with pytest.raises(ValueError, match="illegal semantic adjudicate"):
        core.task_update(root, "controller", updated["revision"], input_file(root, {"semantic_operations": [{"op": "adjudicate", "type": "contradictions", "id": "X-1"}]}))


def test_verification_gate_tracks_artifact_identity_and_current_surface(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    artifact = root / "result.txt"
    artifact.write_text("v1", encoding="utf-8")
    started = core.task_start(root, "verify artifact", None, None)
    registered = core.task_artifact(root, started["revision"], "result", "result.txt", "result artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    native = {"id": "result-source", "kind": "file", "locator": f"file:result.txt#{digest}", "summary": "result content", "confidence": "SUPPORTED"}
    configured = core.task_update(root, "controller", registered["revision"], input_file(root.parent, {
        "evidence_refs": [native],
        "verification_target": {"description": "result must pass", "artifact_refs": ["result"], "changed_surface": []},
    }, "verification-config.json"))
    verified = core.task_record_verification(root, configured["revision"], "check", "test", "PASSED", "verification succeeded", ["result-source"], observed_by="test-runtime")
    assert core.task_close(root, verified["revision"])["status"] == "DONE"

    # A historical pointer remains readable after the target changes, but its
    # recorded identity is visibly stale and can no longer satisfy a close.
    root = repo(tmp_path / "stale")
    core.init(root)
    artifact = root / "result.txt"
    artifact.write_text("v1", encoding="utf-8")
    started = core.task_start(root, "verify stale artifact", None, None)
    registered = core.task_artifact(root, started["revision"], "result", "result.txt", "result artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    native = {"id": "result-source", "kind": "file", "locator": f"file:result.txt#{digest}", "summary": "result content", "confidence": "SUPPORTED"}
    configured = core.task_update(root, "controller", registered["revision"], input_file(root.parent, {"evidence_refs": [native], "verification_target": {"description": "result must pass", "artifact_refs": ["result"], "changed_surface": []}}, "verification-config.json"))
    verified = core.task_record_verification(root, configured["revision"], "check", "test", "PASSED", "verification succeeded", ["result-source"], observed_by="test-runtime")
    artifact.write_text("v2", encoding="utf-8")
    assert core.task_show(root)["state"]["artifact_refs"][0]["content_sha256"] == digest
    assert core.task_status(root)["Artifact Refs"][0]["freshness"] == "STALE"
    with pytest.raises(ValueError, match="artifact is no longer current"):
        core.task_close(root, verified["revision"])


def test_verification_target_rejects_bare_model_claim(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    (root / "changed.py").write_text("v1", encoding="utf-8")
    started = core.task_start(root, "verify", None, input_file(root, {"changed_surface": ["changed.py"], "verification_target": "pytest -q"}))
    with pytest.raises(ValueError, match="trusted successful verification result"):
        core.task_close(root, started["revision"])


def _verification_task(root: Path, paths: list[str], *, boundary: list[str] | None = None) -> tuple[dict[str, object], list[dict[str, str]]]:
    evidence = []
    for index, path in enumerate(paths, 1):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"v{index}", encoding="utf-8")
    started = core.task_start(root, "verification", None, input_file(root.parent, {
        "changed_surface": paths,
        "modification_boundary": {"status": "UNVERIFIED", "includes": boundary or [], "excludes": [], "evidence_refs": []},
        "verification_target": {"description": "verify current files", "artifact_refs": [], "changed_surface": paths},
    }, "start.json"))
    for index, path in enumerate(paths, 1):
        digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
        evidence.append({"id": f"src-{index}", "kind": "file", "locator": f"file:{path}#{digest}", "summary": path, "confidence": "SUPPORTED"})
    configured = core.task_update(root, "controller", started["revision"], input_file(root.parent, {"evidence_refs": evidence}, "evidence.json"))
    return configured, evidence


def test_model_authored_test_evidence_never_becomes_trusted_verification(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    configured, evidence = _verification_task(root, ["subject.py"])
    fake = {"id": "passed", "kind": "test", "locator": "pytest -q tests/test_subject.py", "summary": "passed", "confidence": "SUPPORTED", "source_refs": [evidence[0]["id"]]}
    with_fake = core.task_update(root, "controller", configured["revision"], input_file(root.parent, {"evidence_refs": [fake]}, "fake.json"))
    with pytest.raises(ValueError, match="trusted successful verification result"):
        core.task_close(root, with_fake["revision"])
    with pytest.raises(ValueError, match="not allowed"):
        core.task_update(root, "controller", with_fake["revision"], input_file(root.parent, {"verification_evidence": ["passed"]}, "selection.json"))
    with pytest.raises(ValueError, match="verification target cannot be changed"):
        core.task_update(root, "controller", with_fake["revision"], input_file(root.parent, {"verification_target": None}, "remove-target.json"))


@pytest.mark.parametrize("outcome", ["FAILED", "UNKNOWN"])
def test_nonpassing_trusted_outcomes_cannot_close(tmp_path: Path, outcome: str) -> None:
    root = repo(tmp_path)
    core.init(root)
    configured, evidence = _verification_task(root, ["subject.py"])
    result = core.task_record_verification(root, configured["revision"], "result", "test", outcome, "observed outcome", [evidence[0]["id"]], observed_by="test-runtime")
    with pytest.raises(ValueError, match="does not cover"):
        core.task_close(root, result["revision"])


def test_trusted_verification_requires_every_current_surface_path(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    configured, evidence = _verification_task(root, ["a.py", "b.py"])
    result = core.task_record_verification(root, configured["revision"], "partial", "test", "PASSED", "only a", [evidence[0]["id"]], observed_by="test-runtime")
    with pytest.raises(ValueError, match="does not cover"):
        core.task_close(root, result["revision"])


def test_new_task_scoped_git_mutation_requires_reverification(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    configured, evidence = _verification_task(root, ["src/a.py"], boundary=["src"])
    result = core.task_record_verification(root, configured["revision"], "a-pass", "test", "PASSED", "a passed", [evidence[0]["id"]], observed_by="test-runtime")
    (root / "src/b.py").write_text("new task change", encoding="utf-8")
    with pytest.raises(ValueError, match="does not cover"):
        core.task_close(root, result["revision"])


def test_trusted_verification_binds_deleted_surface_without_fabricated_file_ref(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    removed = root / "removed.py"
    removed.write_text("before", encoding="utf-8")
    commit(root)
    started = core.task_start(root, "remove file", None, input_file(root.parent, {
        "changed_surface": ["removed.py"],
        "modification_boundary": {"status": "UNVERIFIED", "includes": ["removed.py"], "excludes": [], "evidence_refs": []},
        "verification_target": {"description": "verify removal", "artifact_refs": [], "changed_surface": ["removed.py"]},
    }, "remove-start.json"))
    removed.unlink()
    recorded = core.task_record_verification(root, started["revision"], "remove-pass", "test", "PASSED", "observed removal", observed_by="runtime", source_paths=["removed.py"])
    result = core.task_show(root)["state"]["verification_results"][0]
    assert result["source_refs"] == []
    assert result["covered_surface"][0]["state"] == "DELETED"
    assert core.task_close(root, recorded["revision"])["status"] == "DONE"


def test_unknown_post_start_workspace_mutation_fails_closed_but_baseline_does_not(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    (root / "unrelated-before.txt").write_text("existing user work", encoding="utf-8")
    configured, evidence = _verification_task(root, ["subject.py"])
    result = core.task_record_verification(root, configured["revision"], "pass", "test", "PASSED", "subject passed", [evidence[0]["id"]], observed_by="test-runtime")
    assert core.task_close(root, result["revision"])["status"] == "DONE"

    root = repo(tmp_path / "unknown")
    core.init(root)
    configured, evidence = _verification_task(root, ["subject.py"])
    result = core.task_record_verification(root, configured["revision"], "pass", "test", "PASSED", "subject passed", [evidence[0]["id"]], observed_by="test-runtime")
    (root / "unattributed.txt").write_text("new unknown writer", encoding="utf-8")
    with pytest.raises(ValueError, match="attribution is unknown"):
        core.task_close(root, result["revision"])


def test_semantic_projection_marks_stale_provenance_without_rewriting_history(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    source = root / "source.txt"
    source.write_text("v1", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    native = {"id": "src", "kind": "file", "locator": f"file:source.txt#{digest}", "summary": "source", "confidence": "SUPPORTED"}
    core.task_start(root, "semantic freshness", None, input_file(root.parent, {
        "evidence_refs": [native],
        "constraints": [{"text": "preserve public API", "evidence_refs": ["src"]}],
        "contradictions": [{"text": "sources disagree", "evidence_refs": ["src"]}],
        "decisions": [{"text": "use v1", "evidence_refs": ["src"]}],
        "unknowns": [{"text": "open question", "evidence_refs": []}],
    }, "semantic-start.json"))
    source.write_text("v2", encoding="utf-8")
    pack = core.prepare(root, None, "reasoning-specialist")
    assert pack["Hard Constraints"][0]["effective_state"] == "STALE_PROVENANCE"
    assert pack["Contradictions"][0]["effective_state"] == "REVALIDATION_REQUIRED"
    assert pack["Decisions"][0]["effective_state"] == "REVALIDATION_REQUIRED"
    assert pack["Unknowns"][0]["text"] == "open question"
    historical = core.task_show(root)["state"]
    assert "effective_state" not in historical["constraints"][0]
    assert historical["constraints"][0]["status"] == "ACTIVE"


def test_verification_result_requires_and_binds_the_current_target(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    subject = root / "subject.py"
    subject.write_text("subject", encoding="utf-8")
    digest = hashlib.sha256(subject.read_bytes()).hexdigest()
    started = core.task_start(root, "target binding", None, input_file(root.parent, {
        "evidence_refs": [{"id": "src", "kind": "file", "locator": f"file:subject.py#{digest}", "summary": "subject", "confidence": "SUPPORTED"}],
    }, "unbound.json"))
    with pytest.raises(ValueError, match="target is not configured"):
        core.task_record_verification(root, started["revision"], "early", "test", "PASSED", "early", ["src"], observed_by="runtime")
    configured = core.task_update(root, "controller", started["revision"], input_file(root.parent, {
        "changed_surface": ["subject.py"],
        "verification_target": {"description": "target A", "artifact_refs": [], "changed_surface": ["subject.py"]},
    }, "target-a.json"))
    target_a = core._target_fingerprint(core.task_show(root)["state"]["verification_target"])
    assert target_a == core._target_fingerprint({"artifact_refs": [], "changed_surface": ["subject.py"], "description": "target A"})
    assert target_a != core._target_fingerprint({"description": "target B", "artifact_refs": [], "changed_surface": ["subject.py"]})
    with pytest.raises(ValueError, match="verification target cannot be changed"):
        core.task_update(root, "controller", configured["revision"], input_file(root.parent, {
            "verification_target": {"description": "target B", "artifact_refs": [], "changed_surface": ["subject.py"]},
        }, "target-b.json"))
    recorded = core.task_record_verification(root, configured["revision"], "bound", "test", "PASSED", "observed", ["src"], observed_by="runtime")
    result = core.task_show(root)["state"]["verification_results"][0]
    assert result["target_fingerprint"] == target_a
    assert result["observed_at_revision"] == configured["revision"]
    assert core.task_close(root, recorded["revision"])["status"] == "DONE"


def test_forged_or_different_target_fingerprint_cannot_satisfy_close(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    configured, evidence = _verification_task(root, ["subject.py"])
    recorded = core.task_record_verification(root, configured["revision"], "bound", "test", "PASSED", "observed", [evidence[0]["id"]], observed_by="runtime")
    path = root / ".context/state.json"
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["verification_target"] = {"description": "target B", "artifact_refs": [], "changed_surface": ["subject.py"]}
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(ValueError, match="does not cover"):
        core.task_close(root, recorded["revision"])


def test_clean_tracked_deletion_is_not_lost_from_surface_truth(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    target = root / "deleted.py"
    target.write_text("baseline", encoding="utf-8")
    commit(root)
    started = core.task_start(root, "deletion", None, input_file(root.parent, {
        "changed_surface": ["deleted.py"],
        "modification_boundary": {"status": "UNVERIFIED", "includes": ["deleted.py"], "excludes": [], "evidence_refs": []},
        "verification_target": {"description": "keep deleted path covered", "artifact_refs": [], "changed_surface": ["deleted.py"]},
    }, "delete-start.json"))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    configured = core.task_update(root, "controller", started["revision"], input_file(root.parent, {
        "evidence_refs": [{"id": "deleted-source", "kind": "file", "locator": f"file:deleted.py#{digest}", "summary": "before delete", "confidence": "SUPPORTED"}],
    }, "delete-evidence.json"))
    recorded = core.task_record_verification(root, configured["revision"], "before-delete", "test", "PASSED", "observed", ["deleted-source"], observed_by="runtime")
    target.unlink()
    assert core._surface_snapshot(root)[0]["state"] == "DELETED"
    with pytest.raises(ValueError, match="does not cover"):
        core.task_close(root, recorded["revision"])


def test_git_symlinks_are_visible_without_being_followed(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    configured, evidence = _verification_task(root, ["subject.py"])
    recorded = core.task_record_verification(root, configured["revision"], "pass", "test", "PASSED", "observed", [evidence[0]["id"]], observed_by="runtime")
    link = root / "outside-link"
    try:
        link.symlink_to(root.parent / "outside-target")
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    snapshot = {item["path"]: item for item in core._surface_snapshot(root)}
    assert snapshot["outside-link"]["state"] == "SYMLINK"
    with pytest.raises(ValueError, match="attribution is unknown"):
        core.task_close(root, recorded["revision"])
    commit(root, "tracked link")
    link.unlink()
    snapshot = {item["path"]: item for item in core._surface_snapshot(root)}
    assert snapshot["outside-link"]["state"] == "DELETED"


def test_committed_task_changes_remain_in_verification_surface(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    (root / "a.py").write_text("a0", encoding="utf-8")
    source = root / "b.py"
    source.write_text("b0", encoding="utf-8")
    commit(root)
    started = core.task_start(root, "committed surface", None, input_file(root.parent, {
        "changed_surface": ["a.py"],
        "modification_boundary": {"status": "UNVERIFIED", "includes": ["a.py"], "excludes": [], "evidence_refs": []},
        "verification_target": {"description": "verify a", "artifact_refs": [], "changed_surface": ["a.py"]},
    }, "commit-start.json"))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    configured = core.task_update(root, "controller", started["revision"], input_file(root.parent, {
        "evidence_refs": [{"id": "wrong-source", "kind": "file", "locator": f"file:b.py#{digest}", "summary": "other file", "confidence": "SUPPORTED"}],
    }, "commit-evidence.json"))
    recorded = core.task_record_verification(root, configured["revision"], "wrong-pass", "test", "PASSED", "observed", ["wrong-source"], observed_by="runtime")
    (root / "a.py").write_text("a1", encoding="utf-8")
    commit(root, "task change")
    assert core._changed_files(root) == []
    assert "a.py" in core.task_verification_requirements(root)["paths"]
    with pytest.raises(ValueError, match="does not cover"):
        core.task_close(root, recorded["revision"])


def test_head_change_outside_task_boundary_is_unknown(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    (root / "subject.py").write_text("v1", encoding="utf-8")
    commit(root)
    configured, evidence = _verification_task(root, ["subject.py"])
    recorded = core.task_record_verification(root, configured["revision"], "pass", "test", "PASSED", "observed", [evidence[0]["id"]], observed_by="runtime")
    (root / "other.py").write_text("concurrent", encoding="utf-8")
    commit(root, "unattributed head change")
    with pytest.raises(ValueError, match="surface attribution is unknown"):
        core.task_close(root, recorded["revision"])


def _baseline_dirty_task(root: Path, path: str, *, boundary: list[str] | None = None) -> dict[str, object]:
    return core.task_start(root, "baseline dirty surface", None, input_file(root.parent, {
        "changed_surface": [],
        "modification_boundary": {"status": "UNVERIFIED", "includes": boundary or [], "excludes": [], "evidence_refs": []},
    }, f"{path.replace('/', '-')}-start.json"))


def _attributable_paths(root: Path) -> set[str]:
    return core._task_attributable_surface(root, core.task_show(root)["state"], set())


def test_baseline_dirty_tracked_file_restored_to_clean_is_attributable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    target = root / "subject.py"
    target.write_text("clean", encoding="utf-8")
    commit(root)
    target.write_text("dirty before task", encoding="utf-8")
    _baseline_dirty_task(root, "subject.py", boundary=["subject.py"])
    subprocess.run(["git", "restore", "subject.py"], cwd=root, check=True)
    assert "subject.py" in _attributable_paths(root)


def test_baseline_untracked_file_disappearance_is_attributable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    target = root / "scratch.py"
    target.write_text("untracked before task", encoding="utf-8")
    _baseline_dirty_task(root, "scratch.py", boundary=["scratch.py"])
    target.unlink()
    assert "scratch.py" in _attributable_paths(root)


def test_baseline_dirty_file_changed_again_is_attributable_but_unchanged_is_not(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    target = root / "subject.py"
    target.write_text("clean", encoding="utf-8")
    commit(root)
    target.write_text("dirty before task", encoding="utf-8")
    _baseline_dirty_task(root, "subject.py")
    assert _attributable_paths(root) == set()
    target.write_text("different dirty task content", encoding="utf-8")
    with pytest.raises(ValueError, match="surface attribution is unknown"):
        _attributable_paths(root)


def test_baseline_dirty_change_outside_boundary_fails_closed(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    target = root / "subject.py"
    target.write_text("clean", encoding="utf-8")
    commit(root)
    target.write_text("dirty before task", encoding="utf-8")
    _baseline_dirty_task(root, "subject.py", boundary=["other.py"])
    target.write_text("different dirty task content", encoding="utf-8")
    with pytest.raises(ValueError, match="surface attribution is unknown"):
        _attributable_paths(root)
