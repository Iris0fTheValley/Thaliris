"""Small typed configuration and public result vocabulary."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
from pathlib import Path


class Confidence(StrEnum):
    CONFIRMED = "CONFIRMED"
    SUPPORTED = "SUPPORTED"
    UNVERIFIED = "UNVERIFIED"
    STALE = "STALE"


class Health(StrEnum):
    UNKNOWN = "UNKNOWN"
    NO = "NO"
    YES = "YES"


@dataclass(frozen=True)
class ContextConfig:
    """Configuration is deliberately local, opt-in, and has no credentials."""
    schema_version: int = 1
    automatic_injection: bool = False
    automatic_compression: bool = False
    adapter_probes: bool = True
    adapters: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path) -> "ContextConfig":
        path = root / ".context" / "config.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid .context/config.json") from exc
        allowed = {"schema_version", "automatic_injection", "automatic_compression", "adapter_probes", "adapters"}
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise ValueError("unknown configuration field")
        if type(raw.get("schema_version", 1)) is not int or raw.get("schema_version") != 1:
            raise ValueError("unsupported configuration schema")
        for key in ("automatic_injection", "automatic_compression", "adapter_probes"):
            if key in raw and not isinstance(raw[key], bool):
                raise ValueError(f"{key} must be boolean")
        adapter_names = {"serena", "cachebro", "agentmemory"}
        if "adapters" in raw and (not isinstance(raw["adapters"], dict) or not all(k in adapter_names and isinstance(v, bool) for k, v in raw["adapters"].items())):
            raise ValueError("adapters must map strings to booleans")
        # These must remain false; adapters are strictly advisory/manual recall.
        if raw.get("automatic_injection") or raw.get("automatic_compression"):
            raise ValueError("automatic injection and compression are prohibited")
        return cls(**raw)

    def write(self, root: Path) -> bytes:
        return (json.dumps(asdict(self), indent=2, sort_keys=True) + "\n").encode()
