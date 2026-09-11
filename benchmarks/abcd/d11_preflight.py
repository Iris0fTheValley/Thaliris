"""Deterministic formal-run preflight; no task model workflow is started."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

from candidate_manifest import build_manifest
from trusted_surface import identity as trusted_identity, verify as verify_trusted


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _hash_files(paths: Iterable[Path]) -> str:
    entries = [{"path": str(path.resolve()), "sha256": _sha(path)} for path in sorted(paths, key=str)]
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_preflight(
    root: Path,
    *,
    expected_adapter_sha: str,
    harness_paths: Iterable[Path],
    evaluator_path: Path,
    trusted_paths: Iterable[Path] = (),
    gold_result: dict[str, Any] | None = None,
    base_result: dict[str, Any] | None = None,
    no_edit_identity: str | None = None,
    base_identity: str | None = None,
) -> dict[str, Any]:
    """Return a fact ledger suitable for freezing, never a model report."""
    root = root.resolve()
    checks: dict[str, Any] = {}
    actual_adapter = _git(root, "rev-parse", "HEAD")
    checks["adapter_sha"] = {"expected": expected_adapter_sha, "actual": actual_adapter, "pass": actual_adapter == expected_adapter_sha}
    routing = root / "docs" / "thaliris-routing-protocol.md"
    protocol_text = routing.read_text(encoding="utf-8") if routing.is_file() else ""
    checks["product_protocol"] = {"path": str(routing), "sha256": _sha(routing) if routing.is_file() else None, "version": "thaliris-routing-v1" if "thaliris-routing-protocol: thaliris-routing-v1" in protocol_text else None, "pass": routing.is_file() and "thaliris-routing-protocol: thaliris-routing-v1" in protocol_text}
    harness = [Path(path) for path in harness_paths]
    checks["benchmark_harness"] = {"sha256": _hash_files(harness) if all(path.is_file() for path in harness) else None, "pass": bool(harness) and all(path.is_file() for path in harness)}
    checks["evaluator"] = {"path": str(evaluator_path), "sha256": _sha(evaluator_path) if evaluator_path.is_file() else None, "pass": evaluator_path.is_file()}
    trusted = list(trusted_paths)
    frozen_trusted = trusted_identity(trusted) if trusted and all(path.is_file() for path in trusted) else None
    checks["trusted_surface"] = {"identity": frozen_trusted, "pass": bool(trusted) and frozen_trusted is not None and verify_trusted(frozen_trusted, trusted)}
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    checks["clean_fixture"] = {"status": status, "pass": status in {"", None}}
    checks["python_runtime"] = {"version": sys.version, "encoding": sys.getdefaultencoding(), "stdout_encoding": getattr(sys.stdout, "encoding", None), "pass": bool(sys.getdefaultencoding() and getattr(sys.stdout, "encoding", None))}
    try:
        from thaliris import codex_adapter, intent_audit
        profiles = []
        for filename, (model, effort, role) in codex_adapter._AGENT_PROFILES.items():
            path = root / ".codex" / "agents" / filename
            profiles.append(path.is_file() and path.read_bytes() == codex_adapter._agent_profile(filename.removesuffix(".toml"), role, model, effort))
        role_pack = root / "docs" / "thaliris-role-packs.md"
        checks["generated_surfaces"] = {"profiles": profiles, "role_pack": role_pack.is_file() and role_pack.read_bytes() == codex_adapter.ROLE_PACKS.encode("utf-8"), "pass": bool(profiles) and all(profiles) and role_pack.is_file() and role_pack.read_bytes() == codex_adapter.ROLE_PACKS.encode("utf-8")}
        hooks = root / ".codex" / "hooks.json"
        hook_ok = False
        if hooks.is_file():
            hook_data = json.loads(hooks.read_text(encoding="utf-8"))
            _, changed = intent_audit.merge_hooks(hook_data)
            hook_ok = not changed
        checks["hooks"] = {"path": str(hooks), "pass": hook_ok}
        checks["control_plane"] = {"canonical": intent_audit._context_arguments("context task-status") is not None, "fake_path": intent_audit._context_arguments("evil/context.cmd task-status") is None, "pass": intent_audit._context_arguments("context task-status") is not None and intent_audit._context_arguments("evil/context.cmd task-status") is None}
    except (OSError, ValueError, json.JSONDecodeError, ImportError) as exc:
        checks["generated_surfaces"] = {"pass": False, "error": str(exc)}
        checks["hooks"] = {"pass": False}
        checks["control_plane"] = {"pass": False}
    manifest = build_manifest(root)
    checks["candidate_manifest_reproducible"] = {"identity": manifest["identity"], "pass": build_manifest(root)["identity"] == manifest["identity"]}
    checks["gold"] = {"result": gold_result, "pass": isinstance(gold_result, dict) and gold_result.get("status") == "PASS"}
    checks["untouched_base"] = {"result": base_result, "pass": isinstance(base_result, dict) and base_result.get("status") == "FAIL"}
    checks["no_edit_identity"] = {"actual": no_edit_identity, "base": base_identity, "pass": no_edit_identity is not None and no_edit_identity == base_identity}
    passed = all(value.get("pass") is True for value in checks.values())
    return {"status": "PASS" if passed else "PREFLIGHT_FAIL", "checks": checks}
