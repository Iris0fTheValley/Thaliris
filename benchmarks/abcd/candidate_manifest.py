"""Deterministic candidate identity for observable product surfaces.

This module deliberately has no benchmark-specific source names.  It hashes
the candidate checkout as observed by Git plus legal untracked files.  Only
the explicit manifest policy decides which non-product surfaces are excluded.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


DEFAULT_POLICY = {
    "task_state_surface": [".git", ".context", ".agent-memory", ".milestones"],
    "trusted_runtime_surface": [],
    "benchmark_infrastructure_surface": [],
}
MANIFEST_VERSION = 2


def _included(path: str, policy: dict[str, list[str]]) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    excluded = [item.replace("\\", "/").strip("/") for values in policy.values() for item in values]
    return normalized not in excluded and not any(normalized.startswith(prefix + "/") for prefix in excluded)


def _files(root: Path, policy: dict[str, list[str]]) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise ValueError("candidate manifest requires a Git checkout")
    paths = {item.decode("utf-8") for item in proc.stdout.split(b"\0") if item}
    return sorted(path.replace("\\", "/") for path in paths if _included(path, policy))


def _entry(root: Path, path: str) -> dict[str, Any]:
    target = root.joinpath(*path.split("/"))
    if target.is_symlink():
        link = target.readlink().as_posix().encode("utf-8")
        return {"path": path, "state": "SYMLINK", "sha256": hashlib.sha256(link).hexdigest(), "mode": target.lstat().st_mode & 0o7777}
    if not target.exists():
        return {"path": path, "state": "DELETED", "sha256": None, "mode": None}
    if not target.is_file():
        return {"path": path, "state": "SPECIAL", "sha256": None, "mode": target.stat().st_mode & 0o7777}
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": path, "state": "PRESENT", "sha256": digest.hexdigest(), "mode": target.stat().st_mode & 0o7777}


def _policy(value: dict[str, Any] | None) -> dict[str, list[str]]:
    selected = {key: list(values) for key, values in DEFAULT_POLICY.items()}
    if value is not None:
        if set(value) != set(DEFAULT_POLICY) or any(not isinstance(values, list) or not all(isinstance(item, str) and item for item in values) for values in value.values()):
            raise ValueError("candidate manifest policy must name all explicit surfaces")
        selected = {key: list(values) for key, values in value.items()}
    return selected


def build_manifest(root: Path, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root.resolve()
    selected = _policy(policy)
    entries = [_entry(root, path) for path in _files(root, selected)]
    payload = {"version": MANIFEST_VERSION, "policy": selected, "files": entries}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"manifest": payload, "identity": hashlib.sha256(encoded).hexdigest()}


def candidate_identity(root: Path, policy: dict[str, Any] | None = None) -> str:
    return str(build_manifest(root, policy)["identity"])
