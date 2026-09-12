"""Host-only opaque authority capabilities for benchmark collection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


def _identity(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _make_d11_host_boundary() -> tuple[Callable[..., object], Callable[[object], bool]]:
    """Keep the registry type and its seal inside the adapter host closure."""
    seal = object()

    class Registry:
        def __init__(self, verifier: Any, *, epoch: str, intent: str, policy: str) -> None:
            self._verifier = verifier
            self._seal = seal
            self.provenance = "HOST"
            self._epoch = epoch
            self._intent = intent
            self._policy = policy

        def verify_capture(self, descriptor: Any, *, path: Path, binding: dict[str, Any]) -> bool:
            if not isinstance(descriptor, dict):
                return False
            expected = _identity({key: value for key, value in descriptor.items() if key != "digest"})
            try:
                return bool(
                    descriptor.get("provenance") == "HOST"
                    and descriptor.get("binding") == binding
                    and descriptor.get("epoch") == self._epoch
                    and descriptor.get("intent") == self._intent
                    and descriptor.get("policy") == self._policy
                    and descriptor.get("digest") == expected
                    and self._verifier.verify(descriptor, path=path)
                )
            except (AttributeError, OSError, TypeError, ValueError):
                return False

    def bootstrap(verifier: Any, *, epoch: str, intent: str = "formal-collection",
                  policy: str = "codex-rollout-capture") -> object:
        if not all(isinstance(value, str) and value for value in (epoch, intent, policy)):
            raise ValueError("host authority bootstrap is invalid")
        if not callable(getattr(verifier, "verify", None)):
            raise ValueError("host authority verifier is invalid")
        return Registry(verifier, epoch=epoch, intent=intent, policy=policy)

    def accepts(value: object) -> bool:
        return isinstance(value, Registry) and getattr(value, "_seal", None) is seal

    return bootstrap, accepts


_bootstrap_d11_host_registry, _is_d11_host_registry = _make_d11_host_boundary()


def is_d11_host_registry(value: object) -> bool:
    """Validate an opaque registry supplied by the adapter host."""
    return _is_d11_host_registry(value)
