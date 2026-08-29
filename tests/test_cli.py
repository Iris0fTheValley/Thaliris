from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from codex_context.cli import main
from codex_context import core
from codex_context.markdown import parse
from codex_context import doctor


def run(capsys, root: Path, *args: str):
    code = main(["--root", str(root), *args])
    return code, json.loads(capsys.readouterr().out)


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_init_idempotent_preserves_agents_and_required_block(tmp_path, capsys):
    root = repo(tmp_path); (root / "AGENTS.md").write_text("Keep this rule.\n", encoding="utf-8")
    code, first = run(capsys, root, "init")
    assert code == 0 and first["changed"]
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep this rule." in text and all(term in text for term in ("Sol mid", "Sol high", "Luna", "Terra", "Microtask", "concurrency: 1", "MUST fall back"))
    code, second = run(capsys, root, "init")
    assert code == 0 and not second["changed"]


def test_init_preserves_crlf_outside_managed_block(tmp_path, capsys):
    root = repo(tmp_path); original = b"Keep this rule.\r\nKeep another.\r\n"
    (root / "AGENTS.md").write_bytes(original)
    code, first = run(capsys, root, "init")
    assert code == 0 and first["changed"]
    rendered = (root / "AGENTS.md").read_bytes()
    assert rendered.startswith(original)
    assert b"\r\n<!-- codex-context:end -->\r\n" in rendered
    assert b"\n" not in rendered.replace(b"\r\n", b"")
    code, second = run(capsys, root, "init")
    assert code == 0 and not second["changed"]
    assert (root / "AGENTS.md").read_bytes() == rendered


def test_damaged_agents_markers_fail_without_mutation(tmp_path, capsys):
    root = repo(tmp_path); source = "user\n<!-- codex-context:begin -->\n"
    (root / "AGENTS.md").write_text(source, encoding="utf-8")
    code, result = run(capsys, root, "init")
    assert code == 2 and "damaged" in result["error"] and (root / "AGENTS.md").read_text() == source
    assert not (root / ".context").exists()


def test_repo_root_and_rollback_guard(tmp_path, capsys):
    root = repo(tmp_path); nested = root / "nested"; nested.mkdir()
    code, result = run(capsys, nested, "init")
    assert code == 2 and "repository root" in result["error"]
    _, made = run(capsys, root, "init")
    (root / "AGENTS.md").write_text("user changed this", encoding="utf-8")
    code, result = run(capsys, root, "rollback", made["backup"])
    assert code == 3 and result["guarded"] and (root / "AGENTS.md").read_text() == "user changed this"


def test_rollback_accepts_unapplied_planned_files_after_crash(tmp_path, capsys):
    root = repo(tmp_path); _, made = run(capsys, root, "init")
    (root / ".agent-memory/operator.md").unlink()
    code, result = run(capsys, root, "rollback", made["backup"])
    assert code == 0 and result["rolled_back"]
    assert not (root / "AGENTS.md").exists()


def test_migrate_and_uninstall_preserve_changed_facts(tmp_path, capsys):
    root = repo(tmp_path)
    code, first = run(capsys, root, "migrate")
    assert code == 0 and first["migration"] == "v1"
    fact = root / ".agent-memory" / "operator.md"; fact.write_text(fact.read_text() + "User fact.\n", encoding="utf-8")
    code, removed = run(capsys, root, "uninstall")
    assert code == 0 and ".agent-memory/operator.md" in removed["kept"] and fact.is_file()
    assert not (root / "AGENTS.md").exists()


