"""Benchmark-local opaque authority capability boundary."""
from __future__ import annotations


def is_d11_host_registry(value: object) -> bool:
    """Portable benchmark code recognizes no injected host registry by default."""
    del value
    return False
