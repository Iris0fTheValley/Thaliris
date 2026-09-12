"""Host-only opaque authority capabilities for benchmark collection."""
from __future__ import annotations

def is_d11_host_registry(value: object) -> bool:
    """Production has no local registry factory or receipt issuer.

    A native host may replace this boundary when it injects an opaque runtime
    capability.  The portable Python adapter intentionally recognizes none.
    """
    return False
