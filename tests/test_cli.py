from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from thaliris.cli import main
from thaliris import core
from thaliris.markdown import parse
from thaliris import doctor


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
    assert "Keep this rule." in text and all(term in text for term in ("control plane, not an investigator", "repository investigation", "code search", "documentation research", "Git inspection", "runtime probing", "exploratory testing", "Luna investigator", "Sol high", "Terra", "Microtask", "concurrency: 1", "MUST fall back"))
    code, second = run(capsys, root, "init")
    assert code == 0 and not second["changed"]


def test_init_preserves_crlf_outside_managed_block(tmp_path, capsys):
    root = repo(tmp_path); original = b"Keep this rule.\r\nKeep another.\r\n"
    (root / "AGENTS.md").write_bytes(original)
    code, first = run(capsys, root, "init")
    assert code == 0 and first["changed"]
    rendered = (root / "AGENTS.md").read_bytes()
    assert rendered.startswith(original)
    assert b"\r\n<!-- thaliris:end -->\r\n" in rendered
    assert b"\n" not in rendered.replace(b"\r\n", b"")
    assert subprocess.run(["git", "check-ignore", "-q", ".context/state.json"], cwd=root).returncode == 0
    code, second = run(capsys, root, "init")
    assert code == 0 and not second["changed"]
    assert (root / "AGENTS.md").read_bytes() == rendered


def test_damaged_agents_markers_fail_without_mutation(tmp_path, capsys):
    root = repo(tmp_path); source = "user\n<!-- codex-context:begin -->\n"
    (root / "AGENTS.md").write_text(source, encoding="utf-8")
    code, result = run(capsys, root, "init")
    assert code == 2 and "damaged" in result["error"] and (root / "AGENTS.md").read_text() == source
    assert not (root / ".context").exists()


def test_init_and_migrate_upgrade_legacy_markers_without_duplicates(tmp_path, capsys):
    for command in ("init", "migrate"):
        root = repo(tmp_path / command)
        (root / "AGENTS.md").write_text(
            "Keep.\n<!-- codex-context:begin -->\n## Codex context\nOld block.\n<!-- codex-context:end -->\n",
            encoding="utf-8",
        )
        (root / ".gitignore").write_text(
            "keep.me\n# codex-context:begin\n.context/backups/\n.context/state.json\n.context/context.lock\n# codex-context:end\n",
            encoding="utf-8",
        )
        _, diagnostic = run(capsys, root, "doctor")
        assert diagnostic["context"]["agents"] == "YES"
        code, result = run(capsys, root, command)
        assert code == 0 and result["changed"]
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        ignored = (root / ".gitignore").read_text(encoding="utf-8")
        assert "Keep." in agents and "keep.me" in ignored
        assert "Controller is the control plane, not an investigator" in agents
        assert "MUST delegate the investigation to a Luna investigator" in agents
        assert agents.count("<!-- thaliris:begin -->") == agents.count("<!-- thaliris:end -->") == 1
        assert ignored.count("# thaliris:begin") == ignored.count("# thaliris:end") == 1
        assert "codex-context:" not in agents and "codex-context:" not in ignored


def test_uninstall_accepts_legacy_markers_and_damaged_markers_fail_closed(tmp_path, capsys):
    legacy = repo(tmp_path / "legacy")
    (legacy / "AGENTS.md").write_text(
        "Keep.\n<!-- codex-context:begin -->\nOld block.\n<!-- codex-context:end -->\n",
        encoding="utf-8",
    )
    (legacy / ".gitignore").write_text(
        "keep.me\n# codex-context:begin\n.context/state.json\n# codex-context:end\n",
        encoding="utf-8",
    )
    code, result = run(capsys, legacy, "uninstall")
    assert code == 0 and result["changed"]
    assert (legacy / "AGENTS.md").read_text(encoding="utf-8") == "Keep.\n"
    assert (legacy / ".gitignore").read_text(encoding="utf-8") == "keep.me\n"

    damaged = repo(tmp_path / "damaged")
    source = "Keep.\n<!-- thaliris:begin -->\n<!-- codex-context:end -->\n"
    (damaged / "AGENTS.md").write_text(source, encoding="utf-8")
    code, result = run(capsys, damaged, "uninstall")
    assert code == 2 and "damaged" in result["error"]
    assert (damaged / "AGENTS.md").read_text(encoding="utf-8") == source
    assert not (damaged / ".context").exists()

    damaged_ignore = repo(tmp_path / "damaged-ignore")
    ignore_source = "keep.me\n# thaliris:begin\n# codex-context:end\n"
    (damaged_ignore / ".gitignore").write_text(ignore_source, encoding="utf-8")
    code, result = run(capsys, damaged_ignore, "uninstall")
    assert code == 2 and "damaged" in result["error"]
    assert (damaged_ignore / ".gitignore").read_text(encoding="utf-8") == ignore_source
    assert not (damaged_ignore / ".context").exists()


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
    assert code == 0 and first["migration"] == "v2"
    fact = root / ".agent-memory" / "operator.md"; fact.write_text(fact.read_text() + "User fact.\n", encoding="utf-8")
    code, removed = run(capsys, root, "uninstall")
    assert code == 0 and ".agent-memory/operator.md" in removed["kept"] and fact.is_file()
    assert not (root / "AGENTS.md").exists()
    assert not (root / ".gitignore").exists()


