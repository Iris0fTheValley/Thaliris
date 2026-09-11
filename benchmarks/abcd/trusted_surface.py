"""Content identity for host-provided Thaliris infrastructure.

The logical hook specification is not enough to establish trust.  A formal
run pins the actual wrapper/runtime bytes before execution and verifies them
again afterwards.  This module does not make a mutable workspace immutable;
it makes any mutation observable and fail closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity(paths: Iterable[Path]) -> dict[str, Any]:
    entries = []
    for raw in sorted((Path(path).resolve() for path in paths), key=str):
        if not raw.is_file() or raw.is_symlink():
            raise ValueError(f"trusted infrastructure is not a regular file: {raw}")
        entries.append({"path": str(raw), "sha256": _digest(raw), "size": raw.stat().st_size})
    payload = {"version": 1, "files": entries}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"manifest": payload, "identity": hashlib.sha256(encoded).hexdigest()}


def verify(expected: dict[str, Any], paths: Iterable[Path]) -> bool:
    try:
        return identity(paths) == expected
    except (OSError, ValueError):
        return False


def mutation_probe(path: Path) -> str:
    """Probe the actual write boundary, restoring bytes if the host allows it."""
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        return "NOT_OBSERVED"
    original = path.read_bytes()
    try:
        with path.open("ab") as stream:
            stream.write(b"\0")
        path.write_bytes(original)
        return "ALLOWED"
    except PermissionError:
        return "DENIED"
    except OSError:
        return "NOT_OBSERVED"
