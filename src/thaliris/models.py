"""Small typed configuration and public result vocabulary."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ContextConfig:
    """Small local configuration marker; legacy keys are deliberately ignored."""
    schema_version: int = 1

    @classmethod
    def load(cls, root: Path) -> "ContextConfig":
        path = root / ".context" / "config.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid .context/config.json") from exc
        if not isinstance(raw, dict):
            raise ValueError("configuration must be an object")
        if type(raw.get("schema_version", 1)) is not int or raw.get("schema_version") != 1:
            raise ValueError("unsupported configuration schema")
        return cls(schema_version=raw.get("schema_version", 1))

    def write(self, root: Path) -> bytes:
        return (json.dumps(asdict(self), indent=2, sort_keys=True) + "\n").encode()
