"""Cross-host managed children (schema 12): foreign-runner handoffs, their run states and claims."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from thaliris import authority, core

RELAY = hashlib.sha256(b"relay-agent-1").hexdigest()
PROMPT = "Investigate the parser and report.\n\nthaliris-handoff: HX1\n"
BLOCK = "```thaliris-claims\n" + json.dumps({"claims": [
    {"requirement": "R1", "polarity": "supports", "text": "parser ok", "evidence": "src/p.py:3", "basis": "read"},
    {"requirement": "R1", "polarity": "contradicts", "text": "edge case fails", "evidence": "src/p.py:9", "basis": "read"},
    {"requirement": "R9", "polarity": "unknown", "text": "out of scope", "evidence": "src/q.py:1", "basis": "inference"}]}) + "\n```\n"
USAGE = {"model": "gpt-5.5-codex", "effort": "high", "input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500,
         "cost_usd": 0.021, "duration_ms": 4100, "tool_uses": 3, "cost_basis": "subscription-notional"}


def repo(path: Path) -> Path:
    root = path / "project"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    core.task_start(root, "cross host", None, None)
    reg = root.parent / "reg.json"
    reg.write_text(json.dumps({"requirements": [{"id": "R1", "workchain_ref": "w"}, {"id": "R2", "workchain_ref": "w"}],
                               "handoffs": [{"id": "H0", "parent_handoff_id": None, "candidate": "C1", "producer": "implementer",
                                             "requirement_refs": ["R1", "R2"]}]}), encoding="utf-8")
    core.task_evidence_register(root, "controller", core._load_state(root)["revision"], str(reg))
    return root


def handoff(identifier: str = "HX1", parent: str | None = None, refs: list[str] | None = None) -> dict:
    return {"id": identifier, "parent_handoff_id": parent, "candidate": "C1", "producer": "investigator",
            "requirement_refs": refs or ["R1"]}


def revision(root: Path) -> int:
    return core._load_state(root)["revision"]


def stored(root: Path, identifier: str = "HX1") -> dict:
    return next(item for item in core._load_state(root)["evidence_continuity"]["handoffs"] if item["id"] == identifier)


def reserve(root: Path, identifier: str = "HX1", **kwargs) -> dict:
    return core.task_foreign_reserve(root, "controller", revision(root), handoff(identifier, **kwargs), executor_host="codex", prompt=PROMPT)


def session(name: str = "019a-thread-1") -> str:
    return core.foreign_session_hash(name)


def test_full_lifecycle_reserve_launch_bind_result(tmp_path):
    root = repo(tmp_path)
    start = revision(root)
    reserved = reserve(root)
    assert reserved["revision"] == start + 1 and reserved["foreign"]["run_state"] == "reserved"
    item = stored(root)
    assert item["executor_host"] == "codex" and item["prompt_sha256"] == hashlib.sha256(PROMPT.encode()).hexdigest()
    assert "foreign_session_hash" not in item and "transport_agent_id_hash" not in item
    # The launcher reads the prompt back from Core, verified by its digest.
    body = core.task_foreign_body(root, "HX1")
    assert body["text"] == PROMPT and body["role"] == "investigator" and body["executor_host"] == "codex"
    # Before the launch nothing binds.
    assert core.task_foreign_bind(root, session())["binding"] is None
    launched = core.task_foreign_launch(root, "HX1", session(), RELAY, base_revision=revision(root))
    assert launched["foreign"]["run_state"] == "launched"
    assert stored(root)["foreign_session_hash"] == session() and stored(root)["transport_agent_id_hash"] == RELAY
    # Bind is idempotent: the first bind moves launched -> bound, later binds change nothing.
    before = revision(root)
    first = core.task_foreign_bind(root, session())
    assert first["revision"] == before + 1 and first["changed"] == ["evidence_continuity"]
    binding = first["binding"]
    assert binding["binding"] == "FOREIGN_CHILD" and binding["authority"] == "none"
    assert (binding["handoff_id"], binding["role"], binding["candidate"], binding["run_state"]) == ("HX1", "investigator", "C1", "bound")
    again = core.task_foreign_bind(root, session())
    assert again["revision"] == before + 1 and again["changed"] == [] and again["binding"] == binding
    # Only an exact hash matches.
    assert core.task_foreign_bind(root, session("019a-thread-2"))["binding"] is None
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_bind(root, session().upper())
    assert caught.value.code == "FOREIGN_RUN_INVALID"
    # The result: body, digest, provenance-marked claims once, usage with its cost basis.
    result_text = "Parser reviewed.\n\n" + BLOCK
    recorded = core.task_foreign_result(root, "HX1", result_text, None, USAGE, base_revision=revision(root))["foreign"]
    assert recorded["run_state"] == "completed" and recorded["result_source"] == "foreign-runner"
    assert recorded["result_sha256"] == hashlib.sha256(result_text.encode()).hexdigest()
    assert recorded["claims"]["status"] == "present" and recorded["claims"]["supports"] == {"R1": 1}
    item = stored(root)
    assert item["run_state"] == "completed" and item["claims"]["status"] == "present"
    assert item["usage"]["cost_basis"] == "subscription-notional" and item["usage"]["outcome"] == "completed"
    assert item["usage"]["model"] == "gpt-5.5-codex" and item["usage"]["total_tokens"] == 1500
    state = core._load_state(root)
    claim_observations = [obs for obs in state["evidence_continuity"]["observations"] if obs.get("handoff_id") == "HX1"]
    assert len(claim_observations) == 2 and all(obs["provenance"] == "foreign-runner" for obs in claim_observations)
    assert {obs["claim"]["polarity"] for obs in claim_observations} == {"contradicts", "unknown"}
    assert all(obs["producer"] == "investigator" and obs["candidate"] == "C1" for obs in claim_observations)
    assert core.task_foreign_body(root, "HX1", "result")["text"] == result_text
    usage = core.usage_summary(state)
    assert usage["totals"]["handoffs"] == 1 and usage["by_model"]["gpt-5.5-codex"]["total_tokens"] == 1500
    assert state["schema_version"] == core._STATE_SCHEMA_VERSION == 12
    # The settled run still binds (so its adapter keeps denying authority), without a write.
    settled = core.task_foreign_bind(root, session())
    assert settled["binding"]["run_state"] == "completed" and settled["binding"]["live"] is False and settled["changed"] == []


def test_second_launch_second_result_and_nested_delegation_are_refused(tmp_path):
    root = repo(tmp_path)
    reserve(root)
    core.task_foreign_launch(root, "HX1", session(), RELAY)
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_launch(root, "HX1", session("other"), RELAY)
    assert caught.value.code == "FOREIGN_RUN_STATE_CONFLICT" and stored(root)["foreign_session_hash"] == session()
    # A nested reservation (foreign or not) under a foreign handoff is refused: foreign children cannot delegate.
    reg = root.parent / "child.json"
    reg.write_text(json.dumps({"handoffs": [handoff("HC", parent="HX1")]}), encoding="utf-8")
    for attempt in (lambda: core.task_evidence_register(root, "investigator", revision(root), str(reg)),
                    lambda: core.task_foreign_reserve(root, "investigator", revision(root), handoff("HC2", parent="HX1"),
                                                      executor_host="claude", prompt="nested")):
        before = core._state_path(root).read_bytes()
        with pytest.raises(core.ThalirisError) as caught:
            attempt()
        assert caught.value.code == "FOREIGN_DELEGATION_REFUSED" and core._state_path(root).read_bytes() == before
    core.task_foreign_result(root, "HX1", "done\n```thaliris-claims\nnone\n```\n")
    before = core._state_path(root).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_result(root, "HX1", "again\n" + BLOCK)
    assert caught.value.code == "FOREIGN_RUN_STATE_CONFLICT" and "already recorded" in str(caught.value)
    assert core._state_path(root).read_bytes() == before
    # An ordinary parent may still have ordinary children; a foreign handoff under an ordinary parent is fine.
    core.task_foreign_reserve(root, "controller", revision(root), handoff("HX2", parent="H0"), executor_host="claude", prompt=PROMPT)
    assert stored(root, "HX2")["parent_handoff_id"] == "H0"


def test_dispatcher_checkpoints_launch_and_bind_before_readonly_receiver(tmp_path):
    root = repo(tmp_path)
    reserve(root)
    store = authority.AuthorityStore(root, tmp_path / "ext")
    store.establish(core._load_state(root), {"human_instruction": "probe", "boundary": "read-only", "invariants": "local",
                                            "acceptance": "result is recorded", "execution_mode": "delegated"})
    before = revision(root)
    with core._lock(root):
        state = core._load_state(root)
        assert store.check()["task_id"] == state["task_id"]
        core.register_foreign_launch(state, "HX1", session(), RELAY)
        binding, changed = core.bind_foreign_session(state, session())
        assert changed and binding["run_state"] == "bound"
        core._write_state(root, state)
        store.checkpoint()
    ledger_bytes = core._state_path(root).read_bytes()
    received, changed = core.bind_foreign_session(core._load_state(root), session())
    assert received == binding and not changed
    assert received["authority"] == "none" and received["executor_host"] == "codex"
    assert revision(root) == before + 2 and core._state_path(root).read_bytes() == ledger_bytes
    assert store.check()["state_sha256"] == hashlib.sha256(ledger_bytes).hexdigest()


def test_relay_subagent_stop_cannot_double_ingest(tmp_path):
    root = repo(tmp_path)
    reserve(root)
    core.task_foreign_launch(root, "HX1", session(), RELAY)
    # Before the foreign result: the relay's own stop claims change nothing.
    early = core.task_ingest_claims(root, "HX1", BLOCK)
    assert early["changed"] == [] and early["claims"]["ingested_by"] == "foreign-runner"
    assert early["claims"]["already_ingested"] is False and "claims" not in stored(root)
    core.task_foreign_result(root, "HX1", "result\n" + BLOCK, usage=USAGE)
    observations = len(core._load_state(root)["evidence_continuity"]["observations"])
    before = core._state_path(root).read_bytes()
    late = core.task_ingest_claims(root, "HX1", BLOCK)
    assert late["changed"] == [] and late["claims"]["already_ingested"] is True
    assert late["claims"]["reason"] == "already ingested by foreign runner"
    assert core._state_path(root).read_bytes() == before
    assert len(core._load_state(root)["evidence_continuity"]["observations"]) == observations
    # The relay's usage report does not overwrite the foreign model's usage either.
    ignored = core.task_handoff_usage(root, "HX1", {"model": "haiku-relay", "input_tokens": 9})
    assert "ignored" in ignored and ignored["usage"]["model"] == "gpt-5.5-codex"
    assert core._state_path(root).read_bytes() == before
    # A model cannot forge foreign fields or foreign provenance through the ordinary paths.
    reg = root.parent / "forged.json"
    reg.write_text(json.dumps({"handoffs": [{**handoff("HF"), "executor_host": "codex"}]}), encoding="utf-8")
    with pytest.raises(core.ThalirisError, match="assigned by Core"):
        core.task_evidence_register(root, "controller", revision(root), str(reg))
    with pytest.raises(core.ThalirisError, match="assigned by Core"):
        core.task_observe(root, "implementer", {"id": "forged", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R1"],
                                                "source_refs": [f"HX1.c1.s"], "text": "t", "provenance": "foreign-runner",
                                                "claim": {"requirement": "R1", "polarity": "unknown", "basis": "read", "evidence": "x"}})


def test_cancel_transitions(tmp_path):
    root = repo(tmp_path)
    reserve(root, "HA")
    cancelled = core.task_foreign_cancel(root, "HA", "Controller disposed the relay")["foreign"]
    assert cancelled == {"handoff_id": "HA", "run_state": "cancelled", "already_cancelled": False,
                         "cancel_reason": "Controller disposed the relay"}
    before = revision(root)
    again = core.task_foreign_cancel(root, "HA", "twice")
    assert again["foreign"]["already_cancelled"] is True and again["revision"] == before
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_launch(root, "HA", session(), RELAY)
    assert caught.value.code == "FOREIGN_RUN_STATE_CONFLICT"
    # launched -> cancelled and bound -> cancelled; a cancelled run takes no result.
    reserve(root, "HB")
    core.task_foreign_launch(root, "HB", session("b"), RELAY)
    core.task_foreign_cancel(root, "HB", "timeout; process tree killed")
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_result(root, "HB", "late")
    assert caught.value.code == "FOREIGN_RUN_STATE_CONFLICT"
    reserve(root, "HC")
    core.task_foreign_launch(root, "HC", session("c"), RELAY)
    core.task_foreign_bind(root, session("c"))
    assert core.task_foreign_cancel(root, "HC", "dispose")["foreign"]["run_state"] == "cancelled"
    # A completed run cannot be cancelled; a failed result is recorded as failed.
    reserve(root, "HD")
    core.task_foreign_launch(root, "HD", session("d"), RELAY)
    failed = core.task_foreign_result(root, "HD", "", usage={"model": "m"}, outcome="failed")["foreign"]
    assert failed["run_state"] == "failed" and failed["claims"]["status"] == "missing" and failed["usage"]["outcome"] == "failed"
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_cancel(root, "HD", "too late")
    assert caught.value.code == "FOREIGN_RUN_STATE_CONFLICT"
    for bad in ("", "two\nlines", "x" * 513):
        with pytest.raises(core.ThalirisError):
            core.task_foreign_cancel(root, "HC", bad)
    # The session hash of a cancelled run may be reused by a new live run, and binds to it.
    reserve(root, "HE")
    core.task_foreign_launch(root, "HE", session("b"), RELAY)
    assert core.task_foreign_bind(root, session("b"))["binding"]["handoff_id"] == "HE"
    reserve(root, "HF")
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_launch(root, "HF", session("b"), RELAY)
    assert caught.value.code == "FOREIGN_RUN_INVALID"


def test_relay_identity_set_once_and_inputs_validated(tmp_path):
    root = repo(tmp_path)
    core.task_foreign_reserve(root, "controller", revision(root), handoff("HR"), executor_host="claude", prompt=PROMPT,
                              transport_agent_id_hash=RELAY)
    assert stored(root, "HR")["transport_agent_id_hash"] == RELAY
    with pytest.raises(core.ThalirisError, match="relay identity"):
        core.task_foreign_launch(root, "HR", session(), hashlib.sha256(b"other relay").hexdigest())
    core.task_foreign_launch(root, "HR", session(), RELAY)
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_reserve(root, "controller", revision(root), handoff("HZ"), executor_host="gemini", prompt=PROMPT)
    assert caught.value.code == "FOREIGN_RUN_INVALID"
    with pytest.raises(core.ThalirisError):
        core.task_foreign_reserve(root, "controller", revision(root), handoff("HZ"), executor_host="codex", prompt="   ")
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_reserve(root, "controller", revision(root) - 1, handoff("HZ"), executor_host="codex", prompt=PROMPT)
    assert caught.value.code == "TASK_REVISION_CONFLICT"
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_launch(root, "H0", session("x"), RELAY)
    assert caught.value.code == "FOREIGN_RUN_INVALID"
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_result(root, "HR", "r", usage={"model": "m", "cost_basis": "free"})
    assert caught.value.code == "HANDOFF_USAGE_INVALID" and stored(root, "HR")["run_state"] == "launched"
    # A damaged prompt body is reported, never served.
    sha = stored(root, "HR")["prompt_sha256"]
    body = core._body_path(root, core._load_state(root)["task_id"], sha)
    body.write_bytes(b"tampered")
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_body(root, "HR")
    assert caught.value.code == "FOREIGN_BODY_UNAVAILABLE" and caught.value.details["reason"] == "sha256 mismatch"


@pytest.mark.parametrize("role", core.FOREIGN_READONLY_ROLES)
def test_readonly_roles_only_with_strict_reservation_cas(tmp_path, role):
    root = repo(tmp_path)
    before = core._state_path(root).read_bytes()
    for forbidden_role in ("controller", "implementer", "focused-implementer", "unrecognized"):
        with pytest.raises(core.ThalirisError, match="invalid foreign handoff role"):
            core.task_foreign_reserve(root, "controller", revision(root), {**handoff(), "producer": forbidden_role},
                                      executor_host="claude", prompt=PROMPT)
    with pytest.raises(core.ThalirisError) as caught:
        core.task_foreign_reserve(root, "controller", None, {**handoff(), "producer": role},
                                  executor_host="claude", prompt=PROMPT)
    assert caught.value.code == "TASK_REVISION_CONFLICT" and core._state_path(root).read_bytes() == before
    core.task_foreign_reserve(root, "controller", revision(root), {**handoff(), "producer": role},
                              executor_host="claude", prompt=PROMPT)
    assert core.task_foreign_body(root, "HX1")["role"] == role


def test_sidecar_collision_and_claims_mismatch_leave_state_identical(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    before = copy.deepcopy(state)
    path = core._body_path(root, state["task_id"], hashlib.sha256(PROMPT.encode()).hexdigest())
    path.parent.mkdir()
    path.write_bytes(b"unknown bytes")
    with pytest.raises(core.ThalirisError) as caught:
        core.reserve_foreign_handoff(state, handoff(), executor_host="codex", prompt=PROMPT, root=root)
    assert caught.value.code == "FOREIGN_BODY_UNAVAILABLE" and state == before and path.read_bytes() == b"unknown bytes"
    path.unlink()
    reserve(root)
    core.task_foreign_launch(root, "HX1", session(), RELAY)
    state = core._load_state(root)
    before = copy.deepcopy(state)
    with pytest.raises(core.ThalirisError, match="differs from the result body"):
        core.record_foreign_result(state, "HX1", "no claims in this result", BLOCK, root=root)
    assert state == before
    result = "done\n" + BLOCK
    path = core._body_path(root, state["task_id"], hashlib.sha256(result.encode()).hexdigest())
    path.write_bytes(b"unknown result bytes")
    with pytest.raises(core.ThalirisError) as caught:
        core.record_foreign_result(state, "HX1", result, BLOCK, usage=USAGE, root=root)
    assert caught.value.code == "FOREIGN_BODY_UNAVAILABLE" and state == before and path.read_bytes() == b"unknown result bytes"
    path.unlink()
    recorded = core.task_foreign_result(root, "HX1", result, BLOCK, usage=USAGE)["foreign"]
    assert recorded["claims"]["supports"] == {"R1": 1}


def test_forged_or_incoherent_foreign_fields_are_refused_on_load(tmp_path):
    root = repo(tmp_path)
    reserve(root)
    core.task_foreign_launch(root, "HX1", session(), RELAY)
    state = core._load_state(root)

    def broken(change):
        candidate = copy.deepcopy(state)
        change(next(item for item in candidate["evidence_continuity"]["handoffs"] if item["id"] == "HX1"), candidate)
        return candidate

    cases = {
        "unknown host": lambda h, s: h.update(executor_host="gemini"),
        "bad state": lambda h, s: h.update(run_state="running"),
        "session before launch": lambda h, s: h.update(run_state="reserved"),
        "result without completion": lambda h, s: h.update(result_sha256="a" * 64, result_source="foreign-runner"),
        "completed without result": lambda h, s: h.update(run_state="completed"),
        "wrong result source": lambda h, s: h.update(run_state="completed", result_sha256="a" * 64, result_source="relay"),
        "cancel without reason": lambda h, s: h.update(run_state="cancelled"),
        "claims before the result": lambda h, s: h.update(claims={"status": "missing"}),
        "uppercase hash": lambda h, s: h.update(foreign_session_hash=session().upper()),
        "no prompt digest": lambda h, s: h.pop("prompt_sha256"),
        "schema 11 with foreign fields": lambda h, s: s.update(schema_version=11),
    }
    for name, change in cases.items():
        with pytest.raises((core.ThalirisError, ValueError)):
            core._validate_state(root, broken(change))
            pytest.fail(name)
    core._validate_state(root, copy.deepcopy(state))


def test_foreign_fields_survive_eviction_and_rehydration(tmp_path, monkeypatch):
    root = repo(tmp_path)
    for identifier in ("HL", "HS", "HQ"):
        reserve(root, identifier)
    core.task_foreign_launch(root, "HL", session("live"), RELAY)
    core.task_foreign_launch(root, "HS", session("settled"), RELAY)
    core.task_foreign_result(root, "HS", "settled\n```thaliris-claims\n" + json.dumps({"claims": [
        {"requirement": "R1", "polarity": "supports", "text": "ok", "evidence": "src/a.py:1", "basis": "read"}]}) + "\n```\n",
        usage=USAGE)
    core.task_foreign_cancel(root, "HQ", "not needed")
    expected = {identifier: stored(root, identifier) for identifier in ("HL", "HS", "HQ")}
    # Push the three out of the "last 16 handoffs" tail with ordinary settled handoffs.
    reg = root.parent / "pad.json"
    reg.write_text(json.dumps({"handoffs": [{"id": f"P{i}", "parent_handoff_id": None, "candidate": "C2", "producer": "reviewer",
                                             "requirement_refs": ["R2"]} for i in range(20)]}), encoding="utf-8")
    core.task_evidence_register(root, "controller", revision(root), str(reg))
    with core._lock(root):
        state = core._load_state(root, active=True)
        for i in range(20):
            core.set_handoff_usage(state, f"P{i}", {"model": "m", "outcome": "completed"})
        core._write_state(root, state)
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    with core._lock(root):
        state = core._load_state(root, active=True)
        core._write_state(root, state)
    state = core._load_state(root)
    evicted = core._index_map(state)["handoffs"]
    # The unsettled (launched) foreign handoff stays hot; the settled and cancelled ones are evicted.
    assert "HL" not in evicted and "HS" in evicted and "HQ" in evicted
    assert stored(root, "HL") == expected["HL"]
    for identifier in ("HS", "HQ"):
        assert core.task_get(root, identifier)["object"] == expected[identifier]
    # The live run still binds and completes after eviction; the settled one re-hydrates exactly.
    assert core.task_foreign_bind(root, session("live"))["binding"]["handoff_id"] == "HL"
    assert core.task_foreign_body(root, "HS", "result")["text"].startswith("settled")
    after = core.task_ingest_claims(root, "HS", BLOCK)
    assert after["claims"]["already_ingested"] is True and after["claims"]["ingested_by"] == "foreign-runner"
    state = core._load_state(root)
    before = copy.deepcopy(state)
    assert core.ingest_claims(state, "HS", BLOCK)["changed"] is False
    assert core.set_handoff_usage(state, "HS", {"model": "relay"})["model"] == USAGE["model"]
    with pytest.raises(core.ThalirisError, match="already recorded"):
        core.record_foreign_result(state, "HS", "duplicate")
    with pytest.raises(core.ThalirisError, match="cannot launch"):
        core.register_foreign_launch(state, "HS", session("new"), RELAY)
    assert state == before
    # A late observation on the settled handoff brings it back hot, field for field.
    core.task_observe(root, "investigator", {"id": "late-HS", "candidate": "C1", "handoff_id": "HS", "requirement_refs": ["R1"],
                                             "source_refs": ["late-HS.s"], "text": "late note",
                                             "sources": [{"id": "late-HS.s", "kind": "file", "locator": "src/a.py:2", "summary": "s"}]})
    rehydrated = core._load_state(root)
    assert "HS" not in core._index_map(rehydrated)["handoffs"]
    assert next(item for item in rehydrated["evidence_continuity"]["handoffs"] if item["id"] == "HS") == expected["HS"]
    core.task_foreign_result(root, "HL", "live done\n```thaliris-claims\nnone\n```\n")
    # Once settled it may be evicted on the next pressured write; retrieval keeps every field.
    assert core.task_get(root, "HL")["object"]["run_state"] == "completed"
    usage = core.usage_summary(core._load_state(root))
    assert usage["totals"]["handoffs"] == 21


def test_schema_11_states_load_and_promote(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    for version in (7, 8, 9, 10, 11):
        old = {**copy.deepcopy(state), "schema_version": version}
        if version < 9:
            old.pop("checks", None), old.pop("closure", None)
        core._state_path(root).write_bytes(core._serialize_state(old))
        raw = core._state_path(root).read_bytes()
        loaded = core._load_state(root)
        assert loaded["schema_version"] == 12 and core._state_path(root).read_bytes() == raw, version
    reserve(root)
    assert json.loads(core._state_path(root).read_bytes())["schema_version"] == 12
    assert 11 in core.task_state_capacity()["supported_schemas"] and core.task_state_capacity()["schema_version"] == 12
