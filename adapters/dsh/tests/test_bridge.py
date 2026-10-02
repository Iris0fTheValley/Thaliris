"""Exercise the real one-shot process and neutral Core, with no DSH doubles."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "core_bridge.py"
SOURCE = Path(__file__).resolve().parents[3] / "src"
CONTRACT = {"human_instruction": "Selected fixture instruction", "boundary": "Temporary fixture", "invariants": "Controller selects semantics", "acceptance": "Explicit Controller decision", "execution_mode": "delegated"}


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return {"protocol": 1, "core_path": str(SOURCE), "root": str(root), "authority_directory": str(tmp_path / "authority"), "native_controller_id": "native-root"}


def invoke(workspace, operation, arguments, **changes):
    payload = {**workspace, "operation": operation, "arguments": arguments, **changes}
    process = subprocess.run([sys.executable, "-I", str(BRIDGE)], input=json.dumps(payload), text=True, capture_output=True, check=False)
    assert process.stderr == ""
    response = json.loads(process.stdout)
    assert response["protocol"] == 1
    assert process.returncode == (0 if response["ok"] else 1)
    return response


def start(workspace):
    result = invoke(workspace, "start", {"goal": "Bounded bridge fixture", "contract": CONTRACT})
    assert result["ok"]
    return result["result"]


def state_bytes(workspace):
    return (Path(workspace["root"]) / ".context/state.json").read_bytes()


def authority_bytes(workspace):
    anchors = list(Path(workspace["authority_directory"]).glob("*.json"))
    assert len(anchors) == 1
    return anchors[0].read_bytes()


def test_same_core_task_explicit_close_and_external_anchor(workspace):
    task = start(workspace)
    assert task["status"] == "ACTIVE"
    assert not (Path(workspace["root"]) / "AGENTS.md").exists()
    inspected = invoke(workspace, "inspect", {})["result"]
    assert inspected["state"]["task_id"] == task["task_id"]
    assert inspected["contract"] == CONTRACT
    begun = invoke(workspace, "begin", {"task_id": task["task_id"], "base_revision": 1, "observation": "selected Workstream/role/handoff digest"})["result"]
    assert begun["revision"] == 2
    finished = invoke(workspace, "finish", {"task_id": task["task_id"], "base_revision": 2, "observation": "native child-id stop_reason=error"})["result"]
    assert finished["revision"] == 3 and finished["status"] == "ACTIVE"
    closed = invoke(workspace, "close", {"task_id": task["task_id"], "base_revision": 3, "decision": "Controller decided the bounded goal is achieved."})["result"]
    assert closed["status"] == "DONE" and closed["revision"] == 5
    anchor = json.loads(next(Path(workspace["authority_directory"]).glob("*.json")).read_text())
    assert anchor["task_id"] == task["task_id"] and anchor["status"] == "DONE"
    assert anchor["dsh_controller_id"] == "native-root"
    assert anchor["contract"] == CONTRACT
    closed_state = json.loads(state_bytes(workspace))
    assert "stop_reason=error" in closed_state["pending_results"][0]
    assert "Controller close decision" in closed_state["pending_results"][1]
    assert anchor["provenance"] == "SELECTED_TASK_INTENT"
    assert "host_actor_assurance" not in anchor
    assert "death_proof" not in anchor and "child_death_proof" not in anchor
    assert not list((Path(workspace["root"]) / ".context").glob("dsh-input-*"))


@pytest.mark.parametrize(
    ("operation", "arguments", "error"),
    [
        ("begin", {"observation": "replacement Workstream"}, "UNRESOLVED_ACTIVE_WORK_CANNOT_BEGIN"),
        ("close", {"decision": "Controller says done."}, "UNRESOLVED_ACTIVE_WORK_CANNOT_CLOSE"),
    ],
)
def test_unresolved_work_rejects_replacement_and_close_without_mutation(workspace, operation, arguments, error):
    task = start(workspace)
    reservation = "selected Workstream/role/handoff digest"
    begun = invoke(workspace, "begin", {"task_id": task["task_id"], "base_revision": task["revision"], "observation": reservation})["result"]
    assert begun["revision"] == 2
    state_before = state_bytes(workspace)
    anchor_before = authority_bytes(workspace)

    blocked = invoke(workspace, operation, {"task_id": task["task_id"], "base_revision": begun["revision"], **arguments})
    assert not blocked["ok"]
    assert blocked["error"] == error
    assert state_bytes(workspace) == state_before
    assert authority_bytes(workspace) == anchor_before
    inspected = invoke(workspace, "inspect", {})["result"]["state"]
    assert inspected["active_work"] == [reservation]
    assert inspected["pending_results"] == []


@pytest.mark.parametrize("operation,args", [("recover", {}), ("expand", {}), ("start", {"goal": "wider", "contract": CONTRACT}), ("close", {"task_id": "wrong", "base_revision": 1, "decision": "done"})])
def test_unsupported_or_conflicting_operations_preserve_ledger(workspace, operation, args):
    start(workspace)
    before = state_bytes(workspace)
    assert not invoke(workspace, operation, args)["ok"]
    assert state_bytes(workspace) == before


def test_native_id_mismatch_stale_revision_and_caller_actor_rejected(workspace):
    task = start(workspace)
    before = state_bytes(workspace)
    assert "MISMATCH" in invoke(workspace, "inspect", {}, native_controller_id="child-id")["error"]
    assert not invoke(workspace, "close", {"task_id": task["task_id"], "base_revision": 2, "decision": "done"})["ok"]
    assert not invoke(workspace, "inspect", {}, actor="native-root")["ok"]
    assert state_bytes(workspace) == before


def test_unsafe_external_location_fails_before_init(workspace):
    response = invoke(workspace, "start", {"goal": "fixture", "contract": CONTRACT}, authority_directory=str(Path(workspace["root"]) / "authority"))
    assert not response["ok"]
    assert "EXTERNAL_LOCATION_UNSAFE" in response["error"]
    assert not (Path(workspace["root"]) / ".context").exists()


def test_security_conflict_does_not_bless_new_bytes(workspace):
    start(workspace)
    before = state_bytes(workspace)
    (Path(workspace["root"]) / ".context/config.json").write_text("{}\n")
    assert "SECURITY_CHANGED" in invoke(workspace, "inspect", {})["error"]
    assert state_bytes(workspace) == before


def test_invalid_contract_and_oversized_request(workspace):
    assert not invoke(workspace, "start", {"goal": "fixture", "contract": {**CONTRACT, "execution_mode": "guessed"}})["ok"]
    assert not (Path(workspace["root"]) / ".context").exists()
    process = subprocess.run([sys.executable, "-I", str(BRIDGE)], input=" " * 262145, text=True, capture_output=True, check=False)
    assert process.returncode == 1
    assert json.loads(process.stdout)["error"] == "BRIDGE_REQUEST_TOO_LARGE"


def test_bridge_imports_no_codex_facade(workspace):
    code = '''
import importlib.abc, importlib.util, json, sys
class BlockCodex(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in {"thaliris.cli", "thaliris.task_authority", "thaliris.codex", "thaliris.hooks", "thaliris.runtime_identity"}:
                raise AssertionError("Neutral bridge attempted Codex import: " + fullname)
            return None
spec = importlib.util.spec_from_file_location("dsh_bridge_under_test", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.meta_path.insert(0, BlockCodex())
result = module.dispatch(json.loads(sys.stdin.read()))
assert result["status"] == "ACTIVE"
assert "thaliris.task_authority" not in sys.modules
assert "thaliris.cli" not in sys.modules
print("neutral imports verified")
'''
    process = subprocess.run([sys.executable, "-I", "-c", code, str(BRIDGE)], input=json.dumps({**workspace, "operation": "start", "arguments": {"goal": "neutral import fixture", "contract": CONTRACT}}), text=True, capture_output=True, check=False)
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "neutral imports verified"
