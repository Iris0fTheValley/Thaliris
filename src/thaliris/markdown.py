"""Strict, dependency-free Markdown front-matter handling."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess

REQUIRED = ("Evidence", "Revision", "Status", "Applicability", "Confidence")
OPTIONAL_LISTS = ("Audience", "Topics", "Symbols")
KINDS = {"MEMORY", "HARD_CONSTRAINT"}
# STALE is an effective runtime state, never a captured historical value.
CONFIDENCE = {"CONFIRMED", "SUPPORTED", "UNVERIFIED"}
STATUS = {"DRAFT", "ACTIVE", "SUPERSEDED", "DONE"}


@dataclass(frozen=True)
class Entry:
    path: Path
    meta: dict[str, object]
    body: str


def parse(path: Path) -> Entry:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{path}: unterminated front matter")
    meta: dict[str, object] = {}
    for line in text[4:end].splitlines():
        match = re.fullmatch(r"([A-Za-z][A-Za-z ]*): (.+)", line)
        if not match:
            raise ValueError(f"{path}: invalid front matter line")
        key, raw = match.groups()
        if key in meta:
            raise ValueError(f"{path}: duplicate front matter field {key}")
        try:
            meta[key] = json.loads(raw) if raw.startswith("[") else raw
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid list field {key}") from exc
    missing = set(REQUIRED) - set(meta)
    if missing or meta["Confidence"] not in CONFIDENCE or meta["Status"] not in STATUS:
        raise ValueError(f"{path}: required metadata invalid")
    if not isinstance(meta["Revision"], str) or not re.fullmatch(r"[1-9][0-9]*", meta["Revision"]):
        raise ValueError(f"{path}: Revision must be a positive integer")
    for key in OPTIONAL_LISTS:
        if key in meta and (not isinstance(meta[key], list) or not all(isinstance(item, str) and item for item in meta[key])):
            raise ValueError(f"{path}: {key} must be a JSON string list")
    if "Audience" in meta and not set(meta["Audience"]) <= {"all", "controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer"}:
        raise ValueError(f"{path}: Audience contains an unknown role")
    if "Kind" in meta and meta["Kind"] not in KINDS:
        raise ValueError(f"{path}: Kind must be MEMORY or HARD_CONSTRAINT")
    return Entry(path, meta, text[end + 5:])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_status(entry: Entry, root: Path) -> tuple[str, list[str]]:
    """Evaluate file/content evidence without changing the recorded fact."""
    evidence = entry.meta["Evidence"]
    specs = evidence if isinstance(evidence, list) else ([] if evidence == "NONE" else [evidence])
    stale: list[str] = []
    for spec in specs:
        if not isinstance(spec, str):
            stale.append("invalid evidence")
            continue
        # file:relative/path#content-sha256 and git:relative/path#blob-sha1
        match = re.fullmatch(r"(?:file|git):([^#]+)#([0-9a-fA-F]{40,64})", spec)
        if not match:
            stale.append(spec)
            continue
        candidate = (root / match.group(1)).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            stale.append(match.group(1))
            continue
        if not candidate.is_file():
            stale.append(match.group(1))
            continue
        kind = spec.split(":", 1)[0]
        if kind == "git":
            relative = str(candidate.relative_to(root)).replace("\\", "/")
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative], cwd=root, capture_output=True, text=True, check=False)
            indexed = subprocess.run(["git", "rev-parse", "--verify", f":{relative}"], cwd=root, capture_output=True, text=True, check=False)
            probe = subprocess.run(["git", "hash-object", "--", relative], cwd=root, capture_output=True, text=True, check=False)
            actual = probe.stdout.strip() if tracked.returncode == indexed.returncode == probe.returncode == 0 and indexed.stdout.strip().lower() == match.group(2).lower() else ""
        else:
            actual = sha256(candidate)
        if actual.lower() != match.group(2).lower():
            stale.append(match.group(1))
    return ("STALE" if stale else "FRESH", stale)

