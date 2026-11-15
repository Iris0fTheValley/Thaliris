"""Opt-in schema 8; legacy handoffs retain their exact records and schema 7."""
import copy
import json
from pathlib import Path
import runpy

import pytest

from thaliris import core
from tests.test_evidence_continuity import setup, observation


def local():
    return {"id": "local", "candidate": "C1", "handoff_id": None, "provenance": "controller-local",
            "requirement_refs": ["R1"], "source_refs": ["S1"], "text": "Controller's own verification"}


def test_legacy_records_survive_opt_in_and_old_reader_refuses(tmp_path):
    setup(tmp_path)
    legacy = observation("legacy")
    legacy.update(native_actor="cross-host-child", submitted_by="controller", native_status="UNKNOWN")
    core.task_observe(tmp_path, "child", legacy)
    before = core._state_path(tmp_path).read_bytes()
    saved = core.task_get(tmp_path, "legacy")["object"]
    assert core.task_show(tmp_path)["state"]["schema_version"] == 7
    assert core._state_path(tmp_path).read_bytes() == before
    core.task_observe(tmp_path, "controller", local())
    after = core._state_path(tmp_path).read_bytes()
    assert core.task_show(tmp_path)["state"]["schema_version"] == 8
    assert core.task_get(tmp_path, "legacy")["object"] == saved
    assert core.task_state_schema_diagnostic(tmp_path) is None
    assert core._state_path(tmp_path).read_bytes() == after
    predecessor = runpy.run_path(str(Path(__file__).parent / "fixtures/controller-local-predecessor/schema_reader.py"))
    refusal = predecessor["_task_state_schema_diagnostic"](json.loads(after), after)
    assert refusal["status"] == "STATE_SCHEMA_INCOMPATIBLE"
    assert refusal["from_version"] == 8 and refusal["to_version"] == 7
    assert refusal["recoverable"] is False and refusal["recovery_action"] == "NONE"


@pytest.mark.parametrize("actor,changes", [
    ("child", {}), ("controller", {"handoff_id": "H2"}),
    ("controller", {"native_actor": "forged"}), ("controller", {"submitted_by": "controller"}),
    ("controller", {"native_status": "completed"}), ("controller", {"native_status_conflict": False}),
    ("controller", {"provenance": "unknown"}), ("controller", {"requirement_refs": []}),
])
def test_invalid_local_records_do_not_upgrade_or_write(tmp_path, actor, changes):
    setup(tmp_path)
    before = core._state_path(tmp_path).read_bytes()
    with pytest.raises(ValueError):
        core.task_observe(tmp_path, actor, {**local(), **changes})
    assert core._state_path(tmp_path).read_bytes() == before


def test_schema7_cannot_smuggle_local_provenance(tmp_path):
    setup(tmp_path)
    core.task_observe(tmp_path, "controller", local())
    state = copy.deepcopy(core.task_show(tmp_path)["state"])
    state["schema_version"] = 7
    with pytest.raises(core.ThalirisError, match="requires task schema 8"):
        core._validate_state(tmp_path, state)
