"""Fixture-only writers for D11 authority-boundary tests.

The production modules expose validation capabilities only.  Tests inject
these writers explicitly when they need a synthetic host observation.
"""
from __future__ import annotations

from typing import Any


def capture_authority(sources: Any, *, issuer: str = "test-native-capture") -> Any:
    return sources._TestCaptureAuthorityWriter(issuer)


def issue_capture(authority: Any, *, authority_ref: str, task_id: str,
                  task_revision: int, reservation_id: str, session_id: str,
                  path: Any) -> dict[str, Any]:
    return authority.issue(
        authority_ref=authority_ref, task_id=task_id,
        task_revision=task_revision, reservation_id=reservation_id,
        session_id=session_id, path=path,
    )


def observe(protocol: Any, value: dict[str, Any], *, source_bytes: bytes) -> Any:
    return protocol._TestObservationWriter().observe(value, source_bytes=source_bytes)
