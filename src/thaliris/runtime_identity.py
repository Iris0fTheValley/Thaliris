"""Exact dedicated-venv identity for a Host-installed Thaliris runtime.

The base CPython standard library and operating system are outside this
installed-runtime boundary and remain platform trust dependencies.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

MANIFEST_NAME = "thaliris-install.json"
MANIFEST_FORMAT = "thaliris-installed-runtime-v1"


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _safe_file(path: Path) -> Path:
    if not path.is_absolute() or not path.is_file() or _is_link(path):
        raise ValueError(f"unsafe runtime file: {path}")
    resolved = path.resolve(strict=True)
    for parent in (path, *path.parents):
        if _is_link(parent):
            raise ValueError(f"runtime path contains a symlink: {path}")
    return resolved


def _package_dir(executable: Path) -> Path:
    executable = _safe_file(executable)
    parent = executable.parent
    if parent.name.casefold() not in {"scripts", "bin"}:
        raise ValueError("Thaliris launcher is not in a virtual environment Scripts/bin directory")
    venv = parent.parent
    if not (venv / "pyvenv.cfg").is_file() or _is_link(venv / "pyvenv.cfg"):
        raise ValueError("Thaliris launcher is not in a virtual environment")
    if parent.name.casefold() == "scripts":
        candidates = [venv / "Lib" / "site-packages" / "thaliris"]
    else:
        candidates = list((venv / "lib").glob("python*/site-packages/thaliris"))
    candidates = [candidate for candidate in candidates if candidate.is_dir()]
    if len(candidates) != 1:
        raise ValueError("installed Thaliris package directory is missing or ambiguous")
    package = candidates[0]
    for ancestor in (package, *package.parents):
        if _is_link(ancestor):
            raise ValueError("installed Thaliris package path contains a symlink")
    if not (package / "__init__.py").is_file() or not (package / "cli.py").is_file():
        raise ValueError("installed Thaliris package is incomplete")
    return package.resolve(strict=True)


def _assert_isolated_venv(venv: Path) -> None:
    """Reject Python startup paths that can import code outside the pinned tree."""
    config = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
    settings = {}
    for line in config.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            settings[key.strip().casefold()] = value.strip().casefold()
    if settings.get("include-system-site-packages") != "false":
        raise ValueError("installed runtime must disable system site packages")
    for pth in venv.rglob("*.pth"):
        if _is_link(pth) or not pth.is_file():
            raise ValueError("unsafe installed runtime .pth file")
        try:
            lines = pth.read_text(encoding="utf-8").splitlines()
        except UnicodeError as exc:
            raise ValueError("unsafe installed runtime .pth encoding") from exc
        if any(line.strip() and not line.lstrip().startswith("#") for line in lines):
            raise ValueError("installed runtime .pth may not execute or extend import paths")


def _files(venv: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for root, dirs, files in os.walk(venv, followlinks=False):
        root_path = Path(root)
        dirs[:] = sorted(dirs)
        for name in dirs:
            if _is_link(root_path / name):
                raise ValueError("installed runtime contains a symlink")
        for name in sorted(files):
            relative = (root_path / name).relative_to(venv).as_posix()
            path = _safe_file(root_path / name)
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result or "pyvenv.cfg" not in result:
        raise ValueError("installed runtime is incomplete")
    return dict(sorted(result.items()))


def manifest_bytes(executable: Path) -> bytes:
    launcher = _safe_file(executable)
    package = _package_dir(launcher)
    venv = launcher.parent.parent.resolve(strict=True)
    _assert_isolated_venv(venv)
    record = {
        "format": MANIFEST_FORMAT,
        "executable": str(launcher),
        "executable_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
        "venv_dir": str(venv),
        "package_dir": str(package),
        "files": _files(venv),
    }
    return (json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def manifest_identity(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def validate_manifest(contents: bytes, executable: Path, identity: str) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{64}", identity) or manifest_identity(contents) != identity:
        raise ValueError("installed runtime manifest identity mismatch")
    try:
        record = json.loads(contents)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid installed runtime manifest") from exc
    validate_manifest_record(contents)
    current_bytes = manifest_bytes(executable)
    if contents != current_bytes:
        raise ValueError("installed Thaliris runtime changed")
    return record


def validate_manifest_record(contents: bytes) -> dict[str, object]:
    """Validate owned manifest bytes without requiring the old runtime to survive."""
    try:
        record = json.loads(contents)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid installed runtime manifest") from exc
    required = {"format", "executable", "executable_sha256", "venv_dir", "package_dir", "files"}
    legacy = required - {"venv_dir"}
    if not isinstance(record, dict) or set(record) not in (required, legacy) or record.get("format") != MANIFEST_FORMAT:
        raise ValueError("invalid installed runtime manifest format")
    is_legacy = set(record) == legacy
    executable = Path(record["executable"]) if isinstance(record["executable"], str) else Path()
    venv = (Path(record["venv_dir"]) if isinstance(record.get("venv_dir"), str) else Path()) if not is_legacy else executable.parent.parent
    package = Path(record["package_dir"]) if isinstance(record["package_dir"], str) else Path()
    if (not executable.is_absolute() or not venv.is_absolute() or not package.is_absolute()
            or executable.parent.parent != venv or not package.is_relative_to(venv)
            or not re.fullmatch(r"[0-9a-f]{64}", str(record["executable_sha256"]))):
        raise ValueError("invalid installed runtime manifest paths")
    files = record["files"]
    essential = ({"__init__.py", "cli.py"} if is_legacy else {
        "pyvenv.cfg", executable.relative_to(venv).as_posix(),
        (package / "__init__.py").relative_to(venv).as_posix(),
        (package / "cli.py").relative_to(venv).as_posix(),
    })
    if not isinstance(files, dict) or not files or not essential <= set(files):
        raise ValueError("invalid installed runtime manifest files")
    for name, digest in files.items():
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name or name.startswith("/")
                or any(part in {"", ".", ".."} for part in name.split("/"))
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid installed runtime manifest file entry")
    if not is_legacy and files[executable.relative_to(venv).as_posix()] != record["executable_sha256"]:
        raise ValueError("invalid installed runtime launcher hash")
    if contents != (json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"):
        raise ValueError("invalid installed runtime manifest serialization")
    return record
