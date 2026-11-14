"""Build shell command lines for a job runner."""


def build_command(program, args):
    """Return a shell command string for ``program`` with ``args``."""
    parts = [program]
    for arg in args:
        parts.append(f'"{arg}"' if " " in arg else arg)
    return " ".join(parts)
