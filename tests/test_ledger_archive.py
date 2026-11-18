"""Hot/cold ledger archive: writes keep succeeding near the cap, gates are unchanged.

Schema 10 left stubs in the hot lists; schema 11 evicts settled objects entirely (see also
test_ledger_evict.py). These tests cover the behaviour both share.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from thaliris import authority, core

USAGE = {"model": "m-1", "effort": "high", "input_tokens": 1200, "output_tokens": 300, "total_tokens": None,
         "cost_usd": 0.25, "duration_ms": 4000, "tool_uses": 7, "outcome": "completed"}
TREE = "git:" + "a" * 40


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    core.task_start(root, "archive", None, None)
    return root


def filler(length: int, seed: int) -> str:
    words = f"group {seed} evidence about the ledger behaviour under load and its stable invariants "
    return (words * (length // len(words) + 1))[:length]


def group(state: dict, index: int, *, text: int = 1000, reasoning: int = 700, summary: int = 300) -> None:
    """One real-shaped requirement: a finished handoff, one cited observation, one satisfied judgment."""
    task_id = state["task_id"]
    data = state.setdefault("evidence_continuity", {name: [] for name in core._CONTINUITY_KINDS})
    data["requirements"].append({"id": f"R{index}", "workchain_ref": f"w{index}"})
    data["handoffs"].append({"id": f"H{index}", "parent_handoff_id": None, "candidate": "C1", "producer": "implementer",
                             "requirement_refs": [f"R{index}"], "usage": dict(USAGE),
                             "claims": {"status": "present", "total": 1, "truncated": False, "invalid": 0, "duplicates": 0,
                                        "supports": [{"requirement": f"R{index}", "evidence": f"src/m{index}.py:1", "basis": "read"}],
                                        "observations": []}})
    state["evidence_refs"].append({"id": f"O{index}.s", "kind": "file", "locator": f"src/m{index}.py:{index}",
                                   "summary": filler(summary, index)})
    data["observations"].append({"id": f"O{index}", "task_id": task_id, "producer": "implementer", "candidate": "C1",
                                 "handoff_id": f"H{index}", "requirement_refs": [f"R{index}"], "source_refs": [f"O{index}.s"],
                                 "text": filler(text, index)})
    data["judgments"].append({"id": f"J{index}", "task_id": task_id, "producer": "controller", "candidate": "C1",
                              "requirement_ref": f"R{index}", "observation_refs": [f"O{index}"], "outcome": "satisfied",
                              "reasoning": filler(reasoning, index)})


def with_groups(state: dict, start: int, count: int) -> dict:
    for index in range(start, start + count):
        group(state, index)
    return state


def write_raw(root: Path, state: dict, *, indent: bool = False) -> bytes:
    body = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) if indent else json.dumps(
        state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw = (body + "\n").encode("utf-8")
    core._state_path(root).write_bytes(raw)
    return raw


def disk(root: Path) -> dict:
    return json.loads(core._state_path(root).read_bytes())


def segments(root: Path, task_id: str) -> list[Path]:
    directory = root / ".context" / "tasks" / task_id / "archive"
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def write_json(root: Path, name: str, value: object) -> str:
    path = root.parent / f"{name}.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def stub_count(state: dict) -> int:
    """Archived objects: schema-10 stubs still hot plus evicted ids."""
    return sum(1 for _ in core._archived_items(state)) + len(core._indexed_ids(state))


# --- growth past the old cap --------------------------------------------------------------------

def test_real_shaped_ledger_grows_past_512_kib_with_every_write_succeeding(tmp_path):
    root = repo(tmp_path)
    task_id = core._load_state(root)["task_id"]
    sizes = []
    # 170 requirements with ~1 KB observations and ~0.7 KB judgments, then keep going: each step is
    # one ordinary transaction (register + observe + judge through Core's batch entry points).
    for start in range(0, 300, 10):
        state = core._load_state(root)
        base = state["revision"]
        core.task_evidence_register(root, "controller", base, write_json(root, "reg", {
            "requirements": [{"id": f"R{i}", "workchain_ref": f"w{i}"} for i in range(start, start + 10)],
            "handoffs": [{"id": f"H{i}", "parent_handoff_id": None, "candidate": "C1", "producer": "implementer",
                          "requirement_refs": [f"R{i}"]} for i in range(start, start + 10)]}))
        core.task_observe(root, "implementer", {"observations": [{
            "id": f"O{i}", "candidate": "C1", "handoff_id": f"H{i}", "requirement_refs": [f"R{i}"], "source_refs": [f"O{i}.s"],
            "text": filler(1000, i),
            "sources": [{"id": f"O{i}.s", "kind": "file", "locator": f"src/m{i}.py:{i}", "summary": filler(300, i)}]}
            for i in range(start, start + 10)]})
        core.task_judge(root, "controller", base + 2, write_json(root, "judge", {"judgments": [{
            "id": f"J{i}", "candidate": "C1", "requirement_ref": f"R{i}", "observation_refs": [f"O{i}"], "outcome": "satisfied",
            "reasoning": filler(700, i)} for i in range(start, start + 10)]}))
        size = core._state_path(root).stat().st_size
        assert size <= core.STATE_MAX_BYTES
        sizes.append(size)
    state = core._load_state(root)
    assert len(state["evidence_continuity"]["requirements"]) == 300
    # Without archiving the same content is far above the cap.
    unarchived = sum(len(json.dumps(item, separators=(",", ":"))) for kind in core._CONTINUITY_KINDS
                     for item in state["evidence_continuity"][kind])
    assert state.get("archive") and stub_count(state) > 0 and max(sizes) <= core.STATE_MAX_BYTES
    assert unarchived + sum(len(item["summary"]) for item in state["evidence_refs"]) < 1_000_000
    # Merged (compacted) segments leave their predecessors on disk; every indexed segment exists.
    assert {path.stem for path in segments(root, task_id)} >= {entry["sha256"] for entry in state["archive"]}
    # Every archived body is retrievable.
    full = core.task_get(root, "O5")["object"]
    assert full["text"] == filler(1000, 5) and "archived" not in full
    assert core.task_get(root, "J5")["object"]["reasoning"] == filler(700, 5)
    assert core.task_get(root, "O5.s")["object"]["summary"] == filler(300, 5)
    # Nothing is open and the close gate still closes.
    assert core.evidence_summary(state)["unincorporated_total"] == 0
    assert core.task_close(root, state["revision"])["status"] == "DONE"


def test_an_old_indented_ledger_near_the_cap_keeps_accepting_writes(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    state["schema_version"] = 9
    count = 0
    while len(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2)) < core.STATE_MAX_BYTES - 4096:
        group(state, count)
        count += 1
    raw = write_raw(root, state, indent=True)
    assert core.STATE_MAX_BYTES - 4096 <= len(raw) <= core.STATE_MAX_BYTES
    loaded = core._load_state(root)
    assert loaded["schema_version"] == core._STATE_SCHEMA_VERSION and core._state_path(root).read_bytes() == raw
    core.task_observe(root, "implementer", {"id": "after", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R0"],
                                            "source_refs": ["O0.s"], "text": "a new check result"})
    written = core._state_path(root).read_bytes()
    assert len(written) <= core.STATE_ARCHIVE_HIGH_WATER_BYTES and b"\n " not in written
    assert disk(root)["schema_version"] == core._STATE_SCHEMA_VERSION and disk(root)["archive"]
    assert core.evidence_summary(core._load_state(root))["unincorporated"][0]["observation_id"] == "after"


# --- repeated check runs ----------------------------------------------------------------------------

def test_two_hundred_check_runs_across_ten_checks_keep_succeeding_near_the_cap(tmp_path, monkeypatch):
    root = repo(tmp_path)
    state = core._load_state(root)
    count = 0
    while len(core._serialize_state(state)) < core.STATE_MAX_BYTES - 16 * 1024:
        group(state, count)
        count += 1
    state["schema_version"] = 9
    write_raw(root, state)
    revision = core._load_state(root)["revision"]
    core.task_check(root, "controller", revision, {"checks": [
        {"id": f"K{index}", "requirement_refs": [f"R{index}"], "command": [sys.executable, "-c", "pass"]} for index in range(10)]})
    monkeypatch.setattr(core, "tree_identity", lambda root: TREE)
    calls = []

    def run(root, declaration):
        calls.append(declaration["id"])
        outcome = "FAIL" if len(calls) % 3 == 0 else "PASS"
        return {"check_id": declaration["id"], "command_sha256": declaration["command_sha256"], "outcome": outcome,
                "exit_code": 0 if outcome == "PASS" else 1, "duration_ms": 12, "output_tail": filler(2000, len(calls)),
                "output_bytes": 2000, "tree_identity_before": TREE, "tree_identity": TREE,
                "files_digest": declaration["files_digest"], "files_changed_during_run": False,
                "observed_files": [{"path": f"src/f{n}.py", "state": "FILE", "identity": "b" * 64, "mode": 420,
                                    "git_status": "OBSERVED"} for n in range(8)]}

    monkeypatch.setattr(core, "_run_declared_check", run)
    for number in range(200):
        check_id = f"K{number % 10}"
        response = core.task_verify(root, "implementer", check_id)
        assert response["ok"] and response["result"]["check_id"] == check_id
        assert core._state_path(root).stat().st_size <= core.STATE_MAX_BYTES
    assert len(calls) == 200
    state = core._load_state(root)
    runs = core._latest_check_results(state)
    assert all(len(items) == core.CHECK_RESULT_HISTORY and items[-1]["run"] == 20 for items in runs.values())
    # The last two runs of every check stay hot (the failed-twice advisory and freshness read them).
    assert all("archived" not in item for items in runs.values() for item in items[-2:])
    view = core.verification_view(root, state, tree=TREE)
    assert {entry["status"] for entry in view["checks"]} <= {"green", "red"}


# --- gates and aggregates are identical before and after archiving -----------------------------------

def gated_ledger(tmp_path: Path) -> Path:
    root = repo(tmp_path)
    state = core._load_state(root)
    with_groups(state, 0, 40)
    data = state["evidence_continuity"]
    task_id = state["task_id"]
    data["requirements"][2]["kind"] = "compiled"
    data["requirements"][3]["kind"] = "partial"
    # Open evidence: an unincorporated observation and an unresolved repair judgment with its basis.
    state["evidence_refs"].append({"id": "open.s", "kind": "file", "locator": "src/open.py:1", "summary": filler(400, 99)})
    data["observations"].append({"id": "open", "task_id": task_id, "producer": "implementer", "candidate": "C1", "handoff_id": "H0",
                                 "requirement_refs": ["R0"], "source_refs": ["open.s"], "text": filler(900, 98)})
    data["observations"].append({"id": "basis", "task_id": task_id, "producer": "implementer", "candidate": "C1", "handoff_id": "H1",
                                 "requirement_refs": ["R1"], "source_refs": ["O1.s"], "text": filler(900, 97)})
    data["judgments"].append({"id": "repair", "task_id": task_id, "producer": "controller", "candidate": "C1", "requirement_ref": "R1",
                              "observation_refs": ["basis"], "outcome": "repair", "reasoning": filler(800, 96)})
    data["handoffs"][5]["claims"] = {"status": "missing"}
    state["schema_version"] = 9
    write_raw(root, state)
    core.task_check(root, "controller", core._load_state(root)["revision"], {"checks": [
        {"id": "K1", "requirement_refs": ["R2"], "command": [sys.executable, "-c", "pass"]},
        {"id": "K2", "requirement_refs": ["R4"], "command": [sys.executable, "-c", "pass"]}]})
    # A claim block whose adverse claim becomes an open observation, ingested through Core.
    core.task_evidence_register(root, "controller", core._load_state(root)["revision"], write_json(root, "reg", {
        "handoffs": [{"id": "HC", "parent_handoff_id": None, "candidate": "C1", "producer": "reviewer", "requirement_refs": ["R6", "R7"]}]}))
    block = "Report.\n```thaliris-claims\n" + json.dumps({"claims": [
        {"requirement": "R6", "polarity": "contradicts", "text": filler(250, 5), "evidence": "src/m6.py:1", "basis": "read"},
        {"requirement": "R7", "polarity": "supports", "text": "fine", "evidence": "src/m7.py:1", "basis": "read"}]}) + "\n```\n"
    core.task_ingest_claims(root, "HC", block)
    core.task_handoff_usage(root, "HC", {"model": "m-2", "input_tokens": 50, "output_tokens": 5, "outcome": "completed"})
    return root


def views(root: Path, monkeypatch) -> dict:
    monkeypatch.setattr(core, "tree_identity", lambda root: TREE)
    state = core._load_state(root)
    result: dict[str, object] = {
        "evidence_summary": core.evidence_summary(state),
        "evidence_pages": [core.evidence_summary(state, offset, max_bytes=256) for offset in range(0, 6)],
        "continuity_status": core._continuity_status(state),
        "usage": core.usage_summary(state),
        "claims": core._claims_section(state),
        "surfaced": core.surfaced_requirements(state),
        "verification": core.verification_view(root, state),
        "verification_section": core._verification_section(state, core.verification_view(root, state), True),
        "latest": {key: {field: value for field, value in item.items() if field not in ("reasoning", "archived")}
                   for key, item in core._latest_requirement_judgments(state).items()},
        "ids": sorted(core._task_object_ids(state)),
        "counts": core.task_status(root, view="compact")["Counts"],
        "changes_since": core.changes_since(state, 0, recent_max=2),
    }
    for operation in ("close", "judge"):
        attempt = copy.deepcopy(state)
        try:
            if operation == "close":
                outcome = core.close_state(root, attempt)
            else:
                outcome = core._append_judgments(attempt, "controller", [
                    {"id": "gated", "candidate": "C1", "requirement_ref": "R2", "observation_refs": ["O2"], "outcome": "satisfied",
                     "reasoning": "r"},
                    {"id": "free", "candidate": "C1", "requirement_ref": "R9", "observation_refs": ["O9"], "outcome": "satisfied",
                     "reasoning": "r"}], root)
        except core.ThalirisError as exc:
            outcome = {"code": exc.code, "details": exc.details}
        result[operation] = outcome
    # The ingest dedupe and the tamper dedupe read only stub fields.
    attempt = copy.deepcopy(state)
    core.ingest_claims(attempt, "H8", "```thaliris-claims\n" + json.dumps({"claims": [
        {"requirement": "R6", "polarity": "contradicts", "text": "again", "evidence": "src/m6.py:1", "basis": "read"}]}) + "\n```\n")
    result["ingest_duplicates"] = attempt["evidence_continuity"]["handoffs"][8]["claims"]["duplicates"]
    return result


def test_gates_and_aggregates_are_identical_before_and_after_archiving(tmp_path, monkeypatch):
    root = gated_ledger(tmp_path)
    before = views(root, monkeypatch)
    assert before["close"]["code"] == "VERIFICATION_WITHHELD"
    assert before["judge"]["code"] == "VERIFICATION_WITHHELD"
    assert before["evidence_summary"]["unincorporated_total"] >= 2 and before["evidence_summary"]["unresolved_judgments_total"] == 1
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    state = core._load_state(root)
    core.task_update(root, "controller", state["revision"], write_json(root, "u", {"pending_results": ["archive now"]}))
    archived = core._load_state(root)
    assert archived["archive"] and stub_count(archived) >= 100
    stubbed = core._indexed_ids(archived)
    assert {"open", "basis", "repair", "open.s"}.isdisjoint(stubbed), "open evidence is never archived"
    assert {"O3", "J3", "O3.s"} <= stubbed
    after = views(root, monkeypatch)
    before["counts"].pop("records"), after["counts"].pop("records")
    before["changes_since"]["records"] = after["changes_since"]["records"] = []
    for key in before:
        if key == "changes_since":
            for field in ("current_revision", "revision_gap"):
                before[key].pop(field), after[key].pop(field)
        assert after[key] == before[key], key
    # With the gates clear the close still works on the archived ledger.
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", core.STATE_MAX_BYTES * 7 // 10)
    assert core.task_close(root, core._load_state(root)["revision"], override_reason="test close")["status"] == "DONE"


# --- retrieval and damaged segments ----------------------------------------------------------------

def archived_ledger(tmp_path: Path, monkeypatch) -> tuple[Path, dict, dict]:
    root = repo(tmp_path)
    state = with_groups(core._load_state(root), 0, 20)
    state["records"] = [
        {"id": "old", "kind": "note", "text": filler(2000, 1), "producer": "controller", "revision": 1, "source_refs": [],
         "status": "RECORDED", "supersedes": []},
        {"id": "new", "kind": "note", "text": "short", "producer": "controller", "revision": 1, "source_refs": [],
         "status": "RECORDED", "supersedes": ["old"]}]
    state["schema_version"] = 9
    write_raw(root, state)
    original = copy.deepcopy(core._load_state(root))
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    core.task_update(root, "controller", original["revision"], write_json(root, "u", {"pending_results": ["go"]}))
    return root, original, core._load_state(root)


def test_task_get_returns_the_full_archived_object(tmp_path, monkeypatch):
    root, original, state = archived_ledger(tmp_path, monkeypatch)
    observations = {item["id"]: item for item in original["evidence_continuity"]["observations"]}
    assert "O1" in core._indexed_ids(state)
    assert "O1" not in {item["id"] for item in state["evidence_continuity"]["observations"]}, "evicted objects leave the hot list"
    got = core.task_get(root, "O1")
    assert got["object"] == observations["O1"] and got["archived"]["segment"] == state["archive"][0]["sha256"]
    assert core.task_get(root, "J1")["object"] == original["evidence_continuity"]["judgments"][1]
    assert core.task_get(root, "O1.s")["object"] == next(item for item in original["evidence_refs"] if item["id"] == "O1.s")
    assert core.task_get(root, "old")["object"] == original["records"][0]
    assert {"old", "new"} <= {item["id"] for item in state["records"]}, "current and recently written records stay hot"
    # A handoff that changes after eviction is re-hydrated and keeps its new fields.
    core.task_handoff_usage(root, "H1", {"model": "m-9"})
    assert core.task_get(root, "H1")["object"]["usage"]["model"] == "m-9"
    # The segment is content-addressed and holds whole objects.
    segment = next(path for path in segments(root, state["task_id"]) if path.stem == state["archive"][0]["sha256"])
    assert hashlib.sha256(segment.read_bytes()).hexdigest() == segment.stem
    body = json.loads(segment.read_bytes())
    assert body["format"] == core.ARCHIVE_SEGMENT_FORMAT and body["task_id"] == state["task_id"] and body["version"] == 2
    assert {entry["collection"] for entry in body["items"]} >= {"observations", "judgments", "evidence_refs", "handoffs"}


@pytest.mark.parametrize("damage", ["tamper", "delete", "foreign"])
def test_damaged_or_missing_segment_is_reported_and_gates_keep_working(tmp_path, monkeypatch, damage):
    root, original, state = archived_ledger(tmp_path, monkeypatch)
    segment = segments(root, state["task_id"])[0]
    if damage == "tamper":
        segment.write_bytes(segment.read_bytes().replace(b"group 1 ", b"group X "))
    elif damage == "delete":
        segment.unlink()
    else:
        raw = json.loads(segment.read_bytes())
        raw["task_id"] = "00000000-0000-4000-8000-000000000000"
        segment.write_bytes(json.dumps(raw).encode())
    with pytest.raises(core.ThalirisError) as caught:
        core.task_get(root, "O1")
    assert caught.value.code == "TASK_ARCHIVE_UNAVAILABLE" and caught.value.details["object_type"] == "observations"
    assert caught.value.details["segment"] == segment.stem and "restore" in caught.value.recovery
    assert core.task_get(root, "R4")["object"] == {"id": "R4", "workchain_ref": "w4"}
    packet = core.task_status(root, view="compact")
    assert packet["Evidence"]["unincorporated_total"] == 0 and packet["Archive"]["segments"] == 1
    # A write that needs no object from the damaged segment still works (H19 is hot).
    core.task_observe(root, "implementer", {"id": "later", "candidate": "C1", "handoff_id": "H19", "requirement_refs": ["R19"],
                                            "source_refs": ["O19.s"], "text": "still writable"})
    assert core.task_close(root, core._load_state(root)["revision"])["status"] == "DONE"


def test_stubs_cannot_be_forged_or_smuggled(tmp_path, monkeypatch):
    root, original, state = archived_ledger(tmp_path, monkeypatch)
    forged = copy.deepcopy(state)
    forged["evidence_continuity"]["observations"][0]["archived"] = "f" * 64
    with pytest.raises(core.ThalirisError, match="unknown segment"):
        core._validate_state(root, forged)
    orphan = copy.deepcopy(state)
    del orphan["archive"]
    with pytest.raises(core.ThalirisError, match="without an archive index"):
        core._validate_state(root, orphan)
    old = copy.deepcopy(state)
    old["schema_version"] = 9
    with pytest.raises(core.ThalirisError, match="require task schema 10"):
        core._validate_state(root, old)
    with pytest.raises(core.ThalirisError, match="assigned by Core"):
        core.task_observe(root, "implementer", {"id": "x", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R0"],
                                                "source_refs": ["O0.s"], "text": "t", "archived": "f" * 64})
    with pytest.raises(ValueError, match="invalid source reference"):
        core.task_update(root, "controller", state["revision"], write_json(root, "src", {
            "evidence_refs": [{"id": "s-new", "kind": "k", "locator": "l", "summary": "s", "archived": "f" * 64}]}))


# --- schema promotion and serialization --------------------------------------------------------------

@pytest.mark.parametrize("version", [7, 8, 9])
def test_indented_older_state_loads_and_is_promoted_on_write(tmp_path, version):
    root = repo(tmp_path)
    state = with_groups(core._load_state(root), 0, 3)
    for handoff in state["evidence_continuity"]["handoffs"]:
        if version < 9:
            handoff.pop("usage"), handoff.pop("claims")
    state["schema_version"] = version
    raw = write_raw(root, state, indent=True)
    loaded = core.task_show(root)["state"]
    assert loaded["schema_version"] == core._STATE_SCHEMA_VERSION and core._state_path(root).read_bytes() == raw
    core.task_update(root, "controller", state["revision"], write_json(root, "u", {"active_work": ["next"]}))
    written = core._state_path(root).read_bytes()
    assert written == core._serialize_state(core._load_state(root)) and b"\n " not in written
    assert json.loads(written)["schema_version"] == core._STATE_SCHEMA_VERSION
    assert json.loads(written)["evidence_continuity"] == state["evidence_continuity"]


def test_a_schema_7_state_is_read_and_written_by_this_code(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    state["schema_version"] = 7
    state["records"] = [{"id": "r1", "kind": "note", "text": "kept", "producer": "controller", "revision": 1, "source_refs": [],
                         "status": "RECORDED", "supersedes": []}]
    write_raw(root, state, indent=True)
    assert core.task_state_schema_diagnostic(root) is None
    core.task_update(root, "controller", state["revision"], write_json(root, "u", {"pending_results": ["after upgrade"]}))
    written = disk(root)
    assert written["schema_version"] == core._STATE_SCHEMA_VERSION and written["records"] == state["records"]
    assert written["pending_results"] == ["after upgrade"]


def test_only_a_newer_schema_is_refused_and_the_recovery_names_an_upgrade(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    state["schema_version"] = core._STATE_SCHEMA_VERSION + 1
    raw = write_raw(root, state)
    with pytest.raises(core.TaskStateSchemaIncompatible) as caught:
        core._load_state(root)
    diagnostic = caught.value.diagnostic
    assert diagnostic["upgrade_required"] is True and "upgrade" in diagnostic["recovery_action"]
    assert core._state_path(root).read_bytes() == raw


def test_public_capacity_helpers(tmp_path):
    capacity = core.task_state_capacity()
    assert capacity["max_bytes"] == core.STATE_MAX_BYTES == 512 * 1024
    assert capacity["archive_high_water_bytes"] < capacity["max_bytes"]
    assert capacity["schema_version"] == core._STATE_SCHEMA_VERSION and 7 in capacity["supported_schemas"]
    small = tmp_path / "small.json"
    small.write_bytes(b"{}")
    assert core.read_state_bytes(small) == b"{}"
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (core.STATE_MAX_BYTES + 1))
    with pytest.raises(core.ThalirisError) as caught:
        core.read_state_bytes(big)
    assert caught.value.code == "TASK_STATE_INVALID"


# --- atomicity ----------------------------------------------------------------------------------------

def test_cas_conflict_during_archiving_leaves_no_partial_state(tmp_path, monkeypatch):
    root = repo(tmp_path)
    state = with_groups(core._load_state(root), 0, 20)
    state["schema_version"] = 9
    write_raw(root, state)
    stale = core._load_state(root)["revision"]
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    core.task_update(root, "controller", stale, write_json(root, "a", {"pending_results": ["writer A"]}))
    after_a = core._state_path(root).read_bytes()
    task_id = json.loads(after_a)["task_id"]
    written = segments(root, task_id)
    assert json.loads(after_a)["archive"] and len(written) == 1
    with pytest.raises(core.ThalirisError) as caught:
        core.task_update(root, "controller", stale, write_json(root, "b", {"pending_results": ["writer B"]}))
    assert caught.value.code == "TASK_REVISION_CONFLICT"
    assert core._state_path(root).read_bytes() == after_a and segments(root, task_id) == written

    # A failure between the segment write and the state write leaves an orphan segment, not a partial state.
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", core.STATE_MAX_BYTES)
    core.task_observe(root, "implementer", {"id": "more", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R0"],
                                            "source_refs": ["O0.s"], "text": filler(600, 1)})
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "j", {
        "id": "Jmore", "candidate": "C1", "requirement_ref": "R0", "observation_refs": ["more"], "outcome": "satisfied",
        "reasoning": filler(600, 2)}))
    before = core._state_path(root).read_bytes()
    count = len(segments(root, task_id))
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    real = core._atomic_write
    state_path = core._state_path(root)

    def failing(target, content):
        if Path(target) == state_path:
            raise OSError("simulated crash after the segment")
        return real(target, content)

    monkeypatch.setattr(core, "_atomic_write", failing)
    with pytest.raises(OSError, match="simulated"):
        core.task_update(root, "controller", json.loads(before)["revision"], write_json(root, "c", {"pending_results": ["C"]}))
    monkeypatch.setattr(core, "_atomic_write", real)
    assert core._state_path(root).read_bytes() == before
    assert len(segments(root, task_id)) == count + 1, "the orphan segment stays"
    assert core.task_get(root, "O7")["object"]["text"] == filler(1000, 7)
    core.task_update(root, "controller", json.loads(before)["revision"], write_json(root, "d", {"pending_results": ["D"]}))
    assert disk(root)["pending_results"] == ["D"] and core.task_get(root, "more")["object"]["text"] == filler(600, 1)


def test_hot_list_cap_counts_only_hot_items(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    state["evidence_refs"] = [{"id": f"s{i}", "kind": "test", "locator": "tests/x", "summary": "s"} for i in range(600)]
    state["schema_version"] = 9
    # 600 uncited sources: the write stubs settled ones so the hot list fits its cap.
    core._write_state(root, state)
    written = disk(root)
    assert len(written["evidence_refs"]) <= core.STATE_LIST_MAX
    assert len(written["evidence_refs"]) + len(core._index_map(core._load_state(root))["evidence_refs"]) == 600
    assert core.task_get(root, "s1")["object"] == {"id": "s1", "kind": "test", "locator": "tests/x", "summary": "s"}


def test_still_over_the_cap_after_archiving_explains_why(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    with_groups(state, 0, 4)
    task_id = state["task_id"]
    data = state["evidence_continuity"]
    # Open (unincorporated) observations can never move.
    for index in range(40):
        data["observations"].append({"id": f"open{index}", "task_id": task_id, "producer": "implementer", "candidate": "C1",
                                     "handoff_id": "H0", "requirement_refs": ["R0"], "source_refs": ["O0.s"],
                                     "text": filler(15000, index)})
    state["schema_version"] = 9
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError, match="task state exceeds 512 KiB") as caught:
        core._write_state(root, state)
    assert caught.value.code == "TASK_STATE_CAPACITY_EXCEEDED" and caught.value.details["field"] == "state_file"
    assert caught.value.details["open_observation_edges"] == 40 and "open evidence" in caught.value.recovery
    assert core._state_path(root).read_bytes() == before and not segments(root, task_id)


# --- performance ----------------------------------------------------------------------------------

def test_archiving_a_512_kib_ledger_takes_under_a_second(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    count = 0
    while len(core._serialize_state(state)) < core.STATE_MAX_BYTES:
        group(state, count)
        count += 1
    state["schema_version"] = 9
    started = time.perf_counter()
    core._write_state(root, state)
    elapsed = time.perf_counter() - started
    assert disk(root)["archive"] and core._state_path(root).stat().st_size < core.STATE_ARCHIVE_HIGH_WATER_BYTES
    assert elapsed < 1.0, elapsed


# --- authority anchor tolerance -------------------------------------------------------------------

INTENT = {"human_instruction": "x", "boundary": "y", "invariants": "z", "acceptance": "w", "execution_mode": "delegated"}


def test_an_anchor_from_an_older_writer_loads_and_still_detects_tampering(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    store = authority.AuthorityStore(root, tmp_path / "external", protected_paths=(".context/config.json",))
    core.task_start(root, "anchored", None, None, actor="controller")
    record = store.establish(core.task_show(root)["state"], INTENT, adapter_fields={"lifecycle_sha256": "ABSENT"})
    # An older writer: no version marker, no history/snapshots, no execution mode, no adapter digest.
    old = {key: value for key, value in record.items() if key not in ("version", "history", "snapshots", "lifecycle_sha256")}
    old["contract"] = {key: value for key, value in record["contract"].items() if key != "execution_mode"}
    store.path().write_bytes(json.dumps(old).encode("utf-8"))
    loaded = store.read()
    assert loaded["version"] == authority.ANCHOR_VERSION and loaded["history"] == [] and loaded["snapshots"] == {}
    assert loaded["contract"]["execution_mode"] == "delegated"
    lifecycle = tmp_path / "lifecycle.json"
    lifecycle.write_text("{}", encoding="utf-8")
    assert store.check(evidence={"lifecycle_sha256": (lifecycle, "LIFECYCLE_CHANGED")}) is not None
    core.task_update(root, "controller", 1, write_json(root, "u", {"pending_results": ["p"]}))
    with pytest.raises(ValueError, match="TASK_AUTHORITY_STATE_CHANGED"):
        store.check()
    store.checkpoint()
    assert store.check() is not None and json.loads(store.path().read_bytes())["version"] == authority.ANCHOR_VERSION
    (root / ".context" / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="TASK_AUTHORITY_SECURITY_CHANGED"):
        store.check()


def test_an_anchor_from_a_newer_writer_or_without_a_state_digest_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    store = authority.AuthorityStore(root, tmp_path / "external")
    core.task_start(root, "anchored", None, None, actor="controller")
    record = store.establish(core.task_show(root)["state"], INTENT)
    store.path().write_bytes(json.dumps({**record, "version": authority.ANCHOR_VERSION + 1}).encode("utf-8"))
    with pytest.raises(core.ThalirisError, match="TASK_AUTHORITY_INVALID") as caught:
        store.read()
    assert caught.value.details["upgrade_required"] is True and "upgrade" in caught.value.recovery
    store.path().write_bytes(json.dumps({key: value for key, value in record.items() if key != "state_sha256"}).encode("utf-8"))
    with pytest.raises(core.ThalirisError, match="TASK_AUTHORITY_INVALID") as caught:
        store.read()
    assert caught.value.details["missing_fields"] == ["state_sha256"]
