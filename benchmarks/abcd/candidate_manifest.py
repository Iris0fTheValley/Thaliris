"""Deterministic candidate identity for observable product surfaces.

This module deliberately has no benchmark-specific source names.  It hashes
the candidate checkout as observed on disk, retaining deleted tracked paths.
Only the explicit manifest policy decides which non-product surfaces are
excluded; Git ignore rules are never an observable-surface policy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import os
import subprocess
from typing import Any


DEFAULT_POLICY = {
    "task_state_surface": [".git", ".context", ".agent-memory", ".milestones"],
    "trusted_runtime_surface": [],
    "benchmark_infrastructure_surface": [],
}
MANIFEST_VERSION = 2
_EXTERNAL_SYMLINK_POLICY = "external_symlink_surface"


def _excluded_prefixes(policy: dict[str, list[str]]) -> list[str]:
    return [item.replace("\\", "/").strip("/") for key, values in policy.items() if key != _EXTERNAL_SYMLINK_POLICY for item in values]


def _included(path: str, policy: dict[str, list[str]]) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    excluded = _excluded_prefixes(policy)
    return normalized not in excluded and not any(normalized.startswith(prefix + "/") for prefix in excluded)


def _files(root: Path, policy: dict[str, list[str]]) -> list[str]:
    """Return the observed surface, including ignored untracked files.

    Git is used only to retain deleted tracked paths.  ``.gitignore`` is not
    an identity policy: an ignored file is still observable unless the frozen
    explicit policy excludes it.
    """
    proc = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False)
    if proc.returncode:
        raise ValueError("candidate manifest requires a Git checkout")
    paths = {item.decode("utf-8") for item in proc.stdout.split(b"\0") if item}
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if _included((current_path / name).relative_to(root).as_posix(), policy)]
        for name in files:
            paths.add((current_path / name).relative_to(root).as_posix())
        # os.walk reports symlinked directories in dirs; represent the link,
        # but never walk through it.
        for name in list(dirs):
            candidate = current_path / name
            if candidate.is_symlink():
                dirs.remove(name)
                paths.add(candidate.relative_to(root).as_posix())
    return sorted(path.replace("\\", "/") for path in paths if _included(path, policy))


def _entry(root: Path, path: str, policy: dict[str, list[str]]) -> dict[str, Any]:
    target = root.joinpath(*path.split("/"))
    if target.is_symlink():
        resolved = target.resolve(strict=False)
        try:
            relative_target = resolved.relative_to(root).as_posix()
            external = False
        except ValueError:
            relative_target = str(resolved)
            external = True
        registrations = policy.get(_EXTERNAL_SYMLINK_POLICY, [])
        registration = next((item for item in registrations if isinstance(item, dict) and item.get("path") == path), None)
        if external and not isinstance(registration, dict):
            raise ValueError(f"EXTERNAL_SYMLINK_SURFACE: {path}")
        target_sha = None
        if resolved.is_file():
            target_sha = _file_sha(resolved)
        if resolved.is_dir():
            raise ValueError(f"EXTERNAL_SYMLINK_SURFACE: directory link {path}")
        if external and (
            registration.get("content_sha256") != target_sha
            or not isinstance(registration.get("attestation_id"), str)
            or not registration["attestation_id"]
        ):
            raise ValueError(f"EXTERNAL_SYMLINK_SURFACE: unverified dependency {path}")
        link = target.readlink().as_posix().encode("utf-8")
        return {
            "path": path,
            "state": "SYMLINK",
            "sha256": hashlib.sha256(link).hexdigest(),
            "mode": target.lstat().st_mode & 0o7777,
            "resolved_target": relative_target,
            "resolved_target_sha256": target_sha,
            "external": external,
        }
    if not target.exists():
        return {"path": path, "state": "DELETED", "sha256": None, "mode": None}
    if not target.is_file():
        return {"path": path, "state": "SPECIAL", "sha256": None, "mode": target.stat().st_mode & 0o7777}
    return {"path": path, "state": "PRESENT", "sha256": _file_sha(target), "mode": target.stat().st_mode & 0o7777}


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _policy(value: dict[str, Any] | None) -> dict[str, list[str]]:
    selected = {key: list(values) for key, values in DEFAULT_POLICY.items()}
    if value is not None:
        required = set(DEFAULT_POLICY)
        invalid = any(
            key not in required | {_EXTERNAL_SYMLINK_POLICY}
            or not isinstance(values, list)
            or key != _EXTERNAL_SYMLINK_POLICY and not all(isinstance(item, str) and item for item in values)
            for key, values in value.items()
        )
        if not required <= set(value) or invalid:
            raise ValueError("candidate manifest policy must name all explicit surfaces")
        selected = {key: list(value[key]) for key in DEFAULT_POLICY}
        if _EXTERNAL_SYMLINK_POLICY in value:
            external = value[_EXTERNAL_SYMLINK_POLICY]
            if not isinstance(external, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("path"), str)
                or not item["path"]
                or not isinstance(item.get("content_sha256"), str)
                or len(item["content_sha256"]) != 64
                or not isinstance(item.get("attestation_id"), str)
                or not item["attestation_id"]
                for item in external
            ):
                raise ValueError("external symlink policy requires frozen content attestations")
            selected[_EXTERNAL_SYMLINK_POLICY] = list(external)
    return selected


def build_manifest(root: Path, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root.resolve()
    selected = _policy(policy)
    entries = [_entry(root, path, selected) for path in _files(root, selected)]
    payload = {"version": MANIFEST_VERSION, "policy": selected, "files": entries}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"manifest": payload, "identity": hashlib.sha256(encoded).hexdigest()}


def candidate_identity(root: Path, policy: dict[str, Any] | None = None) -> str:
    return str(build_manifest(root, policy)["identity"])
