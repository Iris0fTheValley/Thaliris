from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from thaliris import codex_adapter, codex_app_server, lifecycle


_EVENT_NAMES = {
    "SessionStart": "sessionStart",
    "UserPromptSubmit": "userPromptSubmit",
    "PreToolUse": "preToolUse",
    "PostToolUse": "postToolUse",
    "SubagentStart": "subagentStart",
    "SubagentStop": "subagentStop",
    "Stop": "stop",
}


class FakeAppServer:
    """Protocol fake: hook keys and hashes originate from this Host stand-in."""

    def __init__(self, home: Path, state: dict):
        self.home = home
        self.state = state
        self.requests: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def request(self, method: str, params: dict) -> dict:
        self.requests.append((method, params))
        if method == "hooks/list":
            return {"data": [{"cwd": str(self.home), "hooks": self._hooks(), "errors": [], "warnings": []}]}
        if method == "config/batchWrite":
            edit = params["edits"][0]
            if edit["keyPath"] != "hooks.state":
                raise AssertionError(edit)
            if edit["mergeStrategy"] == "upsert":
                for key, value in edit["value"].items():
                    self.state["state"].setdefault(key, {}).update(value)
            elif edit["mergeStrategy"] == "replace":
                self.state["state"] = edit["value"]
            else:
                raise AssertionError(edit["mergeStrategy"])
            return {"status": "ok", "filePath": str(self.home / "config.toml"), "version": "sha256:after"}
        if method == "config/read":
            return {
                "config": {"hooks": {"state": self.state["state"]}},
                "layers": [{
                    "name": {"type": "user", "file": str(self.home / "config.toml")},
                    "version": "sha256:before",
                    "config": {"hooks": {"state": self.state["state"]}},
                }],
                "origins": {},
            }
        raise AssertionError(method)

    def _hooks(self) -> list[dict]:
        document = json.loads((self.home / "hooks.json").read_text(encoding="utf-8"))
        result = []
        for event in lifecycle.HOOK_EVENTS:
            for group_index, group in enumerate(document.get("hooks", {}).get(event, [])):
                for handler_index, handler in enumerate(group.get("hooks", [])):
                    command = handler.get("command")
                    if not isinstance(command, str):
                        continue
                    key = f"{self.home / 'hooks.json'}:{event}:{group_index}:{handler_index}"
                    current_hash = self.state["hashes"][event]
                    saved = self.state["state"].get(key, {})
                    saved_hash = saved.get("trusted_hash")
                    result.append({
                        "eventName": _EVENT_NAMES[event],
                        "sourcePath": str(self.home / "hooks.json"),
                        "key": key,
                        "currentHash": current_hash,
                        "enabled": saved.get("enabled", True),
                        "trustStatus": "trusted" if saved_hash == current_hash else (
                            "modified" if saved_hash else "untrusted"
                        ),
                        "command": command,
                        "matcher": group.get("matcher"),
                        "timeoutSec": handler.get("timeout", 60),
                        "handlerType": handler.get("type"),
                        "source": "user",
                        "isManaged": False,
                    })
        result.extend(self.state.get("extra_handlers", []))
        return result


def _home_with_hooks(tmp_path: Path, executable: Path, pin: str) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "thaliris-hook.cmd").write_bytes(lifecycle.host_hook_script_bytes())
    fragment = lifecycle.host_hook_spec(home, executable, pin)
    (home / "hooks.json").write_text(json.dumps(fragment), encoding="utf-8")
    return home


def _fake_factory(home: Path, state: dict):
    clients: list[FakeAppServer] = []

    def factory(_home: Path):
        client = FakeAppServer(home, state)
        clients.append(client)
        return client

    return factory, clients


def test_enabled_untrusted_user_hook_is_not_runtime_dispatchable() -> None:
    assert codex_app_server._is_dispatchable({"enabled": True, "trustStatus": "untrusted"}) is False
    assert codex_app_server._is_dispatchable({"enabled": True, "trustStatus": "modified"}) is False
    assert codex_app_server._is_dispatchable({"enabled": True, "trustStatus": "trusted"}) is True
    assert codex_app_server._is_dispatchable({"enabled": False, "trustStatus": "trusted"}) is False


