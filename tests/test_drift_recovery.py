from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from thaliris import codex_adapter, codex_app_server, core, host_preflight, lifecycle, offline_recovery, runtime_identity


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    codex_adapter.init(root)
    task = core.task_start(root, "original incomplete goal", None, None)
    ledger = lifecycle._lifecycle_path(root, task["task_id"])
    home = tmp_path / "disconnected-home"
    home.mkdir()
    (home / "hooks.json").write_text('{"hooks":{}}')
    return root, task, ledger, home


def _packet(root, task, ledger, home):
    return dict(root=root, task_id=task["task_id"], revision=1,
                state_sha256=hashlib.sha256((root / ".context/state.json").read_bytes()).hexdigest(),
                lifecycle_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.exists() else "ABSENT",
                reason="user delegated forced recovery of an obsolete task", codex_home=home,
                operator_asserted_user_delegation=True, integration_disconnected=True)


@pytest.mark.parametrize("malformed", [False, True])
def test_offline_recovery_exact_archival_and_partial_identity_fencing(tmp_path, malformed):
    root, task, ledger, home = _repo(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    owner, child = hashlib.sha256(b"owner").hexdigest(), hashlib.sha256(b"unbound-child").hexdigest()
    raw = json.dumps({"version": 999, "owner_session_id_hash": owner,
                      "pending_authorized_spawn": {"agent_id_hash": child}, "children": "incompatible", "old": True}).encode()
    if malformed:
        raw = raw[:-1] + b', "truncated":'
    ledger.write_bytes(raw)
    state_raw = (root / ".context/state.json").read_bytes()
    result = offline_recovery.recover(**_packet(root, task, ledger, home))
    archive = root / result["archive"]
    assert (archive / "state.json").read_bytes() == state_raw
    assert (archive / "lifecycle.json").read_bytes() == raw
    assert not (root / ".context/state.json").exists()
    record = json.loads((archive / "manifest.json").read_text())
    assert record["recovery_authority"] == offline_recovery.AUTHORITY
    assert record["recovery_session_id_hash"] == "UNKNOWN"
    assert record["recovery_host_attestation"] == "ABSENT"
    assert record["host_termination"] == "UNKNOWN"
    assert owner in lifecycle._read_session_fence(root)
    assert child in lifecycle._read_abandoned_agent_hashes(root)
    # No fabricated session or turn is needed to fence a known child thread.
    payload = {"agent_id": "unbound-child", "tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert "ABANDONED_ROLE_SESSION" in lifecycle.handle_hook(root, "PreToolUse", payload)
    assert "original incomplete goal" in (archive / "state.json").read_text()


@pytest.mark.parametrize("changed", ["state_sha256", "lifecycle_sha256", "revision", "task_id", "assertion", "integration"])
def test_offline_recovery_cas_and_operational_gate(tmp_path, changed):
    root, task, ledger, home = _repo(tmp_path)
    packet = _packet(root, task, ledger, home)
    original = (root / ".context/state.json").read_bytes()
    if changed in {"state_sha256", "lifecycle_sha256"}:
        packet[changed] = "f" * 64
    elif changed == "revision":
        packet[changed] = 2
    elif changed == "task_id":
        packet[changed] = "11111111-1111-1111-1111-111111111111"
    elif changed == "assertion":
        packet["operator_asserted_user_delegation"] = False
    else:
        (home / "hooks.json").write_text('{"hooks":{"PreToolUse":[{"hooks":[{"command":"thaliris audit-hook"}]}]}}')
    with pytest.raises(ValueError):
        offline_recovery.recover(**packet)
    assert (root / ".context/state.json").read_bytes() == original
    assert not list((root / ".context/audit/abandoned").glob("*/manifest.json"))


@pytest.mark.parametrize("appearance", ["file", "directory"])
def test_offline_recovery_reobserves_absent_ledger_before_release(tmp_path, monkeypatch, appearance):
    root, task, ledger, home = _repo(tmp_path)
    packet = _packet(root, task, ledger, home)
    assert packet["lifecycle_sha256"] == "ABSENT"
    original = (root / ".context/state.json").read_bytes()
    observe = offline_recovery._disconnected
    observations = 0

    def late_ledger(codex_home):
        nonlocal observations
        result = observe(codex_home)
        observations += 1
        if observations == 2:
            ledger.parent.mkdir(parents=True, exist_ok=True)
            if appearance == "file":
                ledger.write_text('{"children":[{"agent_id":"late-child"}]}')
            else:
                ledger.mkdir()
        return result

    monkeypatch.setattr(offline_recovery, "_disconnected", late_ledger)
    with pytest.raises((ValueError, OSError)):
        offline_recovery.recover(**packet)
    assert observations == 2
    assert (root / ".context/state.json").read_bytes() == original
    assert ledger.exists()
    archives = list((root / ".context/audit/abandoned").glob("*/state.json"))
    assert len(archives) == 1 and archives[0].read_bytes() == original
    assert hashlib.sha256(b"late-child").hexdigest() not in lifecycle._read_abandoned_agent_hashes(root)


def test_actor_source_contract_does_not_mint_controller_authority(tmp_path):
    contract = json.loads((Path(__file__).parent / "fixtures/codex-0159-actor-source-contract.json").read_text())
    assert contract["provenance"] == "SOURCE_CONTRACT_NOT_LIVE_CAPTURE"
    assert lifecycle._controller_actor_assurance(contract["thread_spawn_pretool"]) == "CHILD"
    ambiguous = contract["builtin_review_pretool"]
    assert lifecycle._controller_actor_assurance(ambiguous) == "UNKNOWN"
    root, task, _ledger, _home = _repo(tmp_path)
    lifecycle.record_task_start_owner(root, task["task_id"], hashlib.sha256(ambiguous["session_id"].encode()).hexdigest())
    for command in ("thaliris task-start goal", "thaliris task-update --role controller --base-revision 1",
                    "thaliris task-abandon", "Set-Content .context/state.json '{}'"):
        payload = {**ambiguous, "tool_input": {"command": command}}
        assert "CONTROLLER_ACTOR_UNKNOWN" in lifecycle.handle_hook(root, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI)
    for command in ("git status", "pytest tests/test_roles.py", "Set-Content src/example.py 'source repair'"):
        assert lifecycle.handle_hook(root, "PreToolUse", {**ambiguous, "tool_input": {"command": command}}, lifecycle.MANAGED_HOOK_ABI) == ""
    assert not (root / ".context/audit/task-start-attestations").exists()
    assert "CONTROLLER_ACTOR_UNKNOWN" in lifecycle._issue_task_start_attestation(root, ambiguous, lifecycle.MANAGED_HOOK_ABI)
    with pytest.raises(ValueError, match="CONTROLLER_ACTOR_UNKNOWN"):
        lifecycle.consume_task_start_attestation(root, "old-receipt")


def test_unknown_actor_can_delegate_ordinary_fresh_work_without_managed_grant(tmp_path):
    root = tmp_path / "ordinary"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    codex_adapter.init(root)
    payload = {"session_id": "ambiguous", "tool_name": "spawn_agent",
               "tool_input": {"agent_type": "thaliris-implementer", "fork_turns": "none", "message": "ordinary authorized source repair"}}
    assert lifecycle.handle_hook(root, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI) == ""
    assert not (root / ".context/state.json").exists()
    assert not list((root / ".context/audit/lifecycle").glob("*.json"))
    payload["tool_input"]["fork_turns"] = "all"
    assert "ISOLATION_REQUIRED" in lifecycle.handle_hook(root, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI)


@pytest.mark.parametrize("actor", [{}, {"agent_id": "child", "agent_type": "thaliris-reviewer"}])
def test_all_automated_actors_denied_offline_route_under_integration(tmp_path, actor):
    root, _task, _ledger, _home = _repo(tmp_path)
    payload = {**actor, "tool_name": "Bash", "tool_input": {"command": "python -I -B tools/thaliris_offline_recovery.py --root ."}}
    assert "OFFLINE_ADMINISTRATION_REQUIRES_DISCONNECTED_INTEGRATION" in lifecycle.handle_hook(root, "PreToolUse", payload)
    assert not lifecycle._offline_administration_requested({"tool_name": "Bash", "tool_input": {"command": "Get-Content tools/thaliris_offline_recovery.py"}})
    assert not lifecycle._offline_administration_requested({"tool_name": "apply_patch", "tool_input": {"patch": "*** Update File: src/thaliris/offline_recovery.py"}})


def test_connection_facts_do_not_invent_daemon_version_from_cli(monkeypatch, tmp_path):
    client = object.__new__(codex_app_server.CodexAppServer)
    client.codex_home = tmp_path
    client.executable = "observed-cli"
    client.initialize_observation = {"codexHome": str(tmp_path), "userAgent": "codex/0.159.2"}
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess([], 0, "codex 0.159.2", ""))
    facts = client.connection_facts()
    assert facts["cli_version"] == "codex 0.159.2"
    assert facts["daemon_version"] == "UNKNOWN"
    assert facts["daemon_control_authority"] == "UNKNOWN"
    assert facts["live_role_catalog"] == "UNKNOWN"


def test_reviewed_source_runner_releases_only_disposable_exact_task(tmp_path):
    root, task, ledger, home = _repo(tmp_path)
    packet = _packet(root, task, ledger, home)
    runner = Path(__file__).resolve().parents[1] / "tools/thaliris_offline_recovery.py"
    result = subprocess.run([sys.executable, "-I", "-B", str(runner), "--root", str(root),
        "--codex-home", str(home), "--task-id", task["task_id"], "--revision", "1",
        "--state-sha256", packet["state_sha256"], "--lifecycle-sha256", "ABSENT",
        "--reason", packet["reason"], "--operator-asserted-user-delegation", "--integration-disconnected"],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["recovery_authority"] == offline_recovery.AUTHORITY
    assert not (root / ".context/state.json").exists()


def test_manifest_diff_treats_new_bytecode_as_execution_input(pinned_test_thaliris):
    exe, _ = pinned_test_thaliris
    prior = runtime_identity.manifest_bytes(exe)
    cache = exe.parent.parent / "Lib/site-packages/thaliris/__pycache__"
    cache.mkdir()
    (cache / "cli.cpython-311.pyc").write_bytes(b"unverified executable input")
    result = runtime_identity.diagnose_manifest(prior)
    difference = result["differences"][0]
    assert result["execution_assurance"] == "UNKNOWN"
    assert difference["surface"] == "python_bytecode"
    assert difference["expected"] == "ABSENT"


def test_drifted_runtime_never_probed_or_imported_during_install(tmp_path, monkeypatch, pinned_test_thaliris):
    exe, digest = pinned_test_thaliris
    home = tmp_path / "home"
    assert codex_adapter.codex_install(home, exe, digest)["ok"] is True
    prior = (home / runtime_identity.MANIFEST_NAME).read_bytes()
    (exe.parent.parent / "Lib/site-packages/thaliris/cli.py").write_text("unverified runtime")
    def forbidden_probe(*_args):
        raise AssertionError("changed runtime reached executable/import probe")
    monkeypatch.setattr(codex_adapter, "_host_install_executable", forbidden_probe)
    result = codex_adapter.codex_install(home, exe, digest)
    assert result["ok"] is False
    assert (home / runtime_identity.MANIFEST_NAME).read_bytes() == prior
    assert any("installed_runtime_changed_in_place" in item and "cli.py" in item for item in result["manual_action_required"])


@pytest.mark.parametrize("unsafe", ["directory", "symlink", "broken_symlink", "ancestor_symlink", "ancestor_junction"])
def test_unsafe_manifest_never_reaches_runtime_probe(tmp_path, monkeypatch, pinned_test_thaliris, unsafe):
    exe, digest = pinned_test_thaliris
    home = tmp_path / "home"
    home.mkdir()
    manifest = home / runtime_identity.MANIFEST_NAME
    if unsafe == "directory":
        manifest.mkdir()
    elif unsafe in {"symlink", "broken_symlink"}:
        target = tmp_path / "manifest-target.json"
        if unsafe == "symlink":
            target.write_bytes(runtime_identity.manifest_bytes(exe))
        try:
            manifest.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"symlink unavailable: {exc}")
    else:
        target = tmp_path / "host-parent"
        target.mkdir()
        link = tmp_path / "linked-parent"
        if unsafe == "ancestor_junction":
            if os.name != "nt":
                pytest.skip("Windows junction")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            assert result.returncode == 0, result.stderr
        else:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                pytest.skip(f"symlink unavailable: {exc}")
        # Also reject linked ancestry when the manifest/home do not yet exist.
        home = link / "new-home"
        manifest = home / runtime_identity.MANIFEST_NAME

    def forbidden_probe(*_args):
        raise AssertionError("unsafe manifest reached executable/import probe")

    monkeypatch.setattr(codex_adapter, "_host_install_executable", forbidden_probe)
    result = codex_adapter.codex_install(home, exe, digest)
    assert result["ok"] is False
    assert any("installed_runtime_manifest_unavailable" in item for item in result["manual_action_required"])
    if unsafe.startswith("ancestor_"):
        assert not home.exists()
    elif unsafe == "directory":
        assert manifest.is_dir()
    else:
        assert manifest.is_symlink()


def _windows_hook(tmp_path, exe, *, drift=True):
    launcher = exe.parent / "dispatch.cmd"
    launcher.write_bytes(b"@echo off\r\necho SHOULD_NOT_EXECUTE\r\n")
    home = tmp_path / "host home"
    home.mkdir()
    (home / host_preflight.NAME).write_bytes(host_preflight.script_bytes())
    (home / lifecycle.HOST_HOOK_SCRIPT_NAME).write_bytes(lifecycle.host_hook_script_bytes())
    manifest = runtime_identity.manifest_bytes(launcher)
    (home / runtime_identity.MANIFEST_NAME).write_bytes(manifest)
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/thaliris.json").write_text('{}')
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    command = lifecycle.host_hook_spec(home, launcher, hashlib.sha256(launcher.read_bytes()).hexdigest(), runtime_identity.manifest_identity(manifest))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert len(command) < 8191
    assert max(map(len, lifecycle.host_hook_script_bytes().decode().splitlines())) < 8191
    assert lifecycle._pinned_host_payload(command)["script"] == str(home / lifecycle.HOST_HOOK_SCRIPT_NAME)
    if drift:
        (exe.parent.parent / "Lib/site-packages/thaliris/cli.py").write_text("tampered runtime")
    return command, home


@pytest.mark.skipif(os.name != "nt", reason="Windows platform preflight")
def test_windows_degraded_policy_allows_repair_and_denies_control(tmp_path, pinned_test_thaliris):
    exe, _ = pinned_test_thaliris
    command, _home = _windows_hook(tmp_path, exe)
    for tool, tool_input, denied in [("Bash", {"command": "pytest tests/test_roles.py"}, False),
                                      ("apply_patch", {"patch": "*** Update File: src/x.py"}, False),
                                      ("spawn_agent", {"agent_type": "thaliris-implementer", "fork_turns": "none", "message": "authorized source repair"}, False),
                                      ("spawn_agent", {}, True),
                                      ("Bash", {"command": "Set-Content .context/state.json '{}'"}, True),
                                      ("Bash", {"command": "python tools/thaliris_offline_recovery.py"}, True)]:
        payload = json.dumps({"tool_name": tool, "tool_input": tool_input}).encode()
        result = subprocess.run(command, shell=True, cwd=tmp_path, input=payload, capture_output=True, timeout=15)
        assert result.returncode == 0, result.stderr
        assert b"SHOULD_NOT_EXECUTE" not in result.stdout
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert (output.get("permissionDecision") == "deny") == denied
        assert "THALIRIS_RUNTIME_DRIFT" in output["additionalContext"]


@pytest.mark.skipif(os.name != "nt", reason="Windows platform preflight")
@pytest.mark.parametrize("damage", ["runtime", "preflight", "trampoline"])
@pytest.mark.parametrize("restriction", ["absent", "active", "invalid", "state_directory", "fence", "child", "inherited", "reuse", "override", "foreign_cwd"])
def test_windows_degraded_fresh_delegation_has_no_managed_grant(tmp_path, pinned_test_thaliris, damage, restriction):
    exe, _ = pinned_test_thaliris
    command, home = _windows_hook(tmp_path, exe)
    if damage == "preflight":
        (home / host_preflight.NAME).write_text("throw 'SHOULD_NOT_EXECUTE'")
    elif damage == "trampoline":
        (home / lifecycle.HOST_HOOK_SCRIPT_NAME).write_text("@echo SHOULD_NOT_EXECUTE")
    payload = {"session_id": "ordinary-session", "tool_name": "functions.spawn_agent",
               "tool_input": {"agent_type": "thaliris-implementer", "fork_turns": "none", "message": "authorized source repair"}}
    state = tmp_path / ".context/state.json"
    if restriction in {"active", "invalid", "state_directory"}:
        state.parent.mkdir()
        if restriction == "state_directory":
            state.mkdir()
        else:
            state.write_text('{"status":"ACTIVE"}' if restriction == "active" else '{"malformed":')
    elif restriction == "fence":
        fence = tmp_path / ".context/audit/abandoned/session-fence.json"
        fence.parent.mkdir(parents=True)
        fence.write_text(json.dumps({"version": 1, "session_id_hashes": [hashlib.sha256(b"ordinary-session").hexdigest()]}))
    elif restriction == "child":
        payload.update(agent_id="known-child", agent_type="thaliris-focused-implementer")
    elif restriction == "inherited":
        payload["tool_input"]["fork_turns"] = "all"
    elif restriction == "reuse":
        payload["tool_name"] = "followup_task"
    elif restriction == "override":
        payload["tool_input"]["model"] = "unapproved-model"
    elif restriction == "foreign_cwd":
        other = tmp_path / "other-worktree"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        (other / ".context").mkdir()
        (other / ".context/state.json").write_text('{"status":"ACTIVE"}')
        payload["cwd"] = str(other)
    result = subprocess.run(command, shell=True, cwd=tmp_path, input=json.dumps(payload).encode(), capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert b"SHOULD_NOT_EXECUTE" not in result.stdout
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert (output.get("permissionDecision") == "deny") == (restriction != "absent")
    assert "THALIRIS_RUNTIME_DRIFT" in output["additionalContext"]
    assert not (tmp_path / ".context/audit/lifecycle").exists()
    assert not (tmp_path / ".context/audit/task-start-attestations").exists()
    if restriction == "absent":
        assert not state.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows platform preflight")
def test_windows_packed_hook_preserves_exact_ownership_and_healthy_dispatch(tmp_path, pinned_test_thaliris):
    exe, _ = pinned_test_thaliris
    command, _home = _windows_hook(tmp_path, exe, drift=False)
    prefix = 'powershell.exe -NoProfile -NonInteractive -Command "'
    assert command.startswith(prefix)
    assert command.endswith('"')
    packed_expression = command[len(prefix):-1]
    source = host_preflight.unpack_literal(packed_expression)
    altered_expression = host_preflight.packed_literal_without_variables(source + ";Write-Output 'altered'")
    altered = prefix + altered_expression + '"'
    assert lifecycle._pinned_host_payload(altered) is None
    assert lifecycle._pinned_host_payload(command + ";Write-Output 'altered'") is None
    assert lifecycle._pinned_host_payload(command[:-1]) is None
    truncated = prefix + host_preflight._VARIABLE_FREE_PACKED_PREFIX + "H4sI" + host_preflight._VARIABLE_FREE_PACKED_SUFFIX + '"'
    assert lifecycle._pinned_host_payload(truncated) is None
    oversized = prefix + host_preflight.packed_literal_without_variables("X" * 65537) + '"'
    assert lifecycle._pinned_host_payload(oversized) is None
    payload = {"tool_name": "Bash", "tool_input": {"command": "Write-Output 'HOOK_INPUT_MUST_NOT_EVALUATE'"}}
    result = subprocess.run(command, shell=True, cwd=tmp_path, input=json.dumps(payload).encode(), capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert b"SHOULD_NOT_EXECUTE" in result.stdout  # Healthy fixture launcher dispatched.
    assert b"HOOK_INPUT_MUST_NOT_EVALUATE" not in result.stdout
