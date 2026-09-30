import hashlib
import json
from pathlib import Path

import pytest

from thaliris import codex_adapter, codex_bootstrap as bootstrap, lifecycle, runtime_identity
from thaliris import cli, core


@pytest.fixture(autouse=True)
def hypothetical_controller_contract(monkeypatch):
    """Synthetic receipt unit contract; never evidence about the live Host."""
    original = lifecycle._controller_actor_assurance
    monkeypatch.setattr(lifecycle, "_controller_actor_assurance", lambda payload:
                        "CONTROLLER" if original(payload) == "UNKNOWN" else original(payload))


def test_zero_state_rejects_obsolete_executable_protocol_signal(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []

    def invoke(executable, root, command):
        calls.append(command)
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {"ok": True, "project_definition_present": "YES", "session_restart_required": True, "manual_action_required": []}

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "EXECUTABLE_PROTOCOL_SKEW"
    assert result["session_restart_required"] is False
    assert calls == ["bootstrap-check", "init"]


def test_manual_action_is_terminal_without_retry(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []

    def invoke(executable, root, command):
        calls.append(command)
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {"ok": True, "project_definition_present": "NO", "manual_action_required": [".codex/hooks.json"]}

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "MANUAL_ACTION_REQUIRED"
    assert calls == ["bootstrap-check", "init"]


def test_bootstrap_forwards_exact_managed_definition_recovery_action(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    digest = "a" * 64
    calls = []

    def invoke(executable, root, command):
        calls.append(command)
        payload = {
            "ok": True,
            "project_definition_present": "NO",
            "instruction_definition_present": "NO",
            "definition_recovery_status": "EXPLICIT_CONFIRMATION_REQUIRED",
            "managed_instruction_state": "USER",
            "managed_instruction_sha256": digest,
            "managed_instruction_recovery_action": f"thaliris init --accept-managed-instruction-sha256 {digest}",
        }
        if command == "init":
            payload["manual_action_required"] = ["AGENTS.md"]
            payload["changed"] = False
        return payload

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "MANUAL_ACTION_REQUIRED"
    assert result["definition_recovery_status"] == "EXPLICIT_CONFIRMATION_REQUIRED"
    assert result["managed_instruction_recovery_action"] == f"thaliris init --accept-managed-instruction-sha256 {digest}"
    assert calls == ["bootstrap-check", "init"]


def test_manual_action_does_not_hide_executable_protocol_skew(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []

    def invoke(executable, root, command):
        calls.append(command)
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {
            "ok": True,
            "project_definition_present": "YES",
            "session_restart_required": True,
            "manual_action_required": ["docs/thaliris-role-packs.md"],
        }

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "EXECUTABLE_PROTOCOL_SKEW"
    assert result["session_restart_required"] is False

    # An obsolete restart field means executable protocol skew; bootstrap does
    # not claim to fence a later CLI invocation or an old Root process.
    monkeypatch.setattr(
        bootstrap,
        "_invoke",
        lambda executable, root, command: {"ok": True, "project_definition_present": "YES"},
    )
    later = bootstrap.bootstrap(tmp_path)
    assert later["status"] == "READY"
    assert later["init_invoked"] is False
    assert later["session_restart_required"] is False
    assert calls == ["bootstrap-check", "init"]


def test_initialized_workspace_does_not_init(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []
    monkeypatch.setattr(bootstrap, "_invoke", lambda executable, root, command: calls.append(command) or {"ok": True, "project_definition_present": "YES"})
    result = bootstrap.bootstrap(tmp_path)
    assert result == {"ok": True, "status": "READY", "project_definition_present": "YES", "init_invoked": False, "session_restart_required": False,
                      "controller_actor_assurance": "CONTROLLER", "ordinary_workspace_work_allowed": True}
    assert calls == ["bootstrap-check"]


def test_zero_state_init_does_not_claim_or_create_host_role_catalog(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    result = codex_adapter.init(tmp_path)
    assert result["project_definition_present"] == "YES"
    assert result["role_catalog_changed"] is False
    assert result["new_role_profile_files"] == []
    assert result["host_role_catalog_status"] == "HOST_ROLE_CATALOG_UNKNOWN"
    assert not (tmp_path / ".codex" / "agents").exists()


def test_probe_failure_calibrates_restart_boolean(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    monkeypatch.setattr(
        bootstrap,
        "_invoke",
        lambda executable, root, command: {
            "ok": False,
            "error": "probe failed",
            "session_restart_required": "not-a-boolean",
        },
    )
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "BOOTSTRAP_UNAVAILABLE"
    assert result["session_restart_required"] is False


def test_nonzero_native_response_preserves_restart_signal(monkeypatch, tmp_path: Path):
    native = {
        "ok": False,
        "error": "restart required",
        "session_restart_required": True,
    }

    class Completed:
        returncode = 7
        stdout = json.dumps(native)
        stderr = ""

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")

    assert result["session_restart_required"] is True
    assert result["response"] == native

    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    outer = bootstrap.bootstrap(tmp_path)
    assert outer["status"] == "BOOTSTRAP_UNAVAILABLE"
    assert outer["session_restart_required"] is False


def test_nonzero_native_response_normalizes_false_or_missing_restart(monkeypatch, tmp_path: Path):
    class Completed:
        returncode = 7
        stderr = ""

    for native in ({"session_restart_required": False}, {}):
        Completed.stdout = json.dumps(native)
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
        result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
        assert result["session_restart_required"] is False


def test_invoke_exception_always_includes_false_restart(monkeypatch, tmp_path: Path):
    def raise_os_error(*args, **kwargs):
        raise OSError("unable to execute")

    monkeypatch.setattr(bootstrap.subprocess, "run", raise_os_error)
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
    assert result == {
        "ok": False,
        "error": "unable to execute",
        "session_restart_required": False,
    }


def test_invoke_malformed_json_always_includes_false_restart(monkeypatch, tmp_path: Path):
    class Completed:
        returncode = 0
        stdout = "not json"
        stderr = "diagnostic"

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
    assert result["session_restart_required"] is False
    assert result["error"] == "trusted executable returned non-JSON output"


def test_invoke_non_object_json_always_includes_false_restart(monkeypatch, tmp_path: Path):
    class Completed:
        returncode = 0
        stdout = "[]"
        stderr = ""

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
    assert result == {
        "ok": False,
        "error": "trusted executable returned a non-object JSON value",
        "session_restart_required": False,
    }


def test_invoke_success_normalizes_restart_to_strict_boolean(monkeypatch, tmp_path: Path):
    class Completed:
        returncode = 0
        stderr = ""

    current = {
        "managed_hook_abi": lifecycle.MANAGED_HOOK_ABI,
        "executable_adapter_protocol_version": lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION,
        "controller_bridge_content": "managed text",
        "controller_bridge_sha256": hashlib.sha256(b"managed text").hexdigest(),
    }
    for native in (True, False, None, "true", 1):
        Completed.stdout = json.dumps({"ok": True, "session_restart_required": native, **current})
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
        result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
        assert result["session_restart_required"] is False
        if native is True:
            assert result["status"] == "EXECUTABLE_PROTOCOL_SKEW"
        assert type(result["session_restart_required"]) is bool

    Completed.stdout = json.dumps({"ok": True, **current})
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


def test_bootstrap_protocol_expectations_follow_lifecycle_authority():
    assert bootstrap.EXPECTED_MANAGED_HOOK_ABI == lifecycle.MANAGED_HOOK_ABI
    assert bootstrap.EXPECTED_ADAPTER_PROTOCOL_VERSION == lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION


def test_invoke_rejects_old_executable_protocol(monkeypatch, tmp_path: Path):
    class Completed:
        returncode = 0
        stdout = json.dumps({"ok": True, "project_definition_present": "YES"})
        stderr = ""

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
    assert result["status"] == "EXECUTABLE_PROTOCOL_SKEW"
    assert result["session_restart_required"] is False


def test_malformed_probe_manual_action_rejects_executable_protocol_skew(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    monkeypatch.setattr(
        bootstrap,
        "_invoke",
        lambda executable, root, command: {
            "ok": True,
            "project_definition_present": "YES",
            "manual_action_required": "malformed",
            "session_restart_required": True,
        },
    )
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "EXECUTABLE_PROTOCOL_SKEW"
    assert result["session_restart_required"] is False


def test_invalid_probe_definition_rejects_executable_protocol_skew(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    monkeypatch.setattr(
        bootstrap,
        "_invoke",
        lambda executable, root, command: {
            "ok": True,
            "project_definition_present": "INVALID",
            "manual_action_required": [],
            "session_restart_required": True,
        },
    )
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "EXECUTABLE_PROTOCOL_SKEW"
    assert result["session_restart_required"] is False


def test_no_restart_init_ready_calibrates_false(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])

    def invoke(executable, root, command):
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {"ok": True, "project_definition_present": "YES", "manual_action_required": [], "session_restart_required": False}

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result == {"ok": True, "status": "READY", "init_invoked": True, "session_restart_required": False,
                      "controller_actor_assurance": "CONTROLLER", "ordinary_workspace_work_allowed": True}


def test_untrusted_executable_stops_before_probe(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: None)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "BOOTSTRAP_UNAVAILABLE"
    assert result["manual_action_required"] == ["canonical_executable_unavailable"]
    assert result["session_restart_required"] is False


def test_cli_non_git_root_returns_structured_bootstrap_failure(tmp_path: Path, capsys):
    exit_code = cli.main(["--root", str(tmp_path), "codex-bootstrap"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "error": "not a Git workspace",
        "ok": False,
        "status": "BOOTSTRAP_UNAVAILABLE",
        "session_restart_required": False,
    }


def test_cli_dispatch_exception_has_explicit_restart_boolean(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(
        cli.codex_bootstrap,
        "bootstrap",
        lambda root: (_ for _ in ()).throw(RuntimeError("not a Git workspace")),
    )
    exit_code = cli.main(["--root", str(tmp_path), "codex-bootstrap"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert json.loads(captured.out) == {
        "error": "not a Git workspace",
        "ok": False,
        "status": "BOOTSTRAP_UNAVAILABLE",
        "session_restart_required": False,
    }


def test_cli_malformed_bootstrap_invocation_has_explicit_restart_boolean(capsys):
    exit_code = cli.main(["codex-bootstrap", "--invalid"])

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        # Values beginning with a dash still follow argparse's root-value
        # grammar when they are valid values, while an option-like value does
        # not resolve a command.
        (["--root", "-1", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        (["--root", "-", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        (["--root=-x", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        # Global abbreviations are parsed by the same grammar as _parser().
        (["--roo", "some-root", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        (["--pre", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        (["-h", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        (["--help", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        # The probe recognizes the command after an end marker even where the
        # real subparser's execution behavior differs by Python version.
        (["--", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        # Unknown options are left to parse_known_args while the first
        # positional command remains observable.
        (["--unknown", "codex-bootstrap", "--invalid"], "codex-bootstrap"),
        (["codex-bootstrap", "--root", "--pretty"], "codex-bootstrap"),
        # These must not turn a root value, unresolved root, or another
        # command into a bootstrap request.
        (["--root", "codex-bootstrap"], None),
        (["--root", "-x", "codex-bootstrap"], None),
        (["--root", "--", "codex-bootstrap"], None),
        (["version", "codex-bootstrap", "--invalid"], "version"),
    ],
)
def test_requested_command_uses_shared_argparse_grammar(argv, expected):
    assert cli._requested_command(argv) == expected


@pytest.mark.parametrize(
    "argv",
    [
        ["--root", "-1", "codex-bootstrap", "--invalid"],
        ["--root", "-", "codex-bootstrap", "--invalid"],
        ["--root=-x", "codex-bootstrap", "--invalid"],
        ["--roo", "some-root", "codex-bootstrap", "--invalid"],
        ["--pre", "codex-bootstrap", "--invalid"],
        ["--", "codex-bootstrap", "--invalid"],
        ["--unknown", "codex-bootstrap", "--invalid"],
        ["codex-bootstrap", "--root", "--pretty"],
    ],
)
def test_cli_probe_strict_schema_covers_malformed_bootstrap_matrix(argv, capsys):
    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


@pytest.mark.parametrize(
    "argv",
    [
        ["--root", "codex-bootstrap"],
        ["--root", "-x", "codex-bootstrap"],
        ["--root", "--", "codex-bootstrap"],
        ["version", "codex-bootstrap", "--invalid"],
        ["version", "--pretty", "codex-bootstrap"],
    ],
)
def test_cli_probe_generic_schema_covers_false_positive_matrix(argv, capsys):
    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert "session_restart_required" not in result


@pytest.mark.parametrize(
    "argv",
    [
        ["version", "codex-bootstrap"],
        ["--root", "codex-bootstrap"],
    ],
)
def test_cli_unrelated_malformed_invocations_keep_normal_error_schema(argv, capsys):
    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert "session_restart_required" not in result


@pytest.mark.parametrize(
    "argv",
    [
        ["--root"],
        ["--root", "--pretty", "codex-bootstrap"],
        ["--root", "-x", "codex-bootstrap"],
        ["--pretty", "--root", "--pretty", "codex-bootstrap"],
        ["--root", "--root=some-root", "codex-bootstrap"],
    ],
)
def test_cli_unresolved_root_does_not_leak_bootstrap_schema(argv, capsys):
    assert cli._requested_command(argv) is None

    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert "session_restart_required" not in result


@pytest.mark.parametrize(
    "argv",
    [
        ["--root", "some-root", "codex-bootstrap", "--invalid"],
        ["--root=some-root", "codex-bootstrap", "--invalid"],
        ["--pretty", "codex-bootstrap", "--invalid"],
        ["--root", "some-root", "--pretty", "codex-bootstrap", "--invalid"],
        ["codex-bootstrap", "--root", "some-root", "--invalid"],
    ],
)
def test_cli_malformed_bootstrap_command_is_scoped_across_global_option_placements(argv, capsys):
    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


@pytest.mark.parametrize("exception", [OSError, RuntimeError])
def test_cli_root_resolution_exception_has_bootstrap_restart_boolean(monkeypatch, tmp_path: Path, capsys, exception):
    original_resolve = Path.resolve

    def fail_for_root(self, *args, **kwargs):
        if self == tmp_path:
            raise exception("root resolution failed")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_for_root)
    exit_code = cli.main(["--root", str(tmp_path), "codex-bootstrap"])

    captured = capsys.readouterr()
    assert exit_code == 2
    result = json.loads(captured.out)
    assert result == {
        "error": "root resolution failed",
        "ok": False,
        "session_restart_required": False,
    }
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


def test_module_entrypoint_exception_has_explicit_restart_boolean(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(
        bootstrap,
        "bootstrap",
        lambda root: (_ for _ in ()).throw(RuntimeError("not a Git workspace")),
    )
    exit_code = bootstrap.main(["--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert json.loads(captured.out) == {
        "error": "not a Git workspace",
        "ok": False,
        "status": "BOOTSTRAP_UNAVAILABLE",
        "session_restart_required": False,
    }


def test_module_entrypoint_parse_error_has_explicit_restart_boolean(capsys):
    exit_code = bootstrap.main(["--invalid"])

    captured = capsys.readouterr()
    assert exit_code == 3
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


def test_native_bootstrap_check_has_explicit_restart_boolean(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(core, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(codex_adapter, "_project_definition_facts", lambda root: {"project_definition_present": "YES"})
    result = codex_adapter.bootstrap_check(tmp_path)
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


def test_bootstrap_uses_full_installed_runtime_manifest(tmp_path: Path, monkeypatch, pinned_test_thaliris):
    executable, _ = pinned_test_thaliris
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("THALIRIS_EXECUTABLE", str(executable))
    (home / runtime_identity.MANIFEST_NAME).write_bytes(runtime_identity.manifest_bytes(executable))
    assert bootstrap._trusted_executable() == [str(executable)]

    package = executable.parent.parent / "Lib" / "site-packages" / "thaliris" / "cli.py"
    package.write_text("changed\n", encoding="utf-8")
    assert bootstrap._trusted_executable() is None
    assert (home / runtime_identity.MANIFEST_NAME).is_file()


def test_active_task_yields_exact_recovery_without_probe_or_init(tmp_path: Path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    started = core.task_start(tmp_path, "unfinished", None, None)
    owner = hashlib.sha256(b"owning-session").hexdigest()
    lifecycle.record_task_start_owner(tmp_path, started["task_id"], owner)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["installed"])
    monkeypatch.setattr(bootstrap, "_invoke", lambda *args: (_ for _ in ()).throw(AssertionError("no project probe")))

    result = bootstrap.bootstrap(tmp_path)
    state = (tmp_path / ".context" / "state.json").read_bytes()
    ledger = lifecycle._lifecycle_path(tmp_path, started["task_id"]).read_bytes()
    assert result["status"] == "UNKNOWN"
    assert result["init_invoked"] is False
    assert result["recovery"] == {
        "status": "ACTIVE", "task_id": started["task_id"], "revision": started["revision"],
        "state_sha256": hashlib.sha256(state).hexdigest(),
        "lifecycle_sha256": hashlib.sha256(ledger).hexdigest(),
        "owner_session_id_hash": owner, "owner_provenance": "TASK_START",
        "current_session_owner_match": "UNKNOWN",
    }


def test_invalid_task_state_stops_before_runtime_or_init(tmp_path: Path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    state = tmp_path / ".context" / "state.json"
    state.parent.mkdir()
    state.write_text('{"status":"ACTIVE"}', encoding="utf-8")
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["installed"])
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "INVALID_STATE"
    assert result["init_invoked"] is False


def test_ready_exposes_single_receipt_and_global_instruction_is_one_command(tmp_path: Path, monkeypatch):
    digest = hashlib.sha256(b"managed text").hexdigest()
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["installed"])
    monkeypatch.setattr(bootstrap, "_invoke", lambda *args: {
        "ok": True, "project_definition_present": "YES",
        "controller_bridge_content": "managed text", "controller_bridge_sha256": digest,
    })
    result = bootstrap.bootstrap(tmp_path)
    assert result["task_start_receipt"] == digest
    assert "controller_bridge_sha256" not in result
    assert "controller_bridge_content" not in result
    rendered = codex_adapter._global_agents_block(Path("C:/installed/thaliris.exe"), digest).decode("utf-8")
    assert rendered.count("--root <repo> codex-bootstrap") == 1
    assert "bootstrap-check" not in rendered and "Get-FileHash" not in rendered
    assert "--bootstrap-receipt" in rendered
    assert "the owning root Controller runs" in rendered
    assert "managed child inside an ACTIVE task" in rendered
    assert "do not run project bootstrap, task-start, or task-abandon" in rendered
    assert "report blocked work honestly" in rendered


def test_cli_bootstrap_receipt_alias_is_passed_to_task_start(tmp_path: Path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(cli.codex_adapter, "task_start", lambda *args: seen.append(args) or {"ok": True})
    assert cli.main(["--root", str(tmp_path), "task-start", "goal", "--bootstrap-receipt", "a" * 64]) == 0
    assert seen[0][-1] == "a" * 64
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_current_hook_attests_receipt_alias_and_allows_active_bootstrap(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    digest = codex_adapter._controller_bridge()["controller_bridge_sha256"]
    payload = {
        "session_id": "controller-session", "turn_id": "start-turn", "tool_name": "Bash",
        "tool_input": {"command": f"thaliris task-start goal --bootstrap-receipt {digest}"},
    }
    response = json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
    assert response["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "--hook-attestation" in response["hookSpecificOutput"]["updatedInput"]["command"]
    core.task_start(tmp_path, "unfinished", None, None)
    active = {"session_id": "controller-session", "turn_id": "active-turn", "tool_name": "Bash", "tool_input": {"command": "thaliris --root . codex-bootstrap"}}
    rewritten = json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", active, lifecycle.MANAGED_HOOK_ABI))
    assert rewritten["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "--hook-attestation" in rewritten["hookSpecificOutput"]["updatedInput"]["command"]


def test_active_bootstrap_proves_owner_or_foreign_session_once(tmp_path: Path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    started = core.task_start(tmp_path, "unfinished", None, None)
    lifecycle.record_task_start_owner(tmp_path, started["task_id"], hashlib.sha256(b"owner-session").hexdigest())
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["installed"])
    monkeypatch.setattr(bootstrap, "_invoke", lambda *args: (_ for _ in ()).throw(AssertionError("ACTIVE must not probe or init")))

    for session, expected in (("owner-session", "CURRENT_CONTINUATION"), ("foreign-session", "FOREIGN_RECOVERY_DECISION")):
        payload = {"session_id": session, "turn_id": "turn", "tool_name": "Bash", "tool_input": {"command": "thaliris --root . codex-bootstrap"}}
        rewritten = json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
        token = rewritten["hookSpecificOutput"]["updatedInput"]["command"].split("--hook-attestation ", 1)[1]
        result = bootstrap.bootstrap(tmp_path, token)
        assert result["status"] == expected
        assert result["recovery"]["current_session_owner_match"] == ("YES" if session == "owner-session" else "NO")
        assert token not in json.dumps(result)
        with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
            bootstrap.bootstrap(tmp_path, token)


def test_active_owner_admission_and_unknown_owner_are_fail_closed(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    started = core.task_start(tmp_path, "unfinished", None, None)
    call = lambda session, tool, data: {"session_id": session, "turn_id": "turn", "tool_name": tool, "tool_input": data}
    spawn = {"fork_turns": "none", "agent_type": "thaliris-implementer", "message": "selected handoff"}
    assert "THALIRIS_ACTIVE_OWNER_REQUIRED" in lifecycle.handle_hook(tmp_path, "PreToolUse", call("owner", "spawn_agent", spawn))
    assert lifecycle.handle_hook(tmp_path, "PreToolUse", call("owner", "Bash", {"command": "thaliris task-status"})) == ""

    lifecycle.record_task_start_owner(tmp_path, started["task_id"], hashlib.sha256(b"owner").hexdigest())
    assert "THALIRIS_ACTIVE_OWNER_REQUIRED" in lifecycle.handle_hook(tmp_path, "PreToolUse", call("foreign", "spawn_agent", spawn))
    assert "THALIRIS_ACTIVE_OWNER_REQUIRED" in lifecycle.handle_hook(tmp_path, "PreToolUse", call("foreign", "Bash", {"command": "thaliris task-update --role controller --base-revision 1 --input x"}))
    assert lifecycle.handle_hook(tmp_path, "PreToolUse", call("owner", "spawn_agent", spawn)) == ""
