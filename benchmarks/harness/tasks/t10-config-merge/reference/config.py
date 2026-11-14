"""Configuration helpers."""
import copy


def merge_config(base, override):
    """Return a new configuration: ``base`` with ``override`` layered on top."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
