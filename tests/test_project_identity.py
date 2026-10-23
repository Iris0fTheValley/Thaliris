"""Project Identity plane: mechanical recording, versioning, CAS and observation only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from thaliris import cli, core, identity

NS = ".project-identity"
TEXT_V1 = """# Example project identity

## ID-1 Identity
We build a reliable ledger.

## INV-1: Never lose recorded data
Recorded data survives every crash.

## INV-2 Explicit authority
Only the owner changes direction.

```markdown
## INV-9 fenced example is not an item
```

## NG-1 Non-goal: hosting
"""


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    core.init(tmp_path)
    return tmp_path


def started(root: Path) -> dict[str, object]:
    return core.task_start(root, "identity work", None, None)


def amend_input(base_version: int, base_sha256: str | None, text: str, **extra: object) -> dict[str, object]:
    return {
        "base_version": base_version,
        "base_sha256": base_sha256,
        "text": text,
        "summary": f"move to v{base_version + 1}",
        "rationale": "the owner decided",
        "decision": {"decided_by": "project owner", "human_instruction": "Please record this identity."},
        **extra,
    }


def establish(root: Path, revision: int, text: str = TEXT_V1) -> dict[str, object]:
    return identity.identity_amend(root, "controller:1", revision, amend_input(0, None, text))


def canonical(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def test_absent_identity_is_normal_and_existing_ops_are_unaffected(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    status = identity.identity_status(root)
    assert status["state"] == "ABSENT" and status["version"] is None and status["summary"] is None
    assert identity.identity_summary(root) is None
    assert not (root / NS).exists()
    packet = core.task_status(root)
    assert packet["schema_version"] == 7
    assert set(packet) == {"ok", "schema_version", "Task", "Active Work", "Pending Results", "Counts",
                           "Recent Artifact IDs", "Active Artifact Count", "Evidence Continuity"}
    with pytest.raises(ValueError, match="ABSENT"):
        identity.identity_get(root)
    core.task_close(root, task["revision"])
    core.init(root)
    assert not (root / NS).exists()


def test_legacy_memory_labels_confer_no_identity(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started(root)
    legacy = root / ".agent-memory" / "constitution.md"
    legacy.write_text("---\nEvidence: NONE\nRevision: 1\nKind: HARD_CONSTRAINT\nStatus: CURRENT\nApplicability: PROJECT\n---\n\n# INV-1 Never change\n", encoding="utf-8")
    assert identity.identity_status(root)["state"] == "ABSENT"
    assert identity.identity_summary(root) is None
    with pytest.raises(ValueError, match="no recorded project identity"):
        identity.identity_challenge(root, "c", 1, {"targets": ["identity:INV-1"], "summary": "s", "text": "t"})
    assert not (root / NS).exists()


def test_establish_and_amend_keep_history_diff_and_dependents(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    first = establish(root, task["revision"])
    assert first["version"] == 1 and first["amendment"] == "A-0001"
    assert first["items"] == {"added": ["ID-1", "INV-1", "INV-2", "NG-1"], "removed": [], "changed": []}
    assert first["written"][-1] == f"{NS}/ledger.json"
    status = identity.identity_status(root)
    assert status["state"] == "CURRENT" and status["version"] == 1 and status["format"] == identity.LEDGER_FORMAT
    assert [item["id"] for item in status["items"]] == ["ID-1", "INV-1", "INV-2", "NG-1"]
    assert status["summary"] == identity.identity_summary(root)
    assert status["summary"].startswith("Project identity v1 (A-0001, CURRENT); 0 open challenges.")
    (root / "docs").mkdir()
    (root / "docs/design.md").write_text("design\n", encoding="utf-8")
    related = identity.identity_relate(root, "c", task["revision"], {"add": [
        {"from": "path:docs/design.md", "rel": "serves", "to": "identity:INV-2"},
        {"from": "path:docs/design.md#ledger", "rel": "serves", "to": "identity:INV-1"},
        {"from": "commit:abcdef1", "rel": "serves", "to": "identity"},
        {"from": "url:https://example.com/x", "rel": "supports", "to": "path:docs/design.md"},
    ]})
    assert len(related["added"]) == 4
    v2 = TEXT_V1.replace("Only the owner changes direction.", "Only the human owner changes direction.").replace(
        "## INV-1: Never lose recorded data\nRecorded data survives every crash.\n\n", "") + "\n## P-1 Small steps\n"
    second = identity.identity_amend(root, "c", task["revision"], amend_input(1, status["on_disk_sha256"], v2,
                                     affected_refs=["identity:INV-1", "path:docs/design.md"], why_not_lower="it is a principle"))
    assert second["version"] == 2 and second["amendment"] == "A-0002"
    assert second["items"] == {"added": ["P-1"], "removed": ["INV-1"], "changed": ["INV-2"]}
    dependents = {item["to"]: item for item in second["registered_dependents"]}
    assert set(dependents) == {"identity", "identity:INV-1", "identity:INV-2"}
    assert dependents["identity:INV-1"]["to_state"] == "REMOVED"
    assert dependents["identity:INV-2"]["to_state"] == "CHANGED_SINCE_v1"
    assert dependents["identity"]["to_state"] == "CHANGED_SINCE_v1"
    assert "absence of a relation is not evidence of independence" in second["notice"]
    assert (root / NS / "versions/v0001.md").read_text(encoding="utf-8") == TEXT_V1
    assert (root / NS / "IDENTITY.md").read_text(encoding="utf-8") == v2
    old = identity.identity_get(root, version=1)
    assert old["text"] == TEXT_V1 and old["current_version"] == 2
    record = identity.identity_get(root, amendment="A-0002")["record"]
    assert record["from_version"] == 1 and record["why_not_lower"] == "it is a principle"
    assert record["decision"]["human_instruction"] == "Please record this identity."
    assert {ref["ref"]: ref.get("version") for ref in record["affected_refs"]}["identity:INV-1"] == 1
    items = identity.identity_get(root, items=["INV-2", "P-1"])
    assert [item["id"] for item in items["items"]] == ["INV-2", "P-1"]
    assert items["items"][0]["text"].startswith("## INV-2 Explicit authority\nOnly the human owner")
    with pytest.raises(ValueError, match="not found"):
        identity.identity_get(root, items=["INV-1"])
    assert identity.identity_get(root, version=1, items=["INV-1"])["items"][0]["title"] == "Never lose recorded data"


def test_cas_conflicts_and_identical_text_are_refused_without_writes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    establish(root, task["revision"])
    sha = identity.identity_status(root)["on_disk_sha256"]
    ledger = (root / NS / "ledger.json").read_bytes()
    with pytest.raises(ValueError, match="identity version conflict"):
        identity.identity_amend(root, "c", task["revision"], amend_input(0, sha, TEXT_V1 + "\nmore\n"))
    with pytest.raises(ValueError, match="base_sha256 conflict"):
        identity.identity_amend(root, "c", task["revision"], amend_input(1, None, TEXT_V1 + "\nmore\n"))
    with pytest.raises(ValueError, match="task revision conflict"):
        identity.identity_amend(root, "c", task["revision"] + 1, amend_input(1, sha, TEXT_V1 + "\nmore\n"))
    with pytest.raises(ValueError, match="identical"):
        identity.identity_amend(root, "c", task["revision"], amend_input(1, sha, TEXT_V1))
    assert (root / NS / "ledger.json").read_bytes() == ledger
    assert not (root / NS / "versions/v0002.md").exists()


def test_mutations_require_selected_active_task_and_do_not_bump_revision(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    state_path = core._state_path(root)
    before = state_path.read_bytes()
    establish(root, task["revision"])
    identity.identity_relate(root, "c", task["revision"], {"add": [{"from": "commit:abcdef1", "rel": "serves", "to": "identity"}]})
    assert state_path.read_bytes() == before
    assert core.task_status(root)["Task"]["revision"] == task["revision"]
    core.select_task(root, None)
    with pytest.raises(ValueError, match="explicit task selection"):
        identity.identity_relate(root, "c", task["revision"], {"add": [{"from": "commit:abcdef2", "rel": "serves", "to": "identity"}]})
    core.select_task(root, str(task["task_id"]))
    core.task_close(root, task["revision"])
    with pytest.raises(ValueError, match="not ACTIVE"):
        identity.identity_relate(root, "c", task["revision"] + 1, {"add": [{"from": "commit:abcdef2", "rel": "serves", "to": "identity"}]})


def test_hand_edit_is_observed_and_reads_serve_recorded_version(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    establish(root, task["revision"])
    baseline = root / NS / "IDENTITY.md"
    baseline.write_text(TEXT_V1 + "\n## INV-3 Sneaky\n", encoding="utf-8")
    status = identity.identity_status(root)
    assert status["state"] == "UNRECORDED_CHANGE"
    assert status["on_disk_sha256"] != status["recorded_sha256"]
    assert "differs" in status["summary"]
    got = identity.identity_get(root)
    assert got["text"] == TEXT_V1 and got["on_disk_divergent"] is True and "notice" in got
    assert baseline.read_text(encoding="utf-8").endswith("Sneaky\n")
    # The amendment must name the hand-edited bytes it replaces.
    with pytest.raises(ValueError, match="base_sha256 conflict"):
        identity.identity_amend(root, "c", task["revision"], amend_input(1, status["recorded_sha256"], TEXT_V1 + "\nx\n"))
    adopted = identity.identity_amend(root, "c", task["revision"], amend_input(1, status["on_disk_sha256"], baseline.read_text(encoding="utf-8")))
    assert adopted["items"]["added"] == ["INV-3"]
    backup = json.loads((root / ".context/backups" / f"{adopted['backup']}.json").read_text(encoding="utf-8"))
    assert backup["action"] == "identity-amend"
    assert any(change["path"] == f"{NS}/IDENTITY.md" and change["old"] for change in backup["changes"])
    baseline.unlink()
    missing = identity.identity_status(root)
    assert missing["state"] == "UNRECORDED_CHANGE" and missing["on_disk_sha256"] is None


def test_crlf_and_bom_bytes_hash_canonically_without_divergence(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    crlf = TEXT_V1.replace("\n", "\r\n")
    result = establish(root, task["revision"], crlf)
    assert result["sha256"] == canonical(TEXT_V1)
    assert (root / NS / "IDENTITY.md").read_bytes() == TEXT_V1.encode()
    # Simulate Git autocrlf checkout of tracked files.
    for path in (root / NS).rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    (root / NS / "IDENTITY.md").write_bytes(b"\xef\xbb\xbf" + TEXT_V1.replace("\n", "\r\n").encode())
    status = identity.identity_status(root)
    assert status["state"] == "CURRENT"
    assert status["on_disk_sha256"] == canonical(TEXT_V1)
    assert identity.canonical_sha256(b"a\rb\r\nc\n") == identity.canonical_sha256(b"a\nb\nc\n")
    assert identity.identity_get(root)["text"] == TEXT_V1


def test_ledger_or_snapshot_inconsistency_is_invalid_and_mutations_refuse(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    establish(root, task["revision"])
    snapshot = root / NS / "versions/v0001.md"
    original = snapshot.read_bytes()
    snapshot.write_bytes(original + b"tampered\n")
    status = identity.identity_status(root)
    assert status["state"] == "INVALID" and "snapshot hash mismatch" in status["detail"][0]
    assert identity.identity_summary(root).startswith("Project identity INVALID")
    with pytest.raises(ValueError, match="INVALID"):
        identity.identity_get(root)
    with pytest.raises(ValueError, match="mutations refuse"):
        identity.identity_relate(root, "c", task["revision"], {"add": [{"from": "commit:abcdef1", "rel": "serves", "to": "identity"}]})
    snapshot.unlink()
    assert "missing snapshot" in identity.identity_status(root)["detail"][0]
    snapshot.write_bytes(original)
    assert identity.identity_status(root)["state"] == "CURRENT"
    ledger_path = root / NS / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["versions"].append(dict(ledger["versions"][0]))
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    assert identity.identity_status(root)["state"] == "INVALID"
    ledger_path.write_text("<<<<<<< ours\n{}\n=======\n{}\n>>>>>>> theirs\n", encoding="utf-8")
    assert "invalid JSON" in identity.identity_status(root)["detail"][0]


def test_unknown_ledger_format_is_reported_and_refused_for_writes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    establish(root, task["revision"])
    ledger_path = root / NS / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["format"] = "thaliris-project-identity-v9"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    status = identity.identity_status(root)
    assert status["state"] == "INVALID" and status["format"] == "thaliris-project-identity-v9"
    assert "unsupported ledger format" in status["detail"][0]
    with pytest.raises(ValueError, match="unsupported ledger format"):
        identity.identity_amend(root, "c", task["revision"], amend_input(1, status["on_disk_sha256"], TEXT_V1 + "\nx\n"))


def test_anchor_parsing_rejects_duplicates_and_ignores_fenced_code(tmp_path: Path) -> None:
    items = identity.parse_items(TEXT_V1)
    assert list(items) == ["ID-1", "INV-1", "INV-2", "NG-1"]
    assert "INV-9" not in items
    assert items["INV-2"].text.endswith("```markdown\n## INV-9 fenced example is not an item\n```")
    nested = identity.parse_items("## A-1 Parent\nx\n### B-1 Child\ny\n## A-2 Next\n#### INV-12345 not an anchor\n## inv-1 lower\n")
    assert list(nested) == ["A-1", "B-1", "A-2"]
    assert "### B-1 Child" in nested["A-1"].text and nested["B-1"].text == "### B-1 Child\ny"
    assert "INV-12345" in nested["A-2"].text
    with pytest.raises(ValueError, match="duplicate identity item anchor INV-1"):
        identity.parse_items("## INV-1 a\n## INV-1 b\n")
    root = repo(tmp_path)
    task = started(root)
    with pytest.raises(ValueError, match="duplicate"):
        establish(root, task["revision"], "## INV-1 a\n\n~~~\n## INV-1 fenced\n~~~\n## INV-1 b\n")
    assert not (root / NS).exists()
    assert establish(root, task["revision"], "## INV-1 a\n\n~~~\n## INV-1 fenced\n~~~\n")["items"]["added"] == ["INV-1"]


def test_challenge_open_dismiss_and_resolution_through_amendment(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    establish(root, task["revision"])
    (root / "evidence.txt").write_text("measured\n", encoding="utf-8")
    first = identity.identity_challenge(root, "c", task["revision"], {
        "targets": ["identity:INV-2"], "summary": "Owner rule blocks automation", "text": "evidence says...",
        "evidence_refs": ["path:evidence.txt", "commit:1234567"],
        "proposed_change": "allow delegated owners"})
    second = identity.identity_challenge(root, "c", task["revision"], {"targets": ["identity"], "summary": "Too broad", "text": "t"})
    status = identity.identity_status(root)
    assert status["open_challenges_total"] == 2
    assert status["open_challenges"][0]["targets"] == ["identity:INV-2"]
    assert "2 open challenges" in status["summary"]
    got = identity.identity_get(root, challenge=first["challenge"])
    assert got["status"] == "open" and got["challenge"]["targets"][0]["version"] == 1
    with pytest.raises(ValueError, match="not found"):
        identity.identity_challenge(root, "c", task["revision"], {"targets": ["identity:NOPE-1"], "summary": "s", "text": "t"})
    with pytest.raises(ValueError, match="identity or identity"):
        identity.identity_challenge(root, "c", task["revision"], {"targets": ["path:evidence.txt"], "summary": "s", "text": "t"})
    dismissed = identity.identity_challenge(root, "c", task["revision"], {"dismiss": second["challenge"], "reason": "lower-level repair suffices"})
    assert dismissed["status"] == "dismissed"
    with pytest.raises(ValueError, match="not open"):
        identity.identity_challenge(root, "c", task["revision"], {"dismiss": second["challenge"], "reason": "again"})
    with pytest.raises(ValueError, match="not open"):
        identity.identity_amend(root, "c", task["revision"], amend_input(1, status["on_disk_sha256"], TEXT_V1 + "\nx\n", resolves=[second["challenge"]]))
    amended = identity.identity_amend(root, "c", task["revision"], amend_input(
        1, status["on_disk_sha256"], TEXT_V1.replace("Only the owner", "Owners and delegates"),
        challenge_text="evidence says...", resolves=[first["challenge"]], evidence_refs=[f"challenge:{first['challenge']}"]))
    assert amended["challenges_resolved"] == [first["challenge"]]
    resolved = identity.identity_get(root, challenge=first["challenge"])
    assert resolved["status"] == "amended" and resolved["resolution"]["amendment"] == "A-0002"
    assert identity.identity_get(root, challenge=second["challenge"])["resolution"]["reason"] == "lower-level repair suffices"
    assert identity.identity_status(root)["open_challenges_total"] == 0
    # Challenge history survives task closure.
    core.task_close(root, task["revision"])
    assert identity.identity_status(root)["challenges_total"] == 2


def test_relations_validation_retraction_and_trace_states(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    establish(root, task["revision"])
    rev = task["revision"]
    (root / "docs").mkdir()
    for name in ("a.md", "b.md", "c.md"):
        (root / "docs" / name).write_text(name, encoding="utf-8")
    with pytest.raises(ValueError, match="identity-challenge"):
        identity.identity_relate(root, "c", rev, {"add": [{"from": "path:docs/a.md", "rel": "challenges", "to": "identity:INV-1"}]})
    with pytest.raises(ValueError, match="identity-challenge"):
        identity.identity_relate(root, "c", rev, {"add": [{"from": "path:docs/a.md", "rel": "challenges", "to": "identity"}]})
    with pytest.raises(ValueError, match="self relations"):
        identity.identity_relate(root, "c", rev, {"add": [{"from": "path:docs/a.md", "rel": "serves", "to": "path:docs/a.md"}]})
    with pytest.raises(ValueError, match="rel must be"):
        identity.identity_relate(root, "c", rev, {"add": [{"from": "path:docs/a.md", "rel": "implements", "to": "identity"}]})
    for bad in ("path:../x.md", "path:.context/state.json", "path:docs/none.md", "identity:NOPE-1", "amendment:A-0009",
                "task:not-a-uuid/x", "commit:xyz", "url:ftp://x", "mystery:1"):
        with pytest.raises(ValueError):
            identity.identity_relate(root, "c", rev, {"add": [{"from": bad, "rel": "serves", "to": "identity"}]})
    added = identity.identity_relate(root, "c", rev, {"add": [
        {"from": "path:docs/a.md", "rel": "serves", "to": "identity:INV-1", "note": "design A realizes INV-1"},
        {"from": "path:docs/b.md", "rel": "serves", "to": "identity:INV-2"},
        {"from": "path:docs/c.md", "rel": "supports", "to": "path:docs/a.md"},
        {"from": "path:docs/b.md", "rel": "challenges", "to": "path:docs/a.md"},
        {"from": "amendment:A-0001", "rel": "serves", "to": "identity"},
        {"from": "commit:abcdef1", "rel": "supersedes", "to": "commit:1234567"},
    ]})["added"]
    with pytest.raises(ValueError, match="duplicate active relation"):
        identity.identity_relate(root, "c", rev, {"add": [{"from": "path:docs/a.md", "rel": "serves", "to": "identity:INV-1"}]})
    up = identity.identity_trace(root, "path:docs/c.md", "up", 2)
    assert [(edge["from"], edge["to"], edge["depth"]) for edge in up["edges"]] == [
        ("path:docs/c.md", "path:docs/a.md", 1), ("path:docs/a.md", "identity:INV-1", 2)]
    assert up["notice"] == identity.NOTICE and up["truncated"] is False
    assert identity.identity_trace(root, "path:docs/c.md", "up", 1)["edges"][0]["to_state"] == "FRESH"
    down = identity.identity_trace(root, "identity:INV-1", "down", 3)
    assert {edge["from"] for edge in down["edges"]} == {"path:docs/a.md", "path:docs/c.md", "path:docs/b.md"}
    # Evolve: change INV-2, remove INV-1, edit and delete documents.
    v2 = TEXT_V1.replace("Only the owner changes direction.", "Owners decide.").replace(
        "## INV-1: Never lose recorded data\nRecorded data survives every crash.\n\n", "")
    identity.identity_amend(root, "c", rev, amend_input(1, identity.identity_status(root)["on_disk_sha256"], v2))
    (root / "docs/a.md").write_text("changed", encoding="utf-8")
    (root / "docs/c.md").unlink()
    states = {edge["to"]: edge["to_state"] for edge in identity.identity_trace(root, "path:docs/b.md", "up", 1)["edges"]}
    assert states == {"identity:INV-2": "CHANGED_SINCE_v1", "path:docs/a.md": "CHANGED"}
    removed = identity.identity_trace(root, "identity:INV-1", "down", 2)["edges"]
    assert {edge["from"]: edge["from_state"] for edge in removed} == {"path:docs/a.md": "CHANGED", "path:docs/c.md": "MISSING", "path:docs/b.md": "FRESH"}
    assert all(edge["to_state"] == "REMOVED" for edge in removed if edge["to"] == "identity:INV-1")
    whole = identity.identity_trace(root, "identity", "down", 1)["edges"]
    assert whole[0]["to_state"] == "CHANGED_SINCE_v1" and whole[0]["from_state"] == "RECORDED"
    # Re-registering at the new version is a retraction plus a new relation in one request.
    with pytest.raises(ValueError, match="not found"):
        identity.identity_relate(root, "c", rev, {"retract": [{"id": "REL-20990101T000000Z-000000000000", "reason": "x"}]})
    result = identity.identity_relate(root, "c", rev, {
        "retract": [{"id": added[1], "reason": "re-register at v2"}],
        "add": [{"from": "path:docs/b.md", "rel": "serves", "to": "identity:INV-2"}]})
    with pytest.raises(ValueError, match="already retracted"):
        identity.identity_relate(root, "c", rev, {"retract": [{"id": added[1], "reason": "again"}]})
    fresh = [edge for edge in identity.identity_trace(root, "identity:INV-2", "down", 1)["edges"]]
    assert [(edge["id"], edge["to_state"]) for edge in fresh] == [(result["added"][0], "CURRENT")]
    assert (root / NS / "relations" / f"{added[1]}.json").is_file()
    assert (root / NS / "relations" / f"{added[1]}.retraction.json").is_file()
    status = identity.identity_status(root)
    assert status["relations_total"] == 7 and status["relations_active"] == 6


def test_task_refs_verify_locally_or_stay_unverified(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    update = tmp_path.parent / f"{tmp_path.name}-update.json"
    update.write_text(json.dumps({"records": [{"id": "r1", "kind": "note", "text": "decision"}]}), encoding="utf-8")
    rev = core.task_update(root, "c", task["revision"], str(update))["revision"]
    establish(root, rev)
    with pytest.raises(ValueError, match="not found in task"):
        identity.identity_relate(root, "c", rev, {"add": [{"from": f"task:{task['task_id']}/r404", "rel": "serves", "to": "identity"}]})
    other = "00000000-0000-4000-8000-000000000000"
    identity.identity_relate(root, "c", rev, {"add": [
        {"from": f"task:{task['task_id']}/r1", "rel": "serves", "to": "identity:INV-1"},
        {"from": f"task:{other}/x1", "rel": "serves", "to": "identity:INV-1"}]})
    assert core.selected_task(root) == task["task_id"]
    states = {edge["from"]: edge["from_state"] for edge in identity.identity_trace(root, "identity:INV-1", "down", 1)["edges"]}
    assert states == {f"task:{task['task_id']}/r1": "RECORDED", f"task:{other}/x1": "UNVERIFIED"}


def test_rollback_refuses_identity_backups_but_not_other_backups(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    result = establish(root, task["revision"])
    with pytest.raises(ValueError, match="project identity mutation"):
        core.rollback(root, result["backup"])
    assert identity.identity_status(root)["state"] == "CURRENT"
    (root / "plain.txt").write_bytes(b"before")
    with core._lock(root):
        backup = core._apply_with_backup(root, {"plain.txt": b"after"}, [], "test")
    assert core.rollback(root, backup)["rolled_back"] is True
    assert (root / "plain.txt").read_bytes() == b"before"


def test_bounds_and_truncation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    rev = task["revision"]
    with pytest.raises(ValueError, match="exceeds"):
        establish(root, rev, "## INV-1 big\n" + "x" * (identity.IDENTITY_MAX_BYTES + 1))
    many = "".join(f"## I-{index} {'title ' * 30}\nbody\n\n" for index in range(1, 101))
    establish(root, rev, many)
    status = identity.identity_status(root)
    assert status["items_total"] == 100 and len(status["items"]) <= identity.STATUS_MAX_ITEMS
    assert status["truncated"] is True
    assert len(json.dumps(status, ensure_ascii=False, separators=(",", ":")).encode()) <= identity.STATUS_MAX_BYTES
    with pytest.raises(ValueError, match="depth"):
        identity.identity_trace(root, "identity", "up", 5)
    with pytest.raises(ValueError, match="direction"):
        identity.identity_trace(root, "identity", "sideways", 1)
    adds = [{"from": f"commit:{index:07x}", "rel": "serves", "to": "identity"} for index in range(64)]
    adds2 = [{"from": f"commit:{index + 64:07x}", "rel": "serves", "to": "identity"} for index in range(64)]
    adds3 = [{"from": f"commit:{index + 128:07x}", "rel": "serves", "to": "identity"} for index in range(10)]
    for batch in (adds, adds2, adds3):
        identity.identity_relate(root, "c", rev, {"add": batch})
    trace = identity.identity_trace(root, "identity", "down", 1)
    assert len(trace["edges"]) == identity.TRACE_MAX_EDGES and trace["truncated"] is True
    with pytest.raises(ValueError, match="at most 64"):
        identity.identity_relate(root, "c", rev, {"add": adds + adds2})
    with pytest.raises(ValueError, match="selects"):
        identity.identity_get(root, version=1, amendment="A-0001")


def test_existing_identity_document_can_become_v1(tmp_path: Path) -> None:
    root = repo(tmp_path)
    task = started(root)
    (root / NS).mkdir()
    (root / NS / "IDENTITY.md").write_text("## C-1 Constitution\nkept\n", encoding="utf-8")
    status = identity.identity_status(root)
    assert status["state"] == "ABSENT" and status["on_disk_sha256"] == canonical("## C-1 Constitution\nkept\n")
    assert "no version is recorded" in status["detail"][0]
    with pytest.raises(ValueError, match="base_sha256 conflict"):
        establish(root, task["revision"], "## C-1 Constitution\nkept\n")
    result = identity.identity_amend(root, "c", task["revision"], amend_input(0, status["on_disk_sha256"], "## C-1 Constitution\nkept\n"))
    assert result["version"] == 1 and identity.identity_status(root)["state"] == "CURRENT"


def test_cli_round_trip_and_exit_codes(tmp_path: Path, capsys) -> None:
    root = repo(tmp_path)

    def run(*args: str) -> tuple[int, dict[str, object]]:
        code = cli.main(["--root", str(root), *args])
        return code, json.loads(capsys.readouterr().out)

    code, out = run("identity-status")
    assert code == 0 and out["state"] == "ABSENT"
    code, out = run("task-start", "cli identity")
    task_id, revision = out["task_id"], out["revision"]
    payload = tmp_path.parent / f"{tmp_path.name}-amend.json"
    payload.write_text(json.dumps(amend_input(0, None, TEXT_V1)), encoding="utf-8")
    code, out = run("identity-amend", "--actor", "c", "--base-revision", str(revision), "--input", str(payload))
    assert code == 2 and "explicit --task-id" in out["error"]
    code, out = run("--task-id", task_id, "identity-amend", "--actor", "c", "--base-revision", str(revision), "--input", str(payload))
    assert code == 0 and out["version"] == 1
    code, out = run("--task-id", task_id, "identity-amend", "--actor", "c", "--base-revision", str(revision), "--input", str(payload))
    assert code == 2 and "identity version conflict" in out["error"]
    code, out = run("identity-get", "--item", "INV-1", "--item", "NG-1")
    assert code == 0 and [item["id"] for item in out["items"]] == ["INV-1", "NG-1"]
    code, out = run("identity-get", "--amendment", "A-0001")
    assert code == 0 and out["record"]["to_version"] == 1
    relate = tmp_path.parent / f"{tmp_path.name}-relate.json"
    relate.write_text(json.dumps({"add": [{"from": "commit:abcdef1", "rel": "serves", "to": "identity:INV-1"}]}), encoding="utf-8")
    code, out = run("--task-id", task_id, "identity-relate", "--actor", "c", "--base-revision", str(revision), "--input", str(relate))
    assert code == 0 and len(out["added"]) == 1
    challenge = tmp_path.parent / f"{tmp_path.name}-challenge.json"
    challenge.write_text(json.dumps({"targets": ["identity:INV-1"], "summary": "s", "text": "t"}), encoding="utf-8")
    code, out = run("--task-id", task_id, "identity-challenge", "--actor", "c", "--base-revision", str(revision), "--input", str(challenge))
    assert code == 0 and out["status"] == "open"
    code, out = run("identity-get", "--challenge", out["challenge"])
    assert code == 0 and out["status"] == "open"
    code, out = run("identity-trace", "identity:INV-1", "--direction", "down", "--depth", "2")
    assert code == 0 and out["edges"][0]["from"] == "commit:abcdef1" and out["notice"] == identity.NOTICE
    code, out = run("identity-trace", "bogus")
    assert code == 2
    code, out = run("--task-id", task_id, "task-status")
    assert code == 0 and out["Task"]["revision"] == revision
    backups = [path for path in (root / ".context/backups").glob("*.json")
               if json.loads(path.read_text(encoding="utf-8"))["action"] == "identity-relate"]
    code, out = run("rollback", backups[0].stem)
    assert code == 2 and "project identity mutation" in out["error"]


def test_identity_module_is_host_neutral() -> None:
    script = '''
import importlib.abc, sys
class DenyHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('thaliris_codex', 'thaliris_dsh', 'thaliris_claude')):
            raise AssertionError('Core attempted a Host import')
sys.meta_path.insert(0, DenyHost())
from thaliris import identity, cli
raise SystemExit(cli.main(['version']))
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["ok"] is True
    source = Path(identity.__file__).read_text(encoding="utf-8").lower()
    assert "controller" not in source
