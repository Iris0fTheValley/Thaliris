"""Natural Project Identity formation: basis notes, suggestion preferences, one-time offer.

Everything here lives outside the repository, under ``THALIRIS_HOME`` (default
``~/.thaliris``), and is local to this machine.  Nothing here writes
``.project-identity/`` or changes the identity chain, amendment, challenge or
relation formats: formal identity still changes only through ``identity-amend``.

Core stores, counts, gates and resolves mechanically.  Whether a statement is an
explicit long-term statement by the user, and how a draft is composed from the
notes, are the caller's semantic judgments.

Layout (directories are created lazily, on the first write that needs them)::

    $THALIRIS_HOME/
      preferences.json                                   global suggestion preference
      sessions/<sha256(session key)>.json                session preference (pruned after 30 days)
      workspaces/<workspace key>/preferences.json        this checkout on this machine
      projects/<project key>/project.json                diagnostics: the root path it was created from
      projects/<project key>/preferences.json            project preference (all worktrees)
      projects/<project key>/offer-state.json            highest note id an offer was shown for
      projects/<project key>/identity-basis/N-0001.json  immutable basis note
      projects/<project key>/identity-basis/N-0001.retraction.json

The project key is the sha256 of the resolved Git common directory, so all
worktrees of one repository share notes; outside Git (or when Git is unavailable)
it is the sha256 of the resolved project root.  The workspace key is the sha256
of the resolved project root.  Damaged files are reported, never raised into the
offer, and never make the project identity INVALID.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from . import core, identity
from . import errors as _errors
from .errors import ThalirisError

HOME_ENV = "THALIRIS_HOME"
NOTE_FORMAT = "thaliris-identity-basis-note-v1"
RETRACTION_FORMAT = "thaliris-identity-basis-retraction-v1"
PREFERENCE_FORMAT = "thaliris-identity-suggestions-v1"
OFFER_STATE_FORMAT = "thaliris-identity-offer-state-v1"
PROJECT_FORMAT = "thaliris-identity-project-v1"

NOTE_KINDS = ("purpose", "direction", "constraint", "non-goal", "decision", "rejection", "material", "other")
SCOPES = ("session", "workspace", "project", "global")
SETTINGS = ("on", "off", "clear")

QUOTE_MAX_BYTES = 8 * 1024
CONTEXT_MAX = 300
REFS_MAX = 16
REF_MAX_CHARS = 1024
REASON_MAX = 4096
SESSION_KEY_MAX = 512
MAX_NOTES = 4096
MAX_NOTE_NUMBER = 9999
FILE_MAX_BYTES = 64 * 1024
LIST_MAX_BYTES = 64 * 1024
DAMAGED_LISTED_MAX = 8
SESSION_RETENTION_SECONDS = 30 * 24 * 60 * 60
SESSION_SCAN_MAX = 4096

_NOTE_ID_RE = re.compile(r"N-([0-9]{4})")
_NOTE_FILE_RE = re.compile(r"(N-[0-9]{4})(\.retraction)?\.json")
_SESSION_FILE_RE = re.compile(r"[0-9a-f]{64}\.json")
_NOTE_INPUT_FIELDS = frozenset({"quote", "kind", "context", "refs"})
_NOTE_FIELDS = frozenset({"format", "id", "quote", "kind", "context", "refs", "recorded_at", "actor", "task_id", "identity_version"})
_RETRACTION_FIELDS = frozenset({"format", "note", "reason", "recorded_at", "actor", "task_id"})
_PREFERENCE_FIELDS = frozenset({"format", "suggestions", "actor", "updated_at", "root"})
_OFFER_STATE_FIELDS = frozenset({"format", "last_shown", "shown_at", "identity_state", "identity_version"})

LIST_NOTICE = ("quote holds the user's words as recorded; context, when present, is the recorder's own "
               "framing, not the user's words. Notes are local to this machine and are not identity: "
               "formal identity changes only through identity-amend.")


# ---------------------------------------------------------------------------
# Storage location


def thaliris_home() -> Path:
    """``THALIRIS_HOME`` when set and non-empty, else ``~/.thaliris``; never created here."""
    value = os.environ.get(HOME_ENV)
    base = Path(value).expanduser() if value else Path.home() / ".thaliris"
    return base.resolve()


def _path_key(path: Path) -> str:
    text = str(path)
    if os.name == "nt":
        text = text.casefold()
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()


def _git_common_dir(root: Path) -> Path | None:
    """Resolved ``git rev-parse --git-common-dir`` or None outside Git or without Git."""
    try:
        proc = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="surrogateescape", check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (proc.stdout or "").strip()
    if proc.returncode != 0 or not output:
        return None
    path = Path(output)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve()
    except OSError:
        return None


@dataclass(frozen=True)
class _Store:
    root: Path
    home: Path
    git_common_dir: Path | None
    project_key: str
    workspace_key: str

    @property
    def project_dir(self) -> Path:
        return self.home / "projects" / self.project_key

    @property
    def basis_dir(self) -> Path:
        return self.project_dir / "identity-basis"

    @property
    def workspace_dir(self) -> Path:
        return self.home / "workspaces" / self.workspace_key


def _store(root: Path) -> _Store:
    root = core._repo_root(root)
    common = _git_common_dir(root)
    return _Store(root, thaliris_home(), common, _path_key(common or root), _path_key(root))


def project_key(root: Path) -> str:
    """Key shared by every worktree of one repository (the project root outside Git)."""
    return _store(root).project_key


def workspace_key(root: Path) -> str:
    """Key of this checkout on this machine."""
    return _store(root).workspace_key


# ---------------------------------------------------------------------------
# Bounded tolerant file access


class _Damaged(Exception):
    pass


def _read_json(path: Path) -> dict[str, object] | None:
    """None when absent; _Damaged when unreadable, oversized, not JSON or not an object."""
    try:
        if path.is_symlink():
            raise _Damaged(f"{path.name}: symlink")
        if not path.exists():
            return None
        if not path.is_file():
            raise _Damaged(f"{path.name}: not a regular file")
        with path.open("rb") as stream:
            data = stream.read(FILE_MAX_BYTES + 1)
    except OSError as exc:
        raise _Damaged(f"{path.name}: unreadable") from exc
    if len(data) > FILE_MAX_BYTES:
        raise _Damaged(f"{path.name}: exceeds {FILE_MAX_BYTES} bytes")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _Damaged(f"{path.name}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise _Damaged(f"{path.name}: not a JSON object")
    return value


def _write_json(path: Path, value: dict[str, object]) -> None:
    core._atomic_write(path, identity._json_bytes(value))


def _write_json_new(path: Path, value: dict[str, object]) -> None:
    """Create ``path`` without ever replacing an existing file, so an id is never reused.

    Prefers a hard link from a fully written temp file (atomic); falls back to exclusive
    create where hard links are unsupported.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = identity._json_bytes(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.new")
    exists = _invalid(_errors.IDENTITY_NOTE_LIMIT, f"{path.name} already exists; refusing to overwrite")
    try:
        with open(temporary, "xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
            return
        except FileExistsError as exc:
            raise exists from exc
        except (AttributeError, NotImplementedError, OSError):
            pass
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        try:
            descriptor = os.open(path, flags, 0o666)
        except FileExistsError as exc:
            raise exists from exc
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
        except BaseException:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _now() -> str:
    return identity._now().isoformat()


def _invalid(code: str, message: str, **details: object) -> ThalirisError:
    return ThalirisError(code, message, details=details or None)


def _session_key(value: object) -> str:
    if (not isinstance(value, str) or not value or len(value) > SESSION_KEY_MAX or value != value.strip()
            or identity._has_control(value, allow_newlines=False)):
        raise _invalid(_errors.IDENTITY_PREFERENCE_INVALID, "invalid session key",
                       expected=f"1-{SESSION_KEY_MAX} characters without surrounding whitespace or control characters")
    return value


def _ensure_project_file(store: _Store) -> None:
    path = store.project_dir / "project.json"
    try:
        if _read_json(path) is not None:
            return
    except _Damaged:
        pass
    _write_json(path, {"format": PROJECT_FORMAT, "root": str(store.root),
                       "git_common_dir": None if store.git_common_dir is None else str(store.git_common_dir),
                       "created_at": _now()})


# ---------------------------------------------------------------------------
# Basis notes


@dataclass
class _Basis:
    notes: dict[str, dict[str, object]] = field(default_factory=dict)
    retractions: dict[str, dict[str, object]] = field(default_factory=dict)
    damaged: list[str] = field(default_factory=list)
    highest: int = 0
    truncated: bool = False
    retraction_damaged: set[str] = field(default_factory=set)

    def pending(self, current_version: int) -> list[str]:
        return sorted(identifier for identifier, note in self.notes.items()
                      if identifier not in self.retractions and identifier not in self.retraction_damaged and note["identity_version"] >= current_version)  # type: ignore[operator]

    def counts(self, current_version: int) -> dict[str, int]:
        return {"pending": len(self.pending(current_version)), "total": len(self.notes),
                "retracted": len(self.retractions), "damaged": len(self.damaged)}


def _check_note(identifier: str, value: dict[str, object]) -> None:
    refs = value.get("refs")
    if (set(value) != _NOTE_FIELDS or value["format"] != NOTE_FORMAT or value["id"] != identifier
            or not isinstance(value["quote"], str) or not value["quote"] or value["kind"] not in NOTE_KINDS
            or not (value["context"] is None or isinstance(value["context"], str))
            or not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs)
            or type(value["identity_version"]) is not int or value["identity_version"] < 0  # type: ignore[operator]
            or not (value["task_id"] is None or isinstance(value["task_id"], str))
            or not isinstance(value["actor"], str) or not isinstance(value["recorded_at"], str)):
        raise _Damaged(f"{identifier}.json: invalid note record")


def _check_retraction(identifier: str, value: dict[str, object]) -> None:
    if (set(value) != _RETRACTION_FIELDS or value["format"] != RETRACTION_FORMAT or value["note"] != identifier
            or not isinstance(value["reason"], str) or not (value["task_id"] is None or isinstance(value["task_id"], str))
            or not isinstance(value["actor"], str) or not isinstance(value["recorded_at"], str)):
        raise _Damaged(f"{identifier}.retraction.json: invalid retraction record")


def _load_basis(store: _Store) -> _Basis:
    """Read every note; damaged files are counted and skipped, never raised."""
    basis = _Basis()
    directory = store.basis_dir
    try:
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            basis.damaged.append("identity-basis: not a directory")
            return basis
        if not directory.exists():
            return basis
        names: list[str] = []
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries, start=1):
                if count > 2 * MAX_NOTES + 64:
                    basis.truncated = True
                    basis.damaged.append(f"identity-basis: exceeds {2 * MAX_NOTES + 64} entries; the rest is unread")
                    break
                names.append(entry.name)
    except OSError:
        basis.damaged.append("identity-basis: unreadable")
        return basis
    for name in sorted(names):
        match = _NOTE_FILE_RE.fullmatch(name)
        if match is None:
            continue
        identifier, side = match.group(1), match.group(2) is not None
        basis.highest = max(basis.highest, int(identifier[2:]))
        try:
            value = _read_json(directory / name)
            if value is None:
                continue
            (_check_retraction if side else _check_note)(identifier, value)
        except _Damaged:
            basis.damaged.append(name)
            if side:
                basis.retraction_damaged.add(identifier)
            continue
        (basis.retractions if side else basis.notes)[identifier] = value
    for orphan in sorted(set(basis.retractions) - set(basis.notes)):
        if f"{orphan}.json" not in basis.damaged:
            basis.damaged.append(f"{orphan}.retraction.json")
        del basis.retractions[orphan]
    return basis


