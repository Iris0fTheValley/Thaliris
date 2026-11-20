"""Segment garbage collection after compaction: unreferenced segments go, anchored ones stay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from thaliris import authority, core

INTENT = {"human_instruction": "x", "boundary": "y", "invariants": "z", "acceptance": "w", "execution_mode": "delegated"}


def repo(path: Path) -> Path:
    root = path / "project"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    core.task_start(root, "gc", None, None)
    reg = root.parent / "reg.json"
    reg.write_text(json.dumps({"requirements": [{"id": "R0", "workchain_ref": "w"}],
                               "handoffs": [{"id": "H0", "parent_handoff_id": None, "candidate": "C1", "producer": "implementer",
                                             "requirement_refs": ["R0"]}]}), encoding="utf-8")
    core.task_evidence_register(root, "controller", core._load_state(root)["revision"], str(reg))
    return root


def settle(root: Path, n: int) -> None:
    """One judged observation (settled once judged), written in two writes that each evict."""
    core.task_observe(root, "implementer", {"id": f"O{n}", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R0"],
                                            "source_refs": [f"O{n}.s"], "text": f"observation {n} " * 40,
                                            "sources": [{"id": f"O{n}.s", "kind": "file", "locator": f"x:{n}", "summary": "s"}]})
    judge = root.parent / "j.json"
    judge.write_text(json.dumps({"id": f"J{n}", "candidate": "C1", "requirement_ref": "R0", "observation_refs": [f"O{n}"],
                                 "outcome": "satisfied", "reasoning": f"judged {n} " * 40}), encoding="utf-8")
    core.task_judge(root, "controller", core._load_state(root)["revision"], str(judge))


def on_disk(root: Path) -> set[str]:
    directory = core._state_path(root).parent / "archive"
    return {path.stem for path in directory.glob("*.json")} if directory.is_dir() else set()


def pressured(monkeypatch, entries: int = 3) -> None:
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    monkeypatch.setattr(core, "CHANGES_SINCE_RECENT_MAX", 1)
    monkeypatch.setattr(core, "ARCHIVE_COMPACT_ENTRIES", entries)


def test_compaction_deletes_only_unreferenced_segments(tmp_path, monkeypatch):
    root = repo(tmp_path)
    pressured(monkeypatch)
    referenced_history: list[set[str]] = []
    ever: set[str] = set()
    for n in range(40):
        settle(root, n)
        state = core._load_state(root)
        refs = core._segment_refs(state)
        referenced_history.append(refs)
        ever |= on_disk(root)
        # Every segment the current state or the state before it references is on disk.
        assert refs <= on_disk(root)
        if len(referenced_history) > 1:
            assert referenced_history[-2] <= on_disk(root), "the state just replaced keeps its segments (grace window)"
    # Compaction ran and its merged-away segments were collected: besides what the current index
    # references, only the last compaction's grace generation and segments written since remain.
    state = core._load_state(root)
    unreferenced = on_disk(root) - core._segment_refs(state)
    assert len(ever) > 3 * len(on_disk(root)) and len(unreferenced) <= 2 * (core.ARCHIVE_COMPACT_ENTRIES + 1), (len(ever), unreferenced)
    # Every evicted object is still retrievable after collection.
    for n in range(40):
        assert core.task_get(root, f"O{n}")["object"]["text"].startswith(f"observation {n} ")
    # An unreferenced stray (a crash between segment and state) is collected by the next compaction pass.
    task_id = state["task_id"]
    raw = core._segment_bytes(task_id, 0, [])
    stray = core._archive_segment_path(root, task_id, hashlib.sha256(raw).hexdigest())
    core._write_archive_segment(root, task_id, raw)
    unknown_bytes = b'{"owner":"user"}'
    unknown = stray.with_name(hashlib.sha256(unknown_bytes).hexdigest() + ".json")
    unknown.write_bytes(unknown_bytes)
    foreign_raw = core._segment_bytes("a0000000-0000-0000-0000-000000000000", 0, [])
    other_task = stray.with_name(hashlib.sha256(foreign_raw).hexdigest() + ".json")
    other_task.write_bytes(foreign_raw)
    other = core._state_path(root).parent / "archive" / "notes.json"
    other.write_bytes(b"kept: not a segment name")
    for n in range(40, 60):
        settle(root, n)
    assert not stray.exists() and other.exists()
    assert unknown.read_bytes() == unknown_bytes and other_task.read_bytes() == foreign_raw


def test_failed_compaction_commit_preserves_every_prior_segment(tmp_path, monkeypatch):
    root = repo(tmp_path)
    pressured(monkeypatch, entries=100)
    for n in range(10):
        settle(root, n)
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", core.STATE_MAX_BYTES)
    for n in range(10, 14):
        settle(root, n)
    path = core._state_path(root)
    old_state = path.read_bytes()
    old_segments = on_disk(root)
    assert len(old_segments) > 3

    original = core._atomic_write
    compact = core._compact_archive
    planned = []

    def observe_plan(root, state):
        plan = compact(root, state)
        planned.append(plan is not None)
        return plan

    def refuse_commit(target, data):
        if target == path:
            raise OSError("injected failure before compacted state commit")
        original(target, data)

    pressured(monkeypatch)
    monkeypatch.setattr(core, "_compact_archive", observe_plan)
    monkeypatch.setattr(core, "_atomic_write", refuse_commit)
    with core._lock(root), pytest.raises(OSError, match="before compacted state commit"):
        state = core._load_state(root)
        state["revision"] += 2
        core._write_state(root, state)
    assert planned == [True]
    assert path.read_bytes() == old_state and old_segments <= on_disk(root)


def test_anchor_pinned_segments_are_kept_and_recoverable(tmp_path, monkeypatch):
    root = repo(tmp_path)
    pressured(monkeypatch)
    for n in range(6):
        settle(root, n)
    store = authority.AuthorityStore(root, tmp_path / "external")
    store.establish(core.task_show(root)["state"], INTENT)
    anchored_bytes = core._state_path(root).read_bytes()
    anchored = core._segment_refs(json.loads(anchored_bytes))
    assert anchored and core._read_pins(root, core._load_state(root)["task_id"])
    # Out-of-band writes (no checkpoint) compact and collect many times; the anchor's segments stay.
    for n in range(6, 12):
        settle(root, n)
    second = authority.AuthorityStore(root, tmp_path / "ext2")
    second.establish(core.task_show(root)["state"], INTENT)
    second_bytes = core._state_path(root).read_bytes()
    second_refs = core._segment_refs(json.loads(second_bytes))
    assert second_refs - anchored
    for n in range(12, 50):
        settle(root, n)
    assert anchored | second_refs <= on_disk(root)
    assert not anchored <= core._segment_refs(core._load_state(root)), "the scenario must drop anchored segments from the index"
    # Recovery restores the anchored ledger, and every object it indexes is still readable.
    recovered = store.recover(authority.digest(store.path()), "restore the anchored ledger")
    assert recovered["status"] == "TASK_AUTHORITY_RECOVERED"
    assert core._state_path(root).read_bytes() == anchored_bytes
    for n in range(6):
        assert core.task_get(root, f"O{n}")["object"]["text"].startswith(f"observation {n} ")
    second.recover(authority.digest(second.path()), "restore the other authority snapshot")
    assert core._state_path(root).read_bytes() == second_bytes
    assert core.task_get(root, "O10")["object"]["text"].startswith("observation 10 ")


def test_pre_upgrade_anchors_keep_their_unpinned_segments(tmp_path, monkeypatch):
    root = repo(tmp_path)
    pressured(monkeypatch, entries=100)
    with monkeypatch.context() as legacy:
        legacy.setattr(core, "ARCHIVE_SEGMENT_VERSION", 2)
        for n in range(8):
            settle(root, n)
        state = core._load_state(root)
        state["schema_version"] = 11
        core._state_path(root).write_bytes(core._serialize_state(state))
        store = authority.AuthorityStore(root, tmp_path / "old")
        # Simulate a prior Core writing an anchor before archive pins existed.
        legacy.setattr(core, "pin_anchor_segments", lambda *args: None)
        store.establish(state, INTENT)
    anchor_bytes = store.path().read_bytes()
    refs = core._segment_refs(state)
    assert refs and not core._pins_path(root, state["task_id"]).exists()
    pressured(monkeypatch)
    for n in range(8, 30):
        settle(root, n)
    assert refs <= on_disk(root) and refs - core._segment_refs(core._load_state(root))
    assert store.path().read_bytes() == anchor_bytes
    store.recover(authority.digest(store.path()), "restore pre-upgrade anchor")
    assert core.task_get(root, "O0")["object"]["text"].startswith("observation 0 ")


def test_pin_failure_cannot_publish_an_anchor_with_missing_pins(tmp_path, monkeypatch):
    root = repo(tmp_path)
    pressured(monkeypatch)
    for n in range(8):
        settle(root, n)
    store = authority.AuthorityStore(root, tmp_path / "external")
    task_id = core._load_state(root)["task_id"]
    original = core._atomic_write

    def fail_pins(target, data):
        if target == core._pins_path(root, task_id):
            raise OSError("pin storage unavailable")
        original(target, data)

    monkeypatch.setattr(core, "_atomic_write", fail_pins)
    with pytest.raises(OSError, match="pin storage unavailable"):
        store.establish(core._load_state(root), INTENT)
    assert not store.path().exists()


def test_checkpoints_move_the_pin_and_retirement_releases_it(tmp_path, monkeypatch):
    root = repo(tmp_path)
    pressured(monkeypatch)
    for n in range(6):
        settle(root, n)
    store = authority.AuthorityStore(root, tmp_path / "external")
    store.establish(core.task_show(root)["state"], INTENT)
    task_id = core._load_state(root)["task_id"]
    for n in range(6, 40):
        settle(root, n)
        store.checkpoint()
        pins = core._read_pins(root, task_id)
        assert set().union(*pins.values()) == core._segment_refs(core._load_state(root))
    assert core._segment_refs(core._load_state(root)) <= on_disk(root)
    # An unreadable pins file switches collection off entirely (nothing is deleted).
    path = core._pins_path(root, task_id)
    pinned_bytes = path.read_bytes()
    path.write_bytes(b"not json")
    before = on_disk(root)
    for n in range(40, 60):
        settle(root, n)
    assert before <= on_disk(root)
    # Loss of an established registry also fails closed. Its authoritative bytes must be restored.
    path.unlink()
    before = on_disk(root)
    for n in range(60, 65):
        settle(root, n)
    assert before <= on_disk(root)
    anchor = store.path().read_bytes()
    with pytest.raises(ValueError, match="pin registry is missing"):
        store.checkpoint()
    assert store.path().read_bytes() == anchor
    path.write_bytes(pinned_bytes)
    # Closing the task retires the anchor and drops its pin.
    store.checkpoint()
    core.task_close(root, core._load_state(root)["revision"])
    store.checkpoint()
    assert core._read_pins(root, task_id) == {}


def test_tasks_that_never_archive_get_no_pins_file(tmp_path):
    root = repo(tmp_path)
    store = authority.AuthorityStore(root, tmp_path / "external")
    store.establish(core.task_show(root)["state"], INTENT)
    settle(root, 0)
    store.checkpoint()
    assert not core._pins_path(root, core._load_state(root)["task_id"]).exists()
