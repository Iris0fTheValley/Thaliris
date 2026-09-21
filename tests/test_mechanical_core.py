from __future__ import annotations

import json
import importlib.util
import hashlib
import re
from pathlib import Path
import subprocess
import sys
import pytest

from thaliris import cli, codex_adapter, core, lifecycle as lifecycle_module, markdown


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    return tmp_path


def write_json(path: Path, value: object) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_durable_task_a_promotion_recovers_in_fresh_task_b_without_automatic_curator(tmp_path: Path) -> None:
    """The Controller-owned protocol is explicit: map, exact read, promotion.

    This deliberately calls no Curator or broad durable discovery API.  It
    exercises the high-fidelity recovery path a fresh controller uses after
    Task A has closed.
    """
    root = repo(tmp_path)
    task_a = core.task_start(root, "Task A durable architecture", None, None)
    index_path = root / ".agent-memory" / "INDEX.md"
    old_index = index_path.read_bytes()
    updated_index = core._entry("Memory map", "[Architecture decision](architecture/decision.md)", evidence="NONE").decode()
    promoted = core.task_promote(root, "controller", task_a["revision"], write_json(tmp_path / "task-a-promote.json", {
        "records": [{"id": "architecture-decision", "path": ".agent-memory/architecture/decision.md",
                     "title": "Architecture decision", "text": "REUSABLE_DECISION", "source_refs": []}],
        "index_update": {"path": ".agent-memory/INDEX.md", "base_sha256": hashlib.sha256(old_index).hexdigest(),
                         "content": updated_index},
    }))
    closed = core.task_close(root, core.task_show(root)["state"]["revision"], expected_task_id=task_a["task_id"])
    assert closed["status"] == "DONE"

    # A genuinely separate interpreter/session starts Task B. It makes the
    # exact document-get reads selected by the root INDEX, never catalog/search.
    index_before_recovery = index_path.read_bytes()
    worker = '''
import json, re, sys
from pathlib import Path
from thaliris import core
root = Path(sys.argv[1])
started = core.task_start(root, "Task B recover durable decision", None, None)
reads = [".agent-memory/INDEX.md"]
index = core.document_get(root, reads)["documents"][0]["body"]
path = re.search(r"\\]\(([^)]+)\\)", index).group(1)
reads.append(".agent-memory/" + path)
doc = core.document_get(root, [reads[-1]])["documents"][0]["body"]
print(json.dumps({"task": started["status"], "reads": reads, "body": doc}))
'''
    result = subprocess.run([sys.executable, "-c", worker, str(root)], check=True, capture_output=True, text=True)
    recovery = json.loads(result.stdout)
    assert recovery["task"] == "ACTIVE"
    assert recovery["reads"] == [".agent-memory/INDEX.md", ".agent-memory/architecture/decision.md"]
    assert "REUSABLE_DECISION" in recovery["body"]
    assert index_path.read_bytes() == index_before_recovery


def test_core_has_no_execution_role_context_packet(tmp_path: Path) -> None:
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
    core.task_artifact(root, started["revision"], "details", "artifact.md", "details", producer="investigator")
    memory = root / ".agent-memory" / "private.md"
    memory.write_bytes(core._entry("Private", "MEMORY_TEXT"))

    assert not hasattr(core, "prepare")
    assert not hasattr(core, "recall")


def test_core_mechanically_accepts_opaque_actor_and_provenance(tmp_path: Path) -> None:
    root = repo(tmp_path)
    actor = "external-orchestrator:42"
    started = core.task_start(root, "opaque identities", None, write_json(tmp_path / "initial.json", {
        "records": [{"id": "r1", "kind": "note", "text": "initial"}],
    }), actor=actor)
    assert core.task_show(root)["state"]["records"][0]["producer"] == actor
    updated = core.task_update(root, actor, started["revision"], write_json(tmp_path / "update.json", {
        "records": [{"id": "r2", "kind": "note", "text": "updated"}],
    }))
    artifact = root / "opaque.md"
    artifact.write_text("body", encoding="utf-8")
    core.task_artifact(root, updated["revision"], "a1", "opaque.md", "opaque", producer="another-system", registered_by=actor)
    state = core.task_show(root)["state"]
    assert state["records"][-1]["producer"] == actor
    assert state["artifact_refs"][-1]["producer"] == "another-system"
    assert state["artifact_refs"][-1]["registered_by"] == actor


def test_core_source_has_no_controller_role_contract() -> None:
    source = Path(core.__file__).read_text(encoding="utf-8").lower()
    assert "controller" not in source


def test_adapter_retains_controller_authorization() -> None:
    assert codex_adapter.controller_actor("controller") == "controller"
    with pytest.raises(ValueError, match="only Controller"):
        codex_adapter.controller_actor("implementer")


def test_public_role_ingress_is_exactly_the_six_thaliris_roles(capsys: pytest.CaptureFixture[str]) -> None:
    expected = (
        "controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer",
    )
    assert codex_adapter.ROLE_CHOICES == expected
    help_text = cli._parser()._subparsers._group_actions[0].choices["task-update"].format_help()
    for role in expected:
        assert role in help_text
    for alias in ("worker", "explorer", "thaliris-implementer", "luna-investigator"):
        assert alias not in help_text
        with pytest.raises(ValueError, match="unknown Thaliris role"):
            codex_adapter.semantic_role(alias)

    assert cli.main(["task-update", "--role", "worker", "--base-revision", "1", "--input", "input.json"]) == 2
    assert "invalid choice" in capsys.readouterr().out


def test_context_help_describes_mechanical_purpose_without_context_packs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="0"):
        cli.main(["--help"])
    help_text = capsys.readouterr().out
    assert "context pack" not in help_text.lower()
    for phrase in ("durable records", "identities", "provenance", "explicit retrieval", "lifecycle binding"):
        assert phrase in help_text
    assert "semantic routing" not in help_text.lower()