def _line(value: object, name: str, maximum: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum or value != value.strip()
            or identity._has_control(value, allow_newlines=False) or "\t" in value):
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, f"invalid {name}",
                       expected=f"one non-empty line of at most {maximum} characters")
    return value


def _long_text(value: object, name: str, maximum_bytes: int) -> str:
    if isinstance(value, str):
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    if not isinstance(value, str) or not value.strip() or identity._has_control(value, allow_newlines=True):
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, f"invalid {name}",
                       expected="non-empty text without control characters other than newline and tab")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, f"invalid {name}", expected="valid Unicode text") from exc
    if size > maximum_bytes:
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, f"{name} exceeds {maximum_bytes} bytes", bytes=size)
    return value


def _note_fields(payload: dict[str, object]) -> dict[str, object]:
    if "quote" not in payload or set(payload) - _NOTE_INPUT_FIELDS:
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, "invalid identity-note input fields",
                       allowed=sorted(_NOTE_INPUT_FIELDS), unknown=sorted(set(payload) - _NOTE_INPUT_FIELDS)[:8])
    quote = _long_text(payload["quote"], "quote", QUOTE_MAX_BYTES)
    kind = payload.get("kind", "other")
    if kind not in NOTE_KINDS:
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, "invalid kind", allowed=list(NOTE_KINDS))
    context = payload.get("context")
    if context is not None:
        context = _line(context, "context", CONTEXT_MAX)
    refs = payload.get("refs")
    refs = [] if refs is None else refs
    if not isinstance(refs, list) or len(refs) > REFS_MAX:
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, "invalid refs", expected=f"a list of at most {REFS_MAX} strings")
    refs = [_line(ref, "ref", REF_MAX_CHARS) for ref in refs]
    if len(set(refs)) != len(refs):
        raise _invalid(_errors.IDENTITY_NOTE_INVALID, "duplicate ref")
    return {"quote": quote, "kind": kind, "context": context, "refs": refs}


