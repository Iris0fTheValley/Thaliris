"""Project Identity plane: a versioned, explicitly amended project baseline.

The repository-tracked ``.project-identity/`` namespace holds one project's
current canonical statement of identity and its immutable history.  Core
records, versions, validates references and syntax, enforces compare-and-swap
and atomic writes, observes divergence and returns bounded content.  Models
own every semantic judgment: which layer a change belongs to, whether a
challenge is valid, whether an amendment is wise, what is affected and what
must be revalidated.  Nothing here propagates, gates or injects anything.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import uuid

from . import core

NAMESPACE = ".project-identity"
BASELINE_PATH = f"{NAMESPACE}/IDENTITY.md"
LEDGER_PATH = f"{NAMESPACE}/ledger.json"
LEDGER_FORMAT = "thaliris-project-identity-v1"

IDENTITY_MAX_BYTES = 64 * 1024
RESPONSE_MAX_BYTES = 64 * 1024
STATUS_MAX_BYTES = 16 * 1024
STATUS_MAX_ITEMS = 64
STATUS_MAX_OPEN_CHALLENGES = 16
MAX_VERSIONS = 1000
MAX_CHALLENGES = 512
MAX_RELATIONS = 2048
TRACE_MAX_DEPTH = 4
TRACE_MAX_EDGES = 128
DEPENDENTS_MAX = 128
INPUT_MAX_BYTES = 1024 * 1024
LEDGER_MAX_BYTES = 2 * 1024 * 1024
RECORD_MAX_BYTES = 256 * 1024
REF_MAX_CHARS = 1024
LONG_TEXT_MAX = 16_384
SUMMARY_MAX = 300
DETAIL_MAX_ENTRIES = 8

NOTICE = "Registered relations only; absence of a relation is not evidence of independence."
BACKUP_ACTIONS = ("identity-amend", "identity-challenge", "identity-relate")
RELATION_TYPES = ("serves", "supports", "challenges", "supersedes")

_ITEM_ID = r"[A-Z][A-Z0-9]{0,15}-[0-9]{1,4}"
_ITEM_ID_RE = re.compile(_ITEM_ID)
_ANCHOR_RE = re.compile(rf"({_ITEM_ID})(?![A-Za-z0-9_-])")
_HEADING_RE = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*")
_HEADING_CLOSE_RE = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
_FENCE_OPEN_RE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_FENCE_CLOSE_RE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
_TITLE_LEAD_RE = re.compile(r"^[\s:.)\]\-–—]+")
_CHALLENGE_ID_RE = re.compile(r"CH-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}")
_RELATION_ID_RE = re.compile(r"REL-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}")
_AMENDMENT_ID_RE = re.compile(r"A-([0-9]{4})")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_TASK_REF_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/([A-Za-z0-9_.:-]{1,64})")
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,40}")
_URL_RE = re.compile(r"https?://[^\s]+")
_AMENDMENT_RECORD_MARKER = "\n## Record\n\n```json\n"

_VERSION_FIELDS = {"version", "path", "sha256", "raw_sha256", "amendment", "recorded_at"}
_AMENDMENT_INDEX_FIELDS = {"id", "path", "from_version", "to_version", "sha256", "summary", "recorded_at"}
_CHALLENGE_FIELDS = {"id", "targets", "summary", "text", "evidence_refs", "proposed_change",
                     "identity_version", "task_id", "actor", "recorded_at"}
_RESOLUTION_FIELDS = {"challenge", "resolution", "amendment", "reason", "task_id", "actor", "recorded_at"}
_RELATION_FIELDS = {"id", "from", "rel", "to", "note", "task_id", "actor", "recorded_at"}
_RETRACTION_FIELDS = {"relation", "reason", "task_id", "actor", "recorded_at"}


# ---------------------------------------------------------------------------
# Canonical hashing and item anchors


def canonical_bytes(data: bytes) -> bytes:
    """Return the canonical form: no UTF-8 BOM, CRLF and CR normalized to LF."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def canonical_sha256(data: bytes) -> str:
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def _file_hashes(path: Path) -> tuple[str, str]:
    """Stream (canonical sha256, raw sha256) so size never forces a full read."""
    canonical = hashlib.sha256()
    raw = hashlib.sha256()
    carry = b""
    first = True
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            raw.update(chunk)
            data = carry + chunk
            if first:
                first = False
                if data.startswith(b"\xef\xbb\xbf"):
                    data = data[3:]
            if data.endswith(b"\r"):
                carry, data = b"\r", data[:-1]
            else:
                carry = b""
            canonical.update(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    if carry:
        canonical.update(b"\n")
    return canonical.hexdigest(), raw.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Item:
    """One anchored item: the heading through the line before the next heading of the same or higher level."""

    id: str
    title: str
    level: int
    text: str
    sha256: str


def parse_items(text: str) -> dict[str, Item]:
    """Parse anchored ATX headings outside fenced code; duplicate ids are invalid.

    Core imposes no taxonomy: any id prefix is accepted.  Trailing blank lines
    of an item are not part of its canonical item text.
    """
    lines = text.split("\n")
    headings: list[tuple[int, int, str]] = []
    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        if fence is not None:
            closing = _FENCE_CLOSE_RE.fullmatch(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= fence[1]:
                fence = None
            continue
        opening = _FENCE_OPEN_RE.fullmatch(line)
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = (opening.group(1)[0], len(opening.group(1)))
            continue
        heading = _HEADING_RE.fullmatch(line)
        if heading:
            content = _HEADING_CLOSE_RE.sub("", heading.group(2) or "").strip()
            headings.append((index, len(heading.group(1)), content))
    items: dict[str, Item] = {}
    for position, (index, level, content) in enumerate(headings):
        anchor = _ANCHOR_RE.match(content)
        if anchor is None:
            continue
        identifier = anchor.group(1)
        if identifier in items:
            raise ValueError(f"duplicate identity item anchor {identifier}")
        end = len(lines)
        for later_index, later_level, _ in headings[position + 1:]:
            if later_level <= level:
                end = later_index
                break
        body = "\n".join(lines[index:end]).rstrip()
        title = _TITLE_LEAD_RE.sub("", content[anchor.end():]).strip()[:200]
        items[identifier] = Item(identifier, title, level, body, _sha256_text(body))
    return items


def _item_diff(old: dict[str, Item], new: dict[str, Item]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(key for key in set(old) & set(new) if old[key].sha256 != new[key].sha256),
    }


# ---------------------------------------------------------------------------
# Small validators


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _response_size(value: object) -> int:
    """Size the exact UTF-8 JSON serialization used for retrieval bounds."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _has_control(value: str, *, allow_newlines: bool) -> bool:
    allowed = "\n\t" if allow_newlines else "\t"
    return any((ord(char) < 32 and char not in allowed) or ord(char) == 127 for char in value)


def _text(value: object, field: str, maximum: int = LONG_TEXT_MAX, *, line: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or _has_control(value, allow_newlines=not line):
        raise ValueError(f"invalid {field}")
    if line and ("\n" in value or "\r" in value):
        raise ValueError(f"invalid {field}")
    return value


def _optional_text(value: object, field: str, maximum: int = LONG_TEXT_MAX) -> str | None:
    return None if value is None else _text(value, field, maximum)


def _identity_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid identity text")
    text = canonical_bytes(value.encode("utf-8", errors="strict")).decode("utf-8")
    if not text.strip() or _has_control(text, allow_newlines=True):
        raise ValueError("invalid identity text")
    if len(text.encode("utf-8")) > IDENTITY_MAX_BYTES:
        raise ValueError(f"identity text exceeds {IDENTITY_MAX_BYTES} bytes")
    return text


def _string_list(value: object, field: str, maximum: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum or not all(isinstance(item, str) for item in value) or len(set(value)) != len(value):
        raise ValueError(f"invalid {field}")
    return list(value)


def _version_path(version: int) -> str:
    return f"{NAMESPACE}/versions/v{version:04d}.md"


def _amendment_id(version: int) -> str:
    return f"A-{version:04d}"


def _amendment_path(version: int) -> str:
    return f"{NAMESPACE}/amendments/{_amendment_id(version)}.md"


def _new_id(prefix: str, existing: set[str]) -> str:
    while True:
        identifier = f"{prefix}-{_now():%Y%m%dT%H%M%SZ}-{secrets.token_hex(6)}"
        if identifier not in existing:
            return identifier


def _read_identity_input(value: str | dict[str, object] | None) -> dict[str, object]:
    if isinstance(value, dict):
        raw: object = value
    elif isinstance(value, str):
        if value == "-":
            source = sys.stdin.read(INPUT_MAX_BYTES + 1)
        else:
            path = Path(value)
            if path.stat().st_size > INPUT_MAX_BYTES:
                raise ValueError(f"identity input exceeds {INPUT_MAX_BYTES} bytes")
            source = path.read_text(encoding="utf-8")
        if len(source.encode("utf-8")) > INPUT_MAX_BYTES:
            raise ValueError(f"identity input exceeds {INPUT_MAX_BYTES} bytes")
        try:
            raw = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValueError("identity input must be JSON") from exc
    else:
        raise ValueError("identity input required")
    if not isinstance(raw, dict):
        raise ValueError("identity input must be a JSON object")
    return raw


# ---------------------------------------------------------------------------
# References


def parse_ref(value: object) -> tuple[str, dict[str, str]]:
    """Validate typed ref syntax only; existence is checked at registration."""
    if not isinstance(value, str) or not value or len(value) > REF_MAX_CHARS or value != value.strip() or _has_control(value, allow_newlines=False) or "\t" in value:
        raise ValueError("invalid ref")
    if value == "identity":
        return "identity", {}
    kind, separator, rest = value.partition(":")
    if not separator or not rest:
        raise ValueError(f"invalid ref {value!r}")
    if kind == "identity":
        if not _ITEM_ID_RE.fullmatch(rest):
            raise ValueError(f"invalid identity item ref {value!r}")
        return "identity_item", {"item": rest}
    if kind == "amendment":
        if not _AMENDMENT_ID_RE.fullmatch(rest):
            raise ValueError(f"invalid amendment ref {value!r}")
        return "amendment", {"amendment": rest}
    if kind == "challenge":
        if not _CHALLENGE_ID_RE.fullmatch(rest):
            raise ValueError(f"invalid challenge ref {value!r}")
        return "challenge", {"challenge": rest}
    if kind == "path":
        path, has_anchor, anchor = rest.partition("#")
        if not path or (has_anchor and (not anchor or len(anchor) > 256 or any(char.isspace() for char in anchor))):
            raise ValueError(f"invalid path ref {value!r}")
        parts = {"path": path}
        if has_anchor:
            parts["anchor"] = anchor
        return "path", parts
    if kind == "task":
        match = _TASK_REF_RE.fullmatch(rest)
        if not match or str(uuid.UUID(match.group(1))) != match.group(1):
            raise ValueError(f"invalid task ref {value!r}")
        return "task", {"task_id": match.group(1), "object_id": match.group(2)}
    if kind == "commit":
        if not _COMMIT_RE.fullmatch(rest):
            raise ValueError(f"invalid commit ref {value!r}")
        return "commit", {}
    if kind == "url":
        if not _URL_RE.fullmatch(rest):
            raise ValueError(f"invalid url ref {value!r}")
        return "url", {}
    raise ValueError(f"unknown ref type {kind!r}")


def _is_identity_ref(value: str) -> bool:
    return value == "identity" or value.startswith("identity:")


@contextmanager
def _task_selection(root: Path, task_id: str):
    previous = core.selected_task(root)
    core.select_task(root, task_id)
    try:
        yield
    finally:
        core.select_task(root, previous)


def _verify_task_ref(root: Path, task_id: str, object_id: str) -> bool:
    """True when the local task ledger contains the object; False when unverifiable."""
    try:
        path = core._state_path(root, task_id)
    except ValueError:
        return False
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with _task_selection(root, task_id):
            core.task_get(root, object_id)
    except ValueError as exc:
        if str(exc) == "task object not found":
            raise ValueError(f"task ref object {object_id} not found in task {task_id}") from exc
        return False
    except OSError:
        return False
    return True


def _path_target(root: Path, relative: str) -> Path:
    normalized = core._valid_relative(root, relative)
    first = normalized.split("/", 1)[0]
    if first in {".git", ".context"}:
        raise ValueError("path ref targets private control data")
    return core._safe_without_final_symlink(root, normalized)


def _path_state(root: Path, relative: str, recorded: object, cache: dict[str, str | None]) -> str:
    if relative not in cache:
        try:
            target = _path_target(root, relative)
            cache[relative] = _file_hashes(target)[0] if target.is_file() else None
        except (OSError, ValueError):
            cache[relative] = None
    current = cache[relative]
    if current is None:
        return "MISSING"
    return "FRESH" if current == recorded else "CHANGED"


Scope = list[tuple[int, dict[str, Item]]]


def _resolve_ref(root: Path, ctx: "_Context", value: object, scope: Scope) -> dict[str, object]:
    """Validate a ref at registration and record what later states compare against."""
    kind, parts = parse_ref(value)
    assert isinstance(value, str)
    descriptor: dict[str, object] = {"ref": value, "type": kind}
    if kind == "identity":
        if not scope:
            raise ValueError("identity ref requires a recorded project identity")
        descriptor["version"] = scope[0][0]
    elif kind == "identity_item":
        for version, items in scope:
            if parts["item"] in items:
                descriptor["version"] = version
                descriptor["item_sha256"] = items[parts["item"]].sha256
                break
        else:
            raise ValueError(f"identity item {parts['item']} not found in the recorded identity")
    elif kind == "amendment":
        if parts["amendment"] not in ctx.amendment_ids:
            raise ValueError(f"amendment {parts['amendment']} not found")
    elif kind == "challenge":
        if parts["challenge"] not in ctx.challenges:
            raise ValueError(f"challenge {parts['challenge']} not found")
    elif kind == "path":
        try:
            target = _path_target(root, parts["path"])
        except ValueError as exc:
            raise ValueError(f"invalid path ref {value!r}: {exc}") from exc
        if not target.is_file():
            raise ValueError(f"path ref {value!r} does not name an existing file")
        descriptor["sha256"] = _file_hashes(target)[0]
    elif kind == "task":
        descriptor["verified"] = _verify_task_ref(root, parts["task_id"], parts["object_id"])
    return descriptor


def _endpoint_state(root: Path, version: int, items: dict[str, Item], descriptor: dict[str, object], cache: dict[str, str | None]) -> str:
    kind = descriptor.get("type")
    ref = str(descriptor.get("ref"))
    if kind == "identity":
        recorded = descriptor.get("version")
        return "CURRENT" if recorded == version else f"CHANGED_SINCE_v{recorded}"
    if kind == "identity_item":
        item = items.get(ref.split(":", 1)[1])
        if item is None:
            return "REMOVED"
        return "CURRENT" if item.sha256 == descriptor.get("item_sha256") else f"CHANGED_SINCE_v{descriptor.get('version')}"
    if kind == "path":
        return _path_state(root, ref[5:].partition("#")[0], descriptor.get("sha256"), cache)
    if kind == "task" and descriptor.get("verified") is not True:
        return "UNVERIFIED"
    return "RECORDED"


# ---------------------------------------------------------------------------
# Loading and integrity observation


class _Invalid(Exception):
    pass


@dataclass
class _Context:
    state: str = "ABSENT"
    detail: list[str] = field(default_factory=list)
    format: str | None = None
    ledger: dict[str, object] | None = None
    version: int = 0
    text: str | None = None
    items: dict[str, Item] = field(default_factory=dict)
    recorded_sha256: str | None = None
    on_disk_sha256: str | None = None
    on_disk_raw_sha256: str | None = None
    amendment_ids: set[str] = field(default_factory=set)
    challenges: dict[str, dict[str, object]] = field(default_factory=dict)
    resolutions: dict[str, dict[str, object]] = field(default_factory=dict)
    relations: dict[str, dict[str, object]] = field(default_factory=dict)
    retractions: dict[str, dict[str, object]] = field(default_factory=dict)

    def scope(self) -> Scope:
        return [(self.version, self.items)] if self.version else []

    def open_challenges(self) -> list[dict[str, object]]:
        values = [value for key, value in self.challenges.items() if key not in self.resolutions]
        return sorted(values, key=lambda value: (str(value["recorded_at"]), str(value["id"])))

    def active_relations(self) -> list[dict[str, object]]:
        values = [value for key, value in self.relations.items() if key not in self.retractions]
        return sorted(values, key=lambda value: (str(value["recorded_at"]), str(value["id"])))


def _read_bounded(root: Path, relative: str, maximum: int) -> bytes | None:
    try:
        target = core._safe_without_final_symlink(root, relative)
    except ValueError as exc:
        raise _Invalid(f"{relative}: {exc}") from exc
    if not target.exists():
        return None
    if not target.is_file():
        raise _Invalid(f"{relative}: not a regular file")
    if target.stat().st_size > maximum:
        raise _Invalid(f"{relative}: exceeds {maximum} bytes")
    data = target.read_bytes()
    if len(data) > maximum:
        raise _Invalid(f"{relative}: exceeds {maximum} bytes")
    return data


def _load_json(root: Path, relative: str, maximum: int) -> object:
    data = _read_bounded(root, relative, maximum)
    if data is None:
        raise _Invalid(f"{relative}: missing")
    try:
        return json.loads(canonical_bytes(data).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _Invalid(f"{relative}: invalid JSON") from exc


def _validate_ledger(root: Path, ctx: _Context, raw: object) -> None:
    if not isinstance(raw, dict):
        raise _Invalid("ledger.json: not a JSON object")
    fmt = raw.get("format")
    ctx.format = fmt if isinstance(fmt, str) else None
    if fmt != LEDGER_FORMAT:
        raise _Invalid(f"ledger.json: unsupported ledger format {str(fmt)[:64]!r}; this Core reads and writes {LEDGER_FORMAT}")
    if set(raw) != {"format", "version", "versions", "amendments"}:
        raise _Invalid("ledger.json: unexpected fields")
    version = raw["version"]
    if type(version) is not int or not 1 <= version <= MAX_VERSIONS:
        raise _Invalid("ledger.json: invalid version")
    versions, amendments = raw["versions"], raw["amendments"]
    if not isinstance(versions, list) or not isinstance(amendments, list) or len(versions) != version or len(amendments) != version:
        raise _Invalid("ledger.json: version chain length does not match version (duplicate or missing version)")
    for number, (entry, amendment) in enumerate(zip(versions, amendments), start=1):
        if not isinstance(entry, dict) or set(entry) != _VERSION_FIELDS:
            raise _Invalid(f"ledger.json: invalid entry for v{number:04d}")
        if entry["version"] != number or entry["path"] != _version_path(number)[len(NAMESPACE) + 1:] or entry["amendment"] != _amendment_id(number):
            raise _Invalid(f"ledger.json: version chain is not contiguous at v{number:04d} (duplicate or missing version)")
        if not all(isinstance(entry[key], str) and _HEX64_RE.fullmatch(entry[key]) for key in ("sha256", "raw_sha256")) or not isinstance(entry["recorded_at"], str):
            raise _Invalid(f"ledger.json: invalid hashes for v{number:04d}")
        if not isinstance(amendment, dict) or set(amendment) != _AMENDMENT_INDEX_FIELDS:
            raise _Invalid(f"ledger.json: invalid amendment index entry {number}")
        if (amendment["id"] != _amendment_id(number) or amendment["from_version"] != number - 1 or amendment["to_version"] != number
                or amendment["path"] != _amendment_path(number)[len(NAMESPACE) + 1:]):
            raise _Invalid(f"ledger.json: amendment chain is not contiguous at {_amendment_id(number)}")
        if not isinstance(amendment["sha256"], str) or not _HEX64_RE.fullmatch(amendment["sha256"]) or not isinstance(amendment["summary"], str) or not isinstance(amendment["recorded_at"], str):
            raise _Invalid(f"ledger.json: invalid amendment index entry {_amendment_id(number)}")
        snapshot = _read_bounded(root, _version_path(number), IDENTITY_MAX_BYTES)
        if snapshot is None:
            raise _Invalid(f"missing snapshot {_version_path(number)}")
        if canonical_sha256(snapshot) != entry["sha256"]:
            raise _Invalid(f"snapshot hash mismatch for {_version_path(number)}")
        record = _read_bounded(root, _amendment_path(number), RECORD_MAX_BYTES)
        if record is None:
            raise _Invalid(f"missing amendment record {_amendment_path(number)}")
        if canonical_sha256(record) != amendment["sha256"]:
            raise _Invalid(f"amendment record hash mismatch for {_amendment_path(number)}")
        if number == version:
            try:
                ctx.text = canonical_bytes(snapshot).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _Invalid(f"{_version_path(number)}: not UTF-8") from exc
            try:
                ctx.items = parse_items(ctx.text)
            except ValueError as exc:
                raise _Invalid(f"{_version_path(number)}: {exc}") from exc
    ctx.ledger = raw
    ctx.version = version
    ctx.recorded_sha256 = str(versions[-1]["sha256"])
    ctx.amendment_ids = {str(item["id"]) for item in amendments}


def _check_descriptor(value: object, where: str) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("ref"), str):
        raise _Invalid(f"{where}: invalid ref descriptor")
    try:
        kind, _ = parse_ref(value["ref"])
    except ValueError as exc:
        raise _Invalid(f"{where}: {exc}") from exc
    if value.get("type") != kind:
        raise _Invalid(f"{where}: ref descriptor type mismatch")


def _check_provenance(value: dict[str, object], where: str) -> None:
    if not all(isinstance(value.get(key), str) and value.get(key) for key in ("task_id", "actor", "recorded_at")):
        raise _Invalid(f"{where}: invalid provenance")


def _scan(root: Path, sub: str, id_re: re.Pattern[str], side_suffix: str, limit: int) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    relative = f"{NAMESPACE}/{sub}"
    try:
        directory = core._safe_without_final_symlink(root, relative)
    except ValueError as exc:
        raise _Invalid(f"{relative}: {exc}") from exc
    if not directory.exists():
        return {}, {}
    if not directory.is_dir():
        raise _Invalid(f"{relative}: not a directory")
    names: list[str] = []
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries, start=1):
            if count > 2 * limit + 64:
                raise _Invalid(f"{relative}: exceeds {limit} records")
            names.append(entry.name)
    primary: dict[str, dict[str, object]] = {}
    side: dict[str, dict[str, object]] = {}
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        stem = name[:-5]
        is_side = stem.endswith(side_suffix)
        identifier = stem[:-len(side_suffix)] if is_side else stem
        if not id_re.fullmatch(identifier):
            continue
        value = _load_json(root, f"{relative}/{name}", RECORD_MAX_BYTES)
        if not isinstance(value, dict):
            raise _Invalid(f"{relative}/{name}: not a JSON object")
        (side if is_side else primary)[identifier] = value
    if len(primary) > limit:
        raise _Invalid(f"{relative}: exceeds {limit} records")
    orphan = sorted(set(side) - set(primary))
    if orphan:
        raise _Invalid(f"{relative}/{orphan[0]}{side_suffix}.json: refers to a missing record")
    return primary, side


def _load_side_records(root: Path, ctx: _Context) -> None:
    challenges, resolutions = _scan(root, "challenges", _CHALLENGE_ID_RE, ".resolution", MAX_CHALLENGES)
    for identifier, value in challenges.items():
        where = f"challenges/{identifier}.json"
        if set(value) != _CHALLENGE_FIELDS or value.get("id") != identifier:
            raise _Invalid(f"{where}: invalid challenge record")
        if not isinstance(value["targets"], list) or not value["targets"] or not isinstance(value["evidence_refs"], list):
            raise _Invalid(f"{where}: invalid challenge refs")
        for descriptor in [*value["targets"], *value["evidence_refs"]]:
            _check_descriptor(descriptor, where)
        if not isinstance(value["summary"], str) or not isinstance(value["text"], str):
            raise _Invalid(f"{where}: invalid challenge text")
        _check_provenance(value, where)
    for identifier, value in resolutions.items():
        where = f"challenges/{identifier}.resolution.json"
        if set(value) != _RESOLUTION_FIELDS or value.get("challenge") != identifier or value.get("resolution") not in {"amended", "dismissed"}:
            raise _Invalid(f"{where}: invalid resolution record")
        if value["resolution"] == "amended" and value.get("amendment") not in ctx.amendment_ids:
            raise _Invalid(f"{where}: resolving amendment is not in the ledger chain")
        _check_provenance(value, where)
    relations, retractions = _scan(root, "relations", _RELATION_ID_RE, ".retraction", MAX_RELATIONS)
    for identifier, value in relations.items():
        where = f"relations/{identifier}.json"
        if set(value) != _RELATION_FIELDS or value.get("id") != identifier or value.get("rel") not in RELATION_TYPES:
            raise _Invalid(f"{where}: invalid relation record")
        _check_descriptor(value["from"], where)
        _check_descriptor(value["to"], where)
        _check_provenance(value, where)
    for identifier, value in retractions.items():
        where = f"relations/{identifier}.retraction.json"
        if set(value) != _RETRACTION_FIELDS or value.get("relation") != identifier:
            raise _Invalid(f"{where}: invalid retraction record")
        _check_provenance(value, where)
    ctx.challenges, ctx.resolutions = challenges, resolutions
    ctx.relations, ctx.retractions = relations, retractions


def _load(root: Path) -> _Context:
    """Observe the namespace; identity content problems become INVALID, never exceptions."""
    ctx = _Context()
    namespace = root / NAMESPACE
    if namespace.is_symlink():
        ctx.state = "INVALID"
        ctx.detail = [f"{NAMESPACE} must not be a symlink"]
        return ctx
    if not namespace.exists():
        return ctx
    try:
        if not namespace.is_dir():
            raise _Invalid(f"{NAMESPACE} is not a directory")
        baseline = core._safe_without_final_symlink(root, BASELINE_PATH) if not (root / BASELINE_PATH).is_symlink() else None
        if baseline is None:
            raise _Invalid(f"{BASELINE_PATH} must not be a symlink")
        if baseline.exists():
            if not baseline.is_file():
                raise _Invalid(f"{BASELINE_PATH} is not a regular file")
            ctx.on_disk_sha256, ctx.on_disk_raw_sha256 = _file_hashes(baseline)
        if (root / LEDGER_PATH).exists() or (root / LEDGER_PATH).is_symlink():
            if (root / LEDGER_PATH).is_symlink():
                raise _Invalid(f"{LEDGER_PATH} must not be a symlink")
            _validate_ledger(root, ctx, _load_json(root, LEDGER_PATH, LEDGER_MAX_BYTES))
        _load_side_records(root, ctx)
    except (_Invalid, OSError, ValueError) as exc:
        ctx.state = "INVALID"
        ctx.detail = [str(exc)[:300]]
        return ctx
    if ctx.ledger is None:
        ctx.state = "ABSENT"
        if ctx.on_disk_sha256 is not None:
            ctx.detail = [f"{BASELINE_PATH} exists but no version is recorded; establish it with identity-amend (base_version 0, base_sha256 = its canonical sha256)"]
    elif ctx.on_disk_sha256 == ctx.recorded_sha256:
        ctx.state = "CURRENT"
    else:
        ctx.state = "UNRECORDED_CHANGE"
        if ctx.on_disk_sha256 is None:
            ctx.detail = [f"{BASELINE_PATH} is missing; reads serve recorded v{ctx.version:04d}"]
        else:
            ctx.detail = [f"{BASELINE_PATH} differs canonically from recorded v{ctx.version:04d}; reads serve the recorded version"]
    return ctx


def _require_readable(ctx: _Context) -> None:
    if ctx.state == "INVALID":
        raise ValueError(f"project identity is INVALID: {'; '.join(ctx.detail)}")


def _require_writable(ctx: _Context) -> None:
    if ctx.state == "INVALID":
        raise ValueError(f"project identity is INVALID; identity mutations refuse until it is repaired: {'; '.join(ctx.detail)}")


# ---------------------------------------------------------------------------
# Read operations


def _summary_line(ctx: _Context) -> str | None:
    if ctx.state == "ABSENT":
        return None
    if ctx.state == "INVALID":
        detail = ctx.detail[0] if ctx.detail else "integrity check failed"
        return f"Project identity INVALID ({detail[:200]}); identity mutations refuse until repaired. Inspect: identity-status."
    count = len(ctx.open_challenges())
    noun = "challenge" if count == 1 else "challenges"
    line = f"Project identity v{ctx.version} ({_amendment_id(ctx.version)}, {ctx.state}); {count} open {noun}."
    if ctx.state == "UNRECORDED_CHANGE":
        line += " IDENTITY.md differs from the recorded version."
    return line + " Read on demand: identity-get."


def identity_status(root: Path) -> dict[str, object]:
    """Bounded observation of the project identity namespace; never writes."""
    root = core._repo_root(root)
    ctx = _load(root)
    last = None
    if ctx.ledger is not None:
        entry = ctx.ledger["amendments"][-1]  # type: ignore[index]
        last = {"id": entry["id"], "summary": str(entry["summary"])[:SUMMARY_MAX], "recorded_at": entry["recorded_at"]}
    items = [{"id": item.id, "title": item.title[:80]} for item in ctx.items.values()]
    open_challenges = [
        {"id": value["id"], "targets": [str(target["ref"]) for target in value["targets"]][:4], "summary": str(value["summary"])[:200]}  # type: ignore[index, union-attr]
        for value in ctx.open_challenges()
    ]
    truncated = len(items) > STATUS_MAX_ITEMS or len(open_challenges) > STATUS_MAX_OPEN_CHALLENGES
    out: dict[str, object] = {
        "ok": True,
        "state": ctx.state,
        "version": ctx.version or None,
        "format": ctx.format,
        "baseline_path": BASELINE_PATH,
        "recorded_sha256": ctx.recorded_sha256,
        "on_disk_sha256": ctx.on_disk_sha256,
        "last_amendment": last,
        "items": items[:STATUS_MAX_ITEMS],
        "items_total": len(items),
        "open_challenges": open_challenges[:STATUS_MAX_OPEN_CHALLENGES],
        "open_challenges_total": len(open_challenges),
        "challenges_total": len(ctx.challenges),
        "relations_total": len(ctx.relations),
        "relations_active": len(ctx.relations) - len(ctx.retractions),
        "summary": _summary_line(ctx),
        "truncated": truncated,
    }
    if ctx.detail:
        out["detail"] = [entry[:300] for entry in ctx.detail[:DETAIL_MAX_ENTRIES]]
    while _response_size(out) > STATUS_MAX_BYTES and (out["items"] or out["open_challenges"]):
        listed_items, listed_challenges = out["items"], out["open_challenges"]
        assert isinstance(listed_items, list) and isinstance(listed_challenges, list)
        (listed_items if _response_size(listed_items) >= _response_size(listed_challenges) else listed_challenges).pop()
        out["truncated"] = True
    return out


def identity_summary(root: Path) -> str | None:
    """One plain line for adapter navigation; None when no identity is recorded."""
    summary = identity_status(root)["summary"]
    return summary if isinstance(summary, str) else None


def _version_response(ctx: _Context, version: int, text: str, sha256: str) -> dict[str, object]:
    divergent = ctx.state == "UNRECORDED_CHANGE"
    response: dict[str, object] = {
        "ok": True,
        "kind": "version",
        "state": ctx.state,
        "version": version,
        "current_version": ctx.version,
        "amendment": _amendment_id(version),
        "sha256": sha256,
        "on_disk_sha256": ctx.on_disk_sha256,
        "on_disk_divergent": divergent,
        "text": text,
    }
    if divergent:
        response["notice"] = "IDENTITY.md differs from the recorded current version; this response serves the recorded version."
    return response


def _check_response(response: dict[str, object], hint: str) -> dict[str, object]:
    if _response_size(response) > RESPONSE_MAX_BYTES:
        raise ValueError(f"identity response exceeds {RESPONSE_MAX_BYTES} bytes; {hint}")
    return response


def _parse_amendment_record(data: bytes, where: str) -> dict[str, object]:
    text = canonical_bytes(data).decode("utf-8")
    start = text.rfind(_AMENDMENT_RECORD_MARKER)
    match = re.fullmatch(r"(\{.*\})\n```\n?", text[start + len(_AMENDMENT_RECORD_MARKER):], re.DOTALL) if start >= 0 else None
    if match is None:
        raise ValueError(f"{where}: amendment record block missing")
    try:
        record = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{where}: invalid amendment record block") from exc
    if not isinstance(record, dict):
        raise ValueError(f"{where}: invalid amendment record block")
    return record


def _challenge_response(ctx: _Context, identifier: str) -> dict[str, object]:
    resolution = ctx.resolutions.get(identifier)
    return {
        "ok": True,
        "kind": "challenge",
        "challenge": ctx.challenges[identifier],
        "status": "open" if resolution is None else str(resolution["resolution"]),
        "resolution": resolution,
    }


def identity_get(root: Path, *, version: int | None = None, items: list[str] | None = None,
                 amendment: str | None = None, challenge: str | None = None) -> dict[str, object]:
    """Bounded explicit retrieval: recorded version (default), historical version, items, one amendment or challenge."""
    root = core._repo_root(root)
    if (amendment is not None) + (challenge is not None) + (version is not None or bool(items)) > 1:
        raise ValueError("identity-get selects a version/items, one amendment or one challenge")
    ctx = _load(root)
    _require_readable(ctx)
    if amendment is not None:
        match = _AMENDMENT_ID_RE.fullmatch(amendment) if isinstance(amendment, str) else None
        if match is None:
            raise ValueError("invalid amendment id")
        if amendment not in ctx.amendment_ids:
            raise ValueError(f"amendment {amendment} not found")
        number = int(match.group(1))
        data = _read_bounded(root, _amendment_path(number), RECORD_MAX_BYTES)
        assert data is not None
        record = _parse_amendment_record(data, _amendment_path(number))
        return _check_response({"ok": True, "kind": "amendment", "amendment": amendment,
                                "path": _amendment_path(number), "record": record}, "inspect the amendment file directly")
    if challenge is not None:
        if not isinstance(challenge, str) or not _CHALLENGE_ID_RE.fullmatch(challenge):
            raise ValueError("invalid challenge id")
        if challenge not in ctx.challenges:
            raise ValueError(f"challenge {challenge} not found")
        return _check_response(_challenge_response(ctx, challenge), "inspect the challenge file directly")
    if ctx.version == 0:
        raise ValueError("project identity is ABSENT; no version is recorded")
    selected = ctx.version if version is None else version
    if type(selected) is not int or not 1 <= selected <= ctx.version:
        raise ValueError(f"identity version must be between 1 and {ctx.version}")
    if selected == ctx.version:
        text = ctx.text
    else:
        data = _read_bounded(root, _version_path(selected), IDENTITY_MAX_BYTES)
        assert data is not None
        text = canonical_bytes(data).decode("utf-8")
    assert text is not None
    entry = ctx.ledger["versions"][selected - 1]  # type: ignore[index]
    if items:
        requested = _string_list(items, "item ids", 64)
        if any(not _ITEM_ID_RE.fullmatch(item) for item in requested):
            raise ValueError("invalid identity item id")
        parsed = ctx.items if selected == ctx.version else parse_items(text)
        missing = [item for item in requested if item not in parsed]
        if missing:
            raise ValueError(f"identity items not found in v{selected}: {', '.join(missing)}")
        response = {
            "ok": True,
            "kind": "items",
            "state": ctx.state,
            "version": selected,
            "current_version": ctx.version,
            "on_disk_divergent": ctx.state == "UNRECORDED_CHANGE",
            "items": [{"id": item.id, "title": item.title, "level": item.level, "sha256": item.sha256, "text": item.text}
                      for item in (parsed[name] for name in requested)],
        }
        return _check_response(response, "request fewer items")
    return _check_response(_version_response(ctx, selected, text, str(entry["sha256"])), "request selected items with --item")


def identity_trace(root: Path, ref: str, direction: str = "both", depth: int = 1) -> dict[str, object]:
    """Bounded traversal of active registered relations with endpoint states now."""
    root = core._repo_root(root)
    parse_ref(ref)
    if direction not in {"up", "down", "both"}:
        raise ValueError("direction must be up, down or both")
    if type(depth) is not int or not 1 <= depth <= TRACE_MAX_DEPTH:
        raise ValueError(f"depth must be between 1 and {TRACE_MAX_DEPTH}")
    ctx = _load(root)
    _require_readable(ctx)
    active = ctx.active_relations()
    cache: dict[str, str | None] = {}
    edges: list[dict[str, object]] = []
    seen_edges: set[str] = set()
    seen_nodes = {ref}
    frontier = [ref]
    truncated = False
    for level in range(1, depth + 1):
        following: list[str] = []
        for node in frontier:
            for relation in active:
                source, target = relation["from"], relation["to"]
                assert isinstance(source, dict) and isinstance(target, dict)
                if direction in {"up", "both"} and source["ref"] == node:
                    neighbor = str(target["ref"])
                elif direction in {"down", "both"} and target["ref"] == node:
                    neighbor = str(source["ref"])
                else:
                    continue
                if relation["id"] in seen_edges:
                    continue
                if len(edges) >= TRACE_MAX_EDGES:
                    truncated = True
                    break
                seen_edges.add(str(relation["id"]))
                edges.append({
                    "id": relation["id"],
                    "from": source["ref"],
                    "from_state": _endpoint_state(root, ctx.version, ctx.items, source, cache),
                    "rel": relation["rel"],
                    "to": target["ref"],
                    "to_state": _endpoint_state(root, ctx.version, ctx.items, target, cache),
                    "note": relation["note"],
                    "recorded_at": relation["recorded_at"],
                    "depth": level,
                })
                if neighbor not in seen_nodes:
                    seen_nodes.add(neighbor)
                    following.append(neighbor)
            if truncated:
                break
        if truncated:
            break
        frontier = following
    response: dict[str, object] = {
        "ok": True,
        "ref": ref,
        "direction": direction,
        "depth": depth,
        "state": ctx.state,
        "version": ctx.version or None,
        "edges": edges,
        "truncated": truncated,
        "notice": NOTICE,
    }
    while _response_size(response) > RESPONSE_MAX_BYTES and edges:
        edges.pop()
        response["truncated"] = True
    return response


# ---------------------------------------------------------------------------
# Mutations


def _begin(root: Path, actor: str, base_revision: int) -> tuple[Path, str]:
    root = core._repo_root(root)
    actor = core._bounded_label(actor, "identity actor", 128)
    if type(base_revision) is not int:
        raise ValueError("invalid base revision")
    if core.selected_task(root) is None:
        raise ValueError("explicit task selection required for identity mutation")
    return root, actor


def _task_for_mutation(root: Path, base_revision: int) -> dict[str, object]:
    state = core._load_state(root, active=True)
    if state["revision"] != base_revision:
        raise ValueError("task revision conflict")
    return state


def _provenance(state: dict[str, object], actor: str) -> dict[str, object]:
    return {"task_id": state["task_id"], "actor": actor, "recorded_at": _now().isoformat()}


def _render_amendment(record: dict[str, object]) -> bytes:
    decision = record["decision"]
    assert isinstance(decision, dict)
    quoted = "\n".join(f"> {line}" if line else ">" for line in str(decision["human_instruction"]).split("\n"))
    items = record["items"]
    assert isinstance(items, dict)

    def listing(values: object) -> str:
        entries = [str(value.get("ref")) if isinstance(value, dict) else str(value) for value in values or []]  # type: ignore[union-attr]
        return "\n".join(f"- `{entry}`" for entry in entries) if entries else "- none"

    sections = [
        f"# {record['id']}: {record['summary']}",
        "",
        f"- From version: {'none (establishment)' if record['from_version'] == 0 else 'v%04d' % record['from_version']}",
        f"- To version: v{record['to_version']:04d} (`{record['snapshot']}`, canonical sha256 `{record['sha256']}`)",
        f"- Recorded at: {record['recorded_at']}",
        f"- Task: {record['task_id']}",
        f"- Actor: {record['actor']}",
        f"- Decided by: {decision['decided_by']}",
        "",
        "## Human decision",
        "",
        quoted,
        "",
        "## Rationale",
        "",
        str(record["rationale"]),
    ]
    if record.get("challenge_text"):
        sections += ["", "## Challenge", "", str(record["challenge_text"])]
    if record.get("why_not_lower"):
        sections += ["", "## Why lower-level repair is insufficient", "", str(record["why_not_lower"])]
    sections += [
        "",
        "## Item changes",
        "",
        f"- Added: {', '.join(items['added']) or 'none'}",
        f"- Removed: {', '.join(items['removed']) or 'none'}",
        f"- Changed: {', '.join(items['changed']) or 'none'}",
        "",
        "## Declared affected refs",
        "",
        listing(record["affected_refs"]),
        "",
        "## Evidence refs",
        "",
        listing(record["evidence_refs"]),
        "",
        "## Resolved challenges",
        "",
        listing(record["resolves"]),
        "",
        "The replacement text is the immutable snapshot named above.",
    ]
    body = "\n".join(sections) + "\n" + _AMENDMENT_RECORD_MARKER
    body += json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    return body.encode("utf-8")


def _dependents(root: Path, ctx: _Context, diff: dict[str, list[str]], version: int, items: dict[str, Item]) -> list[dict[str, object]]:
    targets = {"identity"} | {f"identity:{item}" for item in [*diff["removed"], *diff["changed"]]}
    cache: dict[str, str | None] = {}
    result = []
    for relation in ctx.active_relations():
        target = relation["to"]
        assert isinstance(target, dict)
        if target["ref"] in targets:
            source = relation["from"]
            assert isinstance(source, dict)
            result.append({
                "id": relation["id"], "from": source["ref"], "rel": relation["rel"], "to": target["ref"],
                "to_state": _endpoint_state(root, version, items, target, cache), "note": relation["note"],
            })
    return result


def identity_amend(root: Path, actor: str, base_revision: int, input_file: str | dict[str, object] | None) -> dict[str, object]:
    """Record an explicit amendment moving the baseline from version N to N+1 (0 -> 1 establishes it)."""
    root, actor = _begin(root, actor, base_revision)
    payload = _read_identity_input(input_file)
    required = {"base_version", "base_sha256", "text", "summary", "rationale", "decision"}
    optional = {"challenge_text", "why_not_lower", "evidence_refs", "resolves", "affected_refs"}
    if required - set(payload) or set(payload) - required - optional:
        raise ValueError("invalid identity-amend input fields")
    base_version = payload["base_version"]
    if type(base_version) is not int or base_version < 0:
        raise ValueError("invalid base_version")
    base_sha256 = payload["base_sha256"]
    if base_sha256 is not None and (not isinstance(base_sha256, str) or not _HEX64_RE.fullmatch(base_sha256)):
        raise ValueError("invalid base_sha256")
    text = _identity_text(payload["text"])
    summary = _text(payload["summary"], "summary", SUMMARY_MAX, line=True)
    rationale = _text(payload["rationale"], "rationale")
    decision = payload["decision"]
    if not isinstance(decision, dict) or set(decision) != {"decided_by", "human_instruction"}:
        raise ValueError("decision requires decided_by and human_instruction")
    decision = {"decided_by": _text(decision["decided_by"], "decision.decided_by", 200, line=True),
                "human_instruction": _text(decision["human_instruction"], "decision.human_instruction")}
    challenge_text = _optional_text(payload.get("challenge_text"), "challenge_text")
    why_not_lower = _optional_text(payload.get("why_not_lower"), "why_not_lower")
    evidence_refs = _string_list(payload.get("evidence_refs"), "evidence_refs", 64)
    affected_refs = _string_list(payload.get("affected_refs"), "affected_refs", 64)
    resolves = _string_list(payload.get("resolves"), "resolves", 64)
    if any(not _CHALLENGE_ID_RE.fullmatch(item) for item in resolves):
        raise ValueError("invalid challenge id in resolves")
    new_items = parse_items(text)
    encoded = text.encode("utf-8")
    new_sha256 = hashlib.sha256(encoded).hexdigest()
    with core._lock(root):
        state = _task_for_mutation(root, base_revision)
        ctx = _load(root)
        _require_writable(ctx)
        if base_version != ctx.version:
            raise ValueError(f"identity version conflict: base_version {base_version}, recorded version {ctx.version}")
        if base_sha256 != ctx.on_disk_sha256:
            raise ValueError("IDENTITY.md base_sha256 conflict: the on-disk baseline differs from base_sha256")
        if ctx.version >= MAX_VERSIONS:
            raise ValueError(f"identity exceeds {MAX_VERSIONS} versions")
        if ctx.recorded_sha256 == new_sha256:
            raise ValueError("amendment text is identical to the recorded current version")
        for identifier in resolves:
            if identifier not in ctx.challenges:
                raise ValueError(f"challenge {identifier} not found")
            if identifier in ctx.resolutions:
                raise ValueError(f"challenge {identifier} is not open")
        new_version = ctx.version + 1
        evidence = [_resolve_ref(root, ctx, ref, ctx.scope()) for ref in evidence_refs]
        affected = [_resolve_ref(root, ctx, ref, ctx.scope() + [(new_version, new_items)]) for ref in affected_refs]
        diff = _item_diff(ctx.items, new_items)
        provenance = _provenance(state, actor)
        amendment_id = _amendment_id(new_version)
        record: dict[str, object] = {
            "id": amendment_id,
            "from_version": ctx.version,
            "to_version": new_version,
            "previous_sha256": ctx.recorded_sha256,
            "base_on_disk_sha256": base_sha256,
            "snapshot": _version_path(new_version),
            "sha256": new_sha256,
            "summary": summary,
            "rationale": rationale,
            "challenge_text": challenge_text,
            "why_not_lower": why_not_lower,
            "decision": decision,
            "evidence_refs": evidence,
            "affected_refs": affected,
            "resolves": resolves,
            "items": diff,
            **provenance,
        }
        rendered = _render_amendment(record)
        if len(rendered) > RECORD_MAX_BYTES:
            raise ValueError("amendment record exceeds its storage bound")
        _check_response({"ok": True, "kind": "amendment", "amendment": amendment_id, "path": _amendment_path(new_version), "record": record},
                        "shorten the amendment record")
        preview = _Context(state="CURRENT", version=new_version, on_disk_sha256=new_sha256)
        _check_response(_version_response(preview, new_version, text, new_sha256), "shorten the identity text")
        ledger = json.loads(json.dumps(ctx.ledger)) if ctx.ledger is not None else {
            "format": LEDGER_FORMAT, "version": 0, "versions": [], "amendments": []}
        ledger["version"] = new_version
        ledger["versions"].append({
            "version": new_version, "path": _version_path(new_version)[len(NAMESPACE) + 1:], "sha256": new_sha256,
            "raw_sha256": new_sha256, "amendment": amendment_id, "recorded_at": provenance["recorded_at"],
        })
        ledger["amendments"].append({
            "id": amendment_id, "path": _amendment_path(new_version)[len(NAMESPACE) + 1:], "from_version": ctx.version,
            "to_version": new_version, "sha256": canonical_sha256(rendered), "summary": summary,
            "recorded_at": provenance["recorded_at"],
        })
        writes: dict[str, bytes] = {
            _version_path(new_version): encoded,
            BASELINE_PATH: encoded,
            _amendment_path(new_version): rendered,
        }
        for identifier in resolves:
            writes[f"{NAMESPACE}/challenges/{identifier}.resolution.json"] = _json_bytes({
                "challenge": identifier, "resolution": "amended", "amendment": amendment_id, "reason": summary, **provenance})
        writes[LEDGER_PATH] = _json_bytes(ledger)  # commit point: written last
        dependents = _dependents(root, ctx, diff, new_version, new_items)
        backup = core._apply_with_backup(root, writes, [], "identity-amend")
    return {
        "ok": True,
        "task_id": state["task_id"],
        "state_revision": state["revision"],
        "version": new_version,
        "amendment": amendment_id,
        "sha256": new_sha256,
        "items": diff,
        "registered_dependents": dependents[:DEPENDENTS_MAX],
        "registered_dependents_total": len(dependents),
        "registered_dependents_truncated": len(dependents) > DEPENDENTS_MAX,
        "challenges_resolved": resolves,
        "notice": NOTICE + " Nothing is revalidated or propagated automatically.",
        "written": list(writes),
        "backup": backup,
    }


def identity_challenge(root: Path, actor: str, base_revision: int, input_file: str | dict[str, object] | None) -> dict[str, object]:
    """Open a challenge against the recorded identity, or dismiss an open one."""
    root, actor = _begin(root, actor, base_revision)
    payload = _read_identity_input(input_file)
    if "dismiss" in payload:
        if set(payload) != {"dismiss", "reason"}:
            raise ValueError("dismiss requires exactly dismiss and reason")
        identifier = payload["dismiss"]
        if not isinstance(identifier, str) or not _CHALLENGE_ID_RE.fullmatch(identifier):
            raise ValueError("invalid challenge id")
        reason = _text(payload["reason"], "dismiss reason", 4096)
        with core._lock(root):
            state = _task_for_mutation(root, base_revision)
            ctx = _load(root)
            _require_writable(ctx)
            if identifier not in ctx.challenges:
                raise ValueError(f"challenge {identifier} not found")
            if identifier in ctx.resolutions:
                raise ValueError(f"challenge {identifier} is not open")
            resolution = {"challenge": identifier, "resolution": "dismissed", "amendment": None, "reason": reason,
                          **_provenance(state, actor)}
            backup = core._apply_with_backup(root, {f"{NAMESPACE}/challenges/{identifier}.resolution.json": _json_bytes(resolution)}, [],
                                             "identity-challenge")
        return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "challenge": identifier,
                "status": "dismissed", "backup": backup}
    required = {"targets", "summary", "text"}
    if required - set(payload) or set(payload) - required - {"evidence_refs", "proposed_change"}:
        raise ValueError("invalid identity-challenge input fields")
    targets = _string_list(payload["targets"], "targets", 16)
    if not targets or not all(_is_identity_ref(target) for target in targets):
        raise ValueError("challenge targets must be identity or identity:<item> refs")
    summary = _text(payload["summary"], "summary", SUMMARY_MAX, line=True)
    text = _text(payload["text"], "challenge text")
    proposed = _optional_text(payload.get("proposed_change"), "proposed_change")
    evidence_refs = _string_list(payload.get("evidence_refs"), "evidence_refs", 64)
    with core._lock(root):
        state = _task_for_mutation(root, base_revision)
        ctx = _load(root)
        _require_writable(ctx)
        if ctx.version == 0:
            raise ValueError("no recorded project identity to challenge")
        if len(ctx.challenges) >= MAX_CHALLENGES:
            raise ValueError(f"project identity already has {MAX_CHALLENGES} challenges")
        resolved_targets = [_resolve_ref(root, ctx, target, ctx.scope()) for target in targets]
        evidence = [_resolve_ref(root, ctx, ref, ctx.scope()) for ref in evidence_refs]
        identifier = _new_id("CH", set(ctx.challenges))
        record = {"id": identifier, "targets": resolved_targets, "summary": summary, "text": text,
                  "evidence_refs": evidence, "proposed_change": proposed, "identity_version": ctx.version,
                  **_provenance(state, actor)}
        _check_response({"ok": True, "kind": "challenge", "challenge": record, "status": "open", "resolution": None},
                        "shorten the challenge")
        backup = core._apply_with_backup(root, {f"{NAMESPACE}/challenges/{identifier}.json": _json_bytes(record)}, [],
                                         "identity-challenge")
    return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "challenge": identifier,
            "status": "open", "backup": backup}


def identity_relate(root: Path, actor: str, base_revision: int, input_file: str | dict[str, object] | None) -> dict[str, object]:
    """Register and/or retract typed purpose relations; never edits or deletes one."""
    root, actor = _begin(root, actor, base_revision)
    payload = _read_identity_input(input_file)
    if set(payload) - {"add", "retract"}:
        raise ValueError("invalid identity-relate input fields")
    additions = payload.get("add", [])
    retractions = payload.get("retract", [])
    if not isinstance(additions, list) or not isinstance(retractions, list) or len(additions) > 64 or len(retractions) > 64 or not (additions or retractions):
        raise ValueError("identity-relate requires add and/or retract lists of at most 64 entries")
    planned: list[tuple[str, str, str, str | None]] = []
    for value in additions:
        if not isinstance(value, dict) or {"from", "rel", "to"} - set(value) or set(value) - {"from", "rel", "to", "note"}:
            raise ValueError("relation requires from, rel, to and optional note")
        source, rel, target = value["from"], value["rel"], value["to"]
        parse_ref(source)
        parse_ref(target)
        if rel not in RELATION_TYPES:
            raise ValueError(f"rel must be one of {', '.join(RELATION_TYPES)}")
        if source == target:
            raise ValueError("self relations are not allowed")
        if rel == "challenges" and _is_identity_ref(target):
            raise ValueError("a challenges relation may not target identity; record evidence against identity with identity-challenge")
        note = _optional_text(value.get("note"), "relation note", 1024)
        planned.append((source, rel, target, note))
    retracting: list[tuple[str, str]] = []
    for value in retractions:
        if not isinstance(value, dict) or set(value) != {"id", "reason"}:
            raise ValueError("retraction requires id and reason")
        identifier = value["id"]
        if not isinstance(identifier, str) or not _RELATION_ID_RE.fullmatch(identifier):
            raise ValueError("invalid relation id")
        retracting.append((identifier, _text(value["reason"], "retraction reason", 4096)))
    if len({identifier for identifier, _ in retracting}) != len(retracting):
        raise ValueError("relation retracted twice in one request")
    with core._lock(root):
        state = _task_for_mutation(root, base_revision)
        ctx = _load(root)
        _require_writable(ctx)
        for identifier, _ in retracting:
            if identifier not in ctx.relations:
                raise ValueError(f"relation {identifier} not found")
            if identifier in ctx.retractions:
                raise ValueError(f"relation {identifier} is already retracted")
        if len(ctx.relations) + len(planned) > MAX_RELATIONS:
            raise ValueError(f"project identity relations exceed {MAX_RELATIONS}")
        retracted_ids = {identifier for identifier, _ in retracting}
        active = {(relation["from"]["ref"], relation["rel"], relation["to"]["ref"])  # type: ignore[index]
                  for relation in ctx.active_relations() if relation["id"] not in retracted_ids}
        provenance = _provenance(state, actor)
        writes: dict[str, bytes] = {}
        added: list[str] = []
        existing = set(ctx.relations)
        for source, rel, target, note in planned:
            key = (source, rel, target)
            if key in active:
                raise ValueError(f"duplicate active relation {source} {rel} {target}")
            active.add(key)
            identifier = _new_id("REL", existing)
            existing.add(identifier)
            record = {"id": identifier, "from": _resolve_ref(root, ctx, source, ctx.scope()), "rel": rel,
                      "to": _resolve_ref(root, ctx, target, ctx.scope()), "note": note, **provenance}
            writes[f"{NAMESPACE}/relations/{identifier}.json"] = _json_bytes(record)
            added.append(identifier)
        for identifier, reason in retracting:
            writes[f"{NAMESPACE}/relations/{identifier}.retraction.json"] = _json_bytes(
                {"relation": identifier, "reason": reason, **provenance})
        backup = core._apply_with_backup(root, writes, [], "identity-relate")
    return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "added": added,
            "retracted": [identifier for identifier, _ in retracting], "notice": NOTICE, "backup": backup}
