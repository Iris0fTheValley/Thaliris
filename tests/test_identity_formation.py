"""Natural Project Identity formation: basis notes, suggestion preferences and the one-time offer.

Every test runs with a private THALIRIS_HOME (tests/conftest.py); nothing touches the
real ~/.thaliris, and nothing new is written inside the repository.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from thaliris import cli, core, errors, identity, identity_basis

NS = ".project-identity"
TEXT_V1 = """# Example identity

## ID-1 Identity
We build a reliable ledger.
"""


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    core.init(path)
    return path.resolve()


def home() -> Path:
    return Path(os.environ["THALIRIS_HOME"]).resolve()


def note(root: Path, quote: str = "This project exists to keep a reliable ledger.", **extra: object) -> dict[str, object]:
    return identity_basis.identity_note(root, "controller:1", {"quote": quote, **extra})


def establish(root: Path) -> None:
    task = core.task_start(root, "identity work", None, None)
    core.select_task(root, task["task_id"])
    identity.identity_amend(root, "controller:1", task["revision"], {
        "base_version": 0, "base_sha256": None, "text": TEXT_V1, "summary": "establish", "rationale": "owner decided",
        "decision": {"decided_by": "owner", "human_instruction": "Record this."}})
    core.task_close(root, core.task_show(root)["state"]["revision"])
    core.select_task(root, None)


def key(path: Path) -> str:
    text = str(path.resolve())
    return hashlib.sha256((text.casefold() if os.name == "nt" else text).encode("utf-8")).hexdigest()


def tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(root).parts}


# ---------------------------------------------------------------------------
# Basis notes


def test_add_list_retract_and_pending_advances_with_amendment(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    first = note(root, kind="purpose", context="user described the purpose", refs=["path:docs/vision.md", "url:https://e.x"])
    record = first["note"]
    assert first["ok"] and first["pending"] and first["task_id"] is None
    assert record["id"] == "N-0001" and record["identity_version"] == 0 and record["kind"] == "purpose"
    assert record["format"] == identity_basis.NOTE_FORMAT and record["actor"] == "controller:1"
    assert set(record) == set(identity_basis._NOTE_FIELDS)

    task = core.task_start(root, "work", None, None)
    core.select_task(root, task["task_id"])
    second = note(root, "Never become a hosting product.", kind="non-goal")
    assert second["note"]["id"] == "N-0002" and second["note"]["task_id"] == task["task_id"]
    assert second["note"]["kind"] == "non-goal" and second["note"]["context"] is None and second["note"]["refs"] == []
    core.task_close(root, task["revision"])
    # A selected task that is no longer ACTIVE is not recorded (and not required).
    third = note(root, "Default kind is other.")
    assert third["note"]["task_id"] is None and third["note"]["kind"] == "other"
    core.select_task(root, None)

    listed = identity_basis.identity_note_list(root)
    assert [entry["id"] for entry in listed["notes"]] == ["N-0001", "N-0002", "N-0003"]
    assert all(entry["pending"] and not entry["retracted"] for entry in listed["notes"])
    assert listed["basis"] == {"pending": 3, "total": 3, "retracted": 0, "damaged": 0}
    assert listed["identity_state"] == "ABSENT" and "not the user's words" in listed["notice"]

    retracted = identity_basis.identity_note(root, "controller:1", {"retract": "N-0001", "reason": "recorded by mistake"})
    assert retracted["retracted"] == "N-0001" and retracted["basis"]["retracted"] == 1
    assert [entry["id"] for entry in identity_basis.identity_note_list(root)["notes"]] == ["N-0002", "N-0003"]
    full = identity_basis.identity_note_list(root, include_retracted=True)["notes"]
    assert full[0]["retracted"] and not full[0]["pending"] and full[0]["retraction"]["reason"] == "recorded by mistake"
    with pytest.raises(errors.ThalirisError) as exc:
        identity_basis.identity_note(root, "c", {"retract": "N-0001", "reason": "again"})
    assert exc.value.code == errors.IDENTITY_NOTE_ALREADY_RETRACTED
    with pytest.raises(errors.ThalirisError) as exc:
        identity_basis.identity_note(root, "c", {"retract": "N-0099", "reason": "missing"})
    assert exc.value.code == errors.IDENTITY_NOTE_NOT_FOUND

    establish(root)
    assert identity.identity_status(root)["basis"] == {"pending": 0, "total": 3, "retracted": 1, "damaged": 0}
    later = note(root, "Stay single-binary.", kind="constraint")
    assert later["note"]["id"] == "N-0004" and later["note"]["identity_version"] == 1
    listed = identity_basis.identity_note_list(root)
    assert [entry["id"] for entry in listed["notes"] if entry["pending"]] == ["N-0004"]
    assert listed["identity_version"] == 1


def test_note_input_refusals_write_nothing(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    bad = [
        {"quote": "x", "extra": 1},
        {"kind": "purpose"},
        {"quote": ""},
        {"quote": "   \n"},
        {"quote": "a" * (identity_basis.QUOTE_MAX_BYTES + 1)},
        {"quote": "bell\x07"},
        {"quote": "ok", "kind": "vision"},
        {"quote": "ok", "context": "two\nlines"},
        {"quote": "ok", "context": "c" * 301},
        {"quote": "ok", "refs": ["r"] * 17},
        {"quote": "ok", "refs": [1]},
        {"quote": "ok", "refs": ["dup", "dup"]},
        {"quote": "ok", "refs": "path:x"},
        {"retract": "N-0001"},
        {"retract": "N-1", "reason": "r"},
        {"retract": "N-0001", "reason": "r", "quote": "x"},
    ]
    for payload in bad:
        with pytest.raises(errors.ThalirisError) as exc:
            identity_basis.identity_note(root, "c", payload)
        assert exc.value.code == errors.IDENTITY_NOTE_INVALID, payload
    with pytest.raises(ValueError, match="invalid identity actor"):
        identity_basis.identity_note(root, "bad actor", {"quote": "x"})
    assert not home().exists() or not any(home().rglob("N-*.json"))
    exact = note(root, "é" * (identity_basis.QUOTE_MAX_BYTES // 2), context="c" * 300, refs=[f"r{i}" for i in range(16)])
    assert exact["note"]["id"] == "N-0001"
    crlf = note(root, "line one\r\nline two\twith tab")
    assert crlf["note"]["quote"] == "line one\nline two\twith tab"


def test_storage_layout_is_outside_the_repository(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    note(root)
    common = (root / ".git").resolve()
    project = home() / "projects" / key(common)
    assert identity_basis.project_key(root) == key(common)
    assert identity_basis.workspace_key(root) == key(root)
    assert json.loads((project / "identity-basis" / "N-0001.json").read_text(encoding="utf-8"))["id"] == "N-0001"
    meta = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert meta["root"] == str(root) and Path(meta["git_common_dir"]) == common


def test_worktrees_share_the_project_key_and_notes(tmp_path: Path) -> None:
    main = repo(tmp_path / "main")
    git(main, "commit", "-q", "--allow-empty", "-m", "init")
    worktree = tmp_path / "wt"
    git(main, "worktree", "add", "-q", str(worktree))
    worktree = worktree.resolve()
    assert identity_basis.project_key(worktree) == identity_basis.project_key(main)
    assert identity_basis.workspace_key(worktree) != identity_basis.workspace_key(main)
    note(main, "Shared across worktrees.")
    listed = identity_basis.identity_note_list(worktree)
    assert [entry["quote"] for entry in listed["notes"]] == ["Shared across worktrees."]
    identity_basis.identity_suggest(worktree, "c", "workspace", "off")
    assert identity_basis.identity_suggest(main, "c", "project", "on")["suggestions"] == {"enabled": True, "source": "project"}
    assert identity.identity_status(worktree)["suggestions"] == {"enabled": False, "source": "workspace"}


def test_non_git_and_git_unavailable_fall_back_to_the_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert identity_basis.project_key(plain) == identity_basis.workspace_key(plain) == key(plain)
    note(plain, "Works outside Git too.")
    assert identity_basis.identity_note_list(plain)["basis"]["total"] == 1
    root = repo(tmp_path / "p")
    monkeypatch.setattr(identity_basis, "_git_common_dir", lambda _root: None)
    assert identity_basis.project_key(root) == key(root)


def test_home_defaults_to_dot_thaliris_under_the_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "fakehome"
    monkeypatch.delenv("THALIRIS_HOME")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    assert identity_basis.thaliris_home() == (fake / ".thaliris").resolve()
    monkeypatch.setenv("THALIRIS_HOME", "")
    assert identity_basis.thaliris_home() == (fake / ".thaliris").resolve()
    monkeypatch.setenv("THALIRIS_HOME", str(tmp_path / "custom"))
    root = repo(tmp_path / "p")
    note(root)
    assert any((tmp_path / "custom").rglob("N-0001.json")) and not fake.exists()


# ---------------------------------------------------------------------------
# Suggestion preferences


def test_preference_precedence_and_clear(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")

    def resolved(session: str | None = None) -> dict[str, object]:
        return identity.identity_status(root, session_key=session)["suggestions"]

    assert resolved() == {"enabled": True, "source": "default"}
    identity_basis.identity_suggest(root, "c", "global", "off")
    assert resolved() == {"enabled": False, "source": "global"}
    identity_basis.identity_suggest(root, "c", "project", "on")
    assert resolved() == {"enabled": True, "source": "project"}
    identity_basis.identity_suggest(root, "c", "workspace", "off")
    assert resolved() == {"enabled": False, "source": "workspace"}
    out = identity_basis.identity_suggest(root, "c", "session", "on", session_key="sess-1")
    assert out["suggestions"] == {"enabled": True, "source": "session"} and out["changed"]
    assert resolved("sess-1") == {"enabled": True, "source": "session"}
    assert resolved("sess-2") == {"enabled": False, "source": "workspace"}
    assert resolved() == {"enabled": False, "source": "workspace"}
    identity_basis.identity_suggest(root, "c", "session", "clear", session_key="sess-1")
    assert resolved("sess-1") == {"enabled": False, "source": "workspace"}
    identity_basis.identity_suggest(root, "c", "workspace", "clear")
    assert resolved() == {"enabled": True, "source": "project"}
    identity_basis.identity_suggest(root, "c", "project", "clear")
    assert resolved() == {"enabled": False, "source": "global"}
    out = identity_basis.identity_suggest(root, "c", "global", "clear")
    assert out["suggestions"] == {"enabled": True, "source": "default"}
    assert identity_basis.identity_suggest(root, "c", "global", "clear")["changed"] is False
    for args, kwargs in ((("session", "off"), {}), (("galaxy", "off"), {}), (("global", "maybe"), {}),
                         (("session", "off"), {"session_key": " padded"}), (("session", "off"), {"session_key": ""})):
        with pytest.raises(errors.ThalirisError) as exc:
            identity_basis.identity_suggest(root, "c", *args, **kwargs)
        assert exc.value.code == errors.IDENTITY_PREFERENCE_INVALID


def test_session_preferences_are_pruned_after_thirty_days(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    sessions = home() / "sessions"
    sessions.mkdir(parents=True)
    old = sessions / ("a" * 64 + ".json")
    recent = sessions / ("b" * 64 + ".json")
    foreign = sessions / "notes.json"
    for path in (old, recent, foreign):
        path.write_text("{}", encoding="utf-8")
    stale = time.time() - 31 * 24 * 3600
    os.utime(old, (stale, stale))
    os.utime(foreign, (stale, stale))
    os.utime(recent, (time.time() - 29 * 24 * 3600,) * 2)
    identity_basis.identity_suggest(root, "c", "session", "off", session_key="native-session")
    assert not old.exists() and recent.exists() and foreign.exists()
    assert (sessions / f"{hashlib.sha256(b'native-session').hexdigest()}.json").exists()


# ---------------------------------------------------------------------------
# The offer


def test_offer_is_gated_and_each_new_note_surfaces_once(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    assert identity_basis.identity_offer(root) is None
    assert not home().exists()  # nothing to offer creates nothing
    note(root)
    line = identity_basis.identity_offer(root)
    assert line is not None and "\n" not in line
    assert line.startswith("Project identity: none recorded; 1 user statement about the project's long-term direction is noted")
    assert "compose a first version" in line and "no answer means no" in line
    assert "identity-suggest --off --scope session|workspace|project|global" in line
    assert identity_basis.identity_offer(root) is None
    assert identity_basis.identity_offer(root, "another-session") is None
    note(root, "A second statement.")
    line = identity_basis.identity_offer(root)
    assert line is not None and "2 user statements about the project's long-term direction are noted" in line
    assert identity_basis.identity_offer(root) is None

    identity_basis.identity_suggest(root, "c", "project", "off")
    note(root, "A third statement.")
    assert identity_basis.identity_offer(root) is None
    identity_basis.identity_suggest(root, "c", "session", "on", session_key="s-on")
    assert identity_basis.identity_offer(root, "s-on") is not None  # session beats project
    note(root, "A fourth statement.")
    identity_basis.identity_suggest(root, "c", "project", "clear")
    identity_basis.identity_suggest(root, "c", "session", "off", session_key="s-off")
    assert identity_basis.identity_offer(root, "s-off") is None
    assert identity_basis.identity_offer(root) is not None
    # Retracting every pending note leaves nothing to offer.
    for identifier in ("N-0001", "N-0002", "N-0003", "N-0004"):
        identity_basis.identity_note(root, "c", {"retract": identifier, "reason": "withdrawn"})
    note(root, "Fresh statement.")
    identity_basis.identity_note(root, "c", {"retract": "N-0005", "reason": "withdrawn"})
    assert identity_basis.identity_offer(root) is None


def test_offer_wording_when_current_and_silence_when_invalid_or_unrecorded(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    note(root, "Before establishment.")
    establish(root)
    assert identity_basis.identity_offer(root) is None  # the old note is no longer pending
    note(root, "A new direction.")
    baseline = root / NS / "IDENTITY.md"
    original = baseline.read_bytes()
    baseline.write_bytes(original + b"\nhand edit\n")
    assert identity.identity_status(root)["state"] == "UNRECORDED_CHANGE"
    assert identity_basis.identity_offer(root) is None
    baseline.write_bytes(original)
    line = identity_basis.identity_offer(root)
    assert line is not None and line.startswith("Project identity v1 (A-0001, CURRENT); 1 user statement")
    assert "noted since v1" in line and "compose an amendment" in line
    note(root, "Another direction.")
    ledger = root / NS / "ledger.json"
    saved = ledger.read_bytes()
    ledger.write_text("{broken", encoding="utf-8")
    assert identity.identity_status(root)["state"] == "INVALID"
    assert identity_basis.identity_offer(root) is None
    ledger.write_bytes(saved)
    assert identity_basis.identity_offer(root) is not None


def test_offer_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path / "p")
    note(root)
    assert identity_basis.identity_offer(tmp_path / "missing") is None
    assert identity_basis.identity_offer(root, "bad\nkey") is None

    def boom(*_args: object) -> None:
        raise RuntimeError("storage exploded")

    monkeypatch.setattr(identity_basis, "_load_basis", boom)
    assert identity_basis.identity_offer(root) is None
    status = identity.identity_status(root)
    assert status["ok"] and status["state"] == "ABSENT" and "storage exploded" in status["basis"]["unavailable"]


# ---------------------------------------------------------------------------
# Damage tolerance, status and repository compatibility


def test_damaged_files_are_reported_never_invalidate_identity(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    establish(root)
    note(root, "Valid statement.")
    project = home() / "projects" / identity_basis.project_key(root)
    (project / "identity-basis" / "N-0002.json").write_text("{not json", encoding="utf-8")
    (project / "identity-basis" / "N-0007.retraction.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    (project / "preferences.json").write_text("[]", encoding="utf-8")
    status = identity.identity_status(root)
    assert status["ok"] and status["state"] == "CURRENT" and status["summary"] == identity.identity_summary(root)
    assert status["basis"] == {"pending": 1, "total": 1, "retracted": 0, "damaged": 2}
    assert status["suggestions"] == {"enabled": True, "source": "default", "damaged": ["project"]}
    assert identity_basis.identity_offer(root) is None  # a damaged consulted preference is not a yes
    listed = identity_basis.identity_note_list(root)
    assert listed["damaged_files"] == ["N-0002.json", "N-0007.retraction.json"]
    # Allocation skips past damaged ids; nothing is overwritten.
    assert note(root, "After damage.")["note"]["id"] == "N-0008"
    identity_basis.identity_suggest(root, "c", "project", "clear")  # clearing removes a damaged preference
    (project / "offer-state.json").write_text("garbage", encoding="utf-8")
    assert identity_basis.identity_offer(root) is None  # cannot prove it was not shown already
    (project / "offer-state.json").unlink()
    assert identity_basis.identity_offer(root) is not None
    assert identity.identity_status(root)["state"] == "CURRENT"


def test_absent_status_keeps_existing_keys_and_writes_nothing(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    status = identity.identity_status(root)
    assert status["ok"] is True and status["state"] == "ABSENT" and status["summary"] is None
    assert status["basis"] == {"pending": 0, "total": 0, "retracted": 0, "damaged": 0}
    assert status["suggestions"] == {"enabled": True, "source": "default"}
    assert set(status) - {"basis", "suggestions"} == {
        "ok", "state", "version", "format", "baseline_path", "recorded_sha256", "on_disk_sha256", "last_amendment",
        "items", "items_total", "open_challenges", "open_challenges_total", "challenges_total", "relations_total",
        "relations_active", "summary", "truncated"}
    identity_basis.identity_note_list(root)
    assert not home().exists() and identity.identity_summary(root) is None


def test_formation_never_touches_the_repository(tmp_path: Path) -> None:
    absent = repo(tmp_path / "absent")
    before = tree(absent)
    note(absent)
    identity_basis.identity_note(absent, "c", {"retract": "N-0001", "reason": "r"})
    note(absent, "Second.")
    for scope in ("workspace", "project", "global"):
        identity_basis.identity_suggest(absent, "c", scope, "on")
    identity_basis.identity_suggest(absent, "c", "session", "on", session_key="k")
    identity_basis.identity_offer(absent, "k")
    identity_basis.identity_note_list(absent, include_retracted=True)
    identity.identity_status(absent, session_key="k")
    assert tree(absent) == before and not (absent / NS).exists()

    current = repo(tmp_path / "current")
    establish(current)
    before = tree(current)
    note(current)
    assert identity_basis.identity_offer(current) is not None
    identity_basis.identity_suggest(current, "c", "project", "off")
    identity.identity_status(current)
    assert tree(current) == before


def test_cli_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = repo(tmp_path / "p")

    def run(*args: str) -> tuple[int, dict[str, object]]:
        code = cli.main(["--root", str(root), *args])
        return code, json.loads(capsys.readouterr().out)

    payload = tmp_path / "note.json"
    payload.write_text(json.dumps({"quote": "The project is a ledger.", "kind": "purpose"}), encoding="utf-8")
    code, out = run("identity-note", "--actor", "controller:1", "--input", str(payload))
    assert code == 0 and out["note"]["id"] == "N-0001"
    code, out = run("identity-note", "--list")
    assert code == 0 and out["basis"]["pending"] == 1
    code, out = run("identity-note", "--input", str(payload))
    assert code == 2 and "--actor" in out["error"]
    code, out = run("identity-note", "--list", "--input", str(payload))
    assert code == 2 and "exactly one" in out["error"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"quote": "x", "why": 1}), encoding="utf-8")
    code, out = run("identity-note", "--actor", "c", "--input", str(bad))
    assert code == 2 and out["code"] == errors.IDENTITY_NOTE_INVALID
    code, out = run("identity-suggest", "--actor", "c", "--off", "--scope", "session")
    assert code == 2 and out["code"] == errors.IDENTITY_PREFERENCE_INVALID
    code, out = run("identity-suggest", "--actor", "c", "--off", "--on", "--scope", "global")
    assert code == 2
    code, out = run("identity-suggest", "--actor", "c", "--off", "--scope", "session", "--session-key", "S")
    assert code == 0 and out["suggestions"] == {"enabled": False, "source": "session"}
    code, out = run("identity-offer", "--session-key", "S")
    assert code == 0 and out == {"ok": True, "identity_offer": None}
    code, out = run("identity-offer")
    assert code == 0 and out["identity_offer"].startswith("Project identity: none recorded")
    code, out = run("identity-offer")
    assert out["identity_offer"] is None
    code, out = run("identity-status", "--session-key", "S")
    assert code == 0 and out["state"] == "ABSENT" and out["suggestions"]["source"] == "session"
    code, out = run("identity-suggest", "--actor", "c", "--clear", "--scope", "session", "--session-key", "S")
    assert code == 0 and out["changed"] is True
    task = core.task_start(root, "work", None, None)
    retract = tmp_path / "retract.json"
    retract.write_text(json.dumps({"retract": "N-0001", "reason": "wrong"}), encoding="utf-8")
    code, out = run("--task-id", task["task_id"], "identity-note", "--actor", "c", "--input", str(retract))
    assert code == 0 and out["retracted"] == "N-0001" and out["task_id"] == task["task_id"]


def test_cli_note_reads_stdin(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    root = repo(tmp_path / "p")
    data = json.dumps({"quote": "From stdin.", "kind": "direction"}).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))
    assert cli.main(["--root", str(root), "identity-note", "--actor", "c", "--input", "-"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["note"]["quote"] == "From stdin." and out["note"]["kind"] == "direction"


def test_damaged_retraction_note_is_never_pending_or_offered(tmp_path: Path) -> None:
    root = repo(tmp_path / "p")
    establish(root)
    note(root, "Valid statement.")
    basis_dir = home() / "projects" / identity_basis.project_key(root) / "identity-basis"
    (basis_dir / "N-0001.retraction.json").write_text("{not json", encoding="utf-8")
    status = identity.identity_status(root)
    assert status["basis"] == {"pending": 0, "total": 1, "retracted": 0, "damaged": 1}
    assert identity_basis.identity_offer(root) is None
    entry = identity_basis.identity_note_list(root)["notes"][0]
    assert entry["pending"] is False and entry["retracted"] is False and entry["retraction_damaged"] is True


def test_add_refuses_when_scan_truncated_and_never_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path / "p")
    establish(root)
    note(root, "First.")
    basis_dir = home() / "projects" / identity_basis.project_key(root) / "identity-basis"
    before = (basis_dir / "N-0001.json").read_bytes()
    monkeypatch.setattr(identity_basis, "MAX_NOTES", 1)
    for index in range(70):
        (basis_dir / f"junk-{index}.txt").write_text("x", encoding="utf-8")
    with pytest.raises(core.ThalirisError) as caught:
        note(root, "Second.")
    assert caught.value.code == errors.IDENTITY_NOTE_LIMIT
    assert (basis_dir / "N-0001.json").read_bytes() == before
    # The write itself refuses to replace an existing file.
    with pytest.raises(core.ThalirisError):
        identity_basis._write_json_new(basis_dir / "N-0001.json", {"a": 1})
    assert (basis_dir / "N-0001.json").read_bytes() == before


@pytest.mark.parametrize("failure", ["eperm", "missing"])
def test_note_write_falls_back_without_hard_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    root = repo(tmp_path / "p")
    establish(root)
    if failure == "eperm":
        def no_link(*args: object, **kwargs: object) -> None:
            raise OSError(errno.EPERM, "hard links unsupported")
        monkeypatch.setattr(os, "link", no_link)
    else:
        monkeypatch.delattr(os, "link")
    note(root, "First.")
    note(root, "Second.")
    basis_dir = home() / "projects" / identity_basis.project_key(root) / "identity-basis"
    assert (basis_dir / "N-0001.json").is_file() and (basis_dir / "N-0002.json").is_file()
    before = (basis_dir / "N-0001.json").read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        identity_basis._write_json_new(basis_dir / "N-0001.json", {"a": 1})
    assert caught.value.code == errors.IDENTITY_NOTE_LIMIT
    assert (basis_dir / "N-0001.json").read_bytes() == before
    assert not [p for p in basis_dir.iterdir() if p.name.endswith(".new")]