def _selected_active_task(root: Path) -> str | None:
    """The explicitly selected task when it is ACTIVE; notes never require one."""
    if core.selected_task(root) is None:
        return None
    try:
        state = core._load_state(root, active=True)
    except (ValueError, OSError):
        return None
    return str(state["task_id"])


def identity_note(root: Path, actor: str, input_file: str | dict[str, object] | None) -> dict[str, object]:
    """Record one basis note ``{quote, kind?, context?, refs?}`` or retract one ``{retract, reason}``.

    No ACTIVE task is required; the selected ACTIVE task id, if any, is recorded.
    Writes only under ``THALIRIS_HOME``.
    """
    root = core._repo_root(root)
    actor = core._bounded_label(actor, "identity actor", 128)
    payload = identity._read_identity_input(input_file)
    retracting = "retract" in payload
    if retracting:
        if set(payload) != {"retract", "reason"}:
            raise _invalid(_errors.IDENTITY_NOTE_INVALID, "retract requires exactly retract and reason")
        identifier = payload["retract"]
        if not isinstance(identifier, str) or not _NOTE_ID_RE.fullmatch(identifier):
            raise _invalid(_errors.IDENTITY_NOTE_INVALID, "invalid note id", expected="N-0001")
        reason = _long_text(payload["reason"], "reason", REASON_MAX)
    else:
        fields = _note_fields(payload)
    task_id = _selected_active_task(root)
    current_version = identity._load(root).version
    store = _store(root)
    with core._file_lock(store.project_dir / ".lock"):
        basis = _load_basis(store)
        if retracting:
            if identifier not in basis.notes:
                raise _invalid(_errors.IDENTITY_NOTE_NOT_FOUND, f"note {identifier} not found")
            if identifier in basis.retractions:
                raise _invalid(_errors.IDENTITY_NOTE_ALREADY_RETRACTED, f"note {identifier} is already retracted")
            record: dict[str, object] = {"format": RETRACTION_FORMAT, "note": identifier, "reason": reason,
                                         "recorded_at": _now(), "actor": actor, "task_id": task_id}
            _ensure_project_file(store)
            _write_json_new(store.basis_dir / f"{identifier}.retraction.json", record)
            basis.retractions[identifier] = record
            return {"ok": True, "retracted": identifier, "retraction": record, "task_id": task_id,
                    "basis": basis.counts(current_version)}
        if basis.truncated:
            raise _invalid(_errors.IDENTITY_NOTE_LIMIT, "identity basis directory exceeds the scan limit; refusing to allocate a note id")
        if len(basis.notes) >= MAX_NOTES or basis.highest >= MAX_NOTE_NUMBER:
            raise _invalid(_errors.IDENTITY_NOTE_LIMIT, f"identity basis holds at most {MAX_NOTES} notes (ids up to N-{MAX_NOTE_NUMBER})")
        identifier = f"N-{basis.highest + 1:04d}"
        record = {"format": NOTE_FORMAT, "id": identifier, **fields, "recorded_at": _now(), "actor": actor,
                  "task_id": task_id, "identity_version": current_version}
        _ensure_project_file(store)
        _write_json_new(store.basis_dir / f"{identifier}.json", record)
        basis.notes[identifier] = record
        basis.highest += 1
    return {"ok": True, "note": record, "pending": True, "task_id": task_id, "basis": basis.counts(current_version)}