def test_stale_effective_confidence_uses_real_file_hash(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest(); entry = root / ".agent-memory" / "fact.md"
    entry.write_text(f'---\nEvidence: file:src.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: CONFIRMED\nAudience: ["sol-high"]\n---\n\n# Fact\n\nConfirmed.\n', encoding="utf-8")
    index = root / ".agent-memory" / "INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "\n- [Fact](fact.md)\n", encoding="utf-8")
    _, fresh = run(capsys, root, "stale")
    record = next(x for x in fresh["entries"] if x["path"].endswith("fact.md")); assert record["effective_confidence"] == "CONFIRMED"
    source.write_text("two", encoding="utf-8")
    _, changed = run(capsys, root, "stale")
    record = next(x for x in changed["entries"] if x["path"].endswith("fact.md")); assert record["state"] == "STALE" and record["effective_confidence"] == "STALE"
    _, pack = run(capsys, root, "prepare", "fact", "--role", "sol-high")
    assert not any(item["source"].endswith("fact.md") for item in pack["Confirmed Facts"])
    assert any("stale evidence" in str(item) for item in pack["Unknowns"])


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
        "sol-high": {"Goal", "Confirmed Facts", "Supported Evidence", "Hard Constraints", "Decisions", "Unknowns", "Contradictions", "Evidence refs", "Investigation Readiness", "Review Readiness"},
        "luna": {"Goal", "Relevant Files", "Relevant Symbols", "Hard Constraints", "Unknowns", "Contradictions", "Evidence refs", "Investigation Target", "Investigation Snapshot", "Verification Target"},
        "terra-implementer": {"Goal", "Confirmed Facts", "Supported Evidence", "Relevant Files", "Hard Constraints", "Decisions", "Modification Boundary", "Required Verification", "Evidence refs"},
        "terra-reviewer": {"Review Goal", "Architectural Intent", "Hard Constraints", "Durable Decisions", "Changed Surface", "Evidence refs"},
    }
    for role, fields in expected.items():
        _, pack = run(capsys, root, "prepare", "implement policy", "--role", role)
        assert fields <= set(pack) and set(pack) - fields <= {"ok", "role", "schema_version", "task_id", "state_revision"}
    _, implementer = run(capsys, root, "prepare", "implement policy", "--role", "terra-implementer")
    assert implementer["Relevant Files"] == []
    assert implementer["Modification Boundary"] == {"status": "UNVERIFIED", "includes": [], "excludes": [], "evidence_refs": []}


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
    assert result["codex"]["model_configured"] == "test-model" and result["adapters"]["serena"]["configured"] == "YES"
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
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "cachebro")
    result = doctor._adapter("cachebro", "0.2.2", {"command": "cachebro"}, True, True)
    assert result["installed"] == "YES" and result["version_validated"] == "YES" and "healthy" not in result


def test_adapter_version_mismatch_is_installed_but_not_validated(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "cachebro")
    monkeypatch.setattr(doctor, "_version", lambda name: "cachebro 0.3.0")
    result = doctor._adapter("cachebro", "0.2.2", None, None, True)
    assert result["installed"] == "YES"
    assert result["version"] == "cachebro 0.3.0"
    assert result["expected_version"] == "0.2.2"
    assert result["version_validated"] == "NO"
    result = doctor._adapter("cachebro", "0.2.2", None, None, False)
    assert result["installed"] == "YES" and result["version"] == "UNKNOWN" and result["version_validated"] == "UNKNOWN"
    monkeypatch.setattr(doctor, "_version", lambda name: "cachebro 0.2.20")
    assert doctor._adapter("cachebro", "0.2.2", None, None, True)["version_validated"] == "NO"


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
    assert pack["Modification Boundary"] == {"status": "UNVERIFIED", "includes": [], "excludes": [], "evidence_refs": []}


