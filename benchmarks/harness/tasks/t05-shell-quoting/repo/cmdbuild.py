"""Build shell command lines for a job runner."""


def build_command(program, args):
    """Return a shell command string for ``program`` with ``args``."""
    return " ".join([program, *args])
