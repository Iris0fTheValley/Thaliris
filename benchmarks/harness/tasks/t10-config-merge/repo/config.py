"""Configuration helpers."""


def merge_config(base, override):
    """Return the configuration ``base`` updated with ``override``."""
    base.update(override)
    return base
