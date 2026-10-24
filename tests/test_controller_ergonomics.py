"""Mechanical Controller ergonomics: structured errors, batches, compact views."""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from thaliris import cli, core, errors


def payload(root, name, value, *, encoding="utf-8"):
    path = root / (name + ".json")
    path.write_bytes(json.dumps(value, ensure_ascii=False).encode(encoding))
    return str(path)


def setup(root):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    started = core.task_start(root, "ergonomics", None, None)
    core.task_evidence_register(root, "controller", 1, payload(root, "register", {
        "requirements": [{"id": "R1", "workchain_ref": "chain-1"}, {"id": "R2", "workchain_ref": "chain-2"}],
        "handoffs": [
            {"id": "H1", "parent_handoff_id": None, "candidate": "C1", "producer": "child-a", "requirement_refs": ["R1", "R2"]},
            {"id": "H2", "parent_handoff_id": None, "candidate": "C1", "producer": "child-b", "requirement_refs": ["R1"]},
        ],
    }))
    core.task_update(root, "controller", 2, payload(root, "source", {
        "evidence_refs": [{"id": "S1", "kind": "test", "locator": "tests/result.txt", "summary": "selected source"}],
    }))
    return started["task_id"]


def observation(identifier, handoff="H1", requirement_refs=("R1",), source_refs=("S1",)):
    return {"id": identifier, "candidate": "C1", "handoff_id": handoff, "requirement_refs": list(requirement_refs),
            "source_refs": list(source_refs), "text": "decision-changing observation"}


def judgment(identifier, refs, requirement="R1", outcome="satisfied", **extra):
    return {"id": identifier, "candidate": "C1", "requirement_ref": requirement, "observation_refs": refs,
            "outcome": outcome, "reasoning": "Controller reasoning", **extra}


