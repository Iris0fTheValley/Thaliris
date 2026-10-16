from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from thaliris import core


def payload(root, name, value):
    path = root / (name + ".json")
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def setup(root):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    started = core.task_start(root, "continuity", None, None)
    core.task_evidence_register(root, "controller", 1, payload(root, "register", {
        "requirements": [
            {"id": "R1", "workchain_ref": "opaque-chain"},
            {"id": "R2", "workchain_ref": "second-opaque-chain"},
        ],
        "handoffs": [
            {"id": "H1", "parent_handoff_id": None, "candidate": "C1", "producer": "parent", "requirement_refs": ["R1", "R2"]},
            {"id": "H2", "parent_handoff_id": "H1", "candidate": "C1", "producer": "child", "requirement_refs": ["R1", "R2"]},
        ],
    }))
    core.task_update(root, "controller", 2, payload(root, "source", {
        "evidence_refs": [{"id": "S1", "kind": "test", "locator": "tests/result.txt", "summary": "selected source"}],
    }))
    return started["task_id"]


def observation(identifier, *, candidate="C1", handoff_id="H2", requirement_refs=None, source_refs=None):
    return {"id": identifier, "candidate": candidate, "handoff_id": handoff_id, "requirement_refs": requirement_refs if requirement_refs is not None else ["R1"], "source_refs": source_refs if source_refs is not None else ["S1"], "text": "model selected decision-changing observation"}


def test_concurrent_append_cas_restart_and_close_preserve_evidence(tmp_path):
    task_id = setup(tmp_path)
    files = [payload(tmp_path, "O" + str(i), observation("O" + str(i))) for i in range(4)]
    code = "from pathlib import Path; import sys; from thaliris import core; r=Path(sys.argv[1]); core.select_task(r,sys.argv[2]); core.task_observe(r,'child',sys.argv[3])"
    def append(path):
        subprocess.run([sys.executable, "-c", code, str(tmp_path), task_id, path], check=True, capture_output=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, files))
    with pytest.raises(ValueError, match="revision conflict"):
        core.task_update(tmp_path, "controller", 2, payload(tmp_path, "stale", {"pending_results": []}))
    state = core.task_show(tmp_path)["state"]
    assert state["revision"] == 7
    assert len(core.task_status(tmp_path)["Evidence Continuity"]["unincorporated"]) == 4
    assert core.task_get(tmp_path, "H2")["object"]["parent_handoff_id"] == "H1"
    core.task_judge(tmp_path, "controller", 7, payload(tmp_path, "judge", {
        "id": "J1", "candidate": "C1", "requirement_ref": "R1", "observation_refs": ["O0"], "outcome": "unknown", "reasoning": "Model examined O0; requirement remains unknown",
    }))
    assert len(core.task_status(tmp_path)["Evidence Continuity"]["unincorporated"]) == 3
    core.task_observe(tmp_path, "child", payload(tmp_path, "new", observation("O4")))
    core.task_update(tmp_path, "controller", 9, payload(tmp_path, "clear", {"active_work": [], "pending_results": []}))
    core.task_close(tmp_path, 10)
    code = "from pathlib import Path; import sys,json; from thaliris import core; r=Path(sys.argv[1]);core.select_task(r,sys.argv[2]); print(json.dumps(core.task_status(r)))"
    restarted = json.loads(subprocess.run([sys.executable, "-c", code, str(tmp_path), task_id], check=True, capture_output=True, text=True).stdout)
    assert restarted["Task"]["status"] == "DONE"
    assert len(restarted["Evidence Continuity"]["unincorporated"]) == 4
    assert core.task_get(tmp_path, "O0")["object"]["task_id"] == task_id


