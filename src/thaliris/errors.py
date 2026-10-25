"""Structured mechanical errors shared by Core and its adapters.

``ThalirisError`` is a ``ValueError`` so existing ``except ValueError``
handlers and message checks keep working: ``str(exc)`` is exactly the human
message (for pre-existing failures, the historical message text or an
extension that starts with it). The stable ``code``, short mechanical
``recovery`` hint and bounded ``details`` are additive attributes that an
adapter may surface via ``to_dict()``. Codes never carry semantic judgment.
"""
from __future__ import annotations

# Stable error codes. Adapters may branch on these; messages may evolve.
TASK_REVISION_CONFLICT = "TASK_REVISION_CONFLICT"
TASK_IDENTITY_CONFLICT = "TASK_IDENTITY_CONFLICT"
TASK_STATE_MISSING = "TASK_STATE_MISSING"
TASK_STATE_INVALID = "TASK_STATE_INVALID"
TASK_NOT_ACTIVE = "TASK_NOT_ACTIVE"
TASK_OBJECT_NOT_FOUND = "TASK_OBJECT_NOT_FOUND"
TASK_OBJECT_ID_COLLISION = "TASK_OBJECT_ID_COLLISION"
INPUT_DECODING_ERROR = "INPUT_DECODING_ERROR"
INPUT_JSON_INVALID = "INPUT_JSON_INVALID"
INPUT_NOT_OBJECT = "INPUT_NOT_OBJECT"
CONTINUITY_INVALID = "CONTINUITY_INVALID"
CONTINUITY_REFERENCE_INVALID = "CONTINUITY_REFERENCE_INVALID"
CONTINUITY_PROVENANCE_CONFLICT = "CONTINUITY_PROVENANCE_CONFLICT"
CONTINUITY_ID_COLLISION = "CONTINUITY_ID_COLLISION"
REVISION_DELTA_INVALID = "REVISION_DELTA_INVALID"
# A bounded ledger list, the routing page or the whole state file is full; the write is refused unchanged.
TASK_STATE_CAPACITY_EXCEEDED = "TASK_STATE_CAPACITY_EXCEEDED"
# The external authority anchor exists but cannot be read as a Core authority record.
TASK_AUTHORITY_INVALID = "TASK_AUTHORITY_INVALID"
# Identity formation (basis notes and suggestion preferences; stored outside the repository).
IDENTITY_NOTE_INVALID = "IDENTITY_NOTE_INVALID"
IDENTITY_NOTE_NOT_FOUND = "IDENTITY_NOTE_NOT_FOUND"
IDENTITY_NOTE_ALREADY_RETRACTED = "IDENTITY_NOTE_ALREADY_RETRACTED"
IDENTITY_NOTE_LIMIT = "IDENTITY_NOTE_LIMIT"
IDENTITY_PREFERENCE_INVALID = "IDENTITY_PREFERENCE_INVALID"


class ThalirisError(ValueError):
    """A ValueError with a stable code, mechanical recovery hint and details."""

    def __init__(self, code: str, message: str, *, recovery: str | None = None,
                 details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recovery = recovery
        self.details = details

    def to_dict(self) -> dict[str, object]:
        """Return the additive JSON error envelope (without ``ok``)."""
        result: dict[str, object] = {"error": self.message, "code": self.code}
        if self.recovery is not None:
            result["recovery"] = self.recovery
        if self.details is not None:
            result["details"] = self.details
        return result


def error_envelope(exc: BaseException) -> dict[str, object]:
    """Render any adapter-facing failure as ``{"ok": False, "error": ...}``.

    Structured errors add ``code``/``recovery``/``details``; other errors keep
    the historical ``{"ok": false, "error": str(exc)}`` shape exactly.
    """
    if isinstance(exc, ThalirisError):
        return {"ok": False, **exc.to_dict()}
    return {"ok": False, "error": str(exc)}
