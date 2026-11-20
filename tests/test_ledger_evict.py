"""Full eviction of settled ledger objects (schema 11): long tasks never fill the hot ledger."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from thaliris import authority, core

TREE = "git:" + "a" * 40
ROLES = ("implementer", "investigator", "reviewer")
FIXTURE = Path(__file__).parent / "fixtures" / "ledger-schema10"


def filler(length: int, seed: int) -> str:
    words = f"group {seed} evidence about the ledger behaviour under load and its stable invariants "
    return (words * (length // len(words) + 1))[:length]


def repo(path: Path, goal: str = "evict") -> Path:
    root = path / "project"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    core.task_start(root, goal, None, None)
    return root


def write_json(root: Path, name: str, value: object) -> str:
    path = root.parent / f"{name}.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def segments(root: Path, task_id: str) -> list[Path]:
    directory = core._state_path(root).parent / "archive"
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def evicted_ids(state: dict) -> set[str]:
    return core._indexed_ids(state)


def run_result(declaration: dict, number: int, *, outcome: str | None = None) -> dict:
    outcome = outcome or ("FAIL" if number % 5 == 0 else "PASS")
    return {"check_id": declaration["id"], "command_sha256": declaration["command_sha256"], "outcome": outcome,
            "exit_code": 0 if outcome == "PASS" else 1, "duration_ms": 12, "output_tail": filler(1500, number),
            "output_bytes": 1500, "tree_identity_before": TREE, "tree_identity": TREE,
            "files_digest": declaration["files_digest"], "files_changed_during_run": False,
            "observed_files": [{"path": f"src/f{k}.py", "state": "FILE", "identity": "b" * 64, "mode": 420,
                                "git_status": "OBSERVED"} for k in range(6)]}


# --- long-task stress -----------------------------------------------------------------------------

def test_long_task_keeps_every_write_below_the_cap(tmp_path, monkeypatch):
    """3000 requirements, 3000 handoffs with usage and claims, 10000 observations and judgments, 2000 check runs."""
    monkeypatch.setattr(core, "tree_identity", lambda root: TREE)
    root = repo(tmp_path, "stress")
    sizes: list[int] = []
    durations: list[float] = []

    def write(operation, *args, **kwargs):
        started = time.perf_counter()
        result = operation(*args, **kwargs)
        durations.append(time.perf_counter() - started)
        sizes.append(core._state_path(root).stat().st_size)
        assert sizes[-1] <= core.STATE_MAX_BYTES
        return result

    def transaction(body):
        with core._lock(root):
            state = core._load_state(root, active=True)
            body(state)
            core._write_state(root, state)

    candidate = lambda i: f"C{i // 150}"   # 20 candidates
    producer = lambda i: ROLES[i % 3]
    runs = 0
    for rnd in range(100):
        requirements = range(30 * rnd, 30 * rnd + 30)
        write(core.task_evidence_register, root, "controller", core._load_state(root)["revision"], write_json(root, "reg", {
            "requirements": [{"id": f"R{i}", "workchain_ref": f"w{i % 7}", **({"kind": "compiled"} if i < 20 else {})}
                             for i in requirements],
            "handoffs": [{"id": f"H{i}", "parent_handoff_id": None, "candidate": candidate(i), "producer": producer(i),
                          "requirement_refs": [f"R{i}"]} for i in requirements]}))
        if rnd == 0:
            write(core.task_check, root, "controller", core._load_state(root)["revision"], {"checks": [
                {"id": f"K{k}", "requirement_refs": [f"R{k}"], "command": [sys.executable, "-c", "pass"]} for k in range(16)]})
            write(core.task_check, root, "controller", core._load_state(root)["revision"], {"checks": [
                {"id": f"K{k}", "requirement_refs": [f"R{k}"], "command": [sys.executable, "-c", "pass"]} for k in range(16, 20)]})

        def usage_and_claims(state, requirements=requirements):
            for i in requirements:
                core.set_handoff_usage(state, f"H{i}", {"model": f"m-{i % 5}", "input_tokens": 1000 + i, "output_tokens": 200,
                                                       "cost_usd": 0.013 * (i % 9), "duration_ms": 3000, "tool_uses": 4,
                                                       "outcome": "completed"})
                block = "```thaliris-claims\n" + json.dumps({"claims": [
                    {"requirement": f"R{i}", "polarity": "supports", "text": "ok", "evidence": f"src/m{i}.py:1", "basis": "read"}]}) + "\n```\n"
                core.ingest_claims(state, f"H{i}", block if i % 15 else "no claims here")

        write(transaction, usage_and_claims)
        observations = []
        for k in range(100):
            i, n = requirements[k % 30], 100 * rnd + k
            observations.append((producer(i), {
                "id": f"O{n}", "candidate": candidate(i), "handoff_id": f"H{i}", "requirement_refs": [f"R{i}"],
                "source_refs": [f"O{n}.s"], "text": filler(400 + (n % 5) * 100, n),
                "sources": [{"id": f"O{n}.s", "kind": "file", "locator": f"src/m{i}.py:{n}", "summary": filler(200, n)}]}))
        for role in ROLES:
            batch = [value for actor, value in observations if actor == role]
            for start in range(0, len(batch), core.CONTINUITY_BATCH_MAX):
                write(core.task_observe, root, role, {"observations": batch[start:start + core.CONTINUITY_BATCH_MAX]})

        def check_runs(state):
            nonlocal runs
            for k in range(20):
                runs += 1
                core.record_check_run(root, state, "implementer", run_result(core._declared_check(state, f"K{k}"), runs + rnd))

        write(transaction, check_runs)
        judgments, last = [], {}
        for k in range(100):
            i, n = requirements[k % 30], 100 * rnd + k
            judgment = {"id": f"J{n}", "candidate": candidate(i), "requirement_ref": f"R{i}", "observation_refs": [f"O{n}"],
                        "outcome": "repair" if (k < 30 and i % 4 == 0) else "satisfied", "reasoning": filler(300 + (n % 3) * 150, n)}
            if f"R{i}" in last:
                judgment["judgment_refs"] = [last[f"R{i}"]]
            if i < 20:
                judgment["override_reason"] = "checks are tracked separately"
            last[f"R{i}"] = judgment["id"]
            judgments.append(judgment)
        for start in range(0, 100, 50):
            write(core.task_judge, root, "controller", core._load_state(root)["revision"],
                  write_json(root, "judge", {"judgments": judgments[start:start + 50]}))

    state = core._load_state(root)
    task_id = state["task_id"]
    counts = core.task_status(root, view="compact")["Counts"]
    assert counts["requirements"] == 3000 and counts["handoffs"] == 3000
    assert counts["observations"] == 10000 and counts["judgments"] == 10000
    # 2000 check runs were recorded; Core keeps the last CHECK_RESULT_HISTORY per check (hot or evicted).
    assert runs == 2000 and counts["verification_observations"] == 20 * core.CHECK_RESULT_HISTORY
    assert max(sizes) <= core.STATE_MAX_BYTES
    final = core._state_path(root).stat().st_size
    evidence = core.evidence_summary(state)
    assert evidence["unincorporated_total"] == 0 and evidence["latest_judgments_total"] == 3000
    usage = core.usage_summary(state)
    assert usage["totals"]["handoffs"] == 3000 and usage["totals"]["input_tokens"] == sum(1000 + i for i in range(3000))
    claims = core._claims_section(state)
    assert claims["handoffs_ingested"] == 3000 and claims["handoffs_without_typed_claims"]["missing"] == 200
    assert core.surfaced_requirements(state)["surfaced_total"] == 2980
    # Segment collection keeps the archive bounded: every referenced segment is on disk, and what is
    # not referenced is at most the last compaction's grace generation plus segments written since.
    on_disk = {path.stem: path.stat().st_size for path in segments(root, task_id)}
    referenced = core._segment_refs(state)
    assert referenced <= on_disk.keys()
    unreferenced = sum(size for sha, size in on_disk.items() if sha not in referenced)
    assert unreferenced <= 2 * core.ARCHIVE_COMPACT_MAX_BYTES, unreferenced
    print(f"\nstress: archive {sum(on_disk.values())} B on disk, {unreferenced} B unreferenced, {len(on_disk)} files")
    print(f"\nstress: final hot {final} B, max hot {max(sizes)} B, segments {len(segments(root, task_id))}, "
          f"index entries {len(state['archive'])}, writes {len(durations)}, "
          f"mean write {1000 * sum(durations) / len(durations):.0f} ms, max write {1000 * max(durations):.0f} ms")
    # Speed: ordinary writes on the large ledger complete well under a second each.
    started = time.perf_counter()
    for k in range(10):
        core.task_observe(root, "reviewer", {"id": f"late{k}", "candidate": "C19", "handoff_id": "H2999", "requirement_refs": ["R2999"],
                                             "source_refs": ["O9999.s"], "text": "a late check result"})
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "late", {"judgments": [
        {"id": f"Jlate{k}", "candidate": "C19", "requirement_ref": "R2999", "observation_refs": [f"late{k}"], "outcome": "satisfied",
         "reasoning": "incorporated"} for k in range(10)]}))
    elapsed = (time.perf_counter() - started) / 11
    assert elapsed < 1.0, elapsed
    assert sum(durations) / len(durations) < 1.0
    # Every evicted object is still retrievable.
    assert core.task_get(root, "O17")["object"]["text"] == filler(400 + (17 % 5) * 100, 17)
    assert core.task_get(root, "J42")["object"]["reasoning"] == filler(300 + (42 % 3) * 150, 42)
    assert core.task_get(root, "H5")["object"]["usage"]["model"] == "m-0"


# --- equivalence before and after eviction ----------------------------------------------------------

def build_ledger(root: Path, monkeypatch) -> None:
    """A real-shaped ledger touching every hot reader: open evidence, overrides, claims, tamper, records, runs."""
    monkeypatch.setattr(core, "tree_identity", lambda root: TREE)
    (root / "src").mkdir()
    (root / "src" / "check.py").write_text("print('ok')\n", encoding="utf-8")
    for start in range(0, 60, 20):
        core.task_evidence_register(root, "controller", core._load_state(root)["revision"], write_json(root, "reg", {
            "requirements": [{"id": f"R{i}", "workchain_ref": f"w{i}", **({"kind": "compiled"} if i in (2, 4) else {}),
                              **({"kind": "partial"} if i % 11 == 5 else {})} for i in range(start, start + 20)],
            "handoffs": [{"id": f"H{i}", "parent_handoff_id": None, "candidate": f"C{1 + i // 30}", "producer": ROLES[i % 3],
                          "requirement_refs": [f"R{i}"]} for i in range(start, start + 20)]}))
    core.task_evidence_register(root, "controller", core._load_state(root)["revision"], write_json(root, "child", {
        "handoffs": [{"id": "H7.child", "parent_handoff_id": "H7", "candidate": "C1", "producer": "investigator", "requirement_refs": ["R7"]}]}))
    core.task_check(root, "controller", core._load_state(root)["revision"], {"checks": [
        {"id": "K1", "requirement_refs": ["R2"], "command": [sys.executable, "-c", "pass"], "files": ["src/check.py"]},
        {"id": "K2", "requirement_refs": ["R4"], "command": [sys.executable, "-c", "pass"]}]})
    with core._lock(root):
        state = core._load_state(root, active=True)
        for i in range(60):
            core.set_handoff_usage(state, f"H{i}", {"model": None if i % 13 == 0 else f"m-{i % 4}", "input_tokens": 100 + i,
                                                   "output_tokens": None if i % 7 == 0 else 20, "total_tokens": 500 if i % 9 == 0 else None,
                                                   "cost_usd": (i % 5) if i % 2 else 0.1 * (i % 3), "duration_ms": 1000,
                                                   "tool_uses": None if i % 4 == 0 else 3,
                                                   "outcome": ("completed", "failed", None)[i % 3]})
            claims = [{"requirement": f"R{i}", "polarity": "supports", "text": "ok", "evidence": f"src/m{i}.py:1", "basis": "read"}]
            if i % 10 == 3:
                claims += [{"requirement": f"R{i}", "polarity": "supports", "text": "more", "evidence": f"src/x{n}.py:1", "basis": "read"}
                           for n in range(6)]
            block = "```thaliris-claims\n" + json.dumps({"claims": claims}) + "\n```\n"
            core.ingest_claims(state, f"H{i}", block if i % 6 else ("no block" if i % 12 else "```thaliris-claims\n{bad\n```\n"))
        core._write_state(root, state)
    for producer in ROLES:
        core.task_observe(root, producer, {"observations": [{
            "id": f"O{i}", "candidate": f"C{1 + i // 30}", "handoff_id": f"H{i}", "requirement_refs": [f"R{i}"], "source_refs": [f"O{i}.s"],
            "text": filler(700, i), "sources": [{"id": f"O{i}.s", "kind": "file", "locator": f"src/m{i}.py:{i}", "summary": filler(250, i)}]}
            for i in range(60) if ROLES[i % 3] == producer]})
    core.task_observe(root, "investigator", {"id": "O7.child", "candidate": "C1", "handoff_id": "H7.child", "requirement_refs": ["R7"],
                                             "source_refs": ["O7.s"], "text": filler(300, 77)})
    with core._lock(root):
        state = core._load_state(root, active=True)
        for number in range(1, 7):
            core.record_check_run(root, state, "implementer", run_result(core._declared_check(state, "K1"), number,
                                                                          outcome="FAIL" if number == 6 else "PASS"))
        core._write_state(root, state)
    for number in range(4):
        core.task_record_verification(root, core._load_state(root)["revision"], f"V{number}", "lint", "PASSED", filler(200, number),
                                      observed_by="implementer")
    judgments = []
    for i in range(60):
        judgment = {"id": f"J{i}", "candidate": f"C{1 + i // 30}", "requirement_ref": f"R{i}", "observation_refs": [f"O{i}"],
                    "outcome": "repair" if i % 8 == 1 else "satisfied", "reasoning": filler(500, i)}
        if i in (2, 4):
            judgment["override_reason"] = f"accepted for now {i}"
        judgments.append(judgment)
    judgments += [{"id": f"J{i}b", "candidate": f"C{1 + i // 30}", "requirement_ref": f"R{i}", "observation_refs": [f"O{i}"],
                   "judgment_refs": [f"J{i}"], "outcome": "satisfied", "reasoning": filler(200, i),
                   **({"override_reason": f"override {i}"} if i in (2, 4) else {})}
                  for i in range(1, 60, 8)]
    judgments.append({"id": "J7.child", "candidate": "C1", "requirement_ref": "R7", "observation_refs": ["O7.child"],
                      "outcome": "satisfied", "reasoning": "child result incorporated"})
    for start in range(0, len(judgments), 32):
        core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "judge", {"judgments": judgments[start:start + 32]}))
    # Ten more overrides on the gated requirements, so the listing shows only the last 8.
    for number in range(10):
        core.task_observe(root, "investigator", {"id": f"Ov{number}", "candidate": "C1", "handoff_id": "H4", "requirement_refs": ["R4"],
                                                "source_refs": ["O4.s"], "text": filler(200, number)})
        core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "ov", {
            "id": f"Jov{number}", "candidate": "C1", "requirement_ref": "R4", "observation_refs": [f"Ov{number}"], "outcome": "satisfied",
            "reasoning": "gate overridden", "override_reason": f"reason {number} " + filler(200, number)}))
    # Tamper with a check file, record the mechanical observation and judge it.
    (root / "src" / "check.py").write_text("print('changed')\n", encoding="utf-8")
    recorded = core.task_status(root, record_tamper=True)["Verification"]["tamper_recorded_now"]
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "tj", {
        "id": "Jtamper", "candidate": "C1", "requirement_ref": "R2", "observation_refs": recorded, "outcome": "unknown",
        "reasoning": "tamper noted"}))
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "tj2", {
        "id": "Jtamper2", "candidate": "C1", "requirement_ref": "R2", "observation_refs": recorded, "judgment_refs": ["Jtamper"],
        "outcome": "satisfied", "reasoning": "tamper accepted", "override_reason": "accepted tamper"}))
    # Records: an old superseded record and its current replacement.
    core.task_update(root, "controller", core._load_state(root)["revision"], write_json(root, "rec", {"records": [
        {"id": "old", "kind": "note", "text": filler(2000, 1), "source_refs": ["O9.s"]}]}))
    core.task_update(root, "controller", core._load_state(root)["revision"], write_json(root, "rec2", {"records": [
        {"id": "new", "kind": "note", "text": "short", "supersedes": ["old"]}]}))
    # Open evidence that must stay hot: an unincorporated observation and an unresolved repair.
    core.task_observe(root, "reviewer", {"id": "open", "candidate": "C1", "handoff_id": "H5", "requirement_refs": ["R5"],
                                         "source_refs": ["O5.s"], "text": filler(600, 98)})
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "rep", {
        "id": "repair", "candidate": "C2", "requirement_ref": "R40", "observation_refs": ["O40"], "outcome": "repair", "reasoning": "fix it"}))
    # Push the tail of every continuity list past CHANGES_SINCE_RECENT_MAX so early objects can be evicted.
    for number in range(20):
        core.task_observe(root, "investigator", {"id": f"T{number}", "candidate": "C1", "handoff_id": "H1", "requirement_refs": ["R1"],
                                                "source_refs": ["O1.s"], "text": filler(150, number)})
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "tail", {"judgments": [
        {"id": f"JT{number}", "candidate": "C1", "requirement_ref": "R1", "observation_refs": [f"T{number}"], "outcome": "satisfied",
         "reasoning": "tail"} for number in range(20)]}))
    core.task_evidence_register(root, "controller", core._load_state(root)["revision"], write_json(root, "tailh", {
        "handoffs": [{"id": f"HT{number}", "parent_handoff_id": None, "candidate": "C2", "producer": "reviewer", "requirement_refs": ["R50"]}
                     for number in range(20)]}))
    for number in range(20):
        core.task_handoff_usage(root, f"HT{number}", {"model": "m-tail", "input_tokens": 1, "outcome": "completed"})


def views(root: Path) -> dict:
    state = core._load_state(root)
    revision = state["revision"]
    result: dict[str, object] = {
        "evidence_summary": core.evidence_summary(state),
        "evidence_pages": [core.evidence_summary(state, offset, max_bytes=256) for offset in range(0, 4)],
        "continuity_status": [core._continuity_status(state, offset) for offset in range(0, 90, 9)],
        "continuity_open": core._continuity_open(state),
        "usage": core.usage_summary(state),
        "claims": core._claims_section(state),
        "surfaced": core.surfaced_requirements(state),
        "verification": core.verification_view(root, state),
        "verification_section": core._verification_section(state, core.verification_view(root, state), True),
        "latest": core._latest_requirement_judgments(state),
        "ids": sorted(core._task_object_ids(state)),
        "compact_counts": core.task_status(root, view="compact")["Counts"],
        "full_counts": core.task_status(root)["Counts"],
        "changes_since": [core.changes_since(state, revision - gap) for gap in range(0, core.CHANGES_SINCE_RECENT_MAX + 1)],
        "tamper_owed": core._mechanical_tamper(state, core.verification_view(root, state)),
        "advisories": core.lane_advisories(None, state, {"execution_mode": "adaptive"}),
    }
    for operation in ("close", "judge"):
        attempt = copy.deepcopy(state)
        try:
            if operation == "close":
                outcome = core.close_state(root, attempt)
            else:
                outcome = core._append_judgments(attempt, "controller", [
                    {"id": "gated", "candidate": "C1", "requirement_ref": "R2", "observation_refs": ["O2"], "outcome": "satisfied", "reasoning": "r"},
                    {"id": "free", "candidate": "C1", "requirement_ref": "R9", "observation_refs": ["O9"], "outcome": "satisfied", "reasoning": "r"}],
                    root)
        except core.ThalirisError as exc:
            outcome = {"code": exc.code, "details": exc.details}
        result[operation] = outcome
    attempt = copy.deepcopy(state)
    override = core.close_state(root, attempt, override_reason="close anyway")
    result["close_override"] = {key: value for key, value in override.items() if key != "changed"}
    # Dedupes: a support already counted on an (evicted) handoff of the same candidate, an adverse claim
    # equal to a still-open one, and a fresh one.
    attempt = copy.deepcopy(state)
    core._append_continuity_items(attempt, [("handoffs", None, {"id": "Hdup", "parent_handoff_id": None, "candidate": "C1",
                                                                  "producer": "reviewer", "requirement_refs": ["R3", "R5"]})])
    ingested = core.ingest_claims(attempt, "Hdup", "```thaliris-claims\n" + json.dumps({"claims": [
        {"requirement": "R3", "polarity": "supports", "text": "again", "evidence": "src/m3.py:1", "basis": "read"},
        {"requirement": "R3", "polarity": "supports", "text": "again", "evidence": "src/x2.py:1", "basis": "read"},
        {"requirement": "R5", "polarity": "supports", "text": "new", "evidence": "src/new.py:1", "basis": "read"}]}) + "\n```\n")
    result["ingest"] = {key: ingested[key] for key in ("duplicates", "supports", "observations", "unassigned")}
    result["claims_after_ingest"] = core._claims_section(attempt)
    return result


def comparable(value: dict) -> dict:
    return json.loads(json.dumps(value, sort_keys=True))


def twin_ledgers(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """The same ledger twice: ``plain`` never evicts, ``evicting`` evicts on every write."""
    plain = repo(tmp_path / "plain")
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", core.STATE_MAX_BYTES)
    build_ledger(plain, monkeypatch)
    evicting = tmp_path / "evicting" / "project"
    shutil.copytree(plain, evicting)
    core.select_task(evicting, core._load_state(plain)["task_id"])
    return plain, evicting


def evict_now(root: Path, monkeypatch) -> dict:
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    with core._lock(root):
        state = core._load_state(root, active=True)
        core._write_state(root, state)
    return core._load_state(root)


def same_operations(root: Path, monkeypatch) -> list[dict]:
    """Writes that need evicted objects back (late usage, late claims, a new child, re-cited sources and
    judgments) or drop evicted check runs; returns the views after each."""
    seen = []
    core.task_handoff_usage(root, "H9", {"model": "m-late", "cost_usd": 1.5, "outcome": "completed"})
    seen.append(views(root))
    core.task_observe(root, "investigator", {"id": "O10.late", "candidate": "C1", "handoff_id": "H10", "requirement_refs": ["R10"],
                                             "source_refs": ["O11.s"], "text": "a late result for an evicted handoff"})
    core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "late", {
        "id": "J10.late", "candidate": "C1", "requirement_ref": "R10", "observation_refs": ["O10.late", "O10"], "judgment_refs": ["J10"],
        "outcome": "satisfied", "reasoning": "late incorporation"}))
    seen.append(views(root))
    core.task_evidence_register(root, "controller", core._load_state(root)["revision"], write_json(root, "child2", {
        "handoffs": [{"id": "H8.child", "parent_handoff_id": "H8", "candidate": "C1", "producer": "implementer", "requirement_refs": ["R8"]}]}))
    core.task_ingest_claims(root, "H8.child", "```thaliris-claims\n" + json.dumps({"claims": [
        {"requirement": "R8", "polarity": "supports", "text": "dup", "evidence": "src/m8.py:1", "basis": "read"}]}) + "\n```\n")
    core.task_update(root, "controller", core._load_state(root)["revision"], write_json(root, "cite", {"records": [
        {"id": "cites-old-source", "kind": "note", "text": "re-cites an evicted source", "source_refs": ["O12.s"]}]}))
    seen.append(views(root))
    with core._lock(root):
        state = core._load_state(root, active=True)
        for number in range(7, 10):
            core.record_check_run(root, state, "implementer", run_result(core._declared_check(state, "K1"), number))
        core._write_state(root, state)
    seen.append(views(root))
    return seen


def test_gates_status_and_dedupes_are_identical_with_and_without_eviction(tmp_path, monkeypatch):
    plain, evicting = twin_ledgers(tmp_path, monkeypatch)
    before = comparable(views(plain))
    assert before["close"]["code"] == "VERIFICATION_WITHHELD" and before["judge"]["code"] == "VERIFICATION_WITHHELD"
    assert before["evidence_summary"]["unincorporated_total"] == 1 and before["evidence_summary"]["unresolved_judgments_total"] == 1
    assert before["verification_section"]["overrides"]["total"] > 8 and before["claims"]["handoffs_without_typed_claims"]["malformed"]
    assert before["ingest"]["duplicates"] == 2 and before["tamper_owed"] == []
    state = evict_now(evicting, monkeypatch)
    evicted = evicted_ids(state)
    assert {"O3", "J3", "O3.s", "H4", "H9", "old", "K1.r3", "V0"} <= evicted
    assert {"open", "repair", "O40", "O5.s", "new", "K1.r6", "V3", "H3", "H54"}.isdisjoint(evicted), "open evidence and listed objects stay hot"
    assert not any("archived" in item for _, item in core._archived_items(state))
    after = comparable(views(evicting))
    for key in before:
        assert after[key] == before[key], key
    # The same later writes keep the two ledgers answering identically, while the evicting one keeps evicting.
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", core.STATE_MAX_BYTES)
    plain_seen = [comparable(item) for item in same_operations(plain, monkeypatch)]
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    evicting_seen = [comparable(item) for item in same_operations(evicting, monkeypatch)]
    for step, (left, right) in enumerate(zip(plain_seen, evicting_seen)):
        for key in left:
            assert right[key] == left[key], (step, key)
    final = core._load_state(evicting)
    assert final["archive"] and len(core._load_state(plain)["evidence_continuity"]["observations"]) > len(final["evidence_continuity"]["observations"])
    # The handoff that received late usage and the re-cited source came back to their exact hot positions.
    assert core.task_get(evicting, "H9")["object"]["usage"]["model"] == "m-late"
    assert core.task_get(evicting, "O12.s")["object"] == core.task_get(plain, "O12.s")["object"]


# --- retrieval and damaged segments -------------------------------------------------------------------

def test_task_get_returns_every_evicted_object_in_full(tmp_path, monkeypatch):
    plain, evicting = twin_ledgers(tmp_path, monkeypatch)
    state = evict_now(evicting, monkeypatch)
    evicted = evicted_ids(state)
    assert len(evicted) > 200
    for identifier in sorted(evicted):
        got = core.task_get(evicting, identifier)
        expected = core.task_get(plain, identifier)
        assert got["object"] == expected["object"] and got["object_type"] == expected["object_type"], identifier
        assert got["archived"]["evicted"] is True and got["archived"]["segment"] in {entry["sha256"] for entry in state["archive"]}


@pytest.mark.parametrize("damage", ["tamper", "delete", "foreign"])
def test_a_damaged_segment_is_reported_while_gates_and_writes_keep_working(tmp_path, monkeypatch, damage):
    plain, evicting = twin_ledgers(tmp_path, monkeypatch)
    state = evict_now(evicting, monkeypatch)
    segment = segments(evicting, state["task_id"])[0]
    if damage == "tamper":
        segment.write_bytes(segment.read_bytes().replace(b"group 3 ", b"group X "))
    elif damage == "delete":
        segment.unlink()
    else:
        raw = json.loads(segment.read_bytes())
        raw["task_id"] = "00000000-0000-4000-8000-000000000000"
        segment.write_bytes(json.dumps(raw).encode())
    with pytest.raises(core.ThalirisError) as caught:
        core.task_get(evicting, "O3")
    assert caught.value.code == "TASK_ARCHIVE_UNAVAILABLE" and caught.value.details["object_type"] == "observations"
    assert caught.value.details["segment"] == segment.stem and "restore" in caught.value.recovery
    # Status and gates read only the hot ledger and the index.
    assert comparable(core.task_status(evicting, view="compact")["Evidence"]) == comparable(core.task_status(plain, view="compact")["Evidence"])
    assert core.close_state(evicting, copy.deepcopy(core._load_state(evicting)), override_reason="x")["surfaced_total"] > 0
    # A write that needs the unreadable object fails cleanly; every other write works.
    before = core._state_path(evicting).read_bytes()
    with pytest.raises(core.ThalirisError) as caught:
        core.task_handoff_usage(evicting, "H9", {"model": "m-9"})
    assert caught.value.code == "TASK_ARCHIVE_UNAVAILABLE" and core._state_path(evicting).read_bytes() == before
    core.task_observe(evicting, "reviewer", {"id": "still", "candidate": "C1", "handoff_id": "H5", "requirement_refs": ["R5"],
                                             "source_refs": ["O5.s"], "text": "still writable"})
    core.task_update(evicting, "controller", core._load_state(evicting)["revision"], write_json(evicting, "u", {"records": [
        {"id": "cites-evicted", "kind": "note", "text": "a source in the damaged segment stays evicted", "source_refs": ["O3.s"]}]}))
    assert "O3.s" in evicted_ids(core._load_state(evicting))
    core.task_evidence_register(evicting, "controller", core._load_state(evicting)["revision"], write_json(evicting, "r", {
        "requirements": [{"id": "Rnew", "workchain_ref": "w"}]}))
    assert core.task_close(evicting, core._load_state(evicting)["revision"], override_reason="done")["status"] == "DONE"


# --- forgery -----------------------------------------------------------------------------------------

def forged(state: dict, change) -> dict:
    copy_ = copy.deepcopy(state)
    change(copy_)
    return copy_


def test_forged_index_ids_totals_and_latest_rows_are_refused(tmp_path, monkeypatch):
    _, evicting = twin_ledgers(tmp_path, monkeypatch)
    state = evict_now(evicting, monkeypatch)
    entry = next(index for index, item in enumerate(state["archive"]) if "ids" in item)

    def first_ids(item, name):
        return item["archive"][entry]["ids"][name]

    cases = {
        "hot id reserved twice": lambda s: first_ids(s, "observations").append("open"),
        "id in two entries": lambda s: s["archive"].append({**copy.deepcopy(s["archive"][entry]), "sha256": "e" * 64}),
        "position past the list": lambda s: first_ids(s, "judgments").extend([10 ** 6, "Jghost"]),
        "non-canonical run": lambda s: first_ids(s, "observations").append(["O1", 0, 3]),
        "unknown collection": lambda s: s["archive"][entry]["ids"].update({"artifact_refs": ["a1"]}),
        "count mismatch": lambda s: s["archive"][entry]["totals"]["counts"].update(observations=1),
        "usage beyond the evicted handoffs": lambda s: s["archive"][entry]["totals"]["usage"]["all"].__setitem__(0, 10 ** 6),
        "outcomes that do not add up": lambda s: s["archive"][entry]["totals"]["usage"]["outcomes"][0].__setitem__(1, 999),
        "overrides beyond the judgments": lambda s: s["archive"][entry]["totals"].update(overrides=10 ** 6),
        "tamper key for a hot observation": lambda s: s["archive"][entry]["totals"]["mechanism"][0].__setitem__(2, "open"),
        "support for an unknown requirement": lambda s: s["archive"][entry]["totals"]["supports"][1].append(["R-ghost", 2]),
        "latest row past the judgments": lambda s: s["settled"]["latest"][0][1][0].__setitem__(2, 10 ** 6),
        "latest row for an unknown requirement": lambda s: s["settled"]["latest"][0][1][0].__setitem__(0, "R-ghost"),
        "latest row with an invalid outcome": lambda s: s["settled"]["latest"][0][1][0].__setitem__(1, 9),
        "latest row first after last": lambda s: s["settled"]["latest"][0][1][0][2:].__len__() and s["settled"]["latest"][0][1][0].__setitem__(
            slice(2, None), [s["settled"]["latest"][0][1][0][2], s["settled"]["latest"][0][1][0][2] + 1]),
        "settled without eviction": lambda s: s.update(archive=[item for item in s["archive"] if "ids" not in item] or None),
        "eviction under schema 10": lambda s: s.update(schema_version=10),
    }
    for name, change in cases.items():
        bad = forged(state, change)
        if bad.get("archive") is None:
            bad.pop("archive")
        with pytest.raises((core.ThalirisError, ValueError)):
            core._validate_state(evicting, bad)
            pytest.fail(name)
    core._validate_state(evicting, copy.deepcopy(state))


def test_the_anchor_covers_the_index_and_segments_are_verified_on_read(tmp_path, monkeypatch):
    _, evicting = twin_ledgers(tmp_path, monkeypatch)
    store = authority.AuthorityStore(evicting, tmp_path / "external")
    store.establish(core.task_show(evicting)["state"], {"human_instruction": "x", "boundary": "y", "invariants": "z",
                                                        "acceptance": "w", "execution_mode": "delegated"})
    state = evict_now(evicting, monkeypatch)
    store.checkpoint()
    assert store.check() is not None
    # Rewriting an aggregate (still valid in shape) changes the state digest the anchor holds.
    raw = json.loads(core._state_path(evicting).read_bytes())
    entry = next(item for item in raw["archive"] if "ids" in item)
    entry["totals"]["usage"]["all"][2] += 1
    core._state_path(evicting).write_bytes(core._serialize_state(raw))
    with pytest.raises(ValueError, match="TASK_AUTHORITY_STATE_CHANGED"):
        store.check()
    # A segment byte change is caught by its digest on read.
    core._state_path(evicting).write_bytes(core._serialize_state(state))
    segment = segments(evicting, state["task_id"])[0]
    segment.write_bytes(segment.read_bytes().replace(b'"O', b'"Q', 1))
    with pytest.raises(core.ThalirisError, match="unavailable") as caught:
        core.task_get(evicting, "O0")
    assert caught.value.details["reason"] == "sha256 mismatch"


# --- pressure policy -----------------------------------------------------------------------------------

def test_only_open_evidence_can_fill_the_hot_ledger(tmp_path):
    root = repo(tmp_path)
    core.task_evidence_register(root, "controller", 1, write_json(root, "reg", {
        "requirements": [{"id": "R0", "workchain_ref": "w"}],
        "handoffs": [{"id": "H0", "parent_handoff_id": None, "candidate": "C1", "producer": "implementer", "requirement_refs": ["R0"]}]}))
    # Settled history never fills it: 600 judged observations of 1.5 KB each are far above the cap.
    for start in range(0, 600, 60):
        core.task_observe(root, "implementer", {"observations": [{
            "id": f"O{i}", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R0"], "source_refs": [f"O{i}.s"],
            "text": filler(1500, i), "sources": [{"id": f"O{i}.s", "kind": "file", "locator": "x", "summary": "s"}]} for i in range(start, start + 60)]})
        core.task_judge(root, "controller", core._load_state(root)["revision"], write_json(root, "j", {"judgments": [{
            "id": f"J{i}", "candidate": "C1", "requirement_ref": "R0", "observation_refs": [f"O{i}"], "outcome": "satisfied",
            "reasoning": filler(400, i)} for i in range(start, start + 60)]}))
    assert core._state_path(root).stat().st_size < core.STATE_ARCHIVE_HIGH_WATER_BYTES
    # Open evidence does: unjudged observations stay hot, and the refusal says why and what to do.
    with pytest.raises(core.ThalirisError) as caught:
        for start in range(0, 600, 30):
            core.task_observe(root, "implementer", {"observations": [{
                "id": f"open{i}", "candidate": "C1", "handoff_id": "H0", "requirement_refs": ["R0"], "source_refs": ["O0.s"],
                "text": filler(15000, i)} for i in range(start, start + 30)]})
    assert caught.value.code == "TASK_STATE_CAPACITY_EXCEEDED" and caught.value.details["field"] == "state_file"
    assert caught.value.details["open_observation_edges"] > 0 and "open evidence" in caught.value.recovery
    assert "judge the open observations" in caught.value.recovery


# --- compatibility ---------------------------------------------------------------------------------------

def install_fixture(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    core.init(root)
    task_dir = next(path for path in FIXTURE.iterdir() if path.is_dir())
    target = root / ".context" / "tasks" / task_dir.name
    shutil.copytree(task_dir, target)
    core.select_task(root, task_dir.name)
    return root, task_dir.name


def fixture_views(state: dict) -> dict:
    return comparable({"evidence_summary": core.evidence_summary(state),
                       "continuity_status": [core._continuity_status(state, offset) for offset in range(0, 60, 7)],
                       "usage": core.usage_summary(state), "claims": core._claims_section(state),
                       "surfaced": core.surfaced_requirements(state),
                       "changes_since": {key: value for key, value in core.changes_since(state, state["revision"] - 3).items()
                                         if key not in ("base_revision", "current_revision")},
                       "ids": sorted(core._task_object_ids(state))})


def test_a_schema_10_ledger_from_3ed67e1_loads_answers_the_same_and_is_evicted_further(tmp_path, monkeypatch):
    root, task_id = install_fixture(tmp_path)
    expected = json.loads((FIXTURE / "views-3ed67e1.json").read_text(encoding="utf-8"))
    for field in ("base_revision", "current_revision"):
        expected["changes_since"].pop(field)
    raw = core._state_path(root).read_bytes()
    state = core._load_state(root)
    assert json.loads(raw)["schema_version"] == 10 and state["schema_version"] == core._STATE_SCHEMA_VERSION == 12
    assert sum(1 for _ in core._archived_items(state)) == 126 and core._state_path(root).read_bytes() == raw
    assert fixture_views(state) == expected
    stub_ids = {item["id"] for _, item in core._archived_items(state)}
    full_before = {identifier: core.task_get(root, identifier)["object"] for identifier in sorted(stub_ids)}
    monkeypatch.setattr(core, "STATE_ARCHIVE_HIGH_WATER_BYTES", 0)
    monkeypatch.setattr(core, "STATE_ARCHIVE_MIN_SAVINGS_BYTES", 0)
    core.task_update(root, "controller", state["revision"], write_json(root, "u", {"pending_results": ["evict the stubs"]}))
    after = core._load_state(root)
    assert after["schema_version"] == 12 and json.loads(core._state_path(root).read_bytes())["schema_version"] == 12
    assert evicted_ids(after) & stub_ids and sum(1 for _ in core._archived_items(after)) < 126
    assert fixture_views(after) == expected
    # Retrieval follows the chain: eviction segment, then the schema-10 segment with the moved body.
    for identifier, full in full_before.items():
        assert core.task_get(root, identifier)["object"] == full, identifier
    assert core.task_get(root, "O4")["object"]["text"].startswith("group 4 evidence")
    # And the task keeps working: a late usage report brings back a schema-10 handoff stub.
    core.task_handoff_usage(root, "H2", {"model": "m-late"})
    assert core.task_get(root, "H2")["object"]["usage"]["model"] == "m-late"
    core.task_observe(root, "implementer", {"id": "after", "candidate": "C1", "handoff_id": "H31", "requirement_refs": ["R31"],
                                            "source_refs": ["O31.s"], "text": "a result after the upgrade"})
    assert core.evidence_summary(core._load_state(root))["unincorporated_total"] == 2


def test_schema_promotion_reaches_12_and_newer_schemas_are_refused(tmp_path):
    root = repo(tmp_path)
    state = core._load_state(root)
    assert core.task_state_capacity()["schema_version"] == 12 and 10 in core.task_state_capacity()["supported_schemas"]
    state["schema_version"] = 13
    core._state_path(root).write_bytes(core._serialize_state(state))
    with pytest.raises(core.TaskStateSchemaIncompatible) as caught:
        core._load_state(root)
    assert caught.value.diagnostic["upgrade_required"] is True


# --- encoding ----------------------------------------------------------------------------------------------

def test_id_runs_round_trip_and_stay_compact():
    pairs = [(f"J{n}", n) for n in range(900)] + [("H445cab76.c1", 950), ("H445cab76.c2", 951), ("odd-id", 952)]
    pairs += [(f"O{n}", 953 + k) for k, n in enumerate(range(900, 999, 3))]
    encoded = core._encode_ids(pairs, True)
    assert list(core._decode_ids(encoded, True)) == pairs
    assert core._encoded_ids_problem(encoded, True) == (None, len(pairs))
    assert len(json.dumps(encoded)) < 120, encoded
    unordered = [("O7.s", None), ("O5.s", None), ("O6.s", None), ("x", None)]
    encoded = core._encode_ids(unordered, False)
    assert sorted(core._decode_ids(encoded, False)) == sorted(unordered) and ["O", 5, 3, ".s"] in encoded