@pytest.mark.parametrize("removed", ["prepare", "recall", "memory-get"])
def test_cli_rejects_removed_memory_commands(removed: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([removed]) == 2
    assert removed in capsys.readouterr().out


def test_authoritative_prose_uses_role_names_or_explicit_native_child_context() -> None:
    root = Path(__file__).resolve().parents[1]
    surfaces = (
        root / "AGENTS.md", root / "README.md", root / "README.en.md", root / "DESIGN.md",
        root / "adapter" / "codex" / "README.md", root / "docs" / "thaliris-routing-protocol.md",
    )
    for surface in surfaces:
        text = surface.read_text(encoding="utf-8")
        assert "Child" not in text, surface
        for line in text.splitlines():
            if "child" in line.lower():
                assert "native Codex child" in line, (surface, line)
    generated = (root / "src" / "thaliris" / "codex_adapter.py").read_text(encoding="utf-8")
    assert "Do not delegate to another child" not in generated
    assert "another native Codex child session" not in generated
    assert "another authorized native Codex role session" in generated
    assert "Shared Child Result" not in generated
    assert "Repository investigation belongs to fresh Investigator sessions" in generated
    assert "belong to fresh\nthose roles" not in generated
    assert "Fresh Investigator,\nCurator, Reasoning Specialist, Implementer, and Reviewer sessions use" in generated
    assert "and receive their tasks plus selected information" in generated


def test_lifecycle_policy_denials_name_role_sessions_or_native_codex_sessions() -> None:
    source = Path(lifecycle_module.__file__).read_text(encoding="utf-8")
    denials = re.findall(r'_permission_deny\("([^"]+)', source)
    assert denials
    for denial in denials:
        assert "child" not in denial.lower(), denial
        assert "Child" not in denial, denial
    assert "fresh Investigator session and edits to a fresh Implementer session" in source
    assert "managed native Codex session lifecycle" in source
    assert "managed child slot" not in source
    assert "managed Child" not in source
    assert "authorized native Codex role-session slot" in source
    assert "authorized native Codex role session" in source
    assert "child_id" in source  # Raw native schema fields remain unchanged.


def test_artifact_freshness_is_observation_only(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "freshness", None, write_json(root.parent / "input.json", {
        "records": [{"id": "decision", "kind": "decision", "text": "keep model conclusion", "status": "accepted"}],
    }))
    artifact = root / "evidence.md"
    artifact.write_text("before", encoding="utf-8")
    registered = core.task_artifact(root, started["revision"], "evidence", "evidence.md", "evidence", producer="investigator")
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
    assert shown["state"]["verification_results"][0]["source_refs"] == []

    closed = core.task_close(root, observed["revision"], expected_task_id=started["task_id"])
    assert closed["status"] == "DONE"


def test_promotion_stores_controller_selection_without_confidence_gate(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "promotion", None, None)
    promotion = write_json(root.parent / "promotion.json", {"records": [{
        "id": "selected",
        "path": ".agent-memory/model-chosen/selected.md",
        "title": "Selected record",
        "text": "MODEL_SELECTED_TEXT",
        "source_refs": [],
    }]})
    result = core.task_promote(root, "controller", started["revision"], promotion)
    assert result["promoted"] == [".agent-memory/model-chosen/selected.md"]
    assert result["index_updated"] is None
    assert "model-chosen/selected.md" not in (root / ".agent-memory" / "INDEX.md").read_text(encoding="utf-8")

    fetched = core.document_get(root, ".agent-memory/model-chosen/selected.md")["documents"][0]
    assert "MODEL_SELECTED_TEXT" in fetched["body"]


def test_promotion_can_atomically_commit_model_authored_index_update(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "promotion and index", None, None)
    index_path = root / ".agent-memory" / "INDEX.md"
    original_index = index_path.read_bytes()
    updated_index = core._entry(
        "Memory map",
        "Model chosen area: [Decision](model-tree/decision.md)",
        evidence="NONE",
    ).decode("utf-8")
    payload = {
        "records": [{
            "id": "D1", "path": ".agent-memory/model-tree/decision.md",
                "title": "Decision", "text": "MODEL_PLACED", "source_refs": [],
        }],
        "index_update": {
            "path": ".agent-memory/INDEX.md",
            "base_sha256": hashlib.sha256(original_index).hexdigest(),
            "content": updated_index,
        },
    }
    result = core.task_promote(root, "controller", started["revision"], write_json(tmp_path / "promotion-index.json", payload))
    assert result["index_updated"] == ".agent-memory/INDEX.md"
    assert (root / ".agent-memory" / "model-tree" / "decision.md").is_file()
    assert index_path.read_text(encoding="utf-8") == updated_index

    rollback_root = repo(tmp_path / "rollback")
    rollback_started = core.task_start(rollback_root, "rollback", None, None)
    rollback_index = rollback_root / ".agent-memory" / "INDEX.md"
    rollback_original = rollback_index.read_bytes()
    rollback_payload = dict(payload)
    rollback_payload["index_update"] = dict(payload["index_update"], base_sha256=hashlib.sha256(rollback_original).hexdigest())
    original_atomic_write = core._atomic_write

    def fail_index_write(target: Path, content: bytes) -> None:
        if target == rollback_index:
            raise OSError("simulated INDEX write failure")
        original_atomic_write(target, content)

    monkeypatch.setattr(core, "_atomic_write", fail_index_write)
    with pytest.raises(OSError, match="simulated INDEX"):
        core.task_promote(
            rollback_root,
            "controller",
            rollback_started["revision"],
            write_json(tmp_path / "promotion-rollback.json", rollback_payload),
        )
    assert not (rollback_root / ".agent-memory" / "model-tree" / "decision.md").exists()
    assert rollback_index.read_bytes() == rollback_original


def test_promotion_rejects_rendered_record_over_explicit_bound_before_writes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    sources = [
        {"id": f"S{index}", "kind": "repo", "locator": "x" * 4096, "summary": "source" * 600}
        for index in range(32)
    ]
    started = core.task_start(root, "large promotion", None, write_json(tmp_path / "sources.json", {
        "evidence_refs": sources,
    }))
    index_before = (root / ".agent-memory" / "INDEX.md").read_bytes()
    payload = write_json(tmp_path / "promotion.json", {"records": [{
        "id": "D1", "path": ".agent-memory/large.md", "title": "Large", "text": "body", "source_refs": [item["id"] for item in sources],
    }], "index_update": {
        "path": ".agent-memory/INDEX.md", "base_sha256": hashlib.sha256(index_before).hexdigest(),
        "content": core._entry("Map", "[D](large.md)", evidence="NONE").decode("utf-8"),
    }})
    with pytest.raises(ValueError, match="promotion record exceeds"):
        core.task_promote(root, "controller", started["revision"], payload)
    assert not (root / ".agent-memory" / "large.md").exists()
    assert (root / ".agent-memory" / "INDEX.md").read_bytes() == index_before


def test_promotion_preflights_exact_document_get_response_with_provenance(tmp_path: Path) -> None:
    root = repo(tmp_path)
    sources = [{"id": f"S{index}", "kind": "repo", "locator": "x" * 4000, "summary": "source"} for index in range(5)]
    started = core.task_start(root, "document response bound", None, write_json(tmp_path / "sources-under.json", {"evidence_refs": sources}))
    payload = write_json(tmp_path / "promotion-under.json", {"records": [{
        "id": "D1", "path": ".agent-memory/under.md", "title": "Under", "text": "body" * 4096,
        "source_refs": [item["id"] for item in sources],
    }]})
    result = core.task_promote(root, "controller", started["revision"], payload)
    raw = (root / result["promoted"][0]).read_bytes()
    fetched = core.document_get(root, result["promoted"][0])
    assert len(raw) < core.EXPLICIT_DOCUMENT_MAX_BYTES
    assert core._document_response_size(fetched) < core.EXPLICIT_DOCUMENT_MAX_BYTES


def test_promotion_rejects_exact_document_get_overflow_before_any_writes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    sources = [{"id": f"S{index}", "kind": "repo", "locator": "x" * 4000, "summary": "source"} for index in range(8)]
    started = core.task_start(root, "document response overflow", None, write_json(tmp_path / "sources-over.json", {"evidence_refs": sources}))
    index_before = (root / ".agent-memory" / "INDEX.md").read_bytes()
    payload = write_json(tmp_path / "promotion-over.json", {"records": [{
        "id": "D1", "path": ".agent-memory/over.md", "title": "Over", "text": "body" * 4096,
        "source_refs": [item["id"] for item in sources],
    }], "index_update": {
        "path": ".agent-memory/INDEX.md", "base_sha256": hashlib.sha256(index_before).hexdigest(),
        "content": core._entry("Map", "unchanged", evidence="NONE").decode("utf-8"),
    }})
    with pytest.raises(ValueError, match="document-get response exceeds"):
        core.task_promote(root, "controller", started["revision"], payload)
    assert not (root / ".agent-memory" / "over.md").exists()
    assert (root / ".agent-memory" / "INDEX.md").read_bytes() == index_before


@pytest.mark.parametrize("later_state", ["MISSING", "CHANGED"])
def test_promotion_reserves_exact_future_freshness_response_boundary(tmp_path: Path, later_state: str) -> None:
    """A worst-case preflight keeps later source churn retrievable at 64 KiB."""
    def setup(root: Path, body: str) -> tuple[list[Path], str]:
        started = core.task_start(root, "future freshness boundary", None, None)
        sources: list[Path] = []
        evidence_refs = []
        for index in range(64):
            source = root / "sources" / ("路径" * 32) / f"証拠-{index:03}.txt"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("stable", encoding="utf-8")
            relative = source.relative_to(root).as_posix()
            sources.append(source)
            evidence_refs.append({
                "id": f"S{index}", "kind": "repo",
                "locator": f"file:{relative}#{hashlib.sha256(source.read_bytes()).hexdigest()}",
                "summary": "long Unicode source path",
            })
        updated = core.task_update(root, "controller", started["revision"], write_json(root.parent / "sources.json", {
            "evidence_refs": evidence_refs,
        }))
        promoted = core.task_promote(root, "controller", updated["revision"], write_json(root.parent / "promotion.json", {
            "records": [{
                "id": "D1", "path": ".agent-memory/边界/near-limit.md", "title": "Boundary",
                "text": body, "source_refs": [item["id"] for item in evidence_refs],
            }],
        }))["promoted"][0]
        return sources, promoted

    # Use a small promoted exemplar to derive the exact public response size,
    # then promote a fresh record whose worst-case reservation is exactly 64 KiB.
    exemplar_root = tmp_path / "exemplar"
    exemplar_root.mkdir()
    sources, path = setup(repo(exemplar_root), "BODY_PRESERVED")
    exemplar = core.document_get(exemplar_root, path)["documents"][0]
    reserved = {**exemplar, "freshness": "MISSING", "freshness_detail": markdown.freshness_detail_budget_placeholder()}
    filler = core.EXPLICIT_DOCUMENT_MAX_BYTES - core._document_response_size({"ok": True, "documents": [reserved]})
    assert core._document_response_size({"ok": True, "documents": [reserved]}) + filler == core.EXPLICIT_DOCUMENT_MAX_BYTES

    root = tmp_path / "boundary"
    root.mkdir()
    sources, path = setup(repo(root), "BODY_PRESERVED" + ("x" * filler))
    fresh = core.document_get(root, path)["documents"][0]
    if later_state == "MISSING":
        for source in sources:
            source.unlink()
    else:
        for source in sources:
            source.write_text("changed", encoding="utf-8")
    fetched = core.document_get(root, path)
    item = fetched["documents"][0]
    assert item["freshness"] == later_state
    assert "BODY_PRESERVED" in item["body"]
    assert item["metadata"] == fresh["metadata"]
    assert item["body"] == fresh["body"]
    assert item["provenance"] == fresh["provenance"]
    assert len(item["provenance"]) == 64
    assert item["metadata"]["Evidence"] == "DURABLE_SOURCE_DESCRIPTORS"
    assert item["provenance"][0]["locator"].startswith("file:sources/路径")
    assert len(json.dumps(item["freshness_detail"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 1800
    assert core._document_response_size(fetched) <= core.EXPLICIT_DOCUMENT_MAX_BYTES


def test_promotion_index_update_rejects_stale_task_revision(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "stale promotion", None, None)
    core.task_update(root, "controller", started["revision"], write_json(tmp_path / "update.json", {
        "records": [{"id": "R1", "kind": "note", "text": "advance revision"}],
    }))
    index = root / ".agent-memory" / "INDEX.md"
    promotion = write_json(tmp_path / "stale-promotion.json", {
        "records": [{"id": "D1", "path": ".agent-memory/custom/d.md", "text": "body"}],
        "index_update": {
            "path": ".agent-memory/INDEX.md",
            "base_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
            "content": core._entry("Memory", "[D](custom/d.md)", evidence="NONE").decode("utf-8"),
        },
    })
    with pytest.raises(ValueError, match="task revision conflict"):
        core.task_promote(root, "controller", started["revision"], promotion)
    assert not (root / ".agent-memory" / "custom" / "d.md").exists()


def test_promoted_provenance_survives_task_state_and_round_trips(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "promotion provenance", None, write_json(root.parent / "sources.json", {
        "evidence_refs": [
            {"id": "source-0", "kind": "repository", "locator": "src/base.py#root", "summary": "root source"},
            {
                "id": "source-1", "kind": "repository", "locator": "src/module.py#symbol",
                "summary": "source", "source_refs": ["source-0"],
            },
        ],
    }))
    artifact_path = root / "details.md"
    artifact_path.write_text("artifact details", encoding="utf-8")
    registered = core.task_artifact(
        root, started["revision"], "artifact-7", "details.md", "details",
        producer="investigator", evidence_refs=["source-1"],
    )
    promotion = write_json(root.parent / "durable.json", {"records": [{
        "id": "durable-decision",
        "path": ".agent-memory/architecture/durable-decision.md",
        "title": "Durable decision",
        "text": "Keep this conclusion",
        "source_refs": ["artifact-7"],
        "status": "accepted",
    }]})
    result = core.task_promote(root, "controller", registered["revision"], promotion)
    durable_path = result["promoted"][0]
    (root / ".context" / "state.json").unlink()

    fetched = core.document_get(root, durable_path)["documents"][0]
    assert "artifact-7" in fetched["body"]
    assert "details.md" in fetched["body"]
    assert hashlib.sha256(b"artifact details").hexdigest() in fetched["body"]
    assert started["task_id"] in fetched["body"]
    assert "source-1" in fetched["body"]
    assert "src/module.py#symbol" in fetched["body"]
    assert "source-0" in fetched["body"]
    assert "src/base.py#root" in fetched["body"]
    assert fetched["freshness"] == "PARTIAL"
    artifact_path.write_text("changed artifact details", encoding="utf-8")
    assert core.document_get(root, durable_path)["documents"][0]["freshness"] == "CHANGED"
    artifact_path.unlink()
    assert core.document_get(root, durable_path)["documents"][0]["freshness"] == "MISSING"


def test_durable_freshness_distinguishes_fresh_and_recorded(tmp_path: Path) -> None:
    fresh_root = repo(tmp_path / "fresh")
    started = core.task_start(fresh_root, "fresh durable", None, None)
    (fresh_root / "artifact.md").write_text("stable", encoding="utf-8")
    registered = core.task_artifact(fresh_root, started["revision"], "a1", "artifact.md", "stable")
    promoted = write_json(tmp_path / "fresh-promotion.json", {"records": [{
        "id": "fresh", "path": ".agent-memory/custom/fresh.md", "title": "Fresh", "text": "fresh", "source_refs": ["a1"],
    }]})
    fresh_path = core.task_promote(fresh_root, "controller", registered["revision"], promoted)["promoted"][0]
    assert core.document_get(fresh_root, fresh_path)["documents"][0]["freshness"] == "FRESH"

    recorded_root = repo(tmp_path / "recorded")
    recorded_started = core.task_start(recorded_root, "recorded durable", None, write_json(tmp_path / "recorded-source.json", {
        "evidence_refs": [{"id": "s1", "kind": "external", "locator": "ticket-17", "summary": "recorded only"}],
    }))
    recorded_promotion = write_json(tmp_path / "recorded-promotion.json", {"records": [{
        "id": "recorded", "path": ".agent-memory/custom/recorded.md", "title": "Recorded", "text": "recorded", "source_refs": ["s1"],
    }]})
    recorded_path = core.task_promote(
        recorded_root, "controller", recorded_started["revision"], recorded_promotion,
    )["promoted"][0]
    assert core.document_get(recorded_root, recorded_path)["documents"][0]["freshness"] == "RECORDED"


@pytest.mark.parametrize("field,value", [
    ("kind", "bad\nkind"),
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
    record = {"id": "invalid", "path": ".agent-memory/custom/invalid.md", "kind": "decision", "title": "Title", "text": "body", field: value}
    promotion = write_json(root.parent / "invalid.json", {"records": [record]})
    with pytest.raises(ValueError):
        core.task_promote(root, "controller", started["revision"], promotion)
    assert not (root / ".agent-memory" / "custom" / "invalid.md").exists()


def test_verification_source_refs_survive_and_affect_result_identity(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "verification provenance", None, write_json(root.parent / "sources.json", {
        "evidence_refs": [{"id": "source-1", "kind": "repo", "locator": "src/a.py", "summary": "source"}],
    }))
    observed = core.task_record_verification(
        root, started["revision"], "verify-1", "test", "PASSED", "observed",
        source_refs=["source-1"], observed_by="native-tool",
    )
    result = core.task_show(root)["state"]["verification_results"][0]
    assert observed["revision"] == started["revision"] + 1
    assert result["source_refs"] == ["source-1"]
    material = {key: result[key] for key in (
        "id", "kind", "outcome", "summary", "source_refs", "observed_by",
        "candidate_identity", "observed_files",
    )}
    assert result["result_hash"] == hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_task_artifact_cli_accepts_repeatable_source_refs(tmp_path: Path, capsys) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "artifact cli", None, write_json(root.parent / "sources.json", {
        "evidence_refs": [
            {"id": "s0", "kind": "repo", "locator": "src/a.py", "summary": "a"},
            {"id": "s1", "kind": "repo", "locator": "src/b.py", "summary": "b"},
        ],
    }))
    (root / "artifact.md").write_text("details", encoding="utf-8")
    exit_code = cli.main([
        "--root", str(root), "task-artifact", "--base-revision", str(started["revision"]),
        "--id", "artifact-cli", "--path", "artifact.md", "--summary", "details",
        "--source-ref", "s0", "--source-ref", "s1",
    ])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert core.task_show(root)["state"]["artifact_refs"][0]["source_refs"] == ["s0", "s1"]


def test_record_artifact_and_promotion_ids_are_unique(tmp_path: Path) -> None:
    duplicate_records_root = repo(tmp_path / "records")
    duplicate_records = write_json(tmp_path / "duplicate-records.json", {"records": [
        {"id": "same", "kind": "note", "text": "one"},
        {"id": "same", "kind": "note", "text": "two"},
    ]})
    with pytest.raises(ValueError, match="duplicate task record id"):
        core.task_start(duplicate_records_root, "duplicates", None, duplicate_records)

    root = repo(tmp_path / "other-ids")
    started = core.task_start(root, "other ids", None, None)
    (root / "a.md").write_text("a", encoding="utf-8")
    first = core.task_artifact(root, started["revision"], "same-artifact", "a.md", "a")
    with pytest.raises(ValueError, match="task object id already exists"):
        core.task_artifact(root, first["revision"], "same-artifact", "a.md", "again")

    duplicate_promotions = write_json(tmp_path / "duplicate-promotions.json", {"records": [
            {"id": "same-promotion", "path": ".agent-memory/custom/one.md", "title": "One", "text": "one"},
            {"id": "same-promotion", "path": ".agent-memory/custom/two.md", "title": "Two", "text": "two"},
    ]})
    with pytest.raises(ValueError, match="duplicate promotion id"):
        core.task_promote(root, "controller", first["revision"], duplicate_promotions)
    assert not (root / ".agent-memory" / "custom" / "one.md").exists()


def test_task_object_ids_are_unique_across_object_kinds(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "cross-kind ids", None, write_json(tmp_path / "initial.json", {
        "evidence_refs": [{"id": "S1", "kind": "repo", "locator": "src/a.py", "summary": "a"}],
        "records": [{"id": "R1", "kind": "note", "text": "record"}],
    }))
    (root / "artifact.md").write_text("body", encoding="utf-8")
    for collision in ("R1", "S1"):
        with pytest.raises(ValueError, match="task object id already exists"):
            core.task_artifact(root, started["revision"], collision, "artifact.md", "artifact")

    promotion = write_json(tmp_path / "collision-promotion.json", {"records": [{
        "id": "R1", "path": ".agent-memory/custom/collision.md", "title": "Collision", "text": "body",
    }]})
    with pytest.raises(ValueError, match="promotion id conflicts with task object"):
        core.task_promote(root, "controller", started["revision"], promotion)


def test_artifact_provenance_is_validated_while_loading_state(tmp_path: Path) -> None:
    root = repo(tmp_path / "unknown")
    started = core.task_start(root, "bad artifact provenance", None, None)
    (root / "artifact.md").write_text("body", encoding="utf-8")
    core.task_artifact(root, started["revision"], "A1", "artifact.md", "artifact")
    path = root / ".context" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["artifact_refs"][0]["source_refs"] = ["missing"]
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact source reference is unknown"):
        core.task_show(root)
    assert lifecycle_module.managed_task_state(root)[0] == "INVALID_STATE"

    legacy_root = repo(tmp_path / "legacy")
    started = core.task_start(legacy_root, "legacy provenance", None, None)
    (legacy_root / "artifact.md").write_text("body", encoding="utf-8")
    core.task_artifact(legacy_root, started["revision"], "A1", "artifact.md", "artifact")
    path = legacy_root / ".context" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["artifact_refs"][0]["evidence_refs"] = state["artifact_refs"][0].pop("source_refs")
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid artifact reference"):
        core.task_show(legacy_root)


def test_git_rename_uses_destination_as_current_surface_path(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "old.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], cwd=root, check=True)
    subprocess.run(["git", "mv", "old.py", "new.py"], cwd=root, check=True)
    surface = core._surface_snapshot(root)
    assert isinstance(surface, list)
    assert [item["path"] for item in surface] == ["new.py"]


def test_task_get_and_artifact_get_return_only_the_selected_object(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "bounded retrieval", None, write_json(tmp_path / "objects.json", {
        "records": [
            {"id": "R1", "kind": "note", "text": "selected body"},
            {"id": "R2", "kind": "note", "text": "unselected sentinel"},
        ],
    }))
    selected = core.task_get(root, "R1")
    assert selected["object"]["text"] == "selected body"
    assert "unselected sentinel" not in json.dumps(selected)

    (root / "artifact.md").write_text("artifact body", encoding="utf-8")
    core.task_artifact(root, started["revision"], "A1", "artifact.md", "artifact")
    fetched = core.artifact_get(root, "A1")
    assert fetched["body"] == "artifact body"
    assert fetched["object_type"] == "artifact"


def test_artifact_get_checks_stat_bound_before_read(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "artifact bound", None, None)
    artifact = root / "large.md"
    artifact.write_bytes(b"x" * (core.EXPLICIT_DOCUMENT_MAX_BYTES + 1))
    core.task_artifact(root, started["revision"], "A1", "large.md", "large")
    monkeypatch.setattr(Path, "read_bytes", lambda _self: (_ for _ in ()).throw(AssertionError("read guard invoked")))
    with pytest.raises(ValueError, match="artifact body exceeds"):
        core.artifact_get(root, "A1")


def test_root_index_is_canonical_global_map_without_recursive_scan(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    target = root / ".agent-memory" / "projects" / "alpha" / "guide.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(core._entry("Guide", "TARGET_BODY", evidence="NONE"))
    (root / ".agent-memory" / "INDEX.md").write_bytes(core._entry(
        "Global memory map",
        "Projects: [Alpha guide](projects/alpha/guide.md) — implementation routing.",
        evidence="NONE",
    ))

    def no_recursive_scan(*args, **kwargs):
        raise AssertionError("catalog must not recursively scan the durable tree")

    monkeypatch.setattr(Path, "rglob", no_recursive_scan)
    discovered = core.catalog(root)
    encoded = json.dumps(discovered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert discovered["canonical_source"] == "INDEX.md"
    assert "projects/alpha/guide.md" in encoded.decode("utf-8")
    assert "TARGET_BODY" not in encoded.decode("utf-8")

    fetched = core.document_get(root, [".agent-memory/projects/alpha/guide.md"])
    assert len(fetched["documents"]) == 1
    assert "TARGET_BODY" in fetched["documents"][0]["body"]
    with pytest.raises(ValueError, match="durable path"):
        core.document_get(root, "README.md")


def test_catalog_keeps_reasonably_large_root_map_and_reports_hard_oversize(tmp_path: Path) -> None:
    root = repo(tmp_path)
    index = root / ".agent-memory" / "INDEX.md"
    body = "Thin global route\n\n" + ("routing-hint " * 300)
    index.write_bytes(core._entry("Global map", body, evidence="NONE"))
    assert index.stat().st_size > core.DURABLE_INDEX_RECOMMENDED_BYTES
    result = core.catalog(root)
    memory = result["indexes"][0]
    assert memory["state"] == "VALID"
    assert "Thin global route" in memory["map"]
    assert "map_omitted" not in memory

    index.write_bytes(core._entry(
            "Global map", "route " * (core.DURABLE_INDEX_HARD_MAX_BYTES // 4), evidence="NONE",
    ))
    result = core.catalog(root)
    assert result["ok"] is False
    assert result["indexes"][0]["state"] == "INDEX_OVERSIZED"
    assert "map" not in result["indexes"][0]
    assert "INDEX_OVERSIZED" in result["errors"][0]


def test_init_creates_only_durable_entrypoints_without_taxonomy(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert (root / ".agent-memory" / "INDEX.md").is_file()
    assert (root / ".milestones" / "INDEX.md").is_file()
    for imposed in (
        ".agent-memory/decisions",
        ".agent-memory/lessons",
        ".agent-memory/runtime",
        ".milestones/M001-name",
    ):
        assert not (root / imposed).exists()


def test_document_get_batches_only_selected_paths_and_enforces_total_size(tmp_path: Path) -> None:
    root = repo(tmp_path)
    durable = root / ".agent-memory" / "custom"
    durable.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (durable / f"{name}.md").write_bytes(core._entry(name.upper(), f"BODY_{name.upper()}", evidence="NONE"))
    fetched = core.document_get(root, [
        ".agent-memory/custom/a.md",
        ".agent-memory/custom/c.md",
    ])
    serialized = json.dumps(fetched)
    assert [item["path"] for item in fetched["documents"]] == [
        ".agent-memory/custom/a.md",
        ".agent-memory/custom/c.md",
    ]
    assert "BODY_A" in serialized and "BODY_C" in serialized and "BODY_B" not in serialized

    for name in ("large-1", "large-2"):
        (durable / f"{name}.md").write_bytes(core._entry(name, "x" * 40_000, evidence="NONE"))
    with pytest.raises(ValueError, match="response exceeds"):
        core.document_get(root, [
            ".agent-memory/custom/large-1.md",
            ".agent-memory/custom/large-2.md",
        ])

    too_large = durable / "too-large.md"
    too_large.write_bytes(b"x" * (core.EXPLICIT_DOCUMENT_MAX_BYTES + 1))
    with pytest.raises(ValueError, match="durable document exceeds"):
        core.document_get(root, ".agent-memory/custom/too-large.md")


def test_document_get_preserves_memory_freshness_and_provenance(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "durable retrieval", None, None)
    (root / "artifact.md").write_text("stable", encoding="utf-8")
    registered = core.task_artifact(root, started["revision"], "A1", "artifact.md", "stable")
    promotion = write_json(tmp_path / "promotion.json", {"records": [{
            "id": "D1", "path": ".agent-memory/model-tree/decision.md", "title": "Decision", "text": "selected", "source_refs": ["A1"],
    }]})
    path = core.task_promote(root, "controller", registered["revision"], promotion)["promoted"][0]
    item = core.document_get(root, path)["documents"][0]
    assert item["freshness"] == "FRESH"
    assert item["freshness_detail"] == []
    assert item["metadata"]["Evidence"] == "DURABLE_SOURCE_DESCRIPTORS"
    assert item["provenance"][0]["artifact_id"] == "A1"


@pytest.mark.parametrize("state", ["missing", "changed"])
def test_document_get_bounds_adversarial_durable_freshness_detail(tmp_path: Path, state: str) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "bounded freshness detail", None, None)
    sources = []
    source_paths = []
    for index in range(64):
        path = root / "sources" / ("p" * 160) / f"{index:03}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stable", encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        sources.append({"id": f"S{index}", "kind": "repo", "locator": f"file:{relative}#{hashlib.sha256(path.read_bytes()).hexdigest()}",
                        "summary": "adversarial source"})
        source_paths.append(relative)
    registered = core.task_update(root, "controller", started["revision"], write_json(tmp_path / "sources.json", {"evidence_refs": sources}))
    promoted = core.task_promote(root, "controller", registered["revision"], write_json(tmp_path / "promotion.json", {"records": [{
        "id": "D1", "path": ".agent-memory/bounded.md", "title": "Bounded", "text": "BODY_PRESERVED", "source_refs": [item["id"] for item in sources],
    }]}))["promoted"][0]
    if state == "missing":
        for relative in source_paths:
            (root / relative).unlink()
        expected = "MISSING"
    else:
        for relative in source_paths:
            (root / relative).write_text("changed", encoding="utf-8")
        expected = "CHANGED"
    first = core.document_get(root, promoted)["documents"][0]
    second = core.document_get(root, promoted)["documents"][0]
    assert first == second
    assert first["freshness"] == expected
    assert len(json.dumps(first["freshness_detail"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= markdown.FRESHNESS_DETAIL_MAX_BYTES
    assert "BODY_PRESERVED" in first["body"]
    assert len(first["provenance"]) == len(sources)
    assert core._document_response_size({"ok": True, "documents": [first]}) <= core.EXPLICIT_DOCUMENT_MAX_BYTES


def test_broken_index_reference_is_mechanically_reported(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / ".agent-memory" / "INDEX.md").write_bytes(core._entry(
            "Memory map", "- [Missing](model-chosen/missing.md)", evidence="NONE",
    ))
    result = core.catalog(root)
    assert result["ok"] is False
    assert result["indexes"][0]["state"] == "BROKEN_REFERENCES"
    assert "missing link target" in result["errors"][0]


def test_explicit_integrity_check_follows_deep_index_links_with_cycle_protection(tmp_path: Path) -> None:
    root = repo(tmp_path)
    memory = root / ".agent-memory"
    (memory / "area" / "deep").mkdir(parents=True)
    (memory / "INDEX.md").write_bytes(core._entry("Root", "[Area](area/INDEX.md)", evidence="NONE"))
    (memory / "area" / "INDEX.md").write_bytes(core._entry(
        "Area", "[Root](../INDEX.md)\n[Deep](deep/INDEX.md)", evidence="NONE",
    ))
    (memory / "area" / "deep" / "INDEX.md").write_bytes(core._entry(
        "Deep", "[Missing](deleted.md)", evidence="NONE",
    ))

    # Normal catalog/SessionStart work validates only the root map.
    assert core.catalog(root)["indexes"][0]["state"] == "VALID"
    checked = core.durable_index_check(root, [".agent-memory/INDEX.md"])
    assert checked["ok"] is False
    assert len(checked["checked"]) == 3
    assert any("deleted.md" in error for error in checked["errors"])


def test_explicit_integrity_check_follows_directory_links_to_nested_indexes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    memory = root / ".agent-memory"
    (memory / "area" / "deep").mkdir(parents=True)
    (memory / "INDEX.md").write_bytes(core._entry("Root", "[Area](area/)", evidence="NONE"))
    (memory / "area" / "INDEX.md").write_bytes(core._entry("Area", "[Deep](deep/INDEX.md)", evidence="NONE"))
    (memory / "area" / "deep" / "INDEX.md").write_bytes(core._entry("Deep", "[Missing](missing.md)", evidence="NONE"))

    assert core.catalog(root)["indexes"][0]["state"] == "VALID"
    checked = core.durable_index_check(root, [".agent-memory/INDEX.md"])
    assert checked["ok"] is False
    assert checked["checked"] == [
        ".agent-memory/INDEX.md",
        ".agent-memory/area/INDEX.md",
        ".agent-memory/area/deep/INDEX.md",
    ]
    assert any("missing.md" in error for error in checked["errors"])
    assert core.catalog(root)["indexes"][0]["state"] == "VALID"


def test_git_status_failure_is_reported_as_unavailable(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)

    class FailedStatus:
        returncode = 1
        stdout = b""

    monkeypatch.setattr(core.subprocess, "run", lambda *args, **kwargs: FailedStatus())
    assert core._surface_snapshot(root) == "UNAVAILABLE"
    assert core._surface_delta(root, [])["status"] == "UNAVAILABLE"

    def unavailable_git(*args, **kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(core.subprocess, "run", unavailable_git)
    assert core._surface_snapshot(root) == "UNAVAILABLE"


def test_task_start_degrades_large_dirty_surface_to_unavailable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    bulk = root / "bulk"
    bulk.mkdir()
    for index in range(core.SURFACE_MAX_ENTRIES + 1):
        (bulk / f"file-{index}.txt").write_text("x", encoding="utf-8")
    started = core.task_start(root, "large dirty surface", None, None)
    assert started["status"] == "ACTIVE"
    assert core.task_show(root)["state"]["task_surface_baseline"] == "UNAVAILABLE"


def test_small_dirty_surface_remains_recorded(tmp_path: Path) -> None:
    root = repo(tmp_path)
    path = root / "small.txt"
    path.write_text("small", encoding="utf-8")
    surface = core._surface_snapshot(root)
    assert isinstance(surface, list)
    item = next(item for item in surface if item["path"] == "small.txt")
    assert item["state"] == "FILE"
    assert item["identity"] == hashlib.sha256(b"small").hexdigest()


def test_large_surface_file_stat_degrades_whole_snapshot_without_hash(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    path = root / "large.txt"
    path.write_text("small placeholder", encoding="utf-8")
    original_stat = core.os.stat

    def large_stat(candidate: object, *args: object, **kwargs: object):
        result = original_stat(candidate, *args, **kwargs)
        if "large" in str(candidate):
            return type("Stat", (), {"st_size": core.SURFACE_MAX_FILE_BYTES + 1, "st_mode": result.st_mode})()
        return result

    monkeypatch.setattr(core.os, "stat", large_stat)
    monkeypatch.setattr(core, "_file_digest", lambda _path: (_ for _ in ()).throw(AssertionError("large file hashed")))
    assert core._surface_snapshot(root) == "UNAVAILABLE"
    assert core.task_start(root, "large file surface", None, None)["status"] == "ACTIVE"


def test_surface_identity_hashes_regular_files_streaming(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    path = root / "streamed.bin"
    path.write_bytes(b"streamed identity")

    def reject_bulk_read(_path: Path):
        raise AssertionError("surface identity must hash through chunks")

    monkeypatch.setattr(Path, "read_bytes", reject_bulk_read)
    identity = core._surface_identity(root, "streamed.bin", "??")
    assert identity["identity"] == hashlib.sha256(b"streamed identity").hexdigest()


def test_final_durable_symlink_is_rejected_while_surface_observes_it(tmp_path: Path) -> None:
    root = repo(tmp_path)
    source = root / "source.md"
    source.write_bytes(core._entry("Source", "body", evidence="NONE"))
    link = root / ".agent-memory" / "x.md"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="durable document not found"):
        core.document_get(root, ".agent-memory/x.md")
    observed = core._surface_identity(root, ".agent-memory/x.md", "??")
    assert observed["state"] == "SYMLINK"


def test_promotion_and_maintenance_never_follow_final_memory_symlink(tmp_path: Path) -> None:
    root = repo(tmp_path)
    target = root / "outside.md"
    target.write_bytes(core._entry("Outside", "body", evidence="NONE"))
    link = root / ".agent-memory" / "linked.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    started = core.task_start(root, "symlink promotion", None, None)
    with pytest.raises(ValueError, match="final component"):
        core.task_promote(root, "controller", started["revision"], write_json(tmp_path / "promotion.json", {
            "records": [{"id": "D1", "path": ".agent-memory/linked.md", "text": "new"}],
        }))
    assert all(entry.path != link for entry in core.entries(root))
    assert all(item["path"] != ".agent-memory/linked.md" for item in core.stale(root)["entries"])


def test_promoted_artifact_provenance_treats_swapped_final_symlink_as_missing(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "provenance symlink", None, None)
    artifact = root / "artifact.md"
    artifact.write_text("stable", encoding="utf-8")
    registered = core.task_artifact(root, started["revision"], "A1", "artifact.md", "artifact")
    promoted = core.task_promote(root, "controller", registered["revision"], write_json(tmp_path / "promotion.json", {
        "records": [{"id": "D1", "path": ".agent-memory/d1.md", "text": "selected", "source_refs": ["A1"]}],
    }))["promoted"][0]
    replacement = root / "replacement.md"
    replacement.write_text("stable", encoding="utf-8")
    try:
        artifact.unlink(); artifact.symlink_to(replacement)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert core.document_get(root, promoted)["documents"][0]["freshness"] == "MISSING"


def test_artifact_final_symlink_is_rejected_for_register_get_and_freshness(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "artifact symlink", None, None)
    source = root / "artifact.md"
    source.write_text("artifact", encoding="utf-8")
    link = root / "artifact-link.md"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="artifact path must name"):
        core.task_artifact(root, started["revision"], "bad", "artifact-link.md", "bad")

    registered = core.task_artifact(root, started["revision"], "good", "artifact.md", "good")
    source.unlink()
    source.symlink_to(link)
    artifact = core.task_show(root)["state"]["artifact_refs"][0]
    assert core._artifact_freshness(root, artifact) == "MISSING"
    with pytest.raises(ValueError, match="artifact body not found"):
        core.artifact_get(root, "good")


def test_index_final_symlink_is_rejected_by_catalog_and_integrity_check(tmp_path: Path) -> None:
    root = repo(tmp_path)
    target = root / "real-index.md"
    target.write_bytes(core._entry("Real", "map", evidence="NONE"))
    link = root / ".agent-memory" / "INDEX.md"
    try:
        link.unlink()
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    catalog = core.catalog(root, ".agent-memory")
    assert catalog["indexes"][0]["state"] == "MISSING"
    checked = core.durable_index_check(root, [".agent-memory/INDEX.md"])
    assert checked["ok"] is False
    assert any("final component" in error for error in checked["errors"])


def test_legacy_metadata_is_opaque_to_exact_retrieval(tmp_path: Path) -> None:
    root = repo(tmp_path)
    path = root / ".agent-memory" / "review-only.md"
    path.write_text("---\nEvidence: NONE\nRevision: 1\nStatus: ACTIVE\nAudience: [\"reviewer\"]\nTopics: [\"routing\"]\nSymbols: [\"module.symbol\"]\nApplicability: PROJECT\nConfidence: SUPPORTED\nKind: record\n---\n\n# Review hint\n\nEXPLICIT_MEMORY_SENTINEL\n", encoding="utf-8")
    assert "EXPLICIT_MEMORY_SENTINEL" in core.document_get(root, ".agent-memory/review-only.md")["documents"][0]["body"]


def test_legacy_config_is_ignored_and_new_durable_documents_are_minimal(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / ".context" / "config.json").write_text(json.dumps({
        "schema_version": 1,
        "automatic_injection": True,
        "automatic_compression": True,
        "adapter_probes": True,
        "adapters": {"serena": True},
    }), encoding="utf-8")
    assert codex_adapter.doctor(root)["context"]["config"] == "YES"
    created = root / ".agent-memory" / "minimal.md"
    created.write_bytes(core._entry("Minimal", "body"))
    document = core.document_get(root, ".agent-memory/minimal.md")["documents"][0]
    assert set(document["metadata"]) == {"Evidence", "Revision"}


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
        producer="investigator", evidence_refs=["source-1"],
    )
    second_path = root / "second.md"
    second_path.write_text("second body", encoding="utf-8")
    second = core.task_artifact(
        root, first["revision"], "a2", "second.md", "replacement",
        producer="curator", supersedes=["a1"],
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
                "source_refs": [],
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