def test_revision_conflict_is_structured_and_reports_changes_since(tmp_path, capsys):
    task_id = setup(tmp_path)
    base = core.task_status(tmp_path)["Task"]["revision"]
    core.task_observe(tmp_path, "child-a", observation("O1"))
    core.task_evidence_register(tmp_path, "controller", base + 1, payload(tmp_path, "late", {
        "handoffs": [{"id": "H3", "parent_handoff_id": "H1", "candidate": "C1", "producer": "child-c", "requirement_refs": ["R2"]}],
    }))
    with pytest.raises(ValueError) as caught:
        core.task_judge(tmp_path, "controller", base, payload(tmp_path, "stale", judgment("J1", ["O1"])))
    exc = caught.value
    assert isinstance(exc, errors.ThalirisError)
    assert str(exc) == "task revision conflict"
    assert exc.code == errors.TASK_REVISION_CONFLICT
    assert exc.details["base_revision"] == base and exc.details["current_revision"] == base + 2
    delta = exc.details["changes_since"]
    assert delta["exact"] is False and delta["revision_gap"] == 2
    assert delta["recent"]["observations"] == [{"id": "O1", "handoff_id": "H1", "requirement_refs": ["R1"]}]
    # Honest hint: recent handoffs are the last k=gap, so H2 (older than base) is included too.
    assert delta["recent"]["handoffs"] == ["H2", "H3"]
    assert delta["evidence"]["unincorporated_total"] == 1
    assert delta["truncated"] is False
    assert f"--base-revision {base + 2}" in exc.recovery
    # Strict CAS: nothing was rebased or merged.
    assert core.task_status(tmp_path)["Task"]["revision"] == base + 2
    assert core.task_show(tmp_path)["state"]["evidence_continuity"]["judgments"] == []

    judge_input = payload(tmp_path, "cli-stale", judgment("J1", ["O1"]))
    assert cli.main(["--root", str(tmp_path), "--task-id", task_id, "task-judge", "--actor", "controller",
                     "--base-revision", str(base), "--input", judge_input]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["error"] == "task revision conflict"
    assert out["code"] == "TASK_REVISION_CONFLICT" and out["details"]["changes_since"]["recent"]["handoffs"][-1] == "H3"


def test_changes_since_is_an_honest_bounded_hint(tmp_path):
    setup(tmp_path)
    for index in range(20):
        core.task_observe(tmp_path, "child-a", observation(f"O{index}"))
    current = core.task_show(tmp_path)["state"]
    hint = core.changes_since(current, current["revision"] - 1)
    assert hint["exact"] is False and hint["revision_gap"] == 1
    assert [item["id"] for item in hint["recent"]["observations"]] == ["O19"]
    assert hint["recent"]["handoffs"] == ["H2"] and hint["recent"]["judgments"] == []
    assert hint["records"] == []
    assert hint["evidence"]["unincorporated_total"] == 20
    wide = core.changes_since(current, 0)
    assert wide["revision_gap"] == current["revision"]
    assert len(wide["recent"]["observations"]) <= core.CHANGES_SINCE_RECENT_MAX
    assert "O19" in [item["id"] for item in wide["recent"]["observations"]]
    assert set(wide["records"]) <= {item["id"] for item in current["records"]}
    assert core._compact_size({key: value for key, value in wide.items() if key != "evidence"}) <= core.CHANGES_SINCE_MAX_BYTES
    assert core.changes_since(current, current["revision"])["recent"]["observations"] == []
    ahead = core.changes_since(current, current["revision"] + 5)
    assert ahead["revision_gap"] == 0 and "reason" in ahead and ahead["recent"]["observations"] == []
    with pytest.raises(errors.ThalirisError) as caught:
        core.changes_since(current, -1)
    assert caught.value.code == errors.REVISION_DELTA_INVALID


def test_batch_judge_is_one_revision_ordered_and_all_or_nothing(tmp_path):
    setup(tmp_path)
    core.task_observe(tmp_path, "child-a", {"observations": [observation("O1"), observation("O2", requirement_refs=["R2"])]})
    state = core.task_show(tmp_path)["state"]
    assert state["revision"] == 4
    assert all("revision" not in item for item in state["evidence_continuity"]["observations"])

    bad = {"judgments": [judgment("J1", ["O1"], outcome="repair"),
                         judgment("J2", ["O2"], requirement="R2"),
                         judgment("J3", ["H1.O9"], judgment_refs=["J1"])]}
    with pytest.raises(ValueError, match="invalid continuity references") as caught:
        core.task_judge(tmp_path, "controller", 4, payload(tmp_path, "bad-batch", bad))
    exc = caught.value
    assert exc.code == errors.CONTINUITY_REFERENCE_INVALID
    assert exc.details["collection"] == "judgments" and exc.details["index"] == 2 and exc.details["id"] == "J3"
    assert exc.details["field"] == "observation_refs" and exc.details["unknown_refs"] == ["H1.O9"]
    assert "judgments[2] (J3) observation_refs" in str(exc)
    after = core.task_show(tmp_path)["state"]
    assert after["revision"] == 4 and after["evidence_continuity"]["judgments"] == []

    good = {"judgments": [judgment("J1", ["O1"], outcome="repair"),
                          judgment("J2", ["O2"], requirement="R2"),
                          judgment("J3", ["O1"], judgment_refs=["J1"])]}
    ack = core.task_judge(tmp_path, "controller", 4, payload(tmp_path, "good-batch", good), compact_evidence=True)
    assert ack["revision"] == 5 and ack["appended"] == ["J1", "J2", "J3"]
    assert ack["evidence"]["unresolved_judgments_total"] == 0 and ack["evidence"]["unincorporated_total"] == 0
    saved = core.task_show(tmp_path)["state"]["evidence_continuity"]["judgments"]
    assert [item["id"] for item in saved] == ["J1", "J2", "J3"] and all("revision" not in item for item in saved)

    # Later-in-batch refs may not point forward.
    forward = {"judgments": [judgment("J4", ["O1"], judgment_refs=["J5"]), judgment("J5", ["O1"])]}
    with pytest.raises(ValueError, match="invalid continuity references"):
        core.task_judge(tmp_path, "controller", 5, payload(tmp_path, "forward", forward))
    with pytest.raises(ValueError, match="invalid judgments batch"):
        core.task_judge(tmp_path, "controller", 5, payload(tmp_path, "empty", {"judgments": []}))


def test_parallel_children_with_same_local_id_get_actionable_collision(tmp_path):
    setup(tmp_path)
    core.task_observe(tmp_path, "child-a", observation("O1", handoff="H1"))
    with pytest.raises(ValueError, match="task object id collision") as caught:
        core.task_observe(tmp_path, "child-b", observation("O1", handoff="H2"))
    exc = caught.value
    assert exc.code == errors.CONTINUITY_ID_COLLISION
    assert exc.details["existing_handoff_id"] == "H1" and exc.details["suggested_id"] == "H2.O1"
    assert "H2.O1" in exc.recovery
    core.task_observe(tmp_path, "child-b", observation("H2.O1", handoff="H2"))
    state = core.task_show(tmp_path)["state"]
    with pytest.raises(ValueError, match="invalid continuity references") as caught:
        core.task_judge(tmp_path, "controller", state["revision"], payload(tmp_path, "bare", judgment("J1", ["O1", "O2"])))
    assert caught.value.details["unknown_refs"] == ["O2"]
    core.task_observe(tmp_path, "child-a", observation("H1.O7", handoff="H1"))
    state = core.task_show(tmp_path)["state"]
    with pytest.raises(ValueError) as caught:
        core.task_judge(tmp_path, "controller", state["revision"], payload(tmp_path, "unqualified", judgment("J1", ["O7"])))
    assert caught.value.details["suggestions"] == {"O7": ["H1.O7"]}


def test_validation_errors_name_collection_item_field_and_format(tmp_path):
    setup(tmp_path)
    with pytest.raises(ValueError, match="invalid observation source refs") as caught:
        core.task_observe(tmp_path, "child-a", observation("O1", source_refs=["S9"]))
    assert caught.value.details["field"] == "source_refs" and caught.value.details["unknown_refs"] == ["S9"]
    assert "embedded in this observation's `sources`" in str(caught.value)
    with pytest.raises(ValueError, match="observation handoff provenance conflict") as caught:
        core.task_observe(tmp_path, "child-b", observation("O1", handoff="H1"))
    assert caught.value.details["field"] == "producer"
    with pytest.raises(ValueError, match="invalid continuity object") as caught:
        core.task_observe(tmp_path, "child-a", {**observation("O1"), "extra": 1})
    assert caught.value.details["unexpected_fields"] == ["extra"]
    with pytest.raises(ValueError, match="continuity objects carry no revision field"):
        core.task_observe(tmp_path, "child-a", {**observation("O1"), "revision": 9})
    with pytest.raises(ValueError, match="invalid continuity id") as caught:
        core.task_observe(tmp_path, "child-a", observation("bad id"))
    assert caught.value.details["expected"].startswith("1-64 characters")
    # Nothing above was recorded.
    assert core.task_show(tmp_path)["state"]["revision"] == 3


def test_adapter_transactions_are_atomic_and_register_handoffs_unstamped(tmp_path):
    setup(tmp_path)
    state = core._load_state(tmp_path)
    before = json.dumps(state, sort_keys=True)
    with pytest.raises(ValueError):
        core.append_observations(state, [("child-a", observation("O1")), ("child-b", observation("O2", handoff="H1"))])
    assert json.dumps(state, sort_keys=True) == before
    assert core.append_observations(state, [("child-a", observation("O1")), ("child-b", observation("O2", handoff="H2"))]) == ["O1", "O2"]
    assert state["revision"] == 4
    record = {"id": "H9", "parent_handoff_id": "H1", "candidate": "C1", "producer": "child-z", "requirement_refs": ["R1"]}
    core._register_evidence_handoff(state, record)
    assert "revision" not in record
    assert state["evidence_continuity"]["handoffs"][-1] == record and state["revision"] == 4
    state["revision"] += 1
    core._write_state(tmp_path, state)
    assert core.changes_since(core._load_state(tmp_path), 4)["recent"]["handoffs"] == ["H9"]


def test_compact_summary_and_status_views_stay_bounded(tmp_path):
    setup(tmp_path)
    state = core.task_show(tmp_path)["state"]
    data = core._continuity(state)
    for i in range(100):
        data["observations"].append({**observation("observation-" + str(i)), "task_id": state["task_id"], "producer": "child-a"})
    core._write_state(tmp_path, state)
    offset, seen = 0, []
    while offset is not None:
        summary = core.evidence_summary(core._load_state(tmp_path), offset)
        assert core._compact_size(summary) <= core.EVIDENCE_SUMMARY_MAX_BYTES
        assert summary["unincorporated_total"] == 100
        seen.extend(item["observation_id"] for item in summary["unincorporated"])
        offset = summary["next_offset"]
    assert len(seen) == len(set(seen)) == 100

    full = core.task_status(tmp_path)
    compact = core.task_status(tmp_path, view="compact", since_revision=2)
    assert "Evidence Continuity" in full and "view" not in full and "Changes Since" not in full
    assert compact["view"] == "compact" and compact["Task"]["revision"] == full["Task"]["revision"]
    assert compact["Counts"]["observations"] == 100 and compact["Evidence"]["unincorporated_total"] == 100
    assert compact["Changes Since"]["base_revision"] == 2
    assert compact["Active Work"] == full["Active Work"] and compact["Pending Results"] == full["Pending Results"]
    assert core._compact_size(compact) < core._compact_size(full)
    with pytest.raises(ValueError, match="invalid status view"):
        core.task_status(tmp_path, view="tiny")


def test_input_accepts_utf8_bom_and_utf16_bom_and_refuses_other_encodings(tmp_path):
    setup(tmp_path)
    value = {"pending_results": ["结果 ✓"]}
    for revision, (name, data) in enumerate((
        ("bom8", b"\xef\xbb\xbf" + json.dumps(value, ensure_ascii=False).encode("utf-8")),
        ("utf16", json.dumps(value, ensure_ascii=False).encode("utf-16")),
        ("utf16be", b"\xfe\xff" + json.dumps(value, ensure_ascii=False).encode("utf-16-be")),
    ), start=3):
        (tmp_path / name).write_bytes(data)
        assert core.task_update(tmp_path, "controller", revision, str(tmp_path / name))["revision"] == revision + 1
    assert core.task_status(tmp_path)["Pending Results"] == ["结果 ✓"]
    for name, data in (("gbk", json.dumps({"pending_results": ["结果"]}, ensure_ascii=False).encode("gbk")),
                       ("utf16-nobom", json.dumps(value).encode("utf-16-le")),
                       ("utf32", json.dumps(value).encode("utf-32"))):
        (tmp_path / name).write_bytes(data)
        with pytest.raises(ValueError) as caught:
            core.task_update(tmp_path, "controller", 6, str(tmp_path / name))
        assert caught.value.code == errors.INPUT_DECODING_ERROR
        assert caught.value.details["expected_encodings"] == ["UTF-8", "UTF-8 with BOM", "UTF-16 with BOM"]
    (tmp_path / "broken").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        core.task_update(tmp_path, "controller", 6, str(tmp_path / "broken"))
    assert caught.value.code == errors.INPUT_JSON_INVALID


def test_non_ascii_git_root_survives_non_utf8_locale(tmp_path):
    root = tmp_path / "中文仓库"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    script = (
        "import json, sys; from pathlib import Path; from thaliris import core; r = Path(sys.argv[1]); "
        "core.init(r); t = core.task_start(r, 'goal', None, None); "
        "print(json.dumps({'root': str(core._git_root(r)), 'task': t['task_id'], 'enc': sys.flags.utf8_mode}))"
    )
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, "-X", "utf8=0", "-c", script, str(root)], capture_output=True,
                            text=True, encoding="utf-8", env=env, check=True)
    out = json.loads(result.stdout)
    assert out["enc"] == 0
    assert Path(out["root"]).resolve() == root.resolve()
    core.select_task(root, out["task"])
    assert core.task_status(root)["Task"]["status"] == "ACTIVE"