def identity_note_list(root: Path, *, include_retracted: bool = False) -> dict[str, object]:
    """Notes oldest first (non-retracted by default), each with ``pending`` and ``retracted``; never writes."""
    root = core._repo_root(root)
    ctx = identity._load(root)
    basis = _load_basis(_store(root))
    pending = set(basis.pending(ctx.version))
    notes: list[dict[str, object]] = []
    for identifier in sorted(basis.notes):
        retraction = basis.retractions.get(identifier)
        if retraction is not None and not include_retracted:
            continue
        entry = {**basis.notes[identifier], "pending": identifier in pending, "retracted": retraction is not None}
        if identifier in basis.retraction_damaged:
            entry["retraction_damaged"] = True
        if retraction is not None:
            entry["retraction"] = {key: retraction[key] for key in ("reason", "recorded_at", "actor", "task_id")}
        notes.append(entry)
    out: dict[str, object] = {
        "ok": True,
        "identity_state": ctx.state,
        "identity_version": ctx.version or None,
        "notes": notes,
        "omitted": 0,
        "truncated": False,
        "basis": basis.counts(ctx.version),
        "notice": LIST_NOTICE,
    }
    if basis.damaged:
        out["damaged_files"] = basis.damaged[:DAMAGED_LISTED_MAX]
    while notes and identity._response_size(out) > LIST_MAX_BYTES:
        notes.pop(0)  # oldest first: pending notes are the newest
        out["omitted"] = int(out["omitted"]) + 1  # type: ignore[call-overload]
        out["truncated"] = True
    return out


