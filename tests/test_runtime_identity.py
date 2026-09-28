from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from thaliris import codex_adapter, lifecycle, runtime_identity


def _pin_installed_hook(monkeypatch, home: Path, executable: Path) -> Path:
    manifest = home / runtime_identity.MANIFEST_NAME
    monkeypatch.setenv(lifecycle.THALIRIS_EXECUTABLE_ENV, str(executable))
    monkeypatch.setenv(lifecycle.THALIRIS_EXECUTABLE_SHA256_ENV, hashlib.sha256(executable.read_bytes()).hexdigest())
    monkeypatch.setenv(lifecycle.THALIRIS_RUNTIME_SHA256_ENV, runtime_identity.manifest_identity(manifest.read_bytes()))
    monkeypatch.setenv("THALIRIS_INSTALL_MANIFEST", str(manifest))
    return home / lifecycle.HOST_RUN_SCRIPT_NAME


def test_install_manifest_pins_package_and_reports_restart(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    exe, exe_sha = pinned_test_thaliris
    result = codex_adapter.codex_install()

    manifest = (home / runtime_identity.MANIFEST_NAME).read_bytes()
    identity = hashlib.sha256(manifest).hexdigest()
    record = runtime_identity.validate_manifest(manifest, exe, identity)
    assert result["ok"] is True
    assert result["installed_runtime_identity"] == identity
    assert result["install_status"] == "RESTART_CODEX_ONCE"
    assert result["session_restart_required"] is True
    assert (home / lifecycle.HOST_RUN_SCRIPT_NAME).read_bytes() == lifecycle.host_run_script_bytes(exe, identity)
    assert str(home / lifecycle.HOST_RUN_SCRIPT_NAME).encode() in (home / "AGENTS.md").read_bytes()
    assert record["executable_sha256"] == exe_sha
    assert {"pyvenv.cfg", "Scripts/test-host-executable.exe", "Lib/site-packages/thaliris/__init__.py", "Lib/site-packages/thaliris/cli.py", "Lib/site-packages/thaliris/lifecycle.py"} <= set(record["files"])
    commands = json.loads((home / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert all(lifecycle._host_hook_command_is_managed(group["hooks"][0], event, home, require_current_pin=True)
               for event in lifecycle.HOOK_EVENTS for group in commands[event])

    package_file = exe.parent.parent / "Lib" / "site-packages" / "thaliris" / "lifecycle.py"
    package_file.write_text("HOOK_ABI = 11\n", encoding="utf-8")
    assert lifecycle.host_hooks_health(home)["hooks_configured"] == "NO"
    second = codex_adapter.codex_install()
    assert second["ok"] is False
    assert second["changed"] is False
    assert (home / runtime_identity.MANIFEST_NAME).read_bytes() == manifest


def test_idempotent_host_install_does_not_request_another_restart(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    first = codex_adapter.codex_install()
    second = codex_adapter.codex_install()
    assert first["install_status"] == "RESTART_CODEX_ONCE"
    assert second["ok"] is True
    assert second["changed"] is False
    assert second["install_status"] == "HOST_INTEGRATION_UNCHANGED"
    assert second["session_restart_required"] is False


def test_install_upgrades_previous_owned_runner(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    executable, _ = pinned_test_thaliris
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_adapter.codex_install()["ok"] is True
    manifest = (home / runtime_identity.MANIFEST_NAME).read_bytes()
    runner = home / lifecycle.HOST_RUN_SCRIPT_NAME
    runner.write_bytes(lifecycle._previous_host_run_script_bytes(executable, runtime_identity.manifest_identity(manifest)))
    upgraded = codex_adapter.codex_install()
    assert upgraded["ok"] is True
    assert upgraded["install_status"] == "RESTART_CODEX_ONCE"
    assert runner.read_bytes() == lifecycle.host_run_script_bytes(executable, runtime_identity.manifest_identity(manifest))


def test_powershell_runner_receipt_and_host_maintenance_are_direct_only(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    executable, _ = pinned_test_thaliris
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_adapter.codex_install()["ok"] is True
    runner = _pin_installed_hook(monkeypatch, home, executable)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    receipt = codex_adapter._controller_bridge()["controller_bridge_sha256"]
    direct = {
        "session_id": "owner", "turn_id": "start", "tool_name": "Bash",
        "tool_input": {"command": f"& '{runner}' --root '{tmp_path}' task-start 'goal' --bootstrap-receipt '{receipt}'"},
    }
    start = json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", direct, lifecycle.MANAGED_HOOK_ABI))
    assert start["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "--hook-attestation" in start["hookSpecificOutput"]["updatedInput"]["command"]

    from thaliris import core
    started = core.task_start(tmp_path, "unfinished", None, None)
    lifecycle.record_task_start_owner(tmp_path, started["task_id"], hashlib.sha256(b"owner").hexdigest())
    for operation in ("codex-install", "codex-uninstall"):
        payload = {**direct, "tool_input": {"command": f"& '{runner}' {operation}"}}
        assert lifecycle.handle_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI) == ""
        payload["tool_input"] = {"command": f"thaliris {operation}"}
        assert "THALIRIS_CONTROLLER_BOUNDARY" in lifecycle.handle_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI)
        payload["tool_input"] = {"command": f"& '{runner}' {operation}; git status"}
        assert "THALIRIS_CONTROLLER_BOUNDARY" in lifecycle.handle_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI)
    source = {**direct, "tool_input": {"command": "git status"}}
    assert "THALIRIS_CONTROLLER_BOUNDARY" in lifecycle.handle_hook(tmp_path, "PreToolUse", source, lifecycle.MANAGED_HOOK_ABI)
    package_code = executable.parent.parent / "Lib" / "site-packages" / "thaliris" / "lifecycle.py"
    package_code.write_text("changed after install\n", encoding="utf-8")
    maintenance = {**direct, "tool_input": {"command": f"& '{runner}' codex-install"}}
    assert "THALIRIS_CONTROLLER_BOUNDARY" in lifecycle.handle_hook(tmp_path, "PreToolUse", maintenance, lifecycle.MANAGED_HOOK_ABI)


def test_self_invoked_uninstall_retains_inert_runner_for_direct_cleanup_or_reinstall(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_adapter.codex_install()["ok"] is True
    runner = home / lifecycle.HOST_RUN_SCRIPT_NAME
    monkeypatch.setenv("THALIRIS_RUN_SCRIPT", str(runner))
    removed = codex_adapter.codex_uninstall()
    assert removed["ok"] is True
    assert removed["status"] == "UNINSTALLED_INERT_RUNNER_RETAINED"
    assert removed["retained_inert_runner"] is True
    assert runner.exists() and lifecycle.installed_run_script_identity(runner.read_bytes()) is not None
    assert not (home / runtime_identity.MANIFEST_NAME).exists()
    assert removed["host_hook_registration_present"] == "NO"
    monkeypatch.delenv("THALIRIS_RUN_SCRIPT")
    cleaned = codex_adapter.codex_uninstall()
    assert cleaned["ok"] is True
    assert not runner.exists()

    assert codex_adapter.codex_install()["ok"] is True
    monkeypatch.setenv("THALIRIS_RUN_SCRIPT", str(runner))
    codex_adapter.codex_uninstall()
    monkeypatch.delenv("THALIRIS_RUN_SCRIPT")
    assert codex_adapter.codex_install()["ok"] is True
    assert (home / runtime_identity.MANIFEST_NAME).exists()


def test_previous_runner_without_self_marker_is_retained_until_direct_cleanup(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_adapter.codex_install()["ok"] is True
    runner = home / lifecycle.HOST_RUN_SCRIPT_NAME
    manifest = (home / runtime_identity.MANIFEST_NAME).read_bytes()
    record = runtime_identity.validate_manifest_record(manifest)
    old_runner = lifecycle._previous_host_run_script_bytes(Path(record["executable"]), runtime_identity.manifest_identity(manifest))
    runner.write_bytes(old_runner)
    monkeypatch.delenv("THALIRIS_RUN_SCRIPT", raising=False)
    removed = codex_adapter.codex_uninstall()
    assert removed["ok"] is True
    assert removed["retained_inert_runner"] is True
    assert runner.read_bytes() == old_runner
    assert not (home / runtime_identity.MANIFEST_NAME).exists()
    cleaned = codex_adapter.codex_uninstall()
    assert cleaned["ok"] is True
    assert not runner.exists()


def test_separate_host_checkout_stays_available_when_project_is_active(tmp_path: Path) -> None:
    from thaliris import core
    active = tmp_path / "active-project"
    maintenance = tmp_path / "host-maintenance"
    for root in (active, maintenance):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    codex_adapter.init(active)
    core.task_start(active, "unfinished", None, None)
    source_command = {
        "session_id": "host-session", "turn_id": "maintenance", "tool_name": "Bash",
        "cwd": str(maintenance), "tool_input": {"command": "git status"},
    }
    assert lifecycle.handle_hook(active, "PreToolUse", source_command, lifecycle.MANAGED_HOOK_ABI) == ""
    source_command["cwd"] = str(active)
    assert "THALIRIS_ACTIVE_OWNER_REQUIRED" in lifecycle.handle_hook(active, "PreToolUse", source_command, lifecycle.MANAGED_HOOK_ABI)


def test_install_rejects_user_manifest_conflict(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    manifest_path = home / runtime_identity.MANIFEST_NAME
    manifest_path.write_text('{"user":"owned"}\n', encoding="utf-8")

    result = codex_adapter.codex_install()

    assert result["ok"] is False
    assert result["host_hook_registration_present"] == "NO"
    assert manifest_path.read_text(encoding="utf-8") == '{"user":"owned"}\n'


def test_manifest_identity_rejects_digest_and_extra_package_file(tmp_path: Path, pinned_test_thaliris) -> None:
    exe, _ = pinned_test_thaliris
    contents = runtime_identity.manifest_bytes(exe)
    identity = runtime_identity.manifest_identity(contents)
    try:
        runtime_identity.validate_manifest(contents + b" ", exe, identity)
    except ValueError as exc:
        assert "identity mismatch" in str(exc)
    else:
        raise AssertionError("manifest byte drift was accepted")

    package = exe.parent.parent / "Lib" / "site-packages" / "thaliris"
    (package / "extra.json").write_text("{}", encoding="utf-8")
    try:
        runtime_identity.validate_manifest(contents, exe, identity)
    except ValueError as exc:
        assert "runtime changed" in str(exc)
    else:
        raise AssertionError("added package data was accepted")


def test_venv_inputs_and_bytecode_caches_are_pinned(tmp_path: Path, pinned_test_thaliris) -> None:
    exe, _ = pinned_test_thaliris
    venv = exe.parent.parent
    interpreter = exe.parent / "python.exe"
    interpreter.write_bytes(b"interpreter")
    pth = venv / "Lib" / "site-packages" / "runtime.pth"
    pth.write_text("# fixed\n", encoding="utf-8")
    for path in (interpreter, venv / "pyvenv.cfg", pth):
        manifest = runtime_identity.manifest_bytes(exe)
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        try:
            runtime_identity.validate_manifest(manifest, exe, runtime_identity.manifest_identity(manifest))
        except ValueError:
            pass
        else:
            raise AssertionError(f"runtime mutation accepted: {path}")
        path.write_bytes(original)
    cache = venv / "Lib" / "site-packages" / "thaliris" / "__pycache__"
    cache.mkdir()
    (cache / "cli.cpython-311.pyc").write_bytes(b"cache")
    (venv / "Lib" / "site-packages" / "thaliris" / "cli.pyc").write_bytes(b"cache")
    manifest = runtime_identity.manifest_bytes(exe)
    (cache / "cli.cpython-311.pyc").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="runtime changed"):
        runtime_identity.validate_manifest(manifest, exe, runtime_identity.manifest_identity(manifest))


def test_drifted_old_runtime_can_be_replaced_at_new_path_and_uninstalled(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    exe, _ = pinned_test_thaliris
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_adapter.codex_install()["ok"] is True
    prior = (home / runtime_identity.MANIFEST_NAME).read_bytes()
    (exe.parent.parent / "Lib" / "site-packages" / "thaliris" / "cli.py").write_text("drifted\n", encoding="utf-8")
    import shutil
    new_venv = tmp_path / "new-runtime"
    shutil.copytree(exe.parent.parent, new_venv)
    new_exe = new_venv / "Scripts" / exe.name
    digest = hashlib.sha256(new_exe.read_bytes()).hexdigest()
    monkeypatch.setattr(codex_adapter, "_host_install_executable", lambda *_: (new_exe, digest, None))
    replacement = codex_adapter.codex_install()
    assert replacement["ok"] is True
    audit_paths = list(home.glob("thaliris-install-audit-*.json"))
    assert len(audit_paths) == 1
    audit = json.loads(audit_paths[0].read_text(encoding="utf-8"))
    import base64
    assert base64.b64decode(audit["prior_manifest_base64"]) == prior
    assert audit["observed_runtime_sha256"] != runtime_identity.manifest_identity(prior)
    (new_venv / "pyvenv.cfg").write_text("more drift\n", encoding="utf-8")
    result = codex_adapter.codex_uninstall()
    assert result["ok"] is True
    assert not (home / runtime_identity.MANIFEST_NAME).exists()
    assert not (home / lifecycle.HOST_RUN_SCRIPT_NAME).exists()
    assert len(list(home.glob("thaliris-install-audit-*.json"))) >= 2


def test_missing_old_runtime_allows_new_path_replacement(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    import shutil
    exe, _ = pinned_test_thaliris
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert codex_adapter.codex_install()["ok"] is True
    prior = (home / runtime_identity.MANIFEST_NAME).read_bytes()
    new_venv = tmp_path / "new-runtime"
    shutil.copytree(exe.parent.parent, new_venv)
    shutil.rmtree(exe.parent.parent)
    new_exe = new_venv / "Scripts" / exe.name
    digest = hashlib.sha256(new_exe.read_bytes()).hexdigest()
    monkeypatch.setattr(codex_adapter, "_host_install_executable", lambda *_: (new_exe, digest, None))
    result = codex_adapter.codex_install()
    assert result["ok"] is True
    assert (home / runtime_identity.MANIFEST_NAME).read_bytes() != prior
    audit = json.loads(next(home.glob("thaliris-install-audit-*.json")).read_text(encoding="utf-8"))
    assert audit["observed_runtime_sha256"] == "UNAVAILABLE"


def test_isolation_rejects_system_site_and_executable_pth(pinned_test_thaliris) -> None:
    exe, _ = pinned_test_thaliris
    venv = exe.parent.parent
    config = venv / "pyvenv.cfg"
    config.write_text("include-system-site-packages = true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="system site packages"):
        runtime_identity.manifest_bytes(exe)
    config.write_text("include-system-site-packages = false\n", encoding="utf-8")
    pth = venv / "Lib" / "site-packages" / "external.pth"
    pth.write_text("C:\\untrusted\\code\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\.pth"):
        runtime_identity.manifest_bytes(exe)


@pytest.mark.skipif(os.name != "nt", reason="Windows Host command")
def test_host_command_rejects_tampered_script_before_dispatch(tmp_path: Path, pinned_test_thaliris) -> None:
    exe, _ = pinned_test_thaliris
    launcher = exe.parent / "test-dispatch.cmd"
    launcher.write_bytes(b"@echo off\r\necho dispatched\r\n")
    digest = hashlib.sha256(launcher.read_bytes()).hexdigest()
    home = tmp_path / "host home"
    home.mkdir()
    script = home / lifecycle.HOST_HOOK_SCRIPT_NAME
    script.write_bytes(lifecycle.host_hook_script_bytes() + b"\r\nrem tampered\r\n")
    manifest = runtime_identity.manifest_bytes(launcher)
    (home / runtime_identity.MANIFEST_NAME).write_bytes(manifest)
    command = lifecycle.host_hook_spec(home, launcher, digest, runtime_identity.manifest_identity(manifest))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "thaliris.json").write_bytes(b'{}')
    result = subprocess.run(command, shell=True, cwd=tmp_path, input=b"{}", capture_output=True, timeout=15)
    assert result.returncode == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    script.write_bytes(lifecycle.host_hook_script_bytes())
    accepted = subprocess.run(command, shell=True, cwd=tmp_path, input=b"{}", capture_output=True, timeout=15)
    assert accepted.returncode == 0
    assert b"dispatched" in accepted.stdout, accepted.stderr.decode("utf-8", errors="replace")


@pytest.mark.skipif(os.name != "nt", reason="Windows installed command")
def test_installed_command_checks_runtime_before_dispatch(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    exe, _ = pinned_test_thaliris
    launcher = exe.parent / "test-dispatch.cmd"
    launcher.write_bytes(b"@echo off\r\necho dispatched\r\n")
    home = tmp_path / "host home"
    home.mkdir()
    manifest = runtime_identity.manifest_bytes(launcher)
    identity = runtime_identity.manifest_identity(manifest)
    (home / runtime_identity.MANIFEST_NAME).write_bytes(manifest)
    wrapper = home / lifecycle.HOST_RUN_SCRIPT_NAME
    wrapper.write_bytes(lifecycle.host_run_script_bytes(launcher, identity))
    monkeypatch.setenv(lifecycle.THALIRIS_EXECUTABLE_ENV, str(launcher))
    monkeypatch.setenv(lifecycle.THALIRIS_EXECUTABLE_SHA256_ENV, hashlib.sha256(launcher.read_bytes()).hexdigest())
    monkeypatch.setenv(lifecycle.THALIRIS_RUNTIME_SHA256_ENV, identity)
    monkeypatch.setenv("THALIRIS_INSTALL_MANIFEST", str(home / runtime_identity.MANIFEST_NAME))
    assert lifecycle._context_arguments(f"& '{wrapper}' --root . task-start goal --bootstrap-receipt {'a' * 64}") is not None
    accepted = subprocess.run([str(wrapper), "--root", str(tmp_path), "codex-bootstrap"],
                              cwd=tmp_path, capture_output=True, timeout=15)
    assert accepted.returncode == 0
    assert b"dispatched" in accepted.stdout
    cache = launcher.parent.parent / "Lib" / "site-packages" / "thaliris" / "__pycache__"
    cache.mkdir()
    (cache / "cli.cpython-311.pyc").write_bytes(b"malicious cache")
    refused = subprocess.run([str(wrapper), "--root", str(tmp_path), "codex-bootstrap"],
                             cwd=tmp_path, capture_output=True, timeout=15)
    assert refused.returncode != 0
    assert b"THALIRIS_RUNTIME_IDENTITY_MISMATCH" in refused.stdout
    assert b"dispatched" not in refused.stdout
    wrapper.write_bytes(wrapper.read_bytes() + b"\r\nrem tampered\r\n")
    assert lifecycle._context_arguments(f"& '{wrapper}' task-start goal") is None
