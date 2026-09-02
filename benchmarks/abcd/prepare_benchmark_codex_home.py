"""Create a minimal fresh CODEX_HOME for an isolated benchmark session.

The source home is the active CC Switch-managed Codex configuration.  Only
the selected provider's non-history configuration and its auth file are
projected; sessions, caches, logs, state databases, plugins, and prompts are
intentionally absent.  Repository-scoped Thaliris hooks remain in the model
workspace, where ``context init`` installs them after the sealed pre-run gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from pathlib import Path
from typing import Any


TOP_LEVEL_KEYS = (
    "model_provider",
    "model",
    "approval_policy",
    "sandbox_mode",
    "web_search",
    "disable_response_storage",
    "model_context_window",
    "model_auto_compact_token_limit",
    "model_reasoning_effort",
)
PROVIDER_KEYS = ("name", "base_url", "wire_api", "requires_openai_auth")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError(f"unsupported minimal config value: {type(value).__name__}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_minimal_home(source: Path, destination: Path, *, global_agents: Path | None = None) -> dict[str, Any]:
    """Project one external-provider configuration without copying history."""

    source = source.resolve()
    destination = destination.resolve()
    config_path = source / "config.toml"
    auth_path = source / "auth.json"
    if not config_path.is_file() or not auth_path.is_file():
        raise ValueError("source CODEX_HOME must contain config.toml and auth.json")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("destination CODEX_HOME must be empty")
    destination.mkdir(parents=True, exist_ok=True)

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    provider_name = config.get("model_provider")
    providers = config.get("model_providers")
    if not isinstance(provider_name, str) or not isinstance(providers, dict):
        raise ValueError("source CODEX_HOME does not define a model provider")
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise ValueError(f"source CODEX_HOME has no [{provider_name}] provider stanza")

    lines = [f"{key} = {_toml_value(config[key])}" for key in TOP_LEVEL_KEYS if key in config]
    lines.extend(("", f"[model_providers.{provider_name}]"))
    lines.extend(f"{key} = {_toml_value(provider[key])}" for key in PROVIDER_KEYS if key in provider)
    (destination / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(auth_path, destination / "auth.json")

    agents_digest: str | None = None
    if global_agents is not None:
        global_agents = global_agents.resolve()
        if not global_agents.is_file():
            raise ValueError("global AGENTS.md path does not exist")
        shutil.copy2(global_agents, destination / "AGENTS.md")
        agents_digest = _sha256(global_agents)

    return {
        "schema_version": 1,
        "source": str(source),
        "destination": str(destination),
        "provider": provider_name,
        "provider_config_keys": [key for key in PROVIDER_KEYS if key in provider],
        "auth_projected": True,
        "global_agents_projected": global_agents is not None,
        "global_agents_sha256": agents_digest,
        "excluded": ["sessions", "archived_sessions", "cache", "log", "state", "sqlite", "plugins", "prompts"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-home", required=True, type=Path)
    parser.add_argument("--destination-home", required=True, type=Path)
    parser.add_argument("--global-agents", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    result = build_minimal_home(args.source_home, args.destination_home, global_agents=args.global_agents)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