# ---------------------------------------------------------------------------
# Suggestion preferences


def _preference_path(store: _Store, scope: str, session_key: str | None) -> Path:
    if scope == "session":
        assert session_key is not None
        return store.home / "sessions" / f"{hashlib.sha256(session_key.encode('utf-8')).hexdigest()}.json"
    if scope == "workspace":
        return store.workspace_dir / "preferences.json"
    if scope == "project":
        return store.project_dir / "preferences.json"
    return store.home / "preferences.json"


def _read_preference(path: Path) -> bool | None:
    value = _read_json(path)
    if value is None:
        return None
    if (value.get("format") != PREFERENCE_FORMAT or set(value) - _PREFERENCE_FIELDS
            or value.get("suggestions") not in ("on", "off")):
        raise _Damaged(f"{path.name}: invalid preference record")
    return value["suggestions"] == "on"


def _resolve(store: _Store, session_key: str | None) -> dict[str, object]:
    """session > workspace > project > global > default on; damaged consulted scopes are listed."""
    damaged: list[str] = []
    result: dict[str, object] = {"enabled": True, "source": "default"}
    for scope in SCOPES:
        if scope == "session" and session_key is None:
            continue
        try:
            value = _read_preference(_preference_path(store, scope, session_key))
        except _Damaged:
            damaged.append(scope)
            continue
        if value is not None:
            result = {"enabled": value, "source": scope}
            break
    if damaged:
        result["damaged"] = damaged
    return result


def _prune_sessions(directory: Path, keep: str) -> None:
    """Opportunistically remove session preferences untouched for 30 days; failures are ignored."""
    cutoff = time.time() - SESSION_RETENTION_SECONDS
    try:
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries, start=1):
                if count > SESSION_SCAN_MAX:
                    break
                if entry.name == keep or not _SESSION_FILE_RE.fullmatch(entry.name):
                    continue
                try:
                    if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < cutoff:
                        os.unlink(entry.path)
                except OSError:
                    pass
    except OSError:
        pass


def identity_suggest(root: Path, actor: str, scope: str, setting: str, *, session_key: str | None = None) -> dict[str, object]:
    """Set (``on``/``off``) or ``clear`` the suggestion preference at one scope.

    Off suppresses only the proactive offer; notes are still recorded and listed,
    and identity facts are never suppressed.
    """
    root = core._repo_root(root)
    actor = core._bounded_label(actor, "identity actor", 128)
    if scope not in SCOPES:
        raise _invalid(_errors.IDENTITY_PREFERENCE_INVALID, "invalid scope", allowed=list(SCOPES))
    if setting not in SETTINGS:
        raise _invalid(_errors.IDENTITY_PREFERENCE_INVALID, "invalid setting", allowed=list(SETTINGS))
    if session_key is not None:
        session_key = _session_key(session_key)
    if scope == "session" and session_key is None:
        raise ThalirisError(_errors.IDENTITY_PREFERENCE_INVALID, "session scope requires the adapter's native session key",
                            recovery="supply the adapter's native session key for session scope")
    store = _store(root)
    path = _preference_path(store, scope, session_key)
    if setting == "clear":
        try:
            path.unlink()
            changed = True
        except FileNotFoundError:
            changed = False
    else:
        record: dict[str, object] = {"format": PREFERENCE_FORMAT, "suggestions": setting, "actor": actor, "updated_at": _now()}
        if scope == "workspace":
            record["root"] = str(store.root)
        if scope == "project":
            _ensure_project_file(store)
        _write_json(path, record)
        changed = True
        if scope == "session":
            _prune_sessions(path.parent, path.name)
    return {"ok": True, "scope": scope, "setting": setting, "changed": changed,
            "suggestions": _resolve(store, session_key)}