def test_host_registration_mismatch_fails_closed_before_any_trust_write(tmp_path: Path) -> None:
    executable = tmp_path / "thaliris.exe"
    executable.write_bytes(b"installer executable pin")
    pin = hashlib.sha256(executable.read_bytes()).hexdigest()
    home = _home_with_hooks(tmp_path, executable, pin)
    document = json.loads((home / "hooks.json").read_text(encoding="utf-8"))
    document["hooks"]["PreToolUse"][0]["hooks"][0]["command"] += " modified"
    (home / "hooks.json").write_text(json.dumps(document), encoding="utf-8")
    state = {
        "hashes": {event: f"sha256:host-returned-opaque-{event}" for event in lifecycle.HOOK_EVENTS},
        "state": {},
    }
    factory, clients = _fake_factory(home, state)

    with pytest.raises(codex_app_server.CodexAppServerError, match="HOST_HOOK_TRUST_INSTALL_FAILED"):
        codex_app_server.trust_installed_host_hooks(home, executable, pin, client_factory=factory)

    assert not any(method == "config/batchWrite" for client in clients for method, _params in client.requests)


def test_installer_trusts_only_exact_host_returned_handlers_and_preserves_user_hook(tmp_path: Path) -> None:
    executable = tmp_path / "thaliris.exe"
    executable.write_bytes(b"installer executable pin")
    pin = hashlib.sha256(executable.read_bytes()).hexdigest()
    home = _home_with_hooks(tmp_path, executable, pin)
    hooks_path = home / "hooks.json"
    document = json.loads(hooks_path.read_text(encoding="utf-8"))
    user_handler = {"type": "command", "command": "user-owned-handler", "timeout": 22}
    document["hooks"]["UserPromptSubmit"].append({"hooks": [user_handler]})
    hooks_path.write_text(json.dumps(document), encoding="utf-8")
    user_key = f"{hooks_path}:user-owned:0:0"
    state = {
        "hashes": {event: f"sha256:host-returned-opaque-{event}" for event in lifecycle.HOOK_EVENTS},
        "state": {user_key: {"trusted_hash": "sha256:user-original", "enabled": True}},
        "extra_handlers": [{
            "eventName": "userPromptSubmit", "sourcePath": str(hooks_path), "key": user_key,
            "currentHash": "sha256:user-current", "enabled": True, "trustStatus": "untrusted",
            "command": "user-owned-handler", "matcher": None, "timeoutSec": 22,
            "handlerType": "command", "source": "user", "isManaged": False,
        }],
    }
    factory, clients = _fake_factory(home, state)

    result = codex_app_server.trust_installed_host_hooks(home, executable, pin, client_factory=factory)

    assert result["status"] == "TRUSTED"
    assert result["trusted_count"] == result["expected_count"] == 7
    assert result["enabled_count"] == 7
    writes = [(method, params) for client in clients for method, params in client.requests if method == "config/batchWrite"]
    assert len(writes) == 1
    method, params = writes[0]
    edit = params["edits"][0]
    assert method == "config/batchWrite"
    assert edit["keyPath"] == "hooks.state"
    assert edit["mergeStrategy"] == "upsert"
    assert params["reloadUserConfig"] is True
    assert set(edit["value"]) == {f"{hooks_path}:{event}:0:0" for event in lifecycle.HOOK_EVENTS}
    assert {value["trusted_hash"] for value in edit["value"].values()} == set(state["hashes"].values())
    assert all(set(value) == {"trusted_hash"} for value in edit["value"].values())
    assert state["state"][user_key] == {"trusted_hash": "sha256:user-original", "enabled": True}
    assert any(hook["key"] == user_key and hook["trustStatus"] == "untrusted" for hook in clients[-1]._hooks())


