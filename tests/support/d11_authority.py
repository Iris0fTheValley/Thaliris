"""Fixture-only host composition for D11 authority-boundary tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _FixtureHostVerifier:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def verify(self, descriptor: Any, *, path: Path) -> bool:
        ref = descriptor.get("authority_ref") if isinstance(descriptor, dict) else None
        return bool(isinstance(ref, str) and self.records.get(ref) == descriptor
                    and descriptor.get("canonical_path") == str(path.resolve())
                    and descriptor.get("content_sha256") == _sha(path))


class FixtureHost:
    def __init__(self, sources: Any, issuer: str) -> None:
        self.issuer = issuer
        self.epoch = "fixture-epoch"; self.intent = "formal-collection"; self.policy = "codex-rollout-capture"
        self._verifier = _FixtureHostVerifier()
        self.registry = sources.compose_host_authority_registry(self._verifier, epoch=self.epoch, intent=self.intent, policy=self.policy)

    def issue(self, *, authority_ref: str, task_id: str, task_revision: int, reservation_id: str, session_id: str, path: Any) -> dict[str, Any]:
        path = Path(path).resolve()
        binding = {"task_id": task_id, "task_revision": task_revision, "reservation_id": reservation_id, "session_id": session_id}
        record = {"authority_ref": authority_ref, "issuer": self.issuer, "boundary": self.policy,
                  "canonical_path": str(path), "content_sha256": _sha(path), "provenance": "HOST",
                  "binding": binding, "epoch": self.epoch, "intent": self.intent, "policy": self.policy}
        record.update(binding); record["digest"] = _digest(record)
        self._verifier.records[authority_ref] = dict(record)
        return record


def capture_authority(sources: Any, *, issuer: str = "test-native-capture") -> FixtureHost:
    return FixtureHost(sources, issuer)


def issue_capture(authority: FixtureHost, *, authority_ref: str, task_id: str,
                  task_revision: int, reservation_id: str, session_id: str,
                  path: Any) -> dict[str, Any]:
    return authority.issue(authority_ref=authority_ref, task_id=task_id, task_revision=task_revision,
                           reservation_id=reservation_id, session_id=session_id, path=path)


def observe(protocol: Any, value: dict[str, Any], *, source_bytes: bytes) -> Any:
    return protocol._TestObservationWriter().observe(value, source_bytes=source_bytes)
