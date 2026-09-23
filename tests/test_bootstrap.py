import json
from pathlib import Path

import pytest

from thaliris import codex_adapter, codex_bootstrap as bootstrap
from thaliris import cli, core


def test_zero_state_invokes_init_once_and_requires_fresh_session(monkeypatch, tmp_path: Path):
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
    assert result["status"] == "SESSION_RESTART_REQUIRED"
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


def test_manual_action_preserves_restart_without_process_local_latch(monkeypatch, tmp_path: Path):
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
    assert result["status"] == "MANUAL_ACTION_REQUIRED"
    assert result["session_restart_required"] is True

    # Restart is a signal for the current Controller; bootstrap does not claim
    # to fence a later CLI invocation or an old Root process.
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
    assert result == {"ok": True, "status": "READY", "project_definition_present": "YES", "init_invoked": False, "session_restart_required": False}
    assert calls == ["bootstrap-check"]


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
    assert outer["session_restart_required"] is True


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

    for native in (True, False, None, "true", 1):
        Completed.stdout = json.dumps({"ok": True, "session_restart_required": native})
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
        result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
        assert result["session_restart_required"] is (native is True)
        assert type(result["session_restart_required"]) is bool

    Completed.stdout = json.dumps({"ok": True})
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: Completed())
    result = bootstrap._invoke(["thaliris"], tmp_path, "bootstrap-check")
    assert result["session_restart_required"] is False
    assert type(result["session_restart_required"]) is bool


def test_malformed_probe_manual_action_preserves_native_restart(monkeypatch, tmp_path: Path):
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
    assert result["status"] == "BOOTSTRAP_UNAVAILABLE"
    assert result["session_restart_required"] is True


def test_invalid_probe_definition_preserves_native_restart(monkeypatch, tmp_path: Path):
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
    assert result["status"] == "BOOTSTRAP_UNAVAILABLE"
    assert result["session_restart_required"] is True


def test_no_restart_init_ready_calibrates_false(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])

    def invoke(executable, root, command):
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {"ok": True, "project_definition_present": "YES", "manual_action_required": [], "session_restart_required": False}

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result == {"ok": True, "status": "READY", "init_invoked": True, "session_restart_required": False}


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
