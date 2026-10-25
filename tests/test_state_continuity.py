"""Task-state continuity: compatible older schemas, named capacity errors, bounded Git, anchor faults."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from thaliris import authority, core


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    core.init(tmp_path)
    return tmp_path


def payload(root: Path, name: str, value: object) -> str:
    path = root.parent / f"{root.name}-{name}.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_version(root: Path, version: object, **changes: object) -> bytes:
    path = core._state_path(root)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["schema_version"] = version
    state.update(changes)
    path.write_bytes((json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return path.read_bytes()


# --- compatible older schema versions -------------------------------------------------------------

def test_valid_v6_state_is_read_as_current_and_becomes_v7_on_the_next_write(tmp_path):
    root = repo(tmp_path)
    started = core.task_start(root, "keep me", None, None)
    core.task_update(root, "controller", 1, payload(root, "u", {
        "records": [{"id": "r1", "kind": "note", "text": "kept"}], "pending_results": ["p"]}))
    v6_bytes = rewrite_version(root, 6)
    state_before = json.loads(v6_bytes)

    shown = core.task_show(root)["state"]
    assert shown["schema_version"] == core._STATE_SCHEMA_VERSION == 7
    assert (shown["task_id"], shown["goal"], shown["revision"], shown["records"]) == (
        started["task_id"], "keep me", state_before["revision"], state_before["records"])
    assert core.task_status(root)["Task"]["revision"] == state_before["revision"]
    assert core.task_state_schema_diagnostic(root) is None
    assert core._state_path(root).read_bytes() == v6_bytes, "reading must not rewrite the ledger"

    core.task_update(root, "controller", state_before["revision"], payload(root, "u2", {"active_work": ["next"]}))
    written = json.loads(core._state_path(root).read_text(encoding="utf-8"))
    assert written["schema_version"] == 7 and written["revision"] == state_before["revision"] + 1
    assert written["records"] == state_before["records"] and written["task_id"] == started["task_id"]
    assert written["active_work"] == ["next"]


def test_v6_done_state_is_readable(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "finished", None, None)
    core.task_close(root, 1)
    rewrite_version(root, 6)
    assert core.task_show(root)["state"]["status"] == "DONE"


@pytest.mark.parametrize("version", [5, 0, 8, 99])
def test_other_schema_versions_are_still_refused_with_the_diagnostic(tmp_path, version):
    root = repo(tmp_path)
    core.task_start(root, "refuse", None, None)
    raw = rewrite_version(root, version)
    with pytest.raises(core.TaskStateSchemaIncompatible, match="invalid task state schema") as caught:
        core.task_show(root)
    diagnostic = caught.value.diagnostic
    assert diagnostic["status"] == "STATE_SCHEMA_INCOMPATIBLE"
    assert diagnostic["from_version"] == version and diagnostic["to_version"] == 7
    assert diagnostic["state_sha256"] == hashlib.sha256(raw).hexdigest()
    assert diagnostic["recoverable"] is (0 < version < 7)
    if diagnostic["recoverable"]:
        action = diagnostic["recovery_action"]
        assert diagnostic["state_sha256"] in action and "task-recover-state" not in action and "adapter" in action
    else:
        assert diagnostic["recovery_action"] == "NONE"
    assert core.task_state_schema_diagnostic(root)["from_version"] == version
    assert core._state_path(root).read_bytes() == raw


@pytest.mark.parametrize("damage", [
    {"surprise_field": 1},
    {"goal": ""},
    {"revision": 0},
    {"records": [{"id": "r1"}]},
    {"task_surface_baseline": "not-a-baseline"},
])
def test_malformed_v6_state_is_refused_not_promoted(tmp_path, damage):
    root = repo(tmp_path)
    core.task_start(root, "malformed", None, None)
    raw = rewrite_version(root, 6, **damage)
    with pytest.raises(core.TaskStateSchemaIncompatible):
        core.task_show(root)
    with pytest.raises(core.TaskStateSchemaIncompatible):
        core.task_update(root, "controller", 1, payload(root, "u", {"active_work": ["x"]}))
    assert core.task_state_schema_diagnostic(root)["from_version"] == 6
    assert core._state_path(root).read_bytes() == raw


def test_bool_and_string_versions_are_not_promoted(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "types", None, None)
    for version in (True, "6", 6.0):
        rewrite_version(root, version)
        with pytest.raises(ValueError):
            core.task_show(root)


def test_prior_versions_come_from_one_extensible_table(tmp_path, monkeypatch):
    root = repo(tmp_path)
    core.task_start(root, "chain", None, None)
    rewrite_version(root, 5)
    with pytest.raises(core.TaskStateSchemaIncompatible):
        core.task_show(root)
    monkeypatch.setitem(core._COMPATIBLE_PRIOR_SCHEMAS, 5, lambda raw: {**raw, "schema_version": 6})
    assert core.task_show(root)["state"]["schema_version"] == 7
    # A gap in the chain keeps older versions refused.
    rewrite_version(root, 4)
    with pytest.raises(core.TaskStateSchemaIncompatible):
        core.task_show(root)


def test_reading_a_v6_ledger_does_not_trip_a_v6_authority_anchor(tmp_path):
    root = repo(tmp_path)
    store = authority.AuthorityStore(root, tmp_path.parent / (tmp_path.name + "-external"), protected_paths=())
    core.task_start(root, "anchored", None, None, actor="controller")
    store.establish(core.task_show(root)["state"], {
        "human_instruction": "x", "boundary": "y", "invariants": "z", "acceptance": "w", "execution_mode": "delegated"})
    v6_bytes = rewrite_version(root, 6)
    store.checkpoint()
    assert store.check() is not None

    # Reads promote in memory only: the anchored digest still matches the disk bytes.
    core.task_show(root)
    core.task_status(root)
    assert store.check() is not None
    assert core._state_path(root).read_bytes() == v6_bytes

    # The write rewrites the ledger as v7: the adapter's checkpoint is what re-anchors it.
    core.task_update(root, "controller", 1, payload(root, "u", {"active_work": ["x"]}))
    with pytest.raises(ValueError, match="TASK_AUTHORITY_STATE_CHANGED"):
        store.check()
    store.checkpoint()
    assert store.check() is not None and json.loads(core._state_path(root).read_text())["schema_version"] == 7

    # Tampering with the promoted ledger is still caught.
    tampered = json.loads(core._state_path(root).read_text())
    tampered["pending_results"] = ["forged"]
    core._state_path(root).write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="TASK_AUTHORITY_STATE_CHANGED"):
        store.check()


# --- named capacity errors -------------------------------------------------------------------------

def bulk_state(root: Path, **lists: list) -> bytes:
    state = core._load_state(root)
    state.update(lists)
    core._write_state(root, state)
    return core._state_path(root).read_bytes()


def record(index: int) -> dict:
    return {"id": f"bulk-{index}", "kind": "note", "text": f"t{index}", "producer": "controller", "revision": 1,
            "source_refs": [], "status": "ACTIVE", "supersedes": []}


def assert_capacity(exc: core.ThalirisError, field: str, limit: int, count: int | None = None) -> None:
    assert isinstance(exc, ValueError) and exc.code == "TASK_STATE_CAPACITY_EXCEEDED"
    assert exc.details["field"] == field and exc.details["limit"] == limit
    if count is not None:
        assert exc.details["count"] == count
    assert exc.recovery and "unchanged" in exc.recovery
    envelope = core.error_envelope(exc)
    assert envelope["code"] == "TASK_STATE_CAPACITY_EXCEEDED" and envelope["details"]["field"] == field


def test_full_records_list_names_the_field_and_leaves_other_writes_and_close_working(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    before = bulk_state(root, records=[record(i) for i in range(512)])
    revision = json.loads(before)["revision"]
    with pytest.raises(core.ThalirisError, match="state list exceeds limit") as caught:
        core.task_update(root, "controller", revision, payload(root, "more", {
            "records": [{"id": "one-more", "kind": "note", "text": "x"}]}))
    assert_capacity(caught.value, "records", 512, 513)
    assert "records" in str(caught.value) and "512" in str(caught.value)
    assert core._state_path(root).read_bytes() == before
    core.task_update(root, "controller", revision, payload(root, "ok", {"pending_results": ["still writable"]}))
    closed = core.task_close(root, revision + 1)
    assert closed["status"] == "DONE"


def test_full_evidence_refs_list_names_the_field(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    sources = [{"id": f"s{i}", "kind": "test", "locator": "tests/x", "summary": "s"} for i in range(512)]
    before = bulk_state(root, evidence_refs=sources)
    with pytest.raises(core.ThalirisError) as caught:
        core.task_update(root, "controller", json.loads(before)["revision"], payload(root, "more", {
            "evidence_refs": [{"id": "extra", "kind": "test", "locator": "tests/x", "summary": "s"}]}))
    assert_capacity(caught.value, "evidence_refs", 512, 513)
    assert core._state_path(root).read_bytes() == before


@pytest.mark.parametrize("field", ["artifact_refs", "verification_results"])
def test_artifact_and_verification_limits_are_named(tmp_path, field):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    state = core._load_state(root)
    state[field] = [{"id": f"x{i}"} for i in range(257)]
    with pytest.raises(core.ThalirisError) as caught:
        core._validate_state(root, state)
    assert_capacity(caught.value, field, 256, 257)


def test_continuity_list_limit_names_the_collection(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    state = core._load_state(root)
    state["evidence_continuity"] = {"requirements": [], "handoffs": [], "judgments": [],
                                    "observations": [{"id": f"o{i}"} for i in range(513)]}
    with pytest.raises(core.ThalirisError) as caught:
        core._validate_state(root, state)
    assert_capacity(caught.value, "observations", 512, 513)


@pytest.mark.parametrize("field", ["active_work", "pending_results"])
def test_routing_list_count_limit_is_named(tmp_path, field):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        core.task_update(root, "controller", 1, payload(root, "many", {field: ["x"] * 65}))
    assert_capacity(caught.value, field, 64, 65)
    assert core._state_path(root).read_bytes() == before


def test_routing_byte_limit_is_named_and_keeps_its_message(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError, match="Active Work \\+ Pending Results exceed 8192 UTF-8 bytes") as caught:
        core.task_update(root, "controller", 1, payload(root, "big", {"active_work": ["a" * 3000] * 3}))
    assert_capacity(caught.value, "active_work+pending_results", 8192)
    assert caught.value.details["unit"] == "UTF-8 bytes" and caught.value.details["count"] > 8192
    assert core._state_path(root).read_bytes() == before


def test_state_file_size_limit_is_named_and_close_still_works(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "capacity", None, None)
    fill = [{"id": f"big-{i}", "kind": "note", "text": "x" * 16000} for i in range(30)]
    core.task_update(root, "controller", 1, payload(root, "fill", {"records": fill}))
    before = core._state_path(root).read_bytes()
    assert len(before) < 512 * 1024
    with pytest.raises(core.ThalirisError, match="task state exceeds 512 KiB") as caught:
        core.task_update(root, "controller", 2, payload(root, "over", {
            "records": [{"id": f"over-{i}", "kind": "note", "text": "y" * 16000} for i in range(3)]}))
    assert_capacity(caught.value, "state_file", 512 * 1024)
    assert core._state_path(root).read_bytes() == before
    assert core.task_close(root, 2)["status"] == "DONE"


def test_oversized_state_file_on_load_is_a_coded_invalid_state(tmp_path):
    root = repo(tmp_path)
    core.task_start(root, "too big", None, None)
    core._state_path(root).write_bytes(b" " * (512 * 1024 + 1))
    with pytest.raises(core.ThalirisError, match="exceeds 512 KiB") as caught:
        core.task_show(root)
    assert caught.value.code == "TASK_STATE_INVALID"


# --- anchor faults and recovery retry --------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    return authority.AuthorityStore(root, tmp_path / "external", protected_paths=(".context/config.json", "host/security.json"))


INTENT = {"human_instruction": "x", "boundary": "y", "invariants": "z", "acceptance": "w", "execution_mode": "delegated"}


def anchored(store):
    core.task_start(store.root, "anchored", None, None, actor="controller")
    return store.establish(core.task_show(store.root)["state"], INTENT)


@pytest.mark.parametrize("damage", [b"{not json", b"", b"\xff\xfe\x00 not utf-8"])
def test_corrupt_anchor_has_a_code_on_every_entry_point(store, damage):
    anchored(store)
    store.path().write_bytes(damage)
    state_bytes = core._state_path(store.root).read_bytes()
    digest = hashlib.sha256(damage).hexdigest()
    calls = [
        store.read,
        store.check,
        lambda: store.recover(digest, "Restore the anchor"),
        lambda: store.establish(core.task_show(store.root)["state"], INTENT),
        store.checkpoint,
    ]
    for call in calls:
        with pytest.raises(core.ThalirisError, match="^TASK_AUTHORITY_INVALID$") as caught:
            call()
        assert caught.value.code == "TASK_AUTHORITY_INVALID" and isinstance(caught.value, ValueError)
        assert core.error_envelope(caught.value)["code"] == "TASK_AUTHORITY_INVALID"
    assert store.path().read_bytes() == damage and core._state_path(store.root).read_bytes() == state_bytes
    assert not (store.directory / "recovery").exists()


def test_recovery_failing_midway_can_be_retried_with_the_same_digest(store, monkeypatch):
    original = anchored(store)
    anchor_bytes = store.path().read_bytes()
    expected = hashlib.sha256(anchor_bytes).hexdigest()
    state_path = core._state_path(store.root)
    config_path = store.root / ".context/config.json"
    state_bytes, config_bytes = state_path.read_bytes(), config_path.read_bytes()
    state_path.write_bytes(b'{"tampered":true}\n')
    config_path.write_bytes(b"changed config\n")

    real_write = core._atomic_write
    failed = []

    def failing_write(target, content):
        if Path(target) == state_path and not failed:
            failed.append(target)
            raise OSError("simulated write failure while restoring the ledger")
        return real_write(target, content)

    monkeypatch.setattr(core, "_atomic_write", failing_write)
    with pytest.raises(OSError, match="simulated"):
        store.recover(expected, "Restore selected intent")
    assert failed and store.path().read_bytes() == anchor_bytes, "a failed recovery must not rewrite the anchor"
    assert config_path.read_bytes() == config_bytes, "the earlier restored file is already back"
    assert state_path.read_bytes() == b'{"tampered":true}\n'

    recovered = store.recover(expected, "Restore selected intent")
    assert recovered["status"] == "TASK_AUTHORITY_RECOVERED" and recovered["task_id"] == original["task_id"]
    assert state_path.read_bytes() == state_bytes and config_path.read_bytes() == config_bytes
    assert store.check()["contract"] == original["contract"]

    archives = sorted((store.directory / "recovery").iterdir())
    assert len(archives) == 2, "each attempt archives what it found before touching anything"
    assert all((archive / "authority.json").read_bytes() == anchor_bytes for archive in archives)
    assert any((archive / state_path.relative_to(store.root)).read_bytes() == b'{"tampered":true}\n' for archive in archives)
    assert any((archive / ".context/config.json").read_bytes() == b"changed config\n" for archive in archives)
    assert Path(store.read()["recoveries"][-1]["archive"]) in archives


# --- bounded Git ------------------------------------------------------------------------------------

@pytest.fixture
def git_calls(monkeypatch):
    calls = []
    real = subprocess.run

    def recording(args, *a, **kw):
        if args and args[0] == "git":
            calls.append((tuple(args[:3]), kw.get("timeout")))
        return real(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", recording)
    return calls


def test_every_core_git_call_is_bounded(tmp_path, git_calls):
    root = repo(tmp_path)
    git_calls.clear()
    started = core.task_start(root, "bounded", None, None)
    core.task_candidate_observation(root)
    core.task_record_verification(root, started["revision"], "v1", "test", "PASS", "ok", observed_by="runner")
    core.task_show(root)
    assert git_calls
    assert {name[1] for name, _ in git_calls} >= {"check-ignore", "status", "rev-parse"}
    assert all(timeout == core.GIT_TIMEOUT_SECONDS == 60 for _, timeout in git_calls), git_calls


def timeout_on(monkeypatch, subcommand: str):
    real = subprocess.run

    def fake(args, *a, **kw):
        if args and args[0] == "git" and subcommand in args:
            raise subprocess.TimeoutExpired(args, kw.get("timeout") or 0)
        return real(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", fake)


def test_git_timeouts_degrade_to_unavailable_instead_of_hanging_or_inventing(tmp_path, monkeypatch):
    root = repo(tmp_path)
    timeout_on(monkeypatch, "status")
    assert core._surface_snapshot(root) == "UNAVAILABLE"
    started = core.task_start(root, "no status", None, None)
    assert core.task_show(root)["state"]["task_surface_baseline"] == "UNAVAILABLE"
    assert core.task_show(root)["task_surface_delta"]["status"] == "UNAVAILABLE"
    assert core.task_candidate_observation(root)["paths"] is None
    monkeypatch.undo()

    timeout_on(monkeypatch, "--verify")
    assert core._git_head(root) is None
    assert core.task_candidate_observation(root)["task_id"] == started["task_id"]
    monkeypatch.undo()


def test_state_ignore_and_root_discovery_timeouts_are_refused_as_unknown(tmp_path, monkeypatch):
    root = repo(tmp_path)
    timeout_on(monkeypatch, "check-ignore")
    with pytest.raises(ValueError, match="UNKNOWN") as caught:
        core.task_start(root, "cannot tell", None, None)
    assert "ignore" in str(caught.value) and "run context init" not in str(caught.value)
    assert not core._state_path(root).exists()
    monkeypatch.undo()

    timeout_on(monkeypatch, "--show-toplevel")
    with pytest.raises(ValueError, match="Git root discovery is UNKNOWN"):
        core._git_root(tmp_path)
