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
