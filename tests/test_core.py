from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from thaliris import core
from thaliris.cli import main


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