def test_provenance_sources_and_candidate_validation(tmp_path):
    setup(tmp_path)
    invalid = observation("bad")
    invalid["candidate"] = "C2"
    with pytest.raises(ValueError, match="provenance conflict"):
        core.task_observe(tmp_path, "child", payload(tmp_path, "bad", invalid))
    with pytest.raises(ValueError, match="provenance conflict"):
        core.task_observe(tmp_path, "sibling", payload(tmp_path, "sibling", observation("bad")))
    missing_requirements = observation("missing-requirement")
    missing_requirements["requirement_refs"] = []
    with pytest.raises(ValueError, match="requirement refs"):
        core.task_observe(tmp_path, "child", payload(tmp_path, "missing-requirement", missing_requirements))
    missing_sources = observation("missing-source")
    missing_sources["source_refs"] = []
    with pytest.raises(ValueError, match="source refs"):
        core.task_observe(tmp_path, "child", payload(tmp_path, "missing-source", missing_sources))
    invalid_submitter = observation("invalid-submitter")
    invalid_submitter["submitted_by"] = ""
    with pytest.raises(ValueError, match="observation submitter"):
        core.task_observe(tmp_path, "child", payload(tmp_path, "invalid-submitter", invalid_submitter))
    oversized_submitter = observation("oversized-submitter")
    oversized_submitter["submitted_by"] = "x" * 65
    with pytest.raises(ValueError, match="observation submitter"):
        core.task_observe(tmp_path, "child", payload(tmp_path, "oversized-submitter", oversized_submitter))
    invalid_status = observation("invalid-status")
    invalid_status["native_status_conflict"] = "false"
    with pytest.raises(ValueError, match="native status conflict"):
        core.task_observe(tmp_path, "child", invalid_status)
    value = observation("O1")
    value.update(native_actor="native-hash", submitted_by="controller", native_status="UNKNOWN", native_status_conflict=True)
    core.task_observe(tmp_path, "child", payload(tmp_path, "valid", value))
    assert core.task_get(tmp_path, "S1")["object"]["locator"] == "tests/result.txt"
    saved = core.task_get(tmp_path, "O1")["object"]
    assert saved["candidate"] == "C1" and saved["producer"] == "child" and saved["handoff_id"] == "H2"
    assert saved["native_actor"] == "native-hash" and saved["submitted_by"] == "controller"
    assert saved["native_status"] == "UNKNOWN" and saved["native_status_conflict"] is True
    assert core.task_status(tmp_path)["Evidence Continuity"]["unincorporated_total"] == 1
    with pytest.raises(ValueError, match="observation refs"):
        core.task_judge(tmp_path, "controller", 4, payload(tmp_path, "empty-judgment", {"id": "J-empty", "candidate": "C2", "requirement_ref": "R1", "observation_refs": [], "outcome": "satisfied", "reasoning": "must cite an observation"}))


def test_cross_candidate_judgment_and_new_evidence_preserve_history(tmp_path):
    task_id = setup(tmp_path)
    original = observation("C1-counterevidence", requirement_refs=["R2"])
    original.update(native_actor="original-bound-child-id", submitted_by="controller")
    core.task_observe(tmp_path, "child", original)
    assert "task_id" not in original and "producer" not in original

    core.task_judge(tmp_path, "controller", 4, payload(tmp_path, "repair", {
        "id": "J1", "candidate": "C2", "requirement_ref": "R1", "observation_refs": ["C1-counterevidence"],
        "outcome": "repair", "reasoning": "C1 counterevidence requires a repair in selected candidate C2",
    }))
    core.task_evidence_register(tmp_path, "controller", 5, payload(tmp_path, "repaired-handoff", {
        "handoffs": [{"id": "H3", "parent_handoff_id": "H2", "candidate": "C2", "producer": "child", "requirement_refs": ["R1"]}],
    }))
    repaired = observation("C2-new-evidence", candidate="C2", handoff_id="H3", source_refs=["S2"])
    repaired["sources"] = [{"id": "S2", "kind": "test", "locator": "tests/repaired-result.txt", "summary": "fresh repaired candidate evidence"}]
    core.task_observe(tmp_path, "child", repaired)
    assert "sources" in repaired and "task_id" not in repaired and "producer" not in repaired
    core.task_judge(tmp_path, "controller", 7, payload(tmp_path, "satisfied", {
        "id": "J2", "candidate": "C2", "requirement_ref": "R1", "observation_refs": ["C1-counterevidence", "C2-new-evidence"],
        "outcome": "satisfied", "reasoning": "The repair and new evidence establish the requirement for C2",
    }))

    state = core.task_show(tmp_path)["state"]
    continuity = state["evidence_continuity"]
    assert len(continuity["judgments"]) == 2
    assert continuity["judgments"][0]["candidate"] == "C2"
    assert continuity["judgments"][0]["observation_refs"] == ["C1-counterevidence"]
    assert continuity["judgments"][0]["outcome"] == "repair"
    assert continuity["judgments"][1]["candidate"] == "C2"
    assert continuity["judgments"][1]["observation_refs"] == ["C1-counterevidence", "C2-new-evidence"]
    assert continuity["judgments"][1]["outcome"] == "satisfied"
    assert continuity["observations"][0]["candidate"] == "C1"
    assert continuity["observations"][0]["producer"] == "child"
    assert continuity["observations"][0]["handoff_id"] == "H2"
    assert continuity["observations"][0]["source_refs"] == ["S1"]
    assert continuity["observations"][0]["requirement_refs"] == ["R2"]
    assert continuity["observations"][0]["task_id"] == task_id
    latest = core.task_status(tmp_path)["Evidence Continuity"]["latest_judgments"]
    assert latest == [{"id": "J2", "candidate": "C2", "requirement_ref": "R1", "outcome": "satisfied", "observation_ref_count": 2}]