def test_host_disabled_state_survives_trust_and_does_not_report_ready(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    pin_exe, pin = pinned_test_thaliris
    monkeypatch.setattr(codex_adapter, "_install_host_hook_trust", lambda *_args: {
        "status": "TRUSTED", "trusted_count": 7, "enabled_count": 6,
        "expected_count": 7, "changed": True, "config_path": str(home / "config.toml"),
    })

    result = codex_adapter.codex_install()

    assert result["host_hook_trust_status"] == "TRUSTED"
    assert result["host_hook_trusted_count"] == 7
    assert result["host_hook_enabled_count"] == 6
    assert result["host_integration_ready"] == "NO"
    assert result["ok"] is False
    assert "one_or_more_Thaliris_Host_hooks_are_disabled_by_user_state" in result["manual_action_required"]


def test_trust_uses_host_current_hash_and_reinstall_trusts_changed_pin(tmp_path: Path) -> None:
    executable = tmp_path / "thaliris.exe"
    executable.write_bytes(b"pin v1")
    pin_v1 = hashlib.sha256(executable.read_bytes()).hexdigest()
    home = _home_with_hooks(tmp_path, executable, pin_v1)
    hashes = {event: f"sha256:host-current-v1-{event}" for event in lifecycle.HOOK_EVENTS}
    state = {"hashes": hashes, "state": {}}
    factory, clients = _fake_factory(home, state)

    first = codex_app_server.trust_installed_host_hooks(home, executable, pin_v1, client_factory=factory)
    first_commands = [hook["command"] for hook in clients[-1]._hooks()]
    assert first["status"] == "TRUSTED"
    assert first["changed"] is True
    assert set(state["state"][f"{home / 'hooks.json'}:{event}:0:0"]["trusted_hash"] for event in lifecycle.HOOK_EVENTS) == set(hashes.values())

    executable.write_bytes(b"pin v2")
    pin_v2 = hashlib.sha256(executable.read_bytes()).hexdigest()
    new_fragment = lifecycle.host_hook_spec(home, executable, pin_v2)
    (home / "hooks.json").write_text(json.dumps(new_fragment), encoding="utf-8")
    second_hashes = {event: f"sha256:host-current-v2-{event}" for event in lifecycle.HOOK_EVENTS}
    state["hashes"] = second_hashes

    second = codex_app_server.trust_installed_host_hooks(home, executable, pin_v2, client_factory=factory)

    second_commands = [hook["command"] for hook in clients[-1]._hooks()]
    assert first_commands != second_commands
    assert pin_v1 not in second_commands[0]
    assert pin_v2 in second_commands[0]
    assert second["status"] == "TRUSTED"
    assert second["changed"] is True
    assert {state["state"][f"{home / 'hooks.json'}:{event}:0:0"]["trusted_hash"] for event in lifecycle.HOOK_EVENTS} == set(second_hashes.values())


def test_uninstall_removes_only_exact_thaliris_trust_state(tmp_path: Path) -> None:
    executable = tmp_path / "thaliris.exe"
    executable.write_bytes(b"pin")
    pin = hashlib.sha256(executable.read_bytes()).hexdigest()
    home = _home_with_hooks(tmp_path, executable, pin)
    hooks_path = home / "hooks.json"
    owned_commands = {
        event: {handler["command"] for group in lifecycle.host_hook_spec(home, executable, pin)["hooks"][event] for handler in group["hooks"]}
        for event in lifecycle.HOOK_EVENTS
    }
    state = {
        "hashes": {event: f"sha256:host-{event}" for event in lifecycle.HOOK_EVENTS},
        "state": {
            **{f"{hooks_path}:{event}:0:0": {"trusted_hash": f"sha256:thaliris-{event}"} for event in lifecycle.HOOK_EVENTS},
            "user-unrelated-key": {"trusted_hash": "sha256:keep", "enabled": False},
        },
    }
    factory, _clients = _fake_factory(home, state)

    exact_keys = codex_app_server.owned_hook_keys_from_host(home, owned_commands, client_factory=factory)
    removed = codex_app_server.remove_owned_hook_trust(home, exact_keys, client_factory=factory)

    assert removed == 7
    assert all(key not in state["state"] for key in exact_keys)
    assert state["state"] == {"user-unrelated-key": {"trusted_hash": "sha256:keep", "enabled": False}}


def test_app_server_failure_fails_closed_without_ready_claim(tmp_path: Path, monkeypatch, pinned_test_thaliris) -> None:
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))

    def fail(_home, _executable, _pin):
        raise codex_app_server.CodexAppServerError("test app-server unavailable")

    monkeypatch.setattr(codex_adapter, "_install_host_hook_trust", fail)

    result = codex_adapter.codex_install()

    assert result["host_hook_registration_present"] == "YES"
    assert result["host_hook_trust_status"] == "HOST_HOOK_TRUST_INSTALL_FAILED"
    assert result["host_integration_ready"] == "NO"
    assert result["ok"] is False
    assert "HOST_HOOK_TRUST_INSTALL_FAILED" in result["manual_action_required"]