def test_console_pretty_after_command(tmp_path):
    root = repo(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "thaliris.cli", "--root", str(root), "doctor", "--pretty"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"]
    assert "\n" in result.stdout
    help_result = subprocess.run(
        [sys.executable, "-m", "thaliris.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0 and "Thaliris" in help_result.stdout


def test_milestone_directory_contract_and_path_escape(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    code, result = run(capsys, root, "milestone-check")
    assert code == 0 and result["ok"]
    (root / ".milestones/INDEX.md").write_text("---\nEvidence: NONE\nRevision: 1\nStatus: DRAFT\nApplicability: PROJECT\nConfidence: UNVERIFIED\n---\n\n# Index\n\n- [escape](../../outside/INDEX.md)\n", encoding="utf-8")
    code, result = run(capsys, root, "milestone-check")
    assert code == 3 and any("escapes" in error for error in result["errors"])


def task_input(root: Path, capsys, data: dict, *args: str):
    path = root / "input.json"; path.write_text(json.dumps(data), encoding="utf-8")
    return run(capsys, root, *args, "--input", str(path))


def test_task_state_cas_atomic_and_cross_reference_validation(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("observed", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {"id": "e1", "kind": "file", "locator": f"file:src.txt#{digest}", "summary": "observed", "confidence": "CONFIRMED"}
    statement = {"text": "x exists", "evidence_refs": ["e1"]}
    code, made = task_input(root, capsys, {"evidence_refs": [evidence], "confirmed_facts": [statement]}, "task-start", "repair")
    assert code == 0 and made["state"]["revision"] == 1
    boundary = {"status": "SUPPORTED", "includes": ["src"], "excludes": [], "evidence_refs": []}
    code, controlled = task_input(root, capsys, {"modification_boundary": boundary}, "task-update", "--role", "controller", "--base-revision", "1")
    assert code == 0 and controlled["state"]["modification_boundary"] == boundary
    state = root / ".context/state.json"; original = state.read_bytes()
    code, failed = task_input(root, capsys, {"modification_boundary": boundary}, "task-update", "--role", "sol-high", "--base-revision", "2")
    assert code == 2 and "not allowed" in failed["error"] and state.read_bytes() == original
    code, failed = task_input(root, capsys, {"unknowns": [{"text": "later", "evidence_refs": []}]}, "task-update", "--role", "luna", "--base-revision", "1")
    assert code == 2 and "not allowed" in failed["error"] and state.read_bytes() == original
    code, failed = task_input(root, capsys, {"confirmed_facts": [{"text": "bad", "evidence_refs": ["missing"]}]}, "task-update", "--role", "terra-implementer", "--base-revision", "2")
    assert code == 2 and "not allowed" in failed["error"]
    state.write_text('{"raw":"tool output"}', encoding="utf-8")
    code, failed = run(capsys, root, "task-show")
    assert code == 2 and "prohibited" in failed["error"]


def test_memory_evidence_cannot_confirm_task_fact(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    ref = {"id": "m1", "kind": "memory", "locator": ".agent-memory/operator.md", "summary": "historical claim", "confidence": "CONFIRMED"}
    fact = {"text": "memory alone proves this", "evidence_refs": ["m1"]}
    code, failed = task_input(root, capsys, {"evidence_refs": [ref], "confirmed_facts": [fact]}, "task-start", "repair")
    assert code == 2 and "non-native evidence" in failed["error"]


def test_supported_memory_evidence_remains_supported_when_fresh(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("stable", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    memory = root / ".agent-memory/supported.md"
    memory.write_text(f'---\nEvidence: file:src.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\nAudience: ["controller"]\nTopics: []\nSymbols: []\n---\n\n# Supported\n\nHistorical observation.\n', encoding="utf-8")
    ref = {"id": "memory1", "kind": "memory", "locator": ".agent-memory/supported.md", "summary": "historical observation", "confidence": "SUPPORTED"}
    claim = {"text": "historical observation", "evidence_refs": ["memory1"]}
    task_input(root, capsys, {"evidence_refs": [ref], "supported_evidence": [claim]}, "task-start", "repair")

    _, pack = run(capsys, root, "prepare", "--role", "sol-high")
    assert claim in pack["Supported Evidence"]
    assert not any("stale supported evidence" in item["text"] for item in pack["Unknowns"])


def test_task_lifecycle_requires_git_repository_root(tmp_path, capsys):
    code, failed = run(capsys, tmp_path, "task-start", "repair")
    assert code == 2 and "git repository" in failed["error"]
    assert not (tmp_path / ".context").exists()
    git_root = repo(tmp_path / "repo")
    code, failed = run(capsys, git_root, "task-start", "repair")
    assert code == 2 and "context init" in failed["error"]
    assert not (git_root / ".context").exists()


def test_task_start_rechecks_ignore_inside_lock(tmp_path, capsys, monkeypatch):
    root = repo(tmp_path); run(capsys, root, "init")
    checks = iter((True, False))
    monkeypatch.setattr(core, "_state_ignored", lambda _root: next(checks))

    code, failed = run(capsys, root, "task-start", "repair")
    assert code == 2 and "not ignored" in failed["error"]
    assert not (root / ".context/state.json").exists()


def test_luna_to_sol_handoff_split_and_fresh_reviewer(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    code, made = run(capsys, root, "task-start", "repair")
    assert code == 0
    source = root / "src.txt"; source.write_text("inspection", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    e = {"id": "s", "kind": "file", "locator": f"file:src.txt#{digest}", "summary": "inspection", "confidence": "SUPPORTED"}
    code, denied = task_input(root, capsys, {"evidence_refs": [e], "supported_evidence": [{"text": "not promoted", "evidence_refs": ["s"]}]}, "task-update", "--role", "luna", "--base-revision", "1")
    assert code == 2 and "not allowed" in denied["error"]
    finding = {"kind": "SUPPORTED", "text": "likely behavior", "evidence_refs": ["s"]}
    code, updated = task_input(root, capsys, {"evidence_refs": [e], "investigation_findings": [finding]}, "task-update", "--role", "luna", "--base-revision", "1")
    assert code == 0
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert "Confirmed Facts" in sol and sol["Confirmed Facts"] == [] and sol["Supported Evidence"] == []
    _, shown = run(capsys, root, "task-show")
    assert shown["state"]["investigation_findings"] == [finding]
    promoted = {"text": "likely behavior", "evidence_refs": ["s"]}
    code, _ = task_input(root, capsys, {"supported_evidence": [promoted]}, "task-update", "--role", "controller", "--base-revision", "2")
    assert code == 0
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert sol["Supported Evidence"] == [promoted]
    _, review = run(capsys, root, "prepare", "--role", "terra-reviewer")
    assert "Unknowns" not in review and "Known Risks" not in review and "check" not in " ".join(review)


def test_non_controller_evidence_updates_are_append_only(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    original = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "original", "confidence": "SUPPORTED"}
    task_input(root, capsys, {"evidence_refs": [original]}, "task-start", "inspect")
    rebound = original | {"summary": "rebound"}
    code, failed = task_input(root, capsys, {"evidence_refs": [rebound]}, "task-update", "--role", "luna", "--base-revision", "1")
    assert code == 2 and "append-only" in failed["error"]
    added = {"id": "extra", "kind": "file", "locator": original["locator"], "summary": "additional", "confidence": "SUPPORTED"}
    code, updated = task_input(root, capsys, {"evidence_refs": [added]}, "task-update", "--role", "luna", "--base-revision", "1")
    assert code == 0 and updated["state"]["evidence_refs"] == [original, added]


def test_v1_task_state_without_findings_is_loaded_compatibly(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "legacy")
    path = root / ".context/state.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy.pop("investigation_findings"); legacy.pop("investigation_snapshot"); legacy.pop("review_findings"); legacy.pop("investigation_covered_through"); legacy.pop("review_handled_through")
    path.write_text(json.dumps(legacy), encoding="utf-8")
    code, shown = run(capsys, root, "task-show")
    assert code == 0 and shown["state"]["investigation_findings"] == [] and shown["state"]["investigation_snapshot"] == [] and shown["state"]["review_findings"] == [] and shown["state"]["investigation_covered_through"] == shown["state"]["review_handled_through"] == 0


def test_v1_unbound_test_evidence_loads_stale_until_reverified(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "legacy test")
    path = root / ".context/state.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy.pop("investigation_findings"); legacy.pop("investigation_snapshot"); legacy.pop("review_findings"); legacy.pop("investigation_covered_through"); legacy.pop("review_handled_through")
    legacy_ref = {"id": "oldtest", "kind": "test", "locator": "pytest", "summary": "passed before source binding", "confidence": "SUPPORTED"}
    legacy["evidence_refs"] = [legacy_ref]
    legacy["supported_evidence"] = [{"text": "legacy test passed", "evidence_refs": ["oldtest"]}]
    path.write_text(json.dumps(legacy), encoding="utf-8")
    code, shown = run(capsys, root, "task-show")
    assert code == 0 and shown["state"]["evidence_refs"][0]["source_refs"] == []
    _, pack = run(capsys, root, "prepare", "--role", "sol-high")
    assert pack["Supported Evidence"] == [] and pack["Unknowns"][0]["text"].startswith("stale supported evidence")
    code, updated = task_input(root, capsys, {"changed_surface": ["src"]}, "task-update", "--role", "terra-implementer", "--base-revision", "1")
    assert code == 0 and updated["state"]["revision"] == 2
    code, closed = run(capsys, root, "task-close", "--base-revision", "2")
    assert code == 0 and closed["state"]["status"] == "DONE"


def test_memory_audience_and_unicode_topics_symbols(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    item = root / ".agent-memory" / "zh.md"
    item.write_text('---\nEvidence: NONE\nRevision: 1\nStatus: DRAFT\nApplicability: PROJECT\nConfidence: UNVERIFIED\nAudience: ["luna"]\nTopics: ["中文路由"]\nSymbols: ["函数甲"]\n---\n\n# private\n\nprivate body\n', encoding="utf-8")
    index = root / ".agent-memory/INDEX.md"; index.write_text(index.read_text(encoding="utf-8") + "\n- [zh](zh.md)\n", encoding="utf-8")
    _, luna = run(capsys, root, "prepare", "检查中文路由函数甲", "--role", "luna")
    _, sol = run(capsys, root, "prepare", "检查中文路由函数甲", "--role", "sol-high")
    assert any(ref["locator"].endswith("zh.md") for ref in luna["Evidence refs"])
    assert not any(ref["locator"].endswith("zh.md") for ref in sol["Evidence refs"])
    run(capsys, root, "task-start", "检查中文路由函数甲")
    _, state_luna = run(capsys, root, "prepare", "--role", "luna")
    _, state_sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert any("zh.md" in str(item) for item in state_luna["Unknowns"])
    assert not any("zh.md" in str(item) for item in state_sol["Unknowns"])

    policy = root / ".agent-memory/policy-extra.md"
    policy.write_text('---\nEvidence: NONE\nRevision: 1\nStatus: DRAFT\nApplicability: PROJECT\nConfidence: UNVERIFIED\nAudience: ["controller"]\nTopics: ["中文路由"]\nSymbols: []\n---\n\n# controller only\n', encoding="utf-8")
    index.write_text(index.read_text(encoding="utf-8") + "\n- [policy](policy-extra.md)\n", encoding="utf-8")
    _, sol = run(capsys, root, "prepare", "检查中文路由", "--role", "sol-high")
    assert not any(ref["locator"].endswith("policy-extra.md") for ref in sol["Evidence refs"])

    legacy = root / ".agent-memory/legacy.md"
    legacy.write_text('---\nEvidence: NONE\nRevision: 1\nStatus: DRAFT\nApplicability: PROJECT\nConfidence: UNVERIFIED\nTopics: ["legacy-topic"]\nSymbols: []\n---\n\n# Legacy\n', encoding="utf-8")
    index.write_text(index.read_text(encoding="utf-8") + "\n- [legacy](legacy.md)\n", encoding="utf-8")
    _, legacy_pack = run(capsys, root, "prepare", "legacy-topic", "--role", "terra-reviewer")
    assert not any(ref["locator"].endswith("legacy.md") for ref in legacy_pack["Evidence refs"])


def test_milestone_slice_and_memory_applicability_is_not_boundary(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    code, _ = run(capsys, root, "task-start", "repair", "--milestone", "M001-name")
    assert code == 0
    _, implementer = run(capsys, root, "prepare", "--role", "terra-implementer")
    assert implementer["Milestone Scope"]["source"].endswith("scope.md")
    assert implementer["Implementation Constraints"]["confidence"] == "UNVERIFIED"
    assert implementer["Modification Boundary"]["includes"] == []


def test_state_pack_keeps_memory_provenance_and_changed_path_evidence(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("stable", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    memory = root / ".agent-memory/fact.md"
    memory.write_text(f'---\nEvidence: file:src.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: src.txt\nConfidence: CONFIRMED\nAudience: ["sol-high", "luna", "terra-implementer"]\nTopics: ["handoff"]\nSymbols: ["Thing.run"]\n---\n\n# Fact\n\nStable behavior.\n', encoding="utf-8")
    index = root / ".agent-memory/INDEX.md"; index.write_text(index.read_text(encoding="utf-8") + "\n- [fact](fact.md)\n", encoding="utf-8")
    evidence = {"id": "changed1", "kind": "file", "locator": f"file:src.txt#{digest}", "summary": "changed path", "confidence": "SUPPORTED"}
    task_input(root, capsys, {"evidence_refs": [evidence], "changed_surface": ["src.txt"]}, "task-start", "handoff Thing.run")
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert not sol["Confirmed Facts"]
    assert any(item.get("source", "").endswith("fact.md") for item in sol["Supported Evidence"])
    assert any(ref["id"].startswith("memory:") and ref["confidence"] == "SUPPORTED" for ref in sol["Evidence refs"])
    _, luna = run(capsys, root, "prepare", "--role", "luna")
    assert "src.txt" in luna["Relevant Files"] and "Thing.run" in luna["Relevant Symbols"]
    _, review = run(capsys, root, "prepare", "--role", "terra-reviewer")
    assert any(ref["id"] == "changed1" for ref in review["Evidence refs"])


def test_reviewer_excludes_memory_unrelated_to_visible_fields(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "source.txt"; source.write_text("stable", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    front_matter = f'---\nEvidence: file:source.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\nKind: HARD_CONSTRAINT\nAudience: ["terra-reviewer"]\nTopics: ["review-memory"]\nSymbols: []\n---\n\n'
    policy = root / ".agent-memory/policy-reviewer.md"
    policy.write_text(front_matter + "# Review policy\n\nPreserve the public contract.\n", encoding="utf-8")
    unrelated = root / ".agent-memory/fact-reviewer.md"
    unrelated.write_text(front_matter.replace("Kind: HARD_CONSTRAINT\n", "Kind: MEMORY\n") + "# Unrelated fact\n\nAn implementation observation.\n", encoding="utf-8")
    index = root / ".agent-memory/INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "\n- [review policy](policy-reviewer.md)\n- [unrelated fact](fact-reviewer.md)\n", encoding="utf-8")
    _, stateless = run(capsys, root, "prepare", "review-memory", "--role", "terra-reviewer")
    stateless_ids = {ref["id"] for ref in stateless["Evidence refs"]}
    assert "memory:.agent-memory/policy-reviewer.md" in stateless_ids
    assert "memory:.agent-memory/fact-reviewer.md" not in stateless_ids
    run(capsys, root, "task-start", "review-memory")

    _, review = run(capsys, root, "prepare", "--role", "terra-reviewer")
    ids = {ref["id"] for ref in review["Evidence refs"]}
    assert "memory:.agent-memory/policy-reviewer.md" in ids
    assert "memory:.agent-memory/fact-reviewer.md" not in ids


def test_test_runtime_evidence_requires_fresh_bound_sources(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    other = root / "other.txt"; other.write_text("unchanged", encoding="utf-8")
    source_ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "source snapshot", "confidence": "SUPPORTED"}
    test_ref = {"id": "test", "kind": "test", "locator": "pytest tests/test_src.py", "summary": "passed", "confidence": "SUPPORTED", "source_refs": ["src"]}
    claim = {"text": "targeted test passed", "evidence_refs": ["test"]}
    code, made = task_input(root, capsys, {"evidence_refs": [source_ref, test_ref], "supported_evidence": [claim]}, "task-start", "verify")
    assert code == 0
    _, fresh = run(capsys, root, "prepare", "--role", "sol-high")
    assert fresh["Supported Evidence"] == [claim]
    assert {ref["id"] for ref in fresh["Evidence refs"]} == {"src", "test"}
    other.write_text("still unrelated", encoding="utf-8")
    _, unrelated = run(capsys, root, "prepare", "--role", "sol-high")
    assert unrelated["Supported Evidence"] == [claim]
    source.write_text("two", encoding="utf-8")
    _, stale = run(capsys, root, "prepare", "--role", "sol-high")
    assert stale["Supported Evidence"] == []
    assert stale["Unknowns"][0]["text"].startswith("stale supported evidence")
    code, updated = task_input(root, capsys, {"changed_surface": ["src.txt"]}, "task-update", "--role", "terra-implementer", "--base-revision", "1")
    assert code == 0 and updated["state"]["revision"] == 2

    bad = {"id": "run", "kind": "runtime", "locator": "manual", "summary": "observed", "confidence": "SUPPORTED", "source_refs": []}
    code, failed = task_input(root, capsys, {"evidence_refs": [bad]}, "task-update", "--role", "controller", "--base-revision", "2")
    assert code == 2 and "source_refs" in failed["error"]


def test_stale_test_ref_demotes_claim_even_with_another_fresh_ref(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    stable = root / "stable.txt"; stable.write_text("stable", encoding="utf-8")
    source_ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "source", "confidence": "SUPPORTED"}
    stable_ref = {"id": "stable", "kind": "file", "locator": f"file:stable.txt#{hashlib.sha256(stable.read_bytes()).hexdigest()}", "summary": "stable", "confidence": "SUPPORTED"}
    test_ref = {"id": "test", "kind": "test", "locator": "pytest", "summary": "passed", "confidence": "SUPPORTED", "source_refs": ["src"]}
    claim = {"text": "test passed for this source", "evidence_refs": ["test", "stable"]}
    task_input(root, capsys, {"evidence_refs": [source_ref, stable_ref, test_ref], "supported_evidence": [claim]}, "task-start", "verify")
    source.write_text("two", encoding="utf-8")
    _, pack = run(capsys, root, "prepare", "--role", "sol-high")
    assert claim not in pack["Supported Evidence"] and any(item["text"].startswith("stale supported evidence") for item in pack["Unknowns"])


def test_project_hard_constraint_bypasses_lexical_routing_but_audience_and_memory_do_not(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "policy.txt"; source.write_text("stable", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    constraint = root / ".agent-memory/global.md"
    constraint.write_text(f'---\nEvidence: file:policy.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\nKind: HARD_CONSTRAINT\nAudience: ["sol-high"]\nTopics: ["python compatibility"]\nSymbols: []\n---\n\n# Compatibility\n\nSupport Python 3.11; unknown future versions require review.\n', encoding="utf-8")
    ordinary = root / ".agent-memory/ordinary.md"
    ordinary.write_text(f'---\nEvidence: file:policy.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\nKind: MEMORY\nAudience: ["sol-high"]\nTopics: ["python compatibility"]\nSymbols: []\n---\n\n# Ordinary\n\nOnly lexical recall.\n', encoding="utf-8")
    index = root / ".agent-memory/INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "\n- [global](global.md)\n- [ordinary](ordinary.md)\n", encoding="utf-8")
    _, sol = run(capsys, root, "prepare", "rename the checkout flow", "--role", "sol-high")
    assert any(item["source"].endswith("global.md") for item in sol["Hard Constraints"])
    assert not any(item.get("source", "").endswith("ordinary.md") for item in sol["Supported Evidence"])
    _, luna = run(capsys, root, "prepare", "rename the checkout flow", "--role", "luna")
    assert not any(ref["locator"].endswith("global.md") for ref in luna["Evidence refs"])

    constraint.write_text(constraint.read_text(encoding="utf-8").replace('Audience: ["sol-high"]', 'Audience: ["luna"]'), encoding="utf-8")
    _, luna = run(capsys, root, "prepare", "rename the checkout flow", "--role", "luna")
    assert any(item["source"].endswith("global.md") for item in luna["Hard Constraints"])


def test_reviewer_findings_are_structured_and_never_projected(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("inspection", encoding="utf-8")
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "inspection", "confidence": "SUPPORTED"}
    run(capsys, root, "task-start", "review")
    finding = {"issue": "missing boundary check", "impact": "can change public behavior", "evidence_refs": ["src"]}
    code, _ = task_input(root, capsys, {"evidence_refs": [ref], "review_findings": [finding]}, "task-update", "--role", "terra-reviewer", "--base-revision", "1")
    assert code == 0
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    _, review = run(capsys, root, "prepare", "--role", "terra-reviewer")
    assert "missing boundary check" not in json.dumps(sol) and "missing boundary check" not in json.dumps(review)
    code, bad = task_input(root, capsys, {"review_findings": [{"issue": "bad", "impact": "bad", "evidence_refs": []}]}, "task-update", "--role", "terra-reviewer", "--base-revision", "2")
    assert code == 2 and "review finding" in bad["error"]


def test_doctor_is_narrow_and_ci_exists(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    _, result = run(capsys, root, "doctor")
    assert result["subagents"] == {"status": "UNKNOWN"}
    assert not ({"authorized", "running", "healthy"} & set(result["adapters"]["serena"]))
    assert "task_state" in result["context"]
    (root / ".context/state.json").write_text('{"invalid":true}', encoding="utf-8")
    _, invalid = run(capsys, root, "doctor")
    assert invalid["context"]["task_state"]["valid"] == "NO"
    ci = Path(__file__).parents[1] / ".github/workflows/ci.yml"
    assert all(value in ci.read_text(encoding="utf-8") for value in ("3.11", "3.12", "3.13", "pip install -e .[test]", "pytest"))


def test_prepare_demotes_changed_native_confirmed_evidence(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {"id": "file1", "kind": "file", "locator": f"file:src.txt#{digest}", "summary": "source", "confidence": "CONFIRMED"}
    fact = {"text": "source is one", "evidence_refs": ["file1"]}
    code, _ = task_input(root, capsys, {"evidence_refs": [evidence], "confirmed_facts": [fact]}, "task-start", "check")
    assert code == 0
    source.write_text("two", encoding="utf-8")
    _, pack = run(capsys, root, "prepare", "--role", "sol-high")
    assert pack["Confirmed Facts"] == []
    assert pack["Unknowns"][0]["evidence_refs"] == ["file1"]


def test_task_state_rejects_newline_and_non_native_confirmed(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    bad = {"id": "run1", "kind": "runtime", "locator": "run", "summary": "run", "confidence": "CONFIRMED"}
    code, result = task_input(root, capsys, {"evidence_refs": [bad], "confirmed_facts": [{"text": "x", "evidence_refs": ["run1"]}]}, "task-start", "line\nbreak")
    assert code == 2 and ("control" in result["error"] or "non-native" in result["error"])


def test_investigation_curation_is_bounded_traceable_and_isolated_from_sol(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "investigate")
    source = root / "src.txt"; source.write_text("observed", encoding="utf-8")
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "inspection", "confidence": "SUPPORTED"}
    supported = {"kind": "SUPPORTED", "text": "likely behavior", "evidence_refs": ["src"]}
    unknown = {"kind": "UNKNOWN", "text": "remaining edge case", "evidence_refs": []}
    code, _ = task_input(root, capsys, {"evidence_refs": [ref], "investigation_findings": [supported, unknown]}, "task-update", "--role", "luna-investigator", "--base-revision", "1")
    assert code == 0

    _, curator = run(capsys, root, "prepare", "--role", "luna-curator")
    assert curator["Uncovered Investigation Findings"] == [supported, unknown]
    assert curator["Current Investigation Snapshot"] == []
    snapshot = [{"id": "S1", "kind": "SUPPORTED", "text": "compact behavior", "derived_from": [0], "supersedes": [], "evidence_refs": ["src"]}]
    code, curated = task_input(root, capsys, {"investigation_snapshot": snapshot}, "task-update", "--role", "luna-curator", "--base-revision", "2")
    assert code == 0 and curated["state"]["investigation_findings"] == [supported, unknown]

    _, investigator = run(capsys, root, "prepare", "--role", "luna-investigator")
    assert investigator["Investigation Snapshot"] == snapshot
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert "Investigation Findings" not in sol and "Investigation Snapshot" not in sol
    assert "compact behavior" not in json.dumps(sol)

    replacement = [{"id": "S2", "kind": "SUPPORTED", "text": "deduplicated behavior", "derived_from": [0], "supersedes": ["S1"], "evidence_refs": ["src"]}]
    code, rewritten = task_input(root, capsys, {"investigation_snapshot": replacement}, "task-update", "--role", "luna-curator", "--base-revision", "3")
    assert code == 0 and rewritten["state"]["investigation_snapshot"] == replacement
    promoted = [{"id": "S3", "kind": "CONFIRMED", "text": "not proven", "derived_from": [0], "supersedes": ["S2"], "evidence_refs": ["src"]}]
    code, failed = task_input(root, capsys, {"investigation_snapshot": promoted}, "task-update", "--role", "luna-curator", "--base-revision", "4")
    assert code == 2 and ("cannot promote" in failed["error"] or "fresh native" in failed["error"])

    oversized = [{"id": f"B{index}", "kind": "UNKNOWN", "text": "x" * 1000, "derived_from": [1], "supersedes": [], "evidence_refs": []} for index in range(40)]
    code, failed = task_input(root, capsys, {"investigation_snapshot": oversized}, "task-update", "--role", "luna-curator", "--base-revision", "4")
    assert code == 2 and "32768 bytes" in failed["error"]
    too_many = [{"id": f"C{index}", "kind": "UNKNOWN", "text": "x", "derived_from": [1], "supersedes": [], "evidence_refs": []} for index in range(65)]
    code, failed = task_input(root, capsys, {"investigation_snapshot": too_many}, "task-update", "--role", "luna-curator", "--base-revision", "4")
    assert code == 2 and "64 items" in failed["error"]


def test_investigator_and_reviewer_updates_append_without_rewriting_history(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "inspect")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "source", "confidence": "SUPPORTED"}
    first = {"kind": "SUPPORTED", "text": "first finding", "evidence_refs": ["src"]}
    second = {"kind": "UNKNOWN", "text": "second finding", "evidence_refs": []}
    task_input(root, capsys, {"evidence_refs": [ref], "investigation_findings": [first]}, "task-update", "--role", "luna", "--base-revision", "1")
    code, appended = task_input(root, capsys, {"investigation_findings": [second]}, "task-update", "--role", "luna", "--base-revision", "2")
    assert code == 0 and appended["state"]["investigation_findings"] == [first, second]
    state_path = root / ".context/state.json"; before = state_path.read_bytes()
    code, failed = task_input(root, capsys, {"investigation_findings": [first]}, "task-update", "--role", "luna", "--base-revision", "3")
    assert code == 2 and "append-only" in failed["error"] and state_path.read_bytes() == before

    review = {"issue": "missing guard", "impact": "behavior can escape scope", "evidence_refs": ["src"]}
    code, reviewed = task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "terra-reviewer", "--base-revision", "3")
    assert code == 0 and reviewed["state"]["review_findings"] == [review]
    before = state_path.read_bytes()
    code, failed = task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "terra-reviewer", "--base-revision", "4")
    assert code == 2 and "append-only" in failed["error"] and state_path.read_bytes() == before


def test_curator_and_sol_high_cannot_write_control_or_decision_state(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "reason")
    forbidden = (
        ("sol-high", {"verification_target": "pytest"}),
        ("sol-high", {"evidence_refs": []}),
        ("sol-high", {"architectural_intent": "new design"}),
        ("luna-curator", {"decisions": []}),
        ("luna-curator", {"investigation_findings": []}),
    )
    state_path = root / ".context/state.json"; original = state_path.read_bytes()
    for role, update in forbidden:
        code, failed = task_input(root, capsys, update, "task-update", "--role", role, "--base-revision", "1")
        assert code == 2 and "not allowed" in failed["error"] and state_path.read_bytes() == original


def test_new_confirmed_finding_requires_fresh_native_confirmed_evidence(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "confirm")
    source = root / "src.txt"; source.write_text("observed", encoding="utf-8")
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "inspection", "confidence": "SUPPORTED"}
    finding = {"kind": "CONFIRMED", "text": "overstated", "evidence_refs": ["src"]}
    code, failed = task_input(root, capsys, {"evidence_refs": [ref], "investigation_findings": [finding]}, "task-update", "--role", "luna-investigator", "--base-revision", "1")
    assert code == 2 and "CONFIRMED" in failed["error"]


def test_controller_projection_is_bounded_and_curator_receives_only_uncovered_suffix(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "investigate")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "source", "confidence": "SUPPORTED"}
    first = {"kind": "SUPPORTED", "text": "first", "evidence_refs": ["src"]}
    second = {"kind": "UNKNOWN", "text": "second", "evidence_refs": []}
    task_input(root, capsys, {"evidence_refs": [ref], "investigation_findings": [first, second]}, "task-update", "--role", "luna", "--base-revision", "1")
    snapshot = [{"id": "S1", "kind": "SUPPORTED", "text": "compact", "derived_from": [0], "supersedes": [], "evidence_refs": ["src"]}]
    task_input(root, capsys, {"investigation_snapshot": snapshot, "investigation_covered_through": 1}, "task-update", "--role", "luna-curator", "--base-revision", "2")
    _, controller = run(capsys, root, "prepare", "--role", "controller")
    assert controller["Investigation Readiness"] == {"raw_finding_count": 2, "covered_through": 1, "pending_findings": 1, "status": "PENDING"}
    assert controller["Investigation Snapshot"][0]["text"] == "compact"
    assert "Investigation Findings" not in controller and "first" not in json.dumps(controller)
    _, curator = run(capsys, root, "prepare", "--role", "luna-curator")
    assert curator["Uncovered Investigation Findings"] == [second]
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert sol["Investigation Readiness"]["status"] == "PENDING"
    assert "compact" not in json.dumps(sol) and "second" not in json.dumps(sol)
    review = {"issue": "review gap", "impact": "needs decision", "evidence_refs": ["src"]}
    task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "terra-reviewer", "--base-revision", "3")
    _, controller = run(capsys, root, "prepare", "--role", "controller")
    assert controller["Review Readiness"] == {"finding_count": 1, "handled_through": 0, "pending_findings": 1, "status": "PENDING"}
    code, _ = task_input(root, capsys, {"review_handled_through": 1}, "task-update", "--role", "controller", "--base-revision", "4")
    assert code == 0


def test_raw_provenance_and_evidence_identity_are_immutable_for_controller(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "control")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{hashlib.sha256(source.read_bytes()).hexdigest()}", "summary": "source", "confidence": "SUPPORTED"}
    finding = {"kind": "SUPPORTED", "text": "raw", "evidence_refs": ["src"]}
    task_input(root, capsys, {"evidence_refs": [ref], "investigation_findings": [finding]}, "task-update", "--role", "luna", "--base-revision", "1")
    code, bad = task_input(root, capsys, {"investigation_findings": [finding]}, "task-update", "--role", "controller", "--base-revision", "2")
    assert code == 2 and "append-only" in bad["error"]
    rebound = ref | {"summary": "different"}
    code, bad = task_input(root, capsys, {"evidence_refs": [rebound]}, "task-update", "--role", "controller", "--base-revision", "2")
    assert code == 2 and "append-only" in bad["error"]
    review = {"issue": "issue", "impact": "impact", "evidence_refs": ["src"]}
    task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "terra-reviewer", "--base-revision", "2")
    code, bad = task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "controller", "--base-revision", "3")
    assert code == 2 and "append-only" in bad["error"]


def test_migrate_exact_legacy_template_is_safe_and_idempotent(tmp_path, capsys):
    root = repo(tmp_path)
    legacy = "---\nEvidence: NONE\nRevision: 1\nStatus: DRAFT\nApplicability: PROJECT\nConfidence: UNVERIFIED\n---\n\n# Operator notes\n\nUnknown. Record only confirmed operating constraints.\n"
    path = root / ".agent-memory/operator.md"; path.parent.mkdir(); path.write_text(legacy, encoding="utf-8")
    code, migrated = run(capsys, root, "migrate")
    assert code == 0 and ".agent-memory/operator.md" in migrated["migrated"] and not migrated["manual_migration_required"]
    assert "Audience:" in path.read_text(encoding="utf-8") and "Kind:" in path.read_text(encoding="utf-8")
    code, repeat = run(capsys, root, "migrate")
    assert code == 0 and not repeat["migrated"]
    path.write_text(legacy + "User change.\n", encoding="utf-8")
    _, unsafe = run(capsys, root, "migrate")
    assert ".agent-memory/operator.md" in unsafe["manual_migration_required"]


def test_memory_index_failure_fails_closed_and_stale_snapshot_is_unknown(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "inspect")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ref = {"id": "src", "kind": "file", "locator": f"file:src.txt#{digest}", "summary": "source", "confidence": "CONFIRMED"}
    finding = {"kind": "CONFIRMED", "text": "confirmed", "evidence_refs": ["src"]}
    task_input(root, capsys, {"evidence_refs": [ref], "investigation_findings": [finding]}, "task-update", "--role", "luna", "--base-revision", "1")
    snapshot = [{"id": "S1", "kind": "CONFIRMED", "text": "compact", "derived_from": [0], "supersedes": [], "evidence_refs": ["src"]}]
    task_input(root, capsys, {"investigation_snapshot": snapshot}, "task-update", "--role", "luna-curator", "--base-revision", "2")
    source.write_text("changed", encoding="utf-8")
    _, investigator = run(capsys, root, "prepare", "--role", "luna-investigator")
    assert investigator["Investigation Snapshot"][0]["kind"] == "UNKNOWN"
    assert investigator["Investigation Snapshot"][0]["recorded_kind"] == "CONFIRMED"
    (root / ".agent-memory/INDEX.md").write_text("not markdown", encoding="utf-8")
    _, pack = run(capsys, root, "prepare", "--role", "controller")
    assert any("memory routing unavailable" in item["text"] for item in pack["Unknowns"])


def test_effective_stale_projections_cover_contradictions_snapshot_derivation_review_cursor_and_changed_surface(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init"); run(capsys, root, "task-start", "inspect")
    stale_file = root / "stale.txt"; stale_file.write_text("one", encoding="utf-8")
    fresh_file = root / "fresh.txt"; fresh_file.write_text("one", encoding="utf-8")
    stale_ref = {"id": "stale", "kind": "file", "locator": f"file:stale.txt#{hashlib.sha256(stale_file.read_bytes()).hexdigest()}", "summary": "old", "confidence": "SUPPORTED"}
    fresh_ref = {"id": "fresh", "kind": "file", "locator": f"file:fresh.txt#{hashlib.sha256(fresh_file.read_bytes()).hexdigest()}", "summary": "fresh", "confidence": "SUPPORTED"}
    raw = [
        {"kind": "SUPPORTED", "text": "old supported", "evidence_refs": ["stale"]},
        {"kind": "SUPPORTED", "text": "fresh supported", "evidence_refs": ["fresh"]},
        {"kind": "CONTRADICTION", "text": "old contradiction", "evidence_refs": ["stale"]},
    ]
    task_input(root, capsys, {"evidence_refs": [stale_ref, fresh_ref], "investigation_findings": raw}, "task-update", "--role", "luna", "--base-revision", "1")
    snapshot = [{"id": "S1", "kind": "SUPPORTED", "text": "mixed compact", "derived_from": [0, 1], "supersedes": [], "evidence_refs": ["fresh"]}]
    task_input(root, capsys, {"investigation_snapshot": snapshot, "investigation_covered_through": 0}, "task-update", "--role", "luna-curator", "--base-revision", "2")
    review = {"issue": "review gap", "impact": "needs handling", "evidence_refs": ["fresh"]}
    task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "terra-reviewer", "--base-revision", "3")
    stale_file.write_text("two", encoding="utf-8")
    _, curator = run(capsys, root, "prepare", "--role", "luna-curator")
    assert curator["Current Investigation Snapshot"][0]["kind"] == "UNKNOWN"
    assert curator["Current Investigation Snapshot"][0]["recorded_kind"] == "SUPPORTED"
    assert curator["Uncovered Investigation Findings"][2]["kind"] == "UNKNOWN"
    assert curator["Uncovered Investigation Findings"][2]["recorded_kind"] == "CONTRADICTION"
    (root / "dirty.txt").write_text("dirty", encoding="utf-8")
    task_input(root, capsys, {"review_handled_through": 1, "changed_surface": ["manual.txt"]}, "task-update", "--role", "controller", "--base-revision", "4")
    _, controller = run(capsys, root, "prepare", "--role", "controller")
    assert controller["Review Findings"] == []
    assert {"manual.txt", "dirty.txt"} <= set(controller["Changed Surface"])
    assert controller["Investigation Snapshot"][0]["kind"] == "UNKNOWN"


def test_memory_index_nested_traversal_and_fail_closed_missing_cycle_and_unindexed(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    source = root / "src.txt"; source.write_text("one", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    front = f'---\nEvidence: file:src.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\nKind: MEMORY\nAudience: ["sol-high"]\nTopics: ["needle"]\nSymbols: []\n---\n\n'
    nested = root / ".agent-memory/nested"; nested.mkdir()
    (nested / "INDEX.md").write_text(front + "# Nested index\n\n- [Nested fact](fact.md)\n", encoding="utf-8")
    (nested / "fact.md").write_text(front + "# Nested fact\n\nNested recall.\n", encoding="utf-8")
    root_index = root / ".agent-memory/INDEX.md"
    root_index.write_text(root_index.read_text(encoding="utf-8") + "\n- [Nested](nested/INDEX.md)\n", encoding="utf-8")
    _, nested_pack = run(capsys, root, "prepare", "needle", "--role", "sol-high")
    assert any(item.get("source", "").endswith("nested/fact.md") for item in nested_pack["Supported Evidence"])
    (root / ".agent-memory/unindexed.md").write_text(front + "# Unindexed\n\nneedle hidden.\n", encoding="utf-8")
    _, unindexed = run(capsys, root, "prepare", "needle hidden", "--role", "sol-high")
    assert not any(item.get("source", "").endswith("unindexed.md") for item in unindexed["Supported Evidence"])
    root_index.write_text(root_index.read_text(encoding="utf-8") + "\n- [Missing](missing.md)\n", encoding="utf-8")
    _, missing = run(capsys, root, "prepare", "needle", "--role", "sol-high")
    assert any("link missing" in item["text"] for item in missing["Unknowns"])
    root_index.write_text(root_index.read_text(encoding="utf-8").replace("\n- [Missing](missing.md)\n", ""), encoding="utf-8")
    (nested / "INDEX.md").write_text(front + "# Nested index\n\n- [Self](INDEX.md)\n", encoding="utf-8")
    _, cycle = run(capsys, root, "prepare", "needle", "--role", "sol-high")
    assert any("cycle" in item["text"] for item in cycle["Unknowns"])


def test_task_input_evidence_is_supported_without_being_misclassified_as_stale(tmp_path, capsys):
    root = repo(tmp_path); run(capsys, root, "init")
    task_ref = {"id": "request", "kind": "task-input", "locator": "user request", "summary": "stated requirement", "confidence": "SUPPORTED"}
    task_input(root, capsys, {"evidence_refs": [task_ref]}, "task-start", "inspect")
    raw = {"kind": "SUPPORTED", "text": "request requires guard", "evidence_refs": ["request"]}
    task_input(root, capsys, {"investigation_findings": [raw]}, "task-update", "--role", "luna", "--base-revision", "1")
    snapshot = [{"id": "S1", "kind": "SUPPORTED", "text": "compact guard", "derived_from": [0], "supersedes": [], "evidence_refs": ["request"]}]
    task_input(root, capsys, {"investigation_snapshot": snapshot, "investigation_covered_through": 0}, "task-update", "--role", "luna-curator", "--base-revision", "2")
    review = {"issue": "missing guard", "impact": "request can fail", "evidence_refs": ["request"]}
    task_input(root, capsys, {"review_findings": [review]}, "task-update", "--role", "terra-reviewer", "--base-revision", "3")
    _, curator = run(capsys, root, "prepare", "--role", "luna-curator")
    assert curator["Uncovered Investigation Findings"][0]["kind"] == "SUPPORTED"
    assert curator["Current Investigation Snapshot"][0]["kind"] == "SUPPORTED"
    _, controller = run(capsys, root, "prepare", "--role", "controller")
    assert controller["Review Findings"][0]["effective_state"] == "SUPPORTED"
