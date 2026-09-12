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


class _TestRegistry:
    """Fixture-only marker that the production formal boundary must reject."""
    def __init__(self, verifier: _FixtureHostVerifier, *, epoch: str, intent: str, policy: str) -> None:
        self.provenance = "HOST"
        self._verifier = verifier
        self._epoch = epoch
        self._intent = intent
        self._policy = policy

    def verify_capture(self, descriptor: Any, *, path: Path, binding: dict[str, Any]) -> bool:
        if not isinstance(descriptor, dict):
            return False
        expected = _digest({key: value for key, value in descriptor.items() if key != "digest"})
        return bool(
            descriptor.get("provenance") == "HOST" and descriptor.get("binding") == binding
            and descriptor.get("epoch") == self._epoch and descriptor.get("intent") == self._intent
            and descriptor.get("policy") == self._policy and descriptor.get("digest") == expected
            and self._verifier.verify(descriptor, path=path)
        )


class FixtureHost:
    def __init__(self, sources: Any, issuer: str) -> None:
        self.issuer = issuer
        self.epoch = "fixture-epoch"; self.intent = "formal-collection"; self.policy = "codex-rollout-capture"
        self._verifier = _FixtureHostVerifier()
        self.registry = _TestRegistry(self._verifier, epoch=self.epoch, intent=self.intent, policy=self.policy)

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


def inject_formal_registry(monkeypatch: Any, sources: Any, authority: FixtureHost) -> Any:
    """Test-only host-runtime injection; production never imports this path."""
    import sys
    registry = authority.registry
    accept = lambda value: value is registry
    monkeypatch.setattr(sources, "is_d11_host_registry", accept)
    loaded = sys.modules.get("d11_sources")
    if loaded is not None:
        monkeypatch.setattr(loaded, "is_d11_host_registry", accept)
    return registry


def issue_capture(authority: FixtureHost, *, authority_ref: str, task_id: str,
                  task_revision: int, reservation_id: str, session_id: str,
                  path: Any) -> dict[str, Any]:
    return authority.issue(authority_ref=authority_ref, task_id=task_id, task_revision=task_revision,
                           reservation_id=reservation_id, session_id=session_id, path=path)


def observe(protocol: Any, value: dict[str, Any], *, source_bytes: bytes) -> Any:
    return protocol._TestObservationWriter().observe(value, source_bytes=source_bytes)
