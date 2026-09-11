"""Deterministic candidate identity for observable product surfaces.

This module deliberately has no benchmark-specific source names.  It hashes
the candidate checkout as observed by Git plus legal untracked files, while
excluding task state, telemetry, and injected runtime infrastructure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


EXCLUDED_PREFIXES = (
    ".git/",
    ".context/",
    ".agent-memory/",
    ".milestones/",
    ".codex/",
    "benchmarks/",
)
EXCLUDED_NAMES = {".git", ".context", ".agent-memory", ".milestones", ".codex"}


def _included(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized not in EXCLUDED_NAMES and not any(normalized.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def _files(root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise ValueError("candidate manifest requires a Git checkout")
    paths = {item.decode("utf-8") for item in proc.stdout.split(b"\0") if item}
    return sorted(path.replace("\\", "/") for path in paths if _included(path))


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


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    entries = [_entry(root, path) for path in _files(root)]
    payload = {"version": 1, "excluded_prefixes": list(EXCLUDED_PREFIXES), "files": entries}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"manifest": payload, "identity": hashlib.sha256(encoded).hexdigest()}


def candidate_identity(root: Path) -> str:
    return str(build_manifest(root)["identity"])