def test_cli_compact_views_and_compact_evidence_flags(tmp_path, capsys):
    task_id = setup(tmp_path)
    observe_input = payload(tmp_path, "observe", {"observations": [observation("O1"), observation("O2")]})
    assert cli.main(["--root", str(tmp_path), "--task-id", task_id, "task-observe", "--actor", "child-a",
                     "--input", observe_input, "--compact-evidence"]) == 0
    observed = json.loads(capsys.readouterr().out)
    assert observed["appended"] == ["O1", "O2"] and observed["evidence"]["unincorporated_total"] == 2
    judge_input = payload(tmp_path, "judge", {"judgments": [judgment("J1", ["O1"]), judgment("J2", ["O2"])]})
    assert cli.main(["--root", str(tmp_path), "--task-id", task_id, "task-judge", "--actor", "controller",
                     "--base-revision", "4", "--input", judge_input, "--compact-evidence"]) == 0
    judged = json.loads(capsys.readouterr().out)
    assert judged["revision"] == 5 and judged["evidence"]["unincorporated_total"] == 0
    assert cli.main(["--root", str(tmp_path), "--task-id", task_id, "task-status", "--view", "compact",
                     "--since-revision", "3"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["view"] == "compact" and status["Changes Since"]["exact"] is False
    assert [item["id"] for item in status["Changes Since"]["recent"]["judgments"]] == ["J1", "J2"]
    assert [item["id"] for item in status["Changes Since"]["recent"]["observations"]] == ["O1", "O2"]


def _git_show(repo, path):
    try:
        return subprocess.run(["git", "-C", str(repo), "show", f"{CORE_050}:{path}"], capture_output=True,
                              check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f"git or commit {CORE_050} (Core 0.5.0) is unavailable")


CORE_050 = "eb540d0"


@pytest.fixture
def core_050():
    """Core 0.5.0 loaded from Git history as a private package, isolated from this Core."""
    import importlib.abc
    import importlib.util
    repo = Path(__file__).resolve().parent.parent
    _git_show(repo, "src/thaliris/core.py")  # skips when git or the commit is unavailable

    class Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, name, path=None, target=None):
            if name == "thaliris_050":
                return importlib.util.spec_from_loader(name, self, is_package=True)
            if name.startswith("thaliris_050."):
                return importlib.util.spec_from_loader(name, self)
            return None

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            if module.__name__ == "thaliris_050":
                module.__path__ = []
                module.__version__ = "0.5.0"
                return
            text = _git_show(repo, f"src/thaliris/{module.__name__.split('.', 1)[1]}.py")
            text = text.replace("from thaliris.", "from thaliris_050.").replace("from thaliris import", "from thaliris_050 import")
            exec(compile(text, f"{CORE_050}:{module.__name__}", "exec"), module.__dict__)

    finder = Finder()
    sys.meta_path.insert(0, finder)
    try:
        yield importlib.import_module("thaliris_050.core")
    finally:
        sys.meta_path.remove(finder)
        for name in [name for name in sys.modules if name == "thaliris_050" or name.startswith("thaliris_050.")]:
            del sys.modules[name]


def test_states_written_by_this_core_validate_under_core_050(tmp_path, core_050):
    old = core_050
    setup(tmp_path)

    def check(label):
        state = json.loads(json.dumps(core._load_state(tmp_path)))
        try:
            old._validate_state(tmp_path, state)
        except Exception as exc:  # noqa: BLE001 - name the operation that broke Core 0.5.0 compatibility
            raise AssertionError(f"Core 0.5.0 rejects the state after {label}: {exc}") from exc

    check("task-start, register and task-update")
    core.task_observe(tmp_path, "child-a", observation("O1"))
    check("observe single")
    core.task_observe(tmp_path, "child-a", {"observations": [observation("O3", requirement_refs=["R2"]), observation("O4")]})
    core.task_observe(tmp_path, "child-b", observation("H2.O2", handoff="H2"))
    check("observe batch")
    state = core._load_state(tmp_path)
    core._register_evidence_handoff(state, {"id": "H9", "parent_handoff_id": "H1", "candidate": "C1",
                                           "producer": "child-z", "requirement_refs": ["R1"]})
    state["revision"] += 1
    core._write_state(tmp_path, state)
    check("reserve handoff")
    current = core.task_status(tmp_path)["Task"]["revision"]
    core.task_judge(tmp_path, "controller", current, payload(tmp_path, "j1", judgment("J1", ["O1"])))
    check("judge single")
    core.task_judge(tmp_path, "controller", current + 1, payload(tmp_path, "jb", {"judgments": [
        judgment("J2", ["H2.O2"]), judgment("J3", ["O4"], judgment_refs=["J1"])]}))
    check("judge batch")
    core.task_update(tmp_path, "controller", core.task_status(tmp_path)["Task"]["revision"],
                     payload(tmp_path, "upd", {"pending_results": ["after judgments"]}))
    check("task-update after continuity writes")


def test_this_core_reads_a_state_written_by_core_050(tmp_path, core_050):
    old = core_050
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    old.init(tmp_path)
    core.select_task(tmp_path, old.task_start(tmp_path, "legacy", None, None)["task_id"])
    old.task_evidence_register(tmp_path, "controller", 1, payload(tmp_path, "register", {
        "requirements": [{"id": "R1", "workchain_ref": "chain-1"}],
        "handoffs": [{"id": "H1", "parent_handoff_id": None, "candidate": "C1", "producer": "child-a", "requirement_refs": ["R1"]}],
    }))
    old.task_update(tmp_path, "controller", 2, payload(tmp_path, "source", {
        "evidence_refs": [{"id": "S1", "kind": "test", "locator": "tests/result.txt", "summary": "selected source"}]}))
    old.task_observe(tmp_path, "child-a", payload(tmp_path, "obs", observation("O1")))
    state = core._load_state(tmp_path)
    assert state["revision"] == 4 and state["evidence_continuity"]["observations"][0]["id"] == "O1"
    hint = core.changes_since(state, 1)
    assert hint["revision_gap"] == 3 and hint["evidence"]["unincorporated_total"] == 1
    core.task_judge(tmp_path, "controller", 4, payload(tmp_path, "j", judgment("J1", ["O1"])))
    assert core.task_status(tmp_path, view="compact", since_revision=2)["Changes Since"]["exact"] is False
