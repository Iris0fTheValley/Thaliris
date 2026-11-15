# Exact schema diagnostic from Core 161f9faf84eb9d802aaaf8e8a05927c0f50c22b3 src/thaliris/core.py.
import hashlib
import uuid
_STATE_SCHEMA_VERSION = 7

def _task_state_schema_diagnostic(raw: object, raw_bytes: bytes) -> dict[str, object] | None:
    """Classify schema-version mismatch without migrating or mutating it."""
    if not isinstance(raw, dict):
        return None
    version = raw.get("schema_version")
    if type(version) is not int or version == _STATE_SCHEMA_VERSION:
        return None
    task_id = raw.get("task_id")
    try:
        uuid.UUID(str(task_id))
        valid_task_id = isinstance(task_id, str)
    except (ValueError, AttributeError, TypeError):
        valid_task_id = False
    status = raw.get("status")
    older_supported_for_archive = 0 < version < _STATE_SCHEMA_VERSION
    recoverable = older_supported_for_archive and valid_task_id and (status == "ACTIVE" or status == "DONE")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    action = "NONE"
    if recoverable:
        action = f"thaliris task-recover-state --expected-sha256 {digest}"
    return {
        "ok": False,
        "status": "STATE_SCHEMA_INCOMPATIBLE",
        "error": "invalid task state schema",
        "from_version": version,
        "to_version": _STATE_SCHEMA_VERSION,
        "state_sha256": digest,
        "recoverable": recoverable,
        "abandon_active_confirmation_required": status == "ACTIVE" and recoverable,
        "recovery_action": action,
    }
