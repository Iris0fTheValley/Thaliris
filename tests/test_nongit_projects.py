from pathlib import Path
import hashlib
import subprocess

import pytest

from thaliris import core, markdown


@pytest.mark.parametrize("git_missing", [False, True])
def test_explicit_nongit_project_supports_task_lifecycle(tmp_path, monkeypatch, git_missing):
    root = tmp_path / "project"
    root.mkdir()
    notes = root / "notes.txt"
    notes.write_bytes(b"user-owned\r\n")
    if git_missing:
        def unavailable(*args, **kwargs):
            raise FileNotFoundError("git is unavailable")
        monkeypatch.setattr(core.subprocess, "run", unavailable)

    assert core.init(root)["ok"]
    started = core.task_start(root, "Explicit project", None, None)
    assert started["status"] == "ACTIVE"
    state = core.task_show(root)["state"]
    assert state["task_base_head"] is None
    assert state["task_surface_baseline"] == "UNAVAILABLE"
    assert core._surface_delta(root, state["task_surface_baseline"])["status"] == "UNAVAILABLE"
    entry = markdown.Entry(root / "entry.md", {"Evidence": "git:notes.txt#" + "a" * 40}, "")
    assert markdown.evidence_status(entry, root)[0] == "UNKNOWN"
    file_entry = markdown.Entry(entry.path, {"Evidence": "file:notes.txt#" + hashlib.sha256(notes.read_bytes()).hexdigest()}, "")
    assert markdown.evidence_status(file_entry, root)[0] == "FRESH"
    assert core.task_close(root, started["revision"], expected_task_id=started["task_id"])["status"] == "DONE"
    assert notes.read_bytes() == b"user-owned\r\n"
    assert not (root / ".git").exists()
    assert not (tmp_path / ".context").exists()


def test_git_root_validation_and_ignore_requirement_remain_exact(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    nested = tmp_path / "nested"
    nested.mkdir()
    assert core._repo_root(tmp_path) == tmp_path.resolve()
    with pytest.raises(ValueError, match="git repository root"):
        core.init(nested)
    with pytest.raises(ValueError, match="not ignored"):
        core.task_start(tmp_path, "uninitialized Git root", None, None)
    core.init(tmp_path)
    assert core.task_start(tmp_path, "initialized Git root", None, None)["status"] == "ACTIVE"


@pytest.mark.parametrize("metadata_kind", ["broken_worktree", "corrupt_config", "bare_repository"])
def test_git_metadata_with_failed_discovery_stays_unknown(tmp_path, monkeypatch, metadata_kind):
    root = tmp_path / "project"
    root.mkdir()
    if metadata_kind == "broken_worktree":
        (root / ".git").write_text("gitdir: missing-worktree-metadata\n", encoding="utf-8")
    elif metadata_kind == "corrupt_config":
        git_dir = root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[broken\n", encoding="utf-8")
    else:
        (root / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (root / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
        (root / "objects").mkdir()

    def discovery_failure(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 128, "", "fatal: metadata could not be read")

    monkeypatch.setattr(core.subprocess, "run", discovery_failure)
    with pytest.raises(ValueError, match="UNKNOWN"):
        core._repo_root(root)
    with pytest.raises(ValueError, match="UNKNOWN"):
        core.task_start(root, "must not be admitted", None, None)
    assert not (root / ".context").exists()


def test_unexpected_git_discovery_error_does_not_start_nongit_task(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    note = root / "notes.txt"
    note.write_bytes(b"user-owned\n")

    def transient_failure(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 128, "", "fatal: transient discovery error")

    monkeypatch.setattr(core.subprocess, "run", transient_failure)
    entry = markdown.Entry(root / "entry.md", {"Evidence": "git:notes.txt#" + "a" * 40}, "")
    assert markdown.evidence_status(entry, root)[0] == "UNKNOWN"
    with pytest.raises(ValueError, match="UNKNOWN"):
        core.task_start(root, "must not be admitted", None, None)
    assert not (root / ".context").exists()


def test_missing_git_executable_with_repository_metadata_stays_unknown(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git is unavailable")

    monkeypatch.setattr(core.subprocess, "run", unavailable)
    with pytest.raises(ValueError, match="UNKNOWN"):
        core.task_start(tmp_path, "must not be admitted", None, None)
    assert not (tmp_path / ".context").exists()


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_invalid_root_does_not_create_project_state(tmp_path, kind):
    root = tmp_path / kind
    if kind == "file":
        root.write_bytes(b"keep")
    with pytest.raises((OSError, ValueError)):
        core.init(root)
    assert not (tmp_path / ".context").exists()
    assert not (tmp_path / ".git").exists()