def test_stale_effective_confidence_uses_real_file_hash(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest(); entry = root / ".agent-memory" / "fact.md"
    entry.write_text(f"---\nEvidence: file:src.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: CONFIRMED\n---\n\n# Fact\n\nConfirmed.\n", encoding="utf-8")
    index = root / ".agent-memory" / "INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "\n- [Fact](fact.md)\n", encoding="utf-8")
    _, fresh = run(capsys, root, "stale")
    record = next(x for x in fresh["entries"] if x["path"].endswith("fact.md")); assert record["effective_confidence"] == "CONFIRMED"
    source.write_text("two", encoding="utf-8")
    _, changed = run(capsys, root, "stale")
    record = next(x for x in changed["entries"] if x["path"].endswith("fact.md")); assert record["state"] == "STALE" and record["effective_confidence"] == "STALE"
    _, pack = run(capsys, root, "prepare", "fact", "--role", "sol-high")
    assert not any(item["source"].endswith("fact.md") for item in pack["Facts"])
    assert any("stale evidence" in item for item in pack["Unknowns"])


def test_stale_cannot_be_persisted_as_captured_confidence(tmp_path):
    path = tmp_path / "entry.md"
    path.write_text("---\nEvidence: NONE\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: STALE\n---\n\n# Bad\n", encoding="utf-8")
    try:
        parse(path)
    except ValueError as exc:
        assert "metadata invalid" in str(exc)
    else:
        raise AssertionError("STALE must be derived, not persisted")
    path.write_text("---\nEvidence: NONE\nRevision: 1\nStatus: STALE\nApplicability: PROJECT\nConfidence: CONFIRMED\n---\n\n# Bad\n", encoding="utf-8")
    try:
        parse(path)
    except ValueError as exc:
        assert "metadata invalid" in str(exc)
    else:
        raise AssertionError("STALE must not be a persisted status")


def test_init_recovers_an_interrupted_multi_file_write(tmp_path, capsys, monkeypatch):
    root = repo(tmp_path)
    original = core._atomic_write
    failed = False

    def fail_once(target, content):
        nonlocal failed
        if not failed and target.name == "operator.md":
            failed = True
            raise OSError("injected write failure")
        return original(target, content)

    monkeypatch.setattr(core, "_atomic_write", fail_once)
    code, result = run(capsys, root, "init")
    assert code == 2 and "injected write failure" in result["error"]
    assert not (root / "AGENTS.md").exists()
    assert not (root / ".agent-memory/INDEX.md").exists()


def test_role_specific_projection_and_native_fallback(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    expected = {
        "sol-high": {"Goal", "Facts", "Constraints", "Decisions", "Unknowns", "Evidence"},
        "luna": {"Goal", "Files", "Unknowns", "Evidence", "Investigation Target"},
        "terra-implementer": {"Goal", "Facts", "Files", "Constraints", "Modification Boundary"},
        "terra-reviewer": {"Architectural Intent", "Decisions", "Changed Surface", "Known Risks", "Evidence"},
    }
    for role, fields in expected.items():
        _, pack = run(capsys, root, "prepare", "implement policy", "--role", role)
        assert fields <= set(pack) and set(pack) - fields <= {"ok", "role"}
    _, implementer = run(capsys, root, "prepare", "implement policy", "--role", "terra-implementer")
    assert implementer["Files"] == []
    assert implementer["Modification Boundary"] == {"status": "UNVERIFIED", "paths": []}


def test_reviewer_changed_surface_expands_rename_paths(tmp_path, capsys):
    root = repo(tmp_path)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    old = root / "old.txt"; old.write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "add", "old.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    subprocess.run(["git", "mv", "old.txt", "new.txt"], cwd=root, check=True)
    _, pack = run(capsys, root, "prepare", "review rename", "--role", "terra-reviewer")
    assert set(pack["Changed Surface"]) == {"old.txt", "new.txt"}


def test_doctor_unknown_invalid_project_config_and_toml(tmp_path, capsys, monkeypatch):
    root = repo(tmp_path); codex_home = root / "codex-home"; codex_home.mkdir()
    (codex_home / "config.toml").write_text('model = "test-model"\nmodel_reasoning_effort = "high"\n[mcp_servers.serena]\n', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    (root / ".context").mkdir(); (root / ".context/config.json").write_text('{"automatic_injection": true}', encoding="utf-8")
    _, result = run(capsys, root, "doctor")
    assert result["codex"]["model"] == "test-model" and result["adapters"]["serena"]["configured"] == "YES"
    assert result["adapters"]["agentmemory"]["automatic_injection"] == "UNKNOWN"


def test_doctor_uses_project_adapter_enablement(tmp_path, capsys, monkeypatch):
    root = repo(tmp_path); codex_home = root / "codex-home"; codex_home.mkdir()
    (codex_home / "config.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    (root / ".context").mkdir()
    (root / ".context/config.json").write_text('{"schema_version":1,"adapters":{"cachebro":true}}', encoding="utf-8")
    _, result = run(capsys, root, "doctor")
    assert result["adapters"]["cachebro"]["configured"] == "NO"
    assert result["adapters"]["cachebro"]["enabled"] == "YES"


def test_config_schema_version_is_strictly_integer(tmp_path, capsys):
    root = repo(tmp_path); (root / ".context").mkdir()
    (root / ".context/config.json").write_text('{"schema_version":true}', encoding="utf-8")
    _, result = run(capsys, root, "doctor")
    assert result["context"]["config"] == "NO"


def test_config_rejects_unknown_adapter_name(tmp_path, capsys):
    root = repo(tmp_path); (root / ".context").mkdir()
    (root / ".context/config.json").write_text('{"schema_version":1,"adapters":{"cachebroo":true}}', encoding="utf-8")
    _, result = run(capsys, root, "doctor")
    assert result["context"]["config"] == "NO"


def test_adapter_version_does_not_claim_health(monkeypatch):
    monkeypatch.setattr(doctor, "_version", lambda name: "cachebro 0.2.2")
    result = doctor._adapter("cachebro", "0.2.2", {"command": "cachebro"}, True, True)
    assert result["installed"] == "YES" and result["healthy"] == "UNKNOWN"


def test_git_blob_evidence_and_pretty_after_command(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "src.txt"], cwd=root, check=True)
    blob = subprocess.run(["git", "hash-object", str(source)], capture_output=True, text=True, check=True).stdout.strip()
    (root / ".agent-memory/fact.md").write_text(f"---\nEvidence: git:src.txt#{blob}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\n---\n\n# Fact\n\nConfirmed.\n", encoding="utf-8")
    code = main(["--root", str(root), "stale", "--pretty"]); output = capsys.readouterr().out
    assert code == 0 and json.loads(output)["stale"] == 0 and "\n" in output


def test_git_evidence_rejects_untracked_file(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "untracked.txt"; source.write_text("one", encoding="utf-8")
    blob = subprocess.run(["git", "hash-object", "-w", str(source)], capture_output=True, text=True, check=True).stdout.strip()
    (root / ".agent-memory/fact.md").write_text(f"---\nEvidence: git:untracked.txt#{blob}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\n---\n\n# Fact\n", encoding="utf-8")
    _, result = run(capsys, root, "stale")
    record = next(item for item in result["entries"] if item["path"].endswith("fact.md"))
    assert record["effective_confidence"] == "STALE"


def test_stale_applicability_does_not_become_modification_boundary(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    fact = root / ".agent-memory/fact.md"
    fact.write_text(f"---\nEvidence: file:src.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: src.txt\nConfidence: SUPPORTED\n---\n\n# Fact\n\nCurrent behavior.\n", encoding="utf-8")
    index = root / ".agent-memory/INDEX.md"; index.write_text(index.read_text(encoding="utf-8") + "\n- [Fact](fact.md)\n", encoding="utf-8")
    source.write_text("two", encoding="utf-8")
    _, pack = run(capsys, root, "prepare", "fact", "--role", "terra-implementer")
    assert pack["Modification Boundary"] == {"status": "UNVERIFIED", "paths": []}


def test_console_pretty_after_command(tmp_path):
    root = repo(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "codex_context.cli", "--root", str(root), "doctor", "--pretty"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"]
    assert "\n" in result.stdout


def test_milestone_directory_contract_and_path_escape(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    code, result = run(capsys, root, "milestone-check")
    assert code == 0 and result["ok"]
    (root / ".milestones/INDEX.md").write_text("---\nEvidence: NONE\nRevision: 1\nStatus: DRAFT\nApplicability: PROJECT\nConfidence: UNVERIFIED\n---\n\n# Index\n\n- [escape](../../outside/INDEX.md)\n", encoding="utf-8")
    code, result = run(capsys, root, "milestone-check")
    assert code == 3 and any("escapes" in error for error in result["errors"])
