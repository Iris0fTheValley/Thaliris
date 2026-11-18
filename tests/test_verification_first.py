"""Verification-first ledger (Core 0.6.0): mechanism may withhold; only a model may grant."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from thaliris import authority, cli, core, errors
from thaliris.claims import parse_claim_block

CHECK_SCRIPT = """import pathlib, sys
value = pathlib.Path("value.txt").read_text().strip()
print("value is", value)
sys.exit(0 if value == "ok" else 1)
"""
LEGACY_STATE_FIELDS = {"schema_version", "revision", "task_id", "status", "goal", "current_milestone", "records", "active_work",
                       "pending_results", "artifact_refs", "evidence_refs", "verification_results", "task_surface_baseline",
                       "task_base_head", "evidence_continuity"}


def project(tmp_path: Path, *, git: bool = True, kinds: bool = True) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    if git:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    (root / "value.txt").write_text("ok\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "check_value.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    core.task_start(root, "verification first", None, None)
    requirements = [{"id": "R1", "workchain_ref": "w1"}, {"id": "R2", "workchain_ref": "w2"}, {"id": "R3", "workchain_ref": "w3"}]
    if kinds:
        requirements[0]["kind"] = "compiled"
        requirements[1].update(kind="partial", surface="contract")
    register(root, {"requirements": requirements, "handoffs": [
        {"id": "H1", "parent_handoff_id": None, "candidate": "C1", "producer": "implementer", "requirement_refs": ["R1", "R2", "R3"]},
        {"id": "H2", "parent_handoff_id": None, "candidate": "C1", "producer": "reviewer", "requirement_refs": ["R1", "R2"]},
    ]})
    return root


def write(root: Path, name: str, value: object) -> str:
    path = root.parent / f"{name}.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def state_of(root: Path) -> dict:
    return core.task_show(root)["state"]


def rev(root: Path) -> int:
    return state_of(root)["revision"]


def register(root: Path, value: dict) -> dict:
    return core.task_evidence_register(root, "controller", rev(root), write(root, "register", value))


def declare(root: Path, check: dict | None = None, **options) -> dict:
    check = check or {"id": "C1", "requirement_refs": ["R1"], "command": [sys.executable, "tests/check_value.py"],
                      "files": ["tests/check_value.py"]}
    return core.task_check(root, "controller", rev(root), check, **options)


def judge(root: Path, identifier: str, requirement: str = "R1", outcome: str = "satisfied", **extra) -> dict:
    refs = extra.pop("observation_refs", None) or [observe(root, f"{identifier}-basis", requirement)]
    return core.task_judge(root, "controller", rev(root), write(root, identifier, {
        "id": identifier, "candidate": "C1", "requirement_ref": requirement, "observation_refs": refs, "outcome": outcome,
        "reasoning": "Controller read the evidence", **extra}))


def observe(root: Path, identifier: str, requirement: str = "R1") -> str:
    core.task_observe(root, "implementer", {
        "id": identifier, "candidate": "C1", "handoff_id": "H1", "requirement_refs": [requirement], "source_refs": [identifier + "-s"],
        "text": "child observation",
        "sources": [{"id": identifier + "-s", "kind": "test", "locator": "tests/check_value.py:1", "summary": "read"}]})
    return identifier


def check_status(root: Path, check_id: str = "C1") -> dict:
    view = core.verification_view(root, state_of(root))
    return next(entry for entry in view["checks"] if entry["id"] == check_id)


def mechanical(root: Path) -> list[dict]:
    return [item for item in state_of(root)["evidence_continuity"]["observations"] if item.get("provenance") == "mechanism"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- requirement kinds ----------------------------------------------------------------------------

def test_requirement_kind_defaults_to_judgment_only_and_keeps_legacy_shape(tmp_path):
    root = project(tmp_path, kinds=False)
    state = state_of(root)
    assert state["schema_version"] == core._STATE_SCHEMA_VERSION
    assert all(set(item) == {"id", "workchain_ref"} for item in state["evidence_continuity"]["requirements"])
    surfaced = core.surfaced_requirements(state)
    assert [(item["requirement"], item["kind"]) for item in surfaced["surfaced"]] == [
        ("R1", "judgment-only"), ("R2", "judgment-only"), ("R3", "judgment-only")]
    assert "Verification" not in core.task_status(root, view="compact")


def test_explicit_kind_and_surface_are_stored_in_the_current_schema(tmp_path):
    root = project(tmp_path)
    state = state_of(root)
    assert state["schema_version"] == core._STATE_SCHEMA_VERSION
    stored = {item["id"]: item for item in state["evidence_continuity"]["requirements"]}
    assert stored["R1"]["kind"] == "compiled" and stored["R2"] == {"id": "R2", "workchain_ref": "w2", "kind": "partial", "surface": "contract"}
    assert "kind" not in stored["R3"]
    section = core.task_status(root, view="compact")["Verification"]
    assert section["requirement_kinds"] == {"compiled": 1, "partial": 1, "judgment-only": 1}
    assert section["uncovered_requirements"] == ["R1", "R2"]
    before = core._state_path(root).read_bytes()
    for bad in ({"kind": "tested"}, {"surface": "api"}, {"kind": None}):
        with pytest.raises(core.ThalirisError) as caught:
            register(root, {"requirements": [{"id": "R9", "workchain_ref": "w9", **bad}]})
        assert caught.value.code == errors.CONTINUITY_INVALID
    assert core._state_path(root).read_bytes() == before


# --- declared checks ------------------------------------------------------------------------------

def test_check_declaration_records_file_hashes_and_supersede_accepts_new_content(tmp_path):
    root = project(tmp_path)
    script = root / "tests" / "check_value.py"
    out = declare(root)
    assert out["declared"] == ["C1"] and out["changed"] == ["checks"]
    found = core.task_get(root, "C1")
    assert found["object_type"] == "check"
    check = found["object"]
    assert check["files"] == [{"path": "tests/check_value.py", "sha256": sha(script)}]
    assert (check["cwd"], check["timeout_s"], check["declaration"], check["history"], check["declared_by"]) == (".", 600, 1, [], "controller")
    assert check["files_digest"] == core._files_digest(check["files"]) and check["declared_at_revision"] == out["revision"]

    with pytest.raises(core.ThalirisError) as caught:
        declare(root)
    assert caught.value.code == errors.CHECK_ALREADY_DECLARED and caught.value.details["content_changed"] is False
    unchanged = declare(root, supersede=True)
    assert unchanged["declared"] == [] and unchanged["changed"] == [] and unchanged["revision"] == out["revision"]

    script.write_text(CHECK_SCRIPT + "# accepted edit\n", encoding="utf-8")
    with pytest.raises(core.ThalirisError) as caught:
        declare(root)
    assert caught.value.details["content_changed"] is True
    again = declare(root, supersede=True)
    check = core.task_get(root, "C1")["object"]
    assert again["checks"][0]["declaration"] == 2 and check["files"][0]["sha256"] == sha(script)
    assert [item["declaration"] for item in check["history"]] == [1]


@pytest.mark.parametrize("change,field", [
    ({"id": "has.dot"}, "id"), ({"requirement_refs": []}, "requirement_refs"), ({"requirement_refs": ["R404"]}, "requirement_refs"),
    ({"command": "pytest"}, "command"), ({"command": []}, "command"), ({"cwd": "missing"}, "cwd"), ({"cwd": "../up"}, "cwd"),
    ({"timeout_s": 0}, "timeout_s"), ({"timeout_s": True}, "timeout_s"), ({"files": ["tests/absent.py"]}, "files"),
    ({"files": [".context/config.json"]}, "files"), ({"shell": True}, None),
])
def test_invalid_check_declarations_are_refused_without_writing(tmp_path, change, field):
    root = project(tmp_path)
    before = core._state_path(root).read_bytes()
    check = {"id": "C1", "requirement_refs": ["R1"], "command": [sys.executable, "-c", "pass"], **change}
    with pytest.raises(core.ThalirisError) as caught:
        declare(root, check)
    assert caught.value.code == errors.CHECK_INVALID and caught.value.details["field"] == field
    assert core._state_path(root).read_bytes() == before


def test_check_ids_share_the_task_object_identity_space(tmp_path):
    root = project(tmp_path)
    with pytest.raises(core.ThalirisError) as caught:
        declare(root, {"id": "H1", "requirement_refs": ["R1"], "command": [sys.executable, "-c", "pass"]})
    assert caught.value.code == errors.TASK_OBJECT_ID_COLLISION
    declare(root)
    with pytest.raises(core.ThalirisError) as caught:
        register(root, {"requirements": [{"id": "C1", "workchain_ref": "w"}]})
    assert caught.value.code == errors.CONTINUITY_ID_COLLISION


# --- verify ---------------------------------------------------------------------------------------

def test_verify_records_pass_fail_timeout_and_error(tmp_path):
    root = project(tmp_path)
    declare(root)
    passed = core.task_verify(root, "implementer", "C1")
    assert passed["result"]["outcome"] == "PASS" and passed["result"]["exit_code"] == 0 and passed["result"]["status"] == "green"
    assert "value is ok" in passed["result"]["output_tail"] and passed["changed"] == ["verification_results"]
    stored = core.task_get(root, "C1.r1")
    assert stored["object_type"] == "verification"
    result = stored["object"]
    assert result["kind"] == "check" and result["observed_by"] == "implementer" and result["run"] == 1
    assert result["tree_identity"].startswith("git:") and result["tree_identity"] == result["tree_identity_before"]
    assert result["observed_files"][0]["identity"] == sha(root / "tests" / "check_value.py")
    assert result["output_tail_sha256"] == hashlib.sha256(result["output_tail"].encode()).hexdigest()

    (root / "value.txt").write_text("broken\n", encoding="utf-8")
    failed = core.task_verify(root, "implementer", "C1")["result"]
    assert (failed["outcome"], failed["exit_code"], failed["status"], failed["id"]) == ("FAIL", 1, "red", "C1.r2")
    assert core.task_get(root, "C1.r1")["object"]["output_tail"] is None, "only the latest result keeps its output tail"

    declare(root, {"id": "slow", "requirement_refs": ["R2"], "timeout_s": 1,
                   "command": [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(60)"]})
    timed_out = core.task_verify(root, "implementer", "slow")["result"]
    assert (timed_out["outcome"], timed_out["exit_code"], timed_out["status"]) == ("TIMEOUT", None, "red")
    assert timed_out["duration_ms"] < 30_000

    declare(root, {"id": "absent", "requirement_refs": ["R2"], "command": ["thaliris-no-such-program-0600"]})
    broken = core.task_verify(root, "implementer", "absent")["result"]
    assert broken["outcome"] == "ERROR" and "could not start" in broken["output_tail"]

    with pytest.raises(core.ThalirisError) as caught:
        core.task_verify(root, "implementer", "C404")
    assert caught.value.code == errors.CHECK_NOT_FOUND


def test_result_history_is_bounded_per_check_and_run_numbers_keep_counting(tmp_path):
    root = project(tmp_path)
    declare(root, {"id": "C1", "requirement_refs": ["R1"], "command": [sys.executable, "-c", "print('x' * 9000)"]})
    for _ in range(core.CHECK_RESULT_HISTORY + 2):
        latest = core.task_verify(root, "implementer", "C1")["result"]
    results = state_of(root)["verification_results"]
    assert [item["run"] for item in results] == [3, 4, 5, 6] and latest["id"] == "C1.r6"
    assert [item["output_tail"] is None for item in results] == [True, True, True, False]
    assert len(results[-1]["output_tail"]) == core.CHECK_OUTPUT_TAIL_CHARS and results[-1]["output_bytes"] > 9000


def test_freshness_follows_the_working_tree(tmp_path):
    root = project(tmp_path)
    declare(root)
    assert check_status(root)["status"] == "unrun"
    core.task_verify(root, "implementer", "C1")
    assert check_status(root)["status"] == "green"
    # .context is outside the tree identity: ledger writes never make a result stale.
    observe(root, "o-noise")
    assert check_status(root)["status"] == "green"
    (root / "new_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    stale = check_status(root)
    assert (stale["status"], stale["reason"], stale["outcome"]) == ("stale", "tree_changed", "PASS")
    (root / "new_module.py").unlink()
    assert check_status(root)["status"] == "green", "identity is content, not time"
    (root / "value.txt").write_text("ok \n", encoding="utf-8")
    assert check_status(root)["status"] == "stale"
    core.task_verify(root, "implementer", "C1")
    assert check_status(root)["status"] == "green"
    real_index = root / ".git" / "index"
    assert not real_index.exists() or b"value.txt" not in real_index.read_bytes(), "the user's index is not touched"


def test_tree_identity_leaves_the_repository_untouched(tmp_path):
    root = project(tmp_path)
    subprocess.run(["git", "add", "value.txt"], cwd=root, check=True)
    index = (root / ".git" / "index").read_bytes()
    objects = sorted(path.relative_to(root).as_posix() for path in (root / ".git" / "objects").rglob("*") if path.is_file())
    first = core.tree_identity(root)
    assert first.startswith("git:") and core.tree_identity(root) == first
    assert (root / ".git" / "index").read_bytes() == index
    assert sorted(path.relative_to(root).as_posix() for path in (root / ".git" / "objects").rglob("*") if path.is_file()) == objects
    (root / ".context" / "extra.json").write_text("{}", encoding="utf-8")
    assert core.tree_identity(root) == first
    (root / "value.txt").write_text("changed\n", encoding="utf-8")
    assert core.tree_identity(root) != first


def test_non_git_tree_is_unknown_and_never_fresh(tmp_path):
    root = project(tmp_path, git=False)
    assert core.tree_identity(root) == "UNKNOWN"
    declare(root)
    result = core.task_verify(root, "implementer", "C1")["result"]
    assert (result["outcome"], result["tree_identity"], result["status"], result["reason"], result["fresh"]) == (
        "PASS", "UNKNOWN", "stale", "tree_unknown", False)
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J1")
    assert caught.value.code == errors.VERIFICATION_WITHHELD
    assert caught.value.details["withheld"][0]["checks"][0]["reason"] == "tree_unknown"
    judge(root, "J1", observation_refs=["J1-basis"], override_reason="non-Git project: the tree identity is unknown")
    assert core.task_get(root, "J1")["object"]["overridden_checks"][0]["reason"] == "tree_unknown"


# --- check tamper ---------------------------------------------------------------------------------

def test_tamper_is_recorded_once_per_new_hash_and_stays_open(tmp_path):
    root = project(tmp_path)
    script = root / "tests" / "check_value.py"
    declare(root)
    core.task_verify(root, "implementer", "C1")
    assert mechanical(root) == []

    script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    packet = core.task_status(root, view="compact")
    assert packet["Verification"]["tamper"] == [{"check_id": "C1", "paths": ["tests/check_value.py"], "recorded": False}]
    assert mechanical(root) == [], "a plain status read never writes"

    rerun = core.task_verify(root, "implementer", "C1")
    assert rerun["result"]["outcome"] == "PASS" and rerun["result"]["status"] == "stale"
    assert rerun["result"]["reason"] == "check_files_changed" and len(rerun["mechanical_observations"]) == 1
    observation = mechanical(root)[0]
    assert observation["id"] == rerun["mechanical_observations"][0]
    assert (observation["producer"], observation["handoff_id"], observation["requirement_refs"]) == ("mechanism", None, ["R1"])
    assert observation["mechanism"]["files"] == [{"path": "tests/check_value.py", "declared_sha256": core.task_get(root, "C1")["object"]["files"][0]["sha256"],
                                                  "current": sha(script)}]
    open_items = core.task_status(root, view="compact")["Evidence"]["unincorporated"]
    assert {"observation_id": observation["id"], "requirement_ref": "R1", "handoff_id": None, "candidate": "mechanism"} in open_items

    core.task_verify(root, "implementer", "C1")
    judge(root, "J-other", "R3", "unknown")
    assert len(mechanical(root)) == 1, "the same new hash is recorded once"

    script.write_text("import sys\nsys.exit(0)  # again\n", encoding="utf-8")
    recorded = core.task_status(root, view="compact", record_tamper=True)
    assert len(recorded["Verification"]["tamper_recorded_now"]) == 1 and len(mechanical(root)) == 2
    assert recorded["Verification"]["tamper"][0]["recorded"] is True
    assert core.task_status(root, view="compact", record_tamper=True)["Task"]["revision"] == recorded["Task"]["revision"]

    judge(root, "J-tamper", "R1", "repair", observation_refs=[item["id"] for item in mechanical(root)])
    still_open = [item["observation_id"] for item in core.task_status(root, view="compact")["Evidence"]["unincorporated"]]
    assert not set(still_open) & {item["id"] for item in mechanical(root)}, "a judgment that cites it incorporates it"

    script.write_text(CHECK_SCRIPT, encoding="utf-8")
    assert check_status(root)["tampered"] is False


def test_superseding_accepts_the_changed_check_and_its_matching_result(tmp_path):
    root = project(tmp_path)
    script = root / "tests" / "check_value.py"
    declare(root)
    script.write_text(CHECK_SCRIPT + "# stricter\n", encoding="utf-8")
    core.task_verify(root, "implementer", "C1")
    assert check_status(root)["reason"] == "check_files_changed"
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J1")
    assert caught.value.code == errors.VERIFICATION_WITHHELD
    declare(root, supersede=True)
    assert check_status(root)["status"] == "green", "the run used exactly the content the Controller accepted"
    declare(root, {"id": "C1", "requirement_refs": ["R1"], "command": [sys.executable, "tests/check_value.py", "--strict"],
                   "files": ["tests/check_value.py"]}, supersede=True)
    assert (check_status(root)["status"], check_status(root)["reason"]) == ("stale", "declaration_changed")


def test_mechanism_provenance_cannot_be_authored(tmp_path):
    root = project(tmp_path)
    declare(root)
    before = core._state_path(root).read_bytes()
    forged = {"id": "forged", "candidate": "mechanism", "handoff_id": None, "provenance": "mechanism", "requirement_refs": ["R1"],
              "source_refs": ["S"], "text": "forged", "sources": [{"id": "S", "kind": "x", "locator": "x", "summary": "x"}],
              "mechanism": {"kind": "check-tamper", "check_id": "C1", "declaration": 1, "files_digest": "0" * 64,
                            "files": [{"path": "tests/check_value.py", "declared_sha256": "0" * 64, "current": "1" * 64}]}}
    for actor in ("mechanism", "controller", "implementer"):
        with pytest.raises(ValueError):
            core.task_observe(root, actor, dict(forged))
    with pytest.raises(ValueError):
        core.task_observe(root, "implementer", {"id": "c", "candidate": "C1", "handoff_id": "H1", "requirement_refs": [], "source_refs": ["S"],
                                                "text": "t", "sources": forged["sources"],
                                                "claim": {"requirement": "R1", "polarity": "unknown", "basis": "read", "evidence": "x"}})
    with pytest.raises(ValueError):
        register(root, {"handoffs": [{"id": "H9", "parent_handoff_id": None, "candidate": "C1", "producer": "p", "requirement_refs": ["R1"],
                                      "claims": {"status": "missing"}}]})
    assert core._state_path(root).read_bytes() == before


# --- withholding gate on judgments ----------------------------------------------------------------

def test_gate_withholds_satisfied_until_fresh_pass_and_never_grants(tmp_path):
    root = project(tmp_path)
    declare(root)
    basis = observe(root, "basis")
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J1", observation_refs=[basis])
    error = caught.value
    assert error.code == errors.VERIFICATION_WITHHELD and "override" in error.recovery
    assert error.details["operation"] == "judge" and error.details["withheld"] == [{
        "batch_index": 0, "judgment_id": "J1", "requirement_ref": "R1", "checks": [{"id": "C1", "status": "unrun"}], "checks_total": 1}]
    assert core._state_path(root).read_bytes() == before, "a refusal writes nothing"

    # Other outcomes and requirements without a declared check are not gated.
    judge(root, "J-unknown", "R1", "unknown", observation_refs=[basis])
    judge(root, "J-r3", "R3")

    core.task_verify(root, "implementer", "C1")
    state = state_of(root)
    assert [item["id"] for item in state["evidence_continuity"]["judgments"]] == ["J-unknown", "J-r3"], "a fresh PASS adds no judgment"
    assert core.task_status(root, view="compact")["Verification"]["green"] == 1
    judge(root, "J1", observation_refs=[basis])
    stored = core.task_get(root, "J1")["object"]
    assert stored["outcome"] == "satisfied" and "override_reason" not in stored

    (root / "value.txt").write_text("broken\n", encoding="utf-8")
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J2", observation_refs=[basis])
    assert caught.value.details["withheld"][0]["checks"][0] == {"id": "C1", "status": "stale", "reason": "tree_changed",
                                                               "outcome": "PASS", "result_id": "C1.r1"}
    core.task_verify(root, "implementer", "C1")
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J2", observation_refs=[basis])
    assert caught.value.details["withheld"][0]["checks"][0]["status"] == "red"


def test_override_is_recorded_with_what_it_overrode_and_shown_in_status(tmp_path):
    root = project(tmp_path)
    declare(root)
    basis = observe(root, "basis")
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J1", observation_refs=[basis], override_reason="  ")
    assert caught.value.code == errors.VERIFICATION_OVERRIDE_INVALID
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J1", observation_refs=[basis], overridden_checks=[{"id": "C1", "status": "unrun"}])
    assert caught.value.code == errors.CONTINUITY_INVALID

    judge(root, "J1", observation_refs=[basis], override_reason="the check needs a licensed service; verified by hand")
    stored = core.task_get(root, "J1")["object"]
    assert stored["override_reason"].startswith("the check needs") and stored["overridden_checks"] == [{"id": "C1", "status": "unrun"}]
    for view in ("compact", "full"):
        overrides = core.task_status(root, view=view)["Verification"]["overrides"]
        assert overrides["total"] == 1 and overrides["judgments"][0]["judgment_id"] == "J1"
        assert overrides["judgments"][0]["overridden_checks"] == ["C1"]

    # A reason that overrides nothing is not stored: on a green check, and on an ungated requirement.
    core.task_verify(root, "implementer", "C1")
    judge(root, "J2", observation_refs=[basis], override_reason="not needed")
    judge(root, "J3", "R3", override_reason="not needed")
    assert "override_reason" not in core.task_get(root, "J2")["object"] and "override_reason" not in core.task_get(root, "J3")["object"]


def test_batch_judgments_are_gated_all_or_nothing_and_cli_reason_applies_to_all(tmp_path):
    root = project(tmp_path)
    declare(root)
    declare(root, {"id": "C2", "requirement_refs": ["R2"], "command": [sys.executable, "-c", "pass"]})
    basis = observe(root, "basis")
    batch = {"judgments": [
        {"id": "B1", "candidate": "C1", "requirement_ref": "R3", "observation_refs": [basis], "outcome": "satisfied", "reasoning": "r"},
        {"id": "B2", "candidate": "C1", "requirement_ref": "R1", "observation_refs": [basis], "outcome": "satisfied", "reasoning": "r"},
        {"id": "B3", "candidate": "C1", "requirement_ref": "R2", "observation_refs": [basis], "outcome": "satisfied", "reasoning": "r",
         "override_reason": "own reason"},
    ]}
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        core.task_judge(root, "controller", rev(root), write(root, "batch", batch))
    assert [item["judgment_id"] for item in caught.value.details["withheld"]] == ["B2"]
    assert core._state_path(root).read_bytes() == before
    core.task_judge(root, "controller", rev(root), write(root, "batch", batch), override_reason="operation-level reason")
    stored = {item["id"]: item for item in state_of(root)["evidence_continuity"]["judgments"]}
    assert "override_reason" not in stored["B1"]
    assert stored["B2"]["override_reason"] == "operation-level reason" and stored["B3"]["override_reason"] == "own reason"


def test_adapter_owned_judgment_append_is_gated_and_needs_the_root(tmp_path):
    root = project(tmp_path)
    declare(root)
    basis = observe(root, "basis")
    core.task_verify(root, "implementer", "C1")
    judgment = {"id": "J1", "candidate": "C1", "requirement_ref": "R1", "observation_refs": [basis], "outcome": "satisfied", "reasoning": "r"}
    state = state_of(root)
    with pytest.raises(core.ThalirisError) as caught:
        core._append_continuity_state(copy.deepcopy(state), "controller", dict(judgment), "judgments")
    assert caught.value.code == errors.VERIFICATION_WITHHELD and caught.value.details["withheld"][0]["checks"][0]["reason"] == "tree_unknown"
    assert core._append_continuity_state(copy.deepcopy(state), "controller", dict(judgment), "judgments", root=root) == ["J1"]


# --- close gate -----------------------------------------------------------------------------------

def test_satisfied_compiled_requirement_without_a_check_is_withheld_but_partial_is_not(tmp_path):
    root = project(tmp_path)  # R1 compiled, R2 partial, R3 judgment-only; no checks declared
    basis = observe(root, "basis")
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        judge(root, "J1", observation_refs=[basis])
    assert caught.value.code == errors.VERIFICATION_WITHHELD
    assert caught.value.details["withheld"][0]["checks"] == [
        {"id": "no-check", "status": "unrun", "reason": "no-declared-check", "requirement_ref": "R1"}]
    assert core._state_path(root).read_bytes() == before
    judge(root, "J-unknown", "R1", "unknown", observation_refs=[basis])  # not satisfied: not gated
    judge(root, "J-r2", "R2")  # partial: surfaced, not withheld
    judge(root, "J-r3", "R3")
    judge(root, "J1", observation_refs=[basis], override_reason="no executable check exists for this requirement")
    stored = core.task_get(root, "J1")["object"]
    assert stored["override_reason"].startswith("no executable") and stored["overridden_checks"][0]["reason"] == "no-declared-check"


def test_close_blocks_a_satisfied_compiled_requirement_without_a_check_unless_overridden(tmp_path):
    root = project(tmp_path)
    judge(root, "J1", override_reason="reviewed by hand")  # recorded override; stripped below to model a pre-gate satisfied judgment
    state = state_of(root)
    state["evidence_continuity"]["judgments"][0].pop("override_reason")
    state["evidence_continuity"]["judgments"][0].pop("overridden_checks")
    untouched = copy.deepcopy(state)
    with pytest.raises(core.ThalirisError) as caught:
        core.close_state(root, state)
    assert caught.value.code == errors.VERIFICATION_WITHHELD and caught.value.details["operation"] == "close"
    assert caught.value.details["checks"][0]["reason"] == "no-declared-check" and state == untouched
    core.close_state(root, state, override_reason="accepted without a check", actor="controller")
    assert state["status"] == "DONE" and state["closure"]["gate"] == "overridden" and not state.get("checks")
    core._validate_state(root, state)


def test_close_ignores_an_unjudged_or_checked_compiled_requirement(tmp_path):
    root = project(tmp_path)
    closed = core.task_close(root, rev(root))
    assert closed["status"] == "DONE" and "closure" not in closed


def test_close_is_withheld_while_a_check_is_not_green_and_lists_surfaced_requirements(tmp_path):
    root = project(tmp_path)
    declare(root)
    declare(root, {"id": "C2", "requirement_refs": ["R2"], "command": [sys.executable, "-c", "pass"]})
    core.task_verify(root, "implementer", "C2")
    judge(root, "J-r3", "R3", "unknown")
    judge(root, "J-r2", "R2")
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        core.task_close(root, rev(root))
    assert caught.value.code == errors.VERIFICATION_WITHHELD and caught.value.details["operation"] == "close"
    assert caught.value.details["checks"] == [{"id": "C1", "status": "unrun"}] and caught.value.details["checks_total"] == 1
    assert core._state_path(root).read_bytes() == before and state_of(root)["status"] == "ACTIVE"

    core.task_verify(root, "implementer", "C1")
    closed = core.task_close(root, rev(root), actor="controller")
    assert closed["status"] == "DONE" and closed["closure"] == {
        "gate": "clear", "tree_identity": core.tree_identity(root), "by": "controller"}
    assert closed["surfaced"] == [
        {"requirement": "R2", "kind": "partial", "latest_judgment": {"id": "J-r2", "outcome": "satisfied", "candidate": "C1", "overridden": False}},
        {"requirement": "R3", "kind": "judgment-only", "latest_judgment": {"id": "J-r3", "outcome": "unknown", "candidate": "C1", "overridden": False}},
    ]
    assert closed["surfaced_total"] == 2 and closed["surfaced_truncated"] is False
    assert not [item for item in state_of(root)["evidence_continuity"]["judgments"] if item["requirement_ref"] == "R1"], "close judged nothing"


def test_close_override_is_recorded_and_done_needs_the_gate(tmp_path):
    root = project(tmp_path)
    declare(root)
    (root / "value.txt").write_text("broken\n", encoding="utf-8")
    core.task_verify(root, "implementer", "C1")
    with pytest.raises(core.ThalirisError):
        core.task_close(root, rev(root))

    # Setting DONE around the gate is not a valid state while checks are declared.
    state = state_of(root)
    state["status"] = "DONE"
    with pytest.raises(core.ThalirisError, match="close gate") as caught:
        core._write_state(root, state)
    assert caught.value.code == errors.TASK_STATE_INVALID and state_of(root)["status"] == "ACTIVE"

    closed = core.task_close(root, rev(root), override_reason="abandoned: the user withdrew the request")
    assert closed["status"] == "DONE" and closed["closure"]["gate"] == "overridden"
    assert closed["closure"]["overridden_checks"] == [{"id": "C1", "status": "red", "outcome": "FAIL", "result_id": "C1.r1"}]
    assert closed["surfaced"][0] == {"requirement": "R2", "kind": "partial", "latest_judgment": None, "reason": "no-declared-check"}
    assert core.task_status(root, view="compact")["Verification"]["overrides"]["close"]["overridden_checks"] == ["C1"]
    assert state_of(root)["closure"]["override_reason"].startswith("abandoned")


def test_close_state_is_the_adapter_owned_close_and_leaves_a_refused_state_unchanged(tmp_path):
    root = project(tmp_path)
    declare(root)
    state = state_of(root)
    untouched = copy.deepcopy(state)
    with pytest.raises(core.ThalirisError) as caught:
        core.close_state(root, state)
    assert caught.value.code == errors.VERIFICATION_WITHHELD and state == untouched
    extras = core.close_state(root, state, override_reason="adapter path", actor="controller")
    assert state["status"] == "DONE" and state["revision"] == untouched["revision"] + 1 and extras["changed"] == ["closure"]
    core._validate_state(root, state)


def test_legacy_close_always_carries_the_surfaced_list(tmp_path):
    root = project(tmp_path, kinds=False)
    judge(root, "J1", "R2", "repair")
    closed = core.task_close(root, rev(root))
    assert closed["status"] == "DONE" and "closure" not in closed and closed["changed"] == ["status"]
    assert [(item["requirement"], item["latest_judgment"] and item["latest_judgment"]["outcome"]) for item in closed["surfaced"]] == [
        ("R1", None), ("R2", "repair"), ("R3", None)]
    assert state_of(root)["schema_version"] == core._STATE_SCHEMA_VERSION and "closure" not in state_of(root)


# --- typed claims ---------------------------------------------------------------------------------

def block(body: object, fence: str = "```") -> str:
    text = body if isinstance(body, str) else json.dumps(body)
    return f"Final report.\n\n{fence}thaliris-claims\n{text}\n{fence}\n"


def claim(requirement="R1", polarity="contradicts", text="finding", evidence="src/app.py:12", basis="read") -> dict:
    return {"requirement": requirement, "polarity": polarity, "text": text, "evidence": evidence, "basis": basis}


def test_claim_parser_present_none_missing_and_malformed():
    parsed = parse_claim_block(block({"claims": [claim(), claim("R2", "supports", evidence="C1", basis="check")]}))
    assert parsed["status"] == "present" and parsed["total"] == 2 and parsed["truncated"] is False and parsed["invalid"] == 0
    assert parsed["claims"][0] == claim() and parsed["claims"][1]["polarity"] == "supports"
    assert parse_claim_block(block("none")) == {"status": "present", "claims": [], "total": 0, "truncated": False, "invalid": 0, "error": None}
    assert parse_claim_block(block(" NONE \n"))["status"] == "present"
    assert parse_claim_block(block({"claims": []}))["status"] == "present"
    for text in ("no block at all", "```json\n{\"claims\": []}\n```", "", None, 7):
        assert parse_claim_block(text)["status"] == "missing"
    for body in ("{not json", "[]", '{"claim": []}', '{"claims": {}}', "nothing to report"):
        malformed = parse_claim_block(block(body))
        assert malformed["status"] == "malformed" and malformed["claims"] == [] and malformed["error"]


def test_claim_parser_uses_the_last_block_and_ignores_nested_examples():
    quoted = "````markdown\n```thaliris-claims\n" + json.dumps({"claims": [claim(text="quoted example")]}) + "\n```\n````\n"
    assert parse_claim_block(quoted)["status"] == "missing"
    text = block({"claims": [claim(text="first")]}) + "more prose\n" + block({"claims": [claim(text="last")]}, fence="~~~")
    assert [item["text"] for item in parse_claim_block(text)["claims"]] == ["last"]
    assert parse_claim_block(quoted + block("none"))["claims"] == []
    unclosed = "report\n```thaliris-claims\n" + json.dumps({"claims": [claim(text="unclosed")]})
    assert parse_claim_block(unclosed)["claims"][0]["text"] == "unclosed"
    assert parse_claim_block(block({"claims": [claim()]}).replace("\n", "\r\n"))["status"] == "present"


def test_claim_parser_caps_truncates_and_degrades_to_the_weakest_reading():
    many = parse_claim_block(block({"claims": [claim(text=f"claim {index}") for index in range(8)] + ["not an object", {"text": " "}]}))
    assert len(many["claims"]) == 5 and many["total"] == 8 and many["truncated"] is True and many["invalid"] == 2
    assert [item["text"] for item in many["claims"]] == [f"claim {index}" for index in range(5)]
    long = parse_claim_block(block({"claims": [claim(text="x" * 400)]}))["claims"][0]
    assert len(long["text"]) == 300 and long["text_truncated"] is True
    weak = parse_claim_block(block({"claims": [{"text": "bad\x07 fields", "polarity": "contradict", "basis": "vibes", "confidence": 0.99}]}))["claims"][0]
    assert weak == {"requirement": "", "polarity": "unknown", "text": "bad  fields", "evidence": "unspecified", "basis": "inference",
                    "normalized": ["requirement", "polarity", "basis", "evidence"]}
    assert "confidence" not in weak


def test_claim_cap_keeps_contradicts_and_unknown_before_supports():
    claims = [claim(polarity="supports", text=f"s{index}") for index in range(5)] + [
        claim(polarity="contradicts", text="late contradiction"), claim(polarity="unknown", text="late unknown")]
    parsed = parse_claim_block(block({"claims": claims}))
    assert parsed["truncated"] is True and parsed["total"] == 7
    assert [item["text"] for item in parsed["claims"]] == ["s0", "s1", "s2", "late contradiction", "late unknown"]
    assert {item["polarity"] for item in parsed["claims"]} == {"supports", "contradicts", "unknown"}


def test_ingest_routes_claims_by_polarity(tmp_path):
    root = project(tmp_path)
    declare(root)
    message = block({"claims": [
        claim("R1", "contradicts", "the parser drops empty lines", "src/parser.py:40", "read"),
        claim("R2", "unknown", "could not exercise the retry path", "C1", "inference"),
        claim("R1", "supports", "the declared check passes", "C1", "check"),
        claim("R1", "supports", "read the guard", "src/guard.py:7", "read"),
        claim("R9", "supports", "a requirement this handoff was not given", "src/other.py:1", "read"),
    ]})
    out = core.task_ingest_claims(root, "H1", message, compact_evidence=True)
    claims = out["claims"]
    assert out["changed"] == ["evidence_continuity"] and out["appended"] == claims["observations"] == ["H1.c1", "H1.c2", "H1.c3"]
    assert claims["supports"] == {"R1": 2} and claims["unassigned"] == ["H1.c3"] and claims["duplicates"] == 0 and claims["status"] == "present"
    first, second, third = (core.task_get(root, identifier)["object"] for identifier in claims["observations"])
    assert (first["producer"], first["candidate"], first["handoff_id"], first["requirement_refs"]) == ("implementer", "C1", "H1", ["R1"])
    assert first["text"] == "the parser drops empty lines"
    assert first["claim"] == {"requirement": "R1", "polarity": "contradicts", "basis": "read", "evidence": "src/parser.py:40"}
    assert core.task_get(root, "H1.c1.s")["object"] == {"id": "H1.c1.s", "kind": "claim-evidence", "locator": "src/parser.py:40",
                                                        "summary": "read evidence cited by a typed contradicts claim"}
    assert second["claim"]["polarity"] == "unknown" and core.task_get(root, "H1.c2.s")["object"]["kind"] == "check"
    assert third["requirement_refs"] == [] and third["claim"]["requirement"] == "R9" and third["claim"]["polarity"] == "supports"
    handoff = core.task_get(root, "H1")["object"]
    assert handoff["claims"] == {"status": "present", "total": 5, "truncated": False, "invalid": 0, "duplicates": 0,
                                 "observations": ["H1.c1", "H1.c2", "H1.c3"],
                                 "supports": [{"requirement": "R1", "evidence": "C1", "basis": "check"},
                                              {"requirement": "R1", "evidence": "src/guard.py:7", "basis": "read"}]}
    evidence = out["evidence"]
    assert evidence["unincorporated_total"] == 3, "supports are counts, not obligations"
    assert {"observation_id": "H1.c3", "requirement_ref": None, "handoff_id": "H1", "candidate": "C1"} in evidence["unincorporated"]
    section = core.task_status(root, view="compact")["Claims"]
    assert section["supports"] == {"R1": 2} and section["handoffs_without_typed_claims"]["total"] == 0

    again = core.task_ingest_claims(root, "H1", message)
    assert again["claims"]["already_ingested"] is True and again["changed"] == [] and again["revision"] == out["revision"]
    with pytest.raises(core.ThalirisError) as caught:
        core.task_ingest_claims(root, "H404", message)
    assert caught.value.code == errors.HANDOFF_NOT_FOUND


def test_ingest_merges_duplicates_within_a_candidate_without_hiding_a_re_report(tmp_path):
    root = project(tmp_path)
    adverse = claim("R1", "contradicts", "boundary case fails", "src/app.py:12")
    core.task_ingest_claims(root, "H1", block({"claims": [adverse, dict(adverse, text="same finding, other words"),
                                                         claim("R1", "supports", "ok", "src/app.py:12")]}))
    assert core.task_get(root, "H1")["object"]["claims"]["duplicates"] == 1
    second = core.task_ingest_claims(root, "H2", block({"claims": [
        adverse, claim("R1", "unknown", "same place, other polarity", "src/app.py:12"), claim("R1", "supports", "ok", "src/app.py:12")]}))
    assert second["claims"]["duplicates"] == 2 and second["claims"]["observations"] == ["H2.c1"] and second["claims"]["supports"] == {}
    assert core.task_get(root, "H2.c1")["object"]["claim"]["polarity"] == "unknown", "another polarity is never merged away"

    # Once the first report is judged, the same finding reported again is a new obligation.
    judge(root, "J1", "R1", "repair", observation_refs=["H1.c1"])
    register(root, {"handoffs": [{"id": "H3", "parent_handoff_id": None, "candidate": "C1", "producer": "reviewer", "requirement_refs": ["R1"]}]})
    third = core.task_ingest_claims(root, "H3", block({"claims": [adverse]}))
    assert third["claims"]["observations"] == ["H3.c1"] and third["claims"]["duplicates"] == 0


def test_missing_or_malformed_block_records_one_marker_that_is_not_an_obligation(tmp_path):
    root = project(tmp_path)
    missing = core.task_ingest_claims(root, "H1", "The work is done.", compact_evidence=True)
    assert missing["claims"]["status"] == "missing" and missing["evidence"]["unincorporated_total"] == 0
    assert core.task_get(root, "H1")["object"]["claims"] == {"status": "missing"}
    malformed = core.task_ingest_claims(root, "H2", block("{oops"))
    assert malformed["claims"]["status"] == "malformed" and core.task_get(root, "H2")["object"]["claims"]["error"].startswith("block is not JSON")
    for view in ("compact", "full"):
        without = core.task_status(root, view=view)["Claims"]["handoffs_without_typed_claims"]
        assert without == {"total": 2, "ids": ["H1", "H2"], "missing": 1, "malformed": 1}
    # A marker may be replaced once by a later readable block; another unreadable message changes nothing.
    assert core.task_ingest_claims(root, "H1", "still nothing")["claims"]["already_ingested"] is True
    replaced = core.task_ingest_claims(root, "H1", block({"claims": [claim()]}))
    assert replaced["claims"]["status"] == "present" and replaced["claims"]["observations"] == ["H1.c1"]
    assert core.task_status(root, view="compact")["Claims"]["handoffs_without_typed_claims"]["ids"] == ["H2"]
    truncated = block({"claims": [claim(text=f"t{index}", evidence=f"a.py:{index}") for index in range(7)]})
    register(root, {"handoffs": [{"id": "H3", "parent_handoff_id": None, "candidate": "C2", "producer": "reviewer", "requirement_refs": ["R1"]}]})
    assert core.task_ingest_claims(root, "H3", truncated)["claims"]["truncated"] is True
    assert core.task_status(root, view="compact")["Claims"]["handoffs_with_truncated_claims"] == {"total": 1, "ids": ["H3"]}


def test_voluntary_observe_is_unchanged(tmp_path):
    root = project(tmp_path, kinds=False)
    observe(root, "plain")
    stored = core.task_get(root, "plain")["object"]
    assert set(stored) == {"id", "task_id", "producer", "candidate", "handoff_id", "requirement_refs", "source_refs", "text"}
    assert state_of(root)["schema_version"] == core._STATE_SCHEMA_VERSION
    with pytest.raises(ValueError, match="requires requirement refs"):
        core.task_observe(root, "implementer", {"id": "empty", "candidate": "C1", "handoff_id": "H1", "requirement_refs": [],
                                                "source_refs": ["plain-s"], "text": "no refs"})


# --- dispatch usage -------------------------------------------------------------------------------

def test_handoff_usage_is_optional_merges_and_aggregates_by_role_and_model(tmp_path):
    root = project(tmp_path)
    first = core.task_handoff_usage(root, "H1", {"model": "large", "input_tokens": 1000, "output_tokens": 200, "outcome": "completed"})
    assert first["usage"] == {"model": "large", "effort": None, "input_tokens": 1000, "output_tokens": 200, "total_tokens": None,
                              "cost_usd": None, "duration_ms": None, "tool_uses": None, "outcome": "completed"}
    merged = core.task_handoff_usage(root, "H1", {"cost_usd": 0.25, "tool_uses": 9, "model": None})["usage"]
    assert (merged["model"], merged["cost_usd"], merged["tool_uses"], merged["input_tokens"]) == ("large", 0.25, 9, 1000)
    core.task_handoff_usage(root, "H2", {"total_tokens": 300, "cost_usd": 0.05, "duration_ms": 4000, "outcome": "failed"})
    assert core.task_get(root, "H2")["object"]["usage"]["model"] is None
    usage = core.task_status(root, view="compact")["Usage"]
    assert usage["totals"] == {"handoffs": 2, "input_tokens": 1000, "output_tokens": 200, "total_tokens": 1500, "cost_usd": 0.3,
                               "duration_ms": 4000, "tool_uses": 9}
    assert usage["by_role"] == {"implementer": {"handoffs": 1, "total_tokens": 1200, "cost_usd": 0.25},
                                "reviewer": {"handoffs": 1, "total_tokens": 300, "cost_usd": 0.05}}
    assert usage["by_model"] == {"large": {"handoffs": 1, "total_tokens": 1200, "cost_usd": 0.25},
                                 "unknown": {"handoffs": 1, "total_tokens": 300, "cost_usd": 0.05}}
    assert usage["outcomes"] == {"completed": 1, "failed": 1}
    before = core._state_path(root).read_bytes()
    for bad in ({}, {"tokens": 1}, {"input_tokens": -1}, {"input_tokens": True}, {"outcome": "great"}, {"cost_usd": float("inf")}, {"model": ""}):
        with pytest.raises(core.ThalirisError) as caught:
            core.task_handoff_usage(root, "H1", dict(bad))
        assert caught.value.code == errors.HANDOFF_USAGE_INVALID
    assert core._state_path(root).read_bytes() == before


# --- adaptive mode --------------------------------------------------------------------------------

def test_adaptive_quick_admission_marks_omitted_fields_unspecified(tmp_path):
    quick = {"human_instruction": "Fix the typo in the README", "acceptance": "The typo is gone", "execution_mode": "adaptive"}
    contract = authority.validate_contract(quick)
    assert contract == {**quick, "boundary": "unspecified", "invariants": "unspecified"} and "boundary" not in quick
    full = {**quick, "boundary": "README only", "invariants": "No other file changes", "write_surface": ["README.md", "docs/**"]}
    assert authority.validate_contract(full) is full
    for mode in ("delegated", "controller-direct", "single-agent"):
        with pytest.raises(ValueError, match="TASK_AUTHORITY_CONTRACT_REQUIRED") as caught:
            authority.validate_contract({**quick, "execution_mode": mode})
        assert caught.value.details["missing_fields"] == ["boundary", "invariants"]
    for missing in ("human_instruction", "acceptance"):
        with pytest.raises(ValueError, match="TASK_AUTHORITY_CONTRACT_REQUIRED") as caught:
            authority.validate_contract({key: value for key, value in quick.items() if key != missing})
        assert caught.value.details["missing_fields"] == [missing]
    for surface in ([], "src/**", ["/abs"], ["../up"], ["a\\b"], ["dup", "dup"], [7]):
        with pytest.raises(ValueError, match="TASK_AUTHORITY_CONTRACT_REQUIRED") as caught:
            authority.validate_contract({**quick, "write_surface": surface})
        assert caught.value.details["invalid_fields"] == ["write_surface"]

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    core.task_start(root, "Fix the typo in the README", None, None)
    store = authority.AuthorityStore(root, tmp_path / "external")
    anchor = store.establish(state_of(root), quick)
    assert anchor["contract"]["boundary"] == "unspecified" and anchor["contract"]["execution_mode"] == "adaptive"
    assert store.check()["contract"] == contract
    switched = store.switch_mode(authority.digest(store.path()), 1, "delegated", "Dispatch it instead")
    assert switched["execution_mode"] == "delegated"
    back = store.switch_mode(authority.digest(store.path()), 2, "adaptive", "Back to adaptive")
    assert back["execution_mode"] == "adaptive"


ADAPTIVE = {"execution_mode": "adaptive"}


def advisory_codes(root: Path, contract: dict | None = None) -> dict[str, dict]:
    packet = core.task_status(root, view="compact", contract=contract or ADAPTIVE)
    assert packet["Advisories"]["blocking"] is False
    return {item["code"]: item for item in packet["Advisories"]["items"]}


def test_advisories_exist_only_in_adaptive_mode_and_flag_requirement_shape(tmp_path):
    root = project(tmp_path)
    assert "Advisories" not in core.task_status(root, view="compact")
    assert "Advisories" not in core.task_status(root, view="compact", contract={"execution_mode": "delegated"})
    codes = advisory_codes(root)
    assert codes["JUDGMENT_ONLY_REQUIREMENT"] == {"code": "JUDGMENT_ONLY_REQUIREMENT", "requirements": ["R3"], "requirements_total": 1}
    assert codes["CONTRACT_SURFACE"] == {"code": "CONTRACT_SURFACE", "requirements": ["R2"], "requirements_total": 1}
    quick = core.task_status(root, contract={**ADAPTIVE, "boundary": "unspecified", "invariants": "unspecified"})["Advisories"]
    assert quick["contract_unspecified"] == ["boundary", "invariants"]
    with pytest.raises(ValueError, match="contract"):
        core.task_status(root, contract=["adaptive"])


def test_advisory_for_a_check_that_fails_twice_on_distinct_trees(tmp_path):
    root = project(tmp_path)
    declare(root)
    (root / "value.txt").write_text("broken\n", encoding="utf-8")
    core.task_verify(root, "implementer", "C1")
    core.task_verify(root, "implementer", "C1")
    assert "CHECK_FAILED_TWICE" not in advisory_codes(root), "the same tree twice is one attempt"
    (root / "value.txt").write_text("still broken\n", encoding="utf-8")
    core.task_verify(root, "implementer", "C1")
    advisory = advisory_codes(root)["CHECK_FAILED_TWICE"]
    assert advisory["check_id"] == "C1" and advisory["result_ids"] == ["C1.r2", "C1.r3"] and len(set(advisory["tree_identities"])) == 2
    (root / "value.txt").write_text("ok\n", encoding="utf-8")
    core.task_verify(root, "implementer", "C1")
    assert "CHECK_FAILED_TWICE" not in advisory_codes(root)


def test_advisories_for_write_surface_and_change_size(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("".join(f"line {index}\n" for index in range(10)), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base"], cwd=root, check=True)
    core.task_start(root, "surface", None, None)
    contract = {**ADAPTIVE, "write_surface": ["src/**", "docs"]}
    assert advisory_codes(root, contract) == {}

    (root / "src" / "app.py").write_text("".join(f"line {index}\n" for index in range(8)) + "new 8\nnew 9\nnew 10\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "note.md").write_text("one\ntwo\n", encoding="utf-8")
    assert advisory_codes(root, contract) == {}
    (root / "setup.cfg").write_text("[x]\n", encoding="utf-8")
    codes = advisory_codes(root, contract)
    assert codes["WRITE_SURFACE_EXCEEDED"] == {"code": "WRITE_SURFACE_EXCEEDED", "paths": ["setup.cfg"], "paths_total": 1}
    assert "CHANGE_SIZE_EXCEEDED" not in codes

    (root / "src" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    size = advisory_codes(root, contract)["CHANGE_SIZE_EXCEEDED"]
    assert size == {"code": "CHANGE_SIZE_EXCEEDED", "files": 4, "changed_lines": 9, "changed_lines_exact": True,
                    "max_files": 3, "max_changed_lines": 150}

    config = root / ".context" / "config.json"
    config.write_text(json.dumps({"schema_version": 1, "advisories": {"max_files": 10, "max_changed_lines": 8}}), encoding="utf-8")
    assert core.advisory_thresholds(root) == {"max_files": 10, "max_changed_lines": 8, "controller_tool_output_tokens": 30000}
    assert advisory_codes(root, contract)["CHANGE_SIZE_EXCEEDED"]["max_changed_lines"] == 8
    config.write_text(json.dumps({"schema_version": 1, "advisories": {"max_files": 10, "max_changed_lines": 9}}), encoding="utf-8")
    assert "CHANGE_SIZE_EXCEEDED" not in advisory_codes(root, contract)
    (root / "big.txt").write_text("row\n" * 200, encoding="utf-8")
    config.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert advisory_codes(root)["CHANGE_SIZE_EXCEEDED"]["changed_lines"] == 209


@pytest.mark.parametrize("pattern,path,covered", [
    ("src/**", "src/a/b.py", True), ("src", "src/a.py", True), ("src/*.py", "src/a.py", True), ("src/*.py", "src/a/b.py", False),
    ("**/*.md", "README.md", True), ("**/*.md", "docs/a/b.md", True), ("docs/", "docs/x.md", True), ("doc", "docs/x.md", False),
    ("./src/**", "src/a.py", True), ("src/?.py", "src/ab.py", False), ("a.b", "aXb", False),
])
def test_write_surface_globs(pattern, path, covered):
    assert core._glob_covers(pattern, path) is covered


def test_controller_tool_output_counter_feeds_an_advisory_without_touching_the_ledger(tmp_path):
    root = project(tmp_path)
    before = core._state_path(root).read_bytes()
    assert core.task_lane_counter(root, add=20_000)["controller_tool_output_tokens"] == 20_000
    assert "CONTROLLER_TOOL_OUTPUT" not in advisory_codes(root)
    out = core.task_lane_counter(root, add=10_001)
    assert out["controller_tool_output_tokens"] == 30_001 and out["revision"] == rev(root)
    assert advisory_codes(root)["CONTROLLER_TOOL_OUTPUT"] == {"code": "CONTROLLER_TOOL_OUTPUT", "tokens": 30_001, "threshold": 30_000}
    assert core._state_path(root).read_bytes() == before, "the counter is a sidecar: no revision, no ledger bytes"
    assert core.task_lane_counter(root, set_to=5)["controller_tool_output_tokens"] == 5
    assert "CONTROLLER_TOOL_OUTPUT" not in advisory_codes(root)
    for bad in ({}, {"add": 1, "set_to": 1}, {"add": -1}, {"set_to": True}):
        with pytest.raises(core.ThalirisError) as caught:
            core.task_lane_counter(root, **bad)
        assert caught.value.code == errors.LANE_COUNTER_INVALID
    core._lane_path(root, state_of(root)["task_id"]).write_text("not json", encoding="utf-8")
    assert core.lane_counters(root, state_of(root)["task_id"]) == {"controller_tool_output_tokens": 0}


def test_advisories_never_block(tmp_path):
    root = project(tmp_path)
    core.task_lane_counter(root, add=10 ** 6)
    for index in range(6):
        (root / f"file{index}.py").write_text("x\n" * 100, encoding="utf-8")
    assert {"CONTROLLER_TOOL_OUTPUT", "CHANGE_SIZE_EXCEEDED", "JUDGMENT_ONLY_REQUIREMENT", "CONTRACT_SURFACE"} <= set(advisory_codes(root))
    judge(root, "J1", "R3")
    assert core.task_close(root, rev(root))["status"] == "DONE"


# --- schema continuity ----------------------------------------------------------------------------

def test_tasks_that_use_no_new_feature_keep_their_field_shape(tmp_path):
    # Every write produces the current schema (a forward chain); an unused feature adds no field.
    root = project(tmp_path, kinds=False)
    observe(root, "o1")
    judge(root, "J1", "R1", observation_refs=["o1"])
    state = state_of(root)
    assert state["schema_version"] == core._STATE_SCHEMA_VERSION and set(state) == LEGACY_STATE_FIELDS
    assert set(core.task_get(root, "J1")["object"]) == {"id", "task_id", "producer", "candidate", "requirement_ref", "observation_refs",
                                                       "outcome", "reasoning"}
    assert set(core.task_status(root)) == {"ok", "schema_version", "Task", "Active Work", "Pending Results", "Counts",
                                           "Recent Artifact IDs", "Active Artifact Count", "Evidence Continuity"}
    assert set(core.task_status(root, view="compact")) == {"ok", "schema_version", "view", "Task", "Active Work", "Pending Results",
                                                           "Counts", "Recent Artifact IDs", "Evidence"}
    core.task_observe(root, "controller", {"id": "local", "candidate": "C1", "handoff_id": None, "provenance": "controller-local",
                                           "requirement_refs": ["R1"], "source_refs": ["o1-s"], "text": "Controller's own reading"})
    assert state_of(root)["schema_version"] == core._STATE_SCHEMA_VERSION
    judge(root, "J2", "R2", observation_refs=["local"])
    assert core.task_close(root, rev(root))["status"] == "DONE"
    assert state_of(root)["schema_version"] == core._STATE_SCHEMA_VERSION and set(state_of(root)) == LEGACY_STATE_FIELDS


@pytest.mark.parametrize("version", [6, 7, 8, 9])
def test_older_states_load_as_current_and_are_promoted_on_the_next_write(tmp_path, version):
    root = project(tmp_path, kinds=False)
    if version == 8:
        observe(root, "o1")
        core.task_observe(root, "controller", {"id": "local", "candidate": "C1", "handoff_id": None, "provenance": "controller-local",
                                               "requirement_refs": ["R1"], "source_refs": ["o1-s"], "text": "Controller's own reading"})
    path = core._state_path(root)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = version
    path.write_bytes((json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    loaded = state_of(root)
    assert loaded["schema_version"] == core._STATE_SCHEMA_VERSION and loaded["revision"] == raw["revision"]
    assert core.task_status(root, view="compact")["Task"]["revision"] == raw["revision"]
    assert json.loads(path.read_bytes())["schema_version"] == version, "reading never rewrites the ledger"
    observe(root, "o-after")
    assert json.loads(path.read_bytes())["schema_version"] == core._STATE_SCHEMA_VERSION, "the next write promotes it"
    declare(root)
    after = state_of(root)
    assert after["schema_version"] == core._STATE_SCHEMA_VERSION
    assert after["evidence_continuity"]["requirements"] == raw["evidence_continuity"]["requirements"]
    if version == 8:
        assert core.task_get(root, "local")["object"]["provenance"] == "controller-local"
    core.task_verify(root, "implementer", "C1")
    judge(root, "J1", observation_refs=["o-after"])
    assert core.task_close(root, rev(root))["closure"]["gate"] == "clear"


def test_older_core_refuses_a_schema_9_state_and_schema_9_fields_cannot_be_smuggled(tmp_path):
    root = project(tmp_path, kinds=False)
    declare(root)
    raw = core._state_path(root).read_bytes()
    assert core.task_state_schema_diagnostic(root) is None
    predecessor = runpy.run_path(str(Path(__file__).parent / "fixtures/controller-local-predecessor/schema_reader.py"))
    refusal = predecessor["_task_state_schema_diagnostic"](json.loads(raw), raw)
    assert refusal["status"] == "STATE_SCHEMA_INCOMPATIBLE" and refusal["from_version"] == core._STATE_SCHEMA_VERSION
    assert refusal["recoverable"] is False
    for version in (7, 8):
        state = copy.deepcopy(state_of(root))
        state["schema_version"] = version
        with pytest.raises(core.ThalirisError, match="require task schema 9"):
            core._validate_state(root, state)
    core.task_handoff_usage(root, "H1", {"model": "m"})
    state = copy.deepcopy(state_of(root))
    del state["checks"]
    state["schema_version"] = 8
    with pytest.raises(core.ThalirisError, match="require task schema 9"):
        core._validate_state(root, state)


# --- compare-and-set on every new write -----------------------------------------------------------

def test_every_new_write_enforces_revision_cas(tmp_path):
    root = project(tmp_path)
    declare(root)
    current = rev(root)
    stale = current - 1
    check = {"id": "C2", "requirement_refs": ["R2"], "command": [sys.executable, "-c", "pass"]}
    marker = tmp_path / "ran.txt"
    counting = {"id": "C3", "requirement_refs": ["R2"], "command": [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x')"]}
    core.task_check(root, "controller", current, counting)
    current = rev(root)
    writes = [
        lambda: core.task_check(root, "controller", stale, check),
        lambda: core.task_check(root, "controller", stale, check, supersede=True),
        lambda: core.task_verify(root, "implementer", "C3", base_revision=stale),
        lambda: core.task_ingest_claims(root, "H1", block("none"), base_revision=stale),
        lambda: core.task_handoff_usage(root, "H1", {"model": "m"}, base_revision=stale),
        lambda: core.task_judge(root, "controller", stale, write(root, "j", {
            "id": "J1", "candidate": "C1", "requirement_ref": "R1", "observation_refs": ["x"], "outcome": "satisfied", "reasoning": "r"}),
            override_reason="stale"),
        lambda: core.task_close(root, stale, override_reason="stale"),
    ]
    before = core._state_path(root).read_bytes()
    for attempt in writes:
        with pytest.raises(core.ThalirisError) as caught:
            attempt()
        assert caught.value.code == errors.TASK_REVISION_CONFLICT and caught.value.details["current_revision"] == current
    assert core._state_path(root).read_bytes() == before and not marker.exists(), "a stale verify does not even run the command"

    # Each accepted write advances the revision by exactly one.
    for attempt in (
        lambda: core.task_check(root, "controller", rev(root), check),
        lambda: core.task_verify(root, "implementer", "C3", base_revision=rev(root)),
        lambda: core.task_verify(root, "implementer", "C3"),
        lambda: core.task_ingest_claims(root, "H1", block("none"), base_revision=rev(root)),
        lambda: core.task_handoff_usage(root, "H1", {"model": "m"}, base_revision=rev(root)),
    ):
        previous = rev(root)
        assert attempt()["revision"] == previous + 1 == rev(root)
    assert marker.read_text() == "xx"


def test_new_writes_need_an_active_task(tmp_path):
    root = project(tmp_path, kinds=False)
    core.task_close(root, rev(root))
    for attempt in (
        lambda: declare(root), lambda: core.task_verify(root, "implementer", "C1"),
        lambda: core.task_ingest_claims(root, "H1", "x"), lambda: core.task_handoff_usage(root, "H1", {"model": "m"}),
        lambda: core.task_lane_counter(root, add=1),
    ):
        with pytest.raises(core.ThalirisError) as caught:
            attempt()
        assert caught.value.code == errors.TASK_NOT_ACTIVE


# --- command boundary -----------------------------------------------------------------------------

def run_cli(capsys, root: Path, *arguments: str) -> tuple[int, dict]:
    capsys.readouterr()
    code = cli.main(["--root", str(root), "--task-id", state_of(root)["task_id"], *arguments])
    return code, json.loads(capsys.readouterr().out)


def test_cli_exposes_the_verification_first_operations(tmp_path, capsys):
    root = project(tmp_path)
    check = write(root, "check", {"id": "C1", "requirement_refs": ["R1"], "command": [sys.executable, "tests/check_value.py"],
                                  "files": ["tests/check_value.py"]})
    code, out = run_cli(capsys, root, "task-check", "--actor", "controller", "--base-revision", str(rev(root)), "--input", check)
    assert code == 0 and out["declared"] == ["C1"]
    code, out = run_cli(capsys, root, "task-check", "--actor", "controller", "--base-revision", str(rev(root)), "--input", check)
    assert code == 2 and out["code"] == "CHECK_ALREADY_DECLARED" and out["ok"] is False and "recovery" in out
    code, out = run_cli(capsys, root, "task-check", "--actor", "controller", "--base-revision", str(rev(root)), "--input", check, "--supersede")
    assert code == 0 and out["declared"] == []

    observe(root, "basis")
    judgment = write(root, "judgment", {"id": "J1", "candidate": "C1", "requirement_ref": "R1", "observation_refs": ["basis"],
                                        "outcome": "satisfied", "reasoning": "r"})
    code, out = run_cli(capsys, root, "task-judge", "--actor", "controller", "--base-revision", str(rev(root)), "--input", judgment)
    assert code == 2 and out["code"] == "VERIFICATION_WITHHELD" and out["details"]["withheld"][0]["checks"] == [{"id": "C1", "status": "unrun"}]
    code, out = run_cli(capsys, root, "task-verify", "--actor", "implementer", "--check", "C1", "--compact-evidence")
    assert code == 0 and out["result"]["outcome"] == "PASS" and out["result"]["fresh"] is True and "evidence" in out
    code, out = run_cli(capsys, root, "task-judge", "--actor", "controller", "--base-revision", str(rev(root)), "--input", judgment)
    assert code == 0

    message = tmp_path / "final.md"
    message.write_text(block({"claims": [claim("R2", "unknown", "not exercised", "C1", "inference")]}), encoding="utf-8")
    code, out = run_cli(capsys, root, "task-ingest-claims", "--handoff", "H1", "--file", str(message))
    assert code == 0 and out["claims"]["observations"] == ["H1.c1"]
    code, out = run_cli(capsys, root, "task-ingest-claims", "--handoff", "H2", "--text", "no block", "--base-revision", str(rev(root)))
    assert code == 0 and out["claims"]["status"] == "missing"
    code, out = run_cli(capsys, root, "task-handoff-usage", "--handoff", "H1", "--input", write(root, "usage", {"model": "m", "total_tokens": 12}))
    assert code == 0 and out["usage"]["total_tokens"] == 12
    code, out = run_cli(capsys, root, "task-lane-counter", "--add", "40000")
    assert code == 0 and out["controller_tool_output_tokens"] == 40000
    code, out = run_cli(capsys, root, "task-lane-counter", "--set", "1", "--add", "1")
    assert code == 2

    contract = write(root, "contract", {"execution_mode": "adaptive", "write_surface": ["src/**"]})
    code, out = run_cli(capsys, root, "task-status", "--view", "compact", "--contract", contract, "--record-tamper")
    assert code == 0 and {"Verification", "Claims", "Usage", "Advisories"} <= set(out)
    assert "CONTROLLER_TOOL_OUTPUT" in {item["code"] for item in out["Advisories"]["items"]}
    assert out["Claims"]["handoffs_without_typed_claims"]["ids"] == ["H2"]

    (root / "value.txt").write_text("broken\n", encoding="utf-8")
    code, out = run_cli(capsys, root, "task-close", "--base-revision", str(rev(root)))
    assert code == 2 and out["code"] == "VERIFICATION_WITHHELD" and out["details"]["operation"] == "close"
    code, out = run_cli(capsys, root, "task-close", "--base-revision", str(rev(root)), "--override-reason", "user stopped the task",
                        "--actor", "controller")
    assert code == 0 and out["status"] == "DONE" and out["closure"]["gate"] == "overridden"
    assert [item["requirement"] for item in out["surfaced"]] == ["R2", "R3"]


def test_cli_new_writes_require_an_explicit_task_id(tmp_path, capsys):
    root = project(tmp_path)
    for arguments in (["task-verify", "--actor", "a", "--check", "C1"], ["task-lane-counter", "--add", "1"],
                      ["task-ingest-claims", "--handoff", "H1", "--text", "x"], ["task-status", "--record-tamper"]):
        capsys.readouterr()
        assert cli.main(["--root", str(root), *arguments]) == 2
        assert "explicit --task-id required" in json.loads(capsys.readouterr().out)["error"]


def test_version_is_0_6_0():
    from thaliris import __version__
    assert __version__ == "0.6.0"
