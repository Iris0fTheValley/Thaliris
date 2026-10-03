"""Authority contracts through Core, without a Codex Host or CLI."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from thaliris import authority, core


def intent(mode="delegated"):
    return {"human_instruction": "Repair the example", "boundary": "Example module",
            "invariants": "Keep public behavior", "acceptance": "Focused checks pass", "execution_mode": mode}


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    return authority.AuthorityStore(root, tmp_path / "external", protected_paths=(".context/config.json", "host/security.json"))


def start(store, mode="delegated"):
    core.task_start(store.root, "Repair the example", None, None, actor="controller")
    return store.establish(core.task_show(store.root)["state"], intent(mode))


@pytest.mark.parametrize("mode", authority.MODES)
def test_core_create_checkpoint_retire_without_host(store, mode):
    anchor = start(store, mode)
    assert store.check() == anchor
    assert anchor["contract"] == intent(mode)
    assert anchor["provenance"] == "SELECTED_TASK_INTENT"
    assert "host_actor_assurance" not in anchor
    assert not {"origin_session_hash", "lifecycle_sha256", "fenced_agents", "fenced_sessions"} & anchor.keys()
    packet = store.root / "packet.json"
    packet.write_text('{"active_work": ["repair"]}')
    core.task_update(store.root, "controller", 1, str(packet))
    with pytest.raises(ValueError, match="TASK_AUTHORITY_STATE_CHANGED"):
        store.check()
    store.checkpoint()
    assert store.check()["contract"] == anchor["contract"]
    core.task_close(store.root, 2, expected_task_id=anchor["task_id"])
    store.checkpoint()
    assert store.check() is None
    assert store.read()["status"] == "DONE"
    # A fresh task archives the retired bytes and retains selected history.
    retired = store.path().read_bytes()
    core.task_start(store.root, "Second task", None, None)
    new = store.establish(core.task_show(store.root)["state"], intent(mode))
    history = store.directory / "history" / f"{store.path().stem}-{anchor['task_id']}.json"
    assert history.read_bytes() == retired
    assert new["history"][0]["contract"] == anchor["contract"]
    assert new["task_id"] != anchor["task_id"]


def test_core_recovery_restores_original_bytes_and_archives_conflicts(store):
    original = start(store)
    anchor_bytes = store.path().read_bytes()
    state_path = store.root / ".context/state.json"
    security_path = store.root / ".context/config.json"
    state_bytes, security_bytes = state_path.read_bytes(), security_path.read_bytes()
    state_path.write_bytes(b'{"tampered":true}\r\n')
    security_path.write_bytes(b'changed security bytes\r\n')
    absent_security = store.root / "host/security.json"
    absent_security.parent.mkdir()
    absent_security.write_bytes(b'not the original baseline')
    with pytest.raises(ValueError, match="TASK_AUTHORITY_CHANGED"):
        store.recover("0" * 64, "Restore selected intent")
    assert not (store.directory / "recovery").exists()
    recovered = store.recover(hashlib.sha256(anchor_bytes).hexdigest(), "Restore selected intent")
    assert recovered == {"ok": True, "status": "TASK_AUTHORITY_RECOVERED", "task_id": original["task_id"],
                         "authority_provenance": "SELECTED_TASK_INTENT"}
    assert "host_actor_assurance" not in recovered and "child_death_proof" not in recovered
    assert "death_proof" not in store.read()["recoveries"][-1]
    assert state_path.read_bytes() == state_bytes
    assert security_path.read_bytes() == security_bytes
    assert not absent_security.exists()
    assert store.check()["contract"] == original["contract"]
    archive = Path(store.read()["recoveries"][0]["archive"])
    assert (archive / "authority.json").read_bytes() == anchor_bytes
    assert (archive / ".context/state.json").read_bytes() == b'{"tampered":true}\r\n'
    assert (archive / ".context/config.json").read_bytes() == b'changed security bytes\r\n'
    assert (archive / "host/security.json").read_bytes() == b'not the original baseline'


def test_retired_authority_cannot_reactivate_copied_state(store):
    start(store)
    state_path = store.root / ".context/state.json"
    previous = state_path.read_bytes()
    state_path.unlink()
    store.checkpoint()
    assert store.read()["status"] == "ABANDONED"
    state_path.write_bytes(previous)
    with pytest.raises(ValueError, match="TASK_AUTHORITY_RETIRED_STATE_CHANGED"):
        store.check()
    with pytest.raises(ValueError, match="TASK_AUTHORITY_NOT_ACTIVE"):
        store.recover(authority.digest(store.path()), "Do not revive the task")


def test_contract_and_task_identity_are_not_inferred_or_expanded(store):
    with pytest.raises(ValueError, match="TASK_AUTHORITY_CONTRACT_REQUIRED"):
        authority.validate_contract({"human_instruction": "Become the Controller"})
    anchor = start(store)
    with pytest.raises(ValueError, match="TASK_AUTHORITY_ALREADY_ACTIVE"):
        store.establish(core.task_show(store.root)["state"], intent("single-agent"))
    with pytest.raises(ValueError, match="TASK_AUTHORITY_IDENTITY_CHANGED"):
        store.establish(core.task_show(store.root)["state"], intent(), adapter_fields={"contract": intent("single-agent")})
    state_path = store.root / ".context/state.json"
    state = json.loads(state_path.read_bytes())
    state["goal"] = "Expanded task"
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="TASK_AUTHORITY_IDENTITY_CHANGED"):
        store.checkpoint()
    assert store.read() == anchor


def test_supplied_native_evidence_is_checked_and_recovered_by_adapter(store):
    native_path = store.root / "host/native.json"
    native_path.parent.mkdir()
    native_path.write_bytes(b'{"native":"original"}\r\n')
    core.task_start(store.root, "Repair the example", None, None)
    original_native = native_path.read_bytes()
    store.establish(core.task_show(store.root)["state"], intent(), adapter_fields={
        "native_sha256": authority.digest(native_path), "native_snapshot": base64.b64encode(original_native).decode()})
    evidence = {"native_sha256": (native_path, "EXAMPLE_NATIVE_CHANGED")}
    assert store.check(evidence=evidence)
    native_path.write_bytes(b'changed native evidence')
    with pytest.raises(ValueError, match="EXAMPLE_NATIVE_CHANGED"):
        store.check(evidence=evidence)

    def restore(record):
        native_path.write_bytes(base64.b64decode(record["native_snapshot"]))

    store.recover(authority.digest(store.path()), "Restore native evidence", archive_paths={"native.json": native_path},
                  restore_adapter=restore, evidence=evidence)
    assert store.check(evidence=evidence)
    archive = Path(store.read()["recoveries"][0]["archive"])
    assert (archive / "native.json").read_bytes() == b'changed native evidence'


@pytest.mark.parametrize("field,value", [("provenance", "ADAPTER_SELECTED_INTENT"),
                                         ("host_actor_assurance", "UNKNOWN")])
def test_adapter_authority_provenance_is_immutable_during_recovery(store, field, value):
    core.task_start(store.root, "Repair the example", None, None)
    anchor = store.establish(core.task_show(store.root)["state"], intent(), adapter_fields={field: value})
    assert anchor[field] == value

    def change_provenance(record):
        record[field] = "CHANGED"

    with pytest.raises(ValueError, match="TASK_AUTHORITY_IDENTITY_CHANGED"):
        store.recover(authority.digest(store.path()), "Keep adapter provenance", restore_adapter=change_provenance)
    assert store.check()[field] == value


def test_core_import_and_operations_do_not_load_codex_modules(tmp_path):
    # An import blocker proves the complete neutral operation chain, including
    # recovery, rather than merely testing the top-level module import.
    script = '''
import importlib.abc, json, sys
from pathlib import Path
class NoCodex(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"thaliris_codex.codex_adapter", "thaliris_codex.codex_bootstrap", "thaliris_codex.lifecycle", "thaliris_codex.runtime_identity", "thaliris_codex.task_authority"}:
            raise AssertionError("Codex dependency: " + fullname)
sys.meta_path.insert(0, NoCodex())
from thaliris import authority, core
root = Path(sys.argv[1])
core.init(root)
core.task_start(root, "Neutral task", None, None)
store = authority.AuthorityStore(root, Path(sys.argv[2]), protected_paths=(".context/config.json",))
intent = {"human_instruction":"Selected instruction", "boundary":"Example", "invariants":"Preserve behavior", "acceptance":"Focused checks", "execution_mode":"single-agent"}
anchor = store.establish(core.task_show(root)["state"], intent)
assert store.check()["task_id"] == anchor["task_id"]
assert anchor["provenance"] == "SELECTED_TASK_INTENT" and "host_actor_assurance" not in anchor
(root / ".context/state.json").write_bytes(b"corrupt")
recovered = store.recover(authority.digest(store.path()), "Restore neutral authority")
assert "host_actor_assurance" not in recovered and "child_death_proof" not in recovered
assert "death_proof" not in store.read()["recoveries"][-1]
store.checkpoint()
core.task_close(root, 1)
store.checkpoint()
assert store.read()["status"] == "DONE" and store.check() is None
print(json.dumps({"anchor": anchor, "recovered": recovered, "retired": store.read()}))
'''
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    result = subprocess.run([sys.executable, "-c", script, str(root), str(tmp_path / "external")],
                            env={**os.environ, "PYTHONPATH": str(Path(core.__file__).parents[1])}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    transported = json.loads(result.stdout)
    assert transported["anchor"]["contract"]["execution_mode"] == "single-agent"
    assert transported["recovered"]["task_id"] == transported["anchor"]["task_id"]
    assert transported["retired"]["status"] == "DONE"


def test_external_storage_and_record_schema_are_checked(store):
    unsafe = authority.AuthorityStore(store.root, store.root / "external")
    with pytest.raises(ValueError, match="TASK_AUTHORITY_EXTERNAL_LOCATION_UNSAFE"):
        unsafe.path()
    start(store)
    record = store.read()
    record["version"] = 999
    store.write(record)
    with pytest.raises(ValueError, match="TASK_AUTHORITY_INVALID"):
        store.read()


def test_recovery_adapter_cannot_change_protected_intent(store):
    anchor = start(store)
    original = store.path().read_bytes()

    def expand(record):
        record["contract"]["execution_mode"] = "single-agent"

    with pytest.raises(ValueError, match="TASK_AUTHORITY_IDENTITY_CHANGED"):
        store.recover(authority.digest(store.path()), "Keep the original contract", restore_adapter=expand)
    assert store.path().read_bytes() == original
    assert store.check()["contract"] == anchor["contract"]


def test_recovery_archive_cannot_replace_core_evidence(store):
    start(store)
    with pytest.raises(ValueError, match="TASK_AUTHORITY_ARCHIVE_PATH_CONFLICT"):
        store.recover(authority.digest(store.path()), "Keep archive evidence", archive_paths={"authority.json": store.root / ".context/state.json"})
    assert not (store.directory / "recovery").exists()


@pytest.mark.parametrize("resolver", ["archive_paths", "evidence"])
def test_recovery_native_path_resolver_cannot_expand_intent(store, resolver):
    start(store)
    original = store.path().read_bytes()

    def expand(record):
        record["contract"]["boundary"] = "A larger scope"
        return {}

    with pytest.raises(ValueError, match="TASK_AUTHORITY_IDENTITY_CHANGED"):
        store.recover(authority.digest(store.path()), "Keep selected intent", **{resolver: expand})
    assert store.path().read_bytes() == original
    if resolver == "archive_paths":
        assert not (store.directory / "recovery").exists()


def test_reopened_store_archives_every_recorded_protected_path(store):
    start(store)
    config = store.root / ".context/config.json"
    original = config.read_bytes()
    config.write_bytes(b"conflicting original protected path")
    reopened = authority.AuthorityStore(store.root, store.directory)
    reopened.recover(authority.digest(reopened.path()), "Restore the recorded baseline")
    archive = Path(reopened.read()["recoveries"][0]["archive"])
    assert (archive / ".context/config.json").read_bytes() == b"conflicting original protected path"
    assert config.read_bytes() == original




@pytest.mark.parametrize("name", ["../escape", "/absolute", "bad\\path"])
def test_protected_paths_are_normalized_relative_paths(store, name):
    with pytest.raises(ValueError, match="path"):
        authority.AuthorityStore(store.root, store.directory, protected_paths=(name,))
