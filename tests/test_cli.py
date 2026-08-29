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
        "sol-high": {"Goal", "Confirmed Facts", "Supported Evidence", "Hard Constraints", "Decisions", "Unknowns", "Contradictions", "Evidence refs"},
        "luna": {"Goal", "Relevant Files", "Relevant Symbols", "Unknowns", "Contradictions", "Evidence refs", "Investigation Target", "Verification Target"},
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
    result = doctor._adapter("cachebro", "0.2.2", {"command": "cachebro"}, True, True)
    assert result["installed"] == "YES" and "healthy" not in result


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
    assert code == 2 and "conflict" in failed["error"] and state.read_bytes() == original
    code, failed = task_input(root, capsys, {"confirmed_facts": [{"text": "bad", "evidence_refs": ["missing"]}]}, "task-update", "--role", "terra-implementer", "--base-revision", "2")
    assert code == 2 and "statement" in failed["error"]
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
    code, updated = task_input(root, capsys, {"evidence_refs": [e], "supported_evidence": [{"text": "likely behavior", "evidence_refs": ["s"]}], "verification_target": "pytest"}, "task-update", "--role", "luna", "--base-revision", "1")
    assert code == 0
    _, sol = run(capsys, root, "prepare", "--role", "sol-high")
    assert "Confirmed Facts" in sol and sol["Confirmed Facts"] == [] and sol["Supported Evidence"][0]["text"] == "likely behavior"
    _, review = run(capsys, root, "prepare", "--role", "terra-reviewer")
    assert "Unknowns" not in review and "Known Risks" not in review and "check" not in " ".join(review)


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
    front_matter = f'---\nEvidence: file:source.txt#{digest}\nRevision: 1\nStatus: ACTIVE\nApplicability: PROJECT\nConfidence: SUPPORTED\nAudience: ["terra-reviewer"]\nTopics: ["review-memory"]\nSymbols: []\n---\n\n'
    policy = root / ".agent-memory/policy-reviewer.md"
    policy.write_text(front_matter + "# Review policy\n\nPreserve the public contract.\n", encoding="utf-8")
    unrelated = root / ".agent-memory/fact-reviewer.md"
    unrelated.write_text(front_matter + "# Unrelated fact\n\nAn implementation observation.\n", encoding="utf-8")
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