def test_controller_cas_racing_children_never_overwrites_observations(tmp_path):
    task_id = setup(tmp_path)
    children = [payload(tmp_path, "race" + str(i), observation("race" + str(i))) for i in range(2)]
    update = payload(tmp_path, "controller", {"pending_results": ["controller routing"]})
    code = """
import sys
from pathlib import Path
from thaliris import core
r=Path(sys.argv[1]);core.select_task(r,sys.argv[2])
if sys.argv[3]=='child':
    core.task_observe(r,'child',sys.argv[4])
else:
    try: core.task_update(r,'controller',3,sys.argv[4])
    except ValueError as exc:
        if str(exc) != 'task revision conflict': raise
"""
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(subprocess.run, [sys.executable, "-c", code, str(tmp_path), task_id, actor, path], check=True, capture_output=True) for actor, path in [("child", children[0]), ("child", children[1]), ("controller", update)]]
        for future in futures:
            future.result()
    state = core.task_show(tmp_path)["state"]
    assert {item["id"] for item in state["evidence_continuity"]["observations"]} == {"race0", "race1"}
    assert state["revision"] in {4, 5}


def test_maintenance_cas_split_delete_links_and_rollback(tmp_path):
    setup(tmp_path)
    old = tmp_path / ".agent-memory" / "old.md"
    old.write_bytes(core._entry("old", "body"))
    index = tmp_path / ".agent-memory" / "INDEX.md"
    before = old.read_bytes(), index.read_bytes()
    value = {"writes": [{"path": ".agent-memory/new.md", "base_sha256": None, "content": core._entry("new", "split body").decode()}],
             "deletes": [{"path": ".agent-memory/old.md", "base_sha256": core._digest(before[0])}],
             "index_update": {"path": ".agent-memory/INDEX.md", "base_sha256": core._digest(before[1]), "content": core._entry("map", "[new](new.md)").decode()}}
    result = core.document_maintain(tmp_path, "controller", 3, payload(tmp_path, "maintain", value))
    assert not old.exists()
    assert "split body" in core.document_get(tmp_path, [".agent-memory/new.md"])["documents"][0]["body"]
    core.rollback(tmp_path, result["backup"])
    assert old.read_bytes() == before[0] and index.read_bytes() == before[1]
    assert not (old.parent / "new.md").exists()
    value["index_update"]["content"] = core._entry("map", "[removed](old.md)").decode()
    with pytest.raises(ValueError, match="missing link"):
        core.document_maintain(tmp_path, "controller", 3, payload(tmp_path, "bad-link", value))
    assert old.read_bytes() == before[0]
    value["index_update"]["content"] = core._entry("map", "[new](new.md)").decode()
    value["deletes"][0]["base_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="revision conflict"):
        core.document_maintain(tmp_path, "controller", 3, payload(tmp_path, "bad-cas", value))
    value["deletes"][0]["path"] = "../escape.md"
    with pytest.raises(ValueError):
        core.document_maintain(tmp_path, "controller", 3, payload(tmp_path, "escape", value))


def test_status_pages_all_pending_ids_without_body_replay(tmp_path):
    setup(tmp_path)
    state = core.task_show(tmp_path)["state"]
    data = core._continuity(state)
    for i in range(100):
        data["observations"].append({**observation("observation-" + str(i)), "task_id": state["task_id"], "producer": "child"})
    core._write_state(tmp_path, state)
    offset, seen = 0, []
    while True:
        packet = core.task_status(tmp_path, offset)["Evidence Continuity"]
        assert len(json.dumps(packet, ensure_ascii=False).encode("utf-8")) <= 4096
        assert packet["unincorporated_total"] == 100
        assert "model selected" not in json.dumps(packet)
        seen.extend(item["observation_id"] for item in packet["unincorporated"])
        offset = packet["next_offset"]
        if offset is None:
            break
    assert len(seen) == len(set(seen)) == 100


def test_maintenance_failure_rolls_back_applied_writes(tmp_path, monkeypatch):
    setup(tmp_path)
    original = core._atomic_write
    def fail_second(target, content):
        if target.name == "two.md":
            raise OSError("injected failure")
        original(target, content)
    monkeypatch.setattr(core, "_atomic_write", fail_second)
    value = {"writes": [{"path": ".agent-memory/" + name + ".md", "base_sha256": None, "content": core._entry(name, "body").decode()} for name in ("one", "two")]}
    with pytest.raises(OSError, match="injected failure"):
        core.document_maintain(tmp_path, "controller", 3, payload(tmp_path, "failed", value))
    assert not (tmp_path / ".agent-memory/one.md").exists()
    assert not (tmp_path / ".agent-memory/two.md").exists()
    assert list((tmp_path / ".context/backups").glob("*.json"))