# ---------------------------------------------------------------------------
# Status fields and the one-time offer


def status_fields(root: Path, current_version: int, session_key: str | None = None) -> tuple[dict[str, object], dict[str, object]]:
    """``basis`` and ``suggestions`` for identity-status; never raises."""
    try:
        store = _store(root)
    except Exception as exc:  # noqa: BLE001 - status must stay readable
        reason = str(exc)[:200]
        return ({"pending": 0, "total": 0, "retracted": 0, "damaged": 0, "unavailable": reason},
                {"enabled": None, "source": "unavailable"})
    try:
        basis: dict[str, object] = dict(_load_basis(store).counts(current_version))
    except Exception as exc:  # noqa: BLE001
        basis = {"pending": 0, "total": 0, "retracted": 0, "damaged": 0, "unavailable": str(exc)[:200]}
    try:
        suggestions = _resolve(store, session_key)
    except Exception:  # noqa: BLE001
        suggestions = {"enabled": None, "source": "unavailable"}
    return basis, suggestions


def _offer_line(state: str, version: int, count: int) -> str:
    noun = "statement" if count == 1 else "statements"
    stop = "To stop these offers: identity-suggest --off --scope session|workspace|project|global."
    if state == "ABSENT":
        verb = "is" if count == 1 else "are"
        return (f"Project identity: none recorded; {count} user {noun} about the project's long-term direction {verb} noted "
                "(identity-note --list). Optional: offer once, briefly, to compose a first version from them for the "
                f"user's confirmation; no answer means no. {stop}")
    return (f"Project identity v{version} ({identity._amendment_id(version)}, CURRENT); {count} user {noun} about the "
            f"project's long-term direction noted since v{version} (identity-note --list). Optional: offer once, briefly, "
            f"to compose an amendment from them for the user's confirmation; no answer means no. {stop}")


def _read_offer_state(path: Path) -> int:
    value = _read_json(path)
    if value is None:
        return 0
    shown = value.get("last_shown")
    match = _NOTE_ID_RE.fullmatch(shown) if isinstance(shown, str) else None
    if value.get("format") != OFFER_STATE_FORMAT or set(value) - _OFFER_STATE_FIELDS or match is None:
        raise _Damaged(f"{path.name}: invalid offer state")
    return int(match.group(1))


def _offer(root: Path, session_key: str | None) -> str | None:
    root = core._repo_root(root)
    if session_key is not None:
        session_key = _session_key(session_key)
    ctx = identity._load(root)
    if ctx.state not in ("ABSENT", "CURRENT"):
        return None  # INVALID and UNRECORDED_CHANGE are facts reported elsewhere
    store = _store(root)
    preference = _resolve(store, session_key)
    if preference["enabled"] is not True or "damaged" in preference:
        return None
    if not store.basis_dir.is_dir():
        return None
    with core._file_lock(store.project_dir / ".lock"):
        pending = _load_basis(store).pending(ctx.version)
        if not pending:
            return None
        highest = int(pending[-1][2:])
        path = store.project_dir / "offer-state.json"
        try:
            last_shown = _read_offer_state(path)
        except _Damaged:
            return None  # cannot prove it was not shown already
        if highest <= last_shown:
            return None
        # Record before returning: a line is returned only once its showing is recorded.
        _write_json(path, {"format": OFFER_STATE_FORMAT, "last_shown": pending[-1], "shown_at": _now(),
                           "identity_state": ctx.state, "identity_version": ctx.version})
    return _offer_line(ctx.state, ctx.version, len(pending))


def identity_offer(root: Path, session_key: str | None = None) -> str | None:
    """One low-priority line at most once per new pending note, or None.

    Returns a line only when suggestions resolve to enabled, the identity is ABSENT
    or CURRENT, at least one note is pending, and the highest pending note id is
    above the one last shown; the shown id is recorded before the line is returned.
    Never raises: any failure (including damaged storage) returns None.
    """
    try:
        return _offer(root, session_key)
    except Exception:  # noqa: BLE001 - adapters call this after close; failures must not surface
        return None
