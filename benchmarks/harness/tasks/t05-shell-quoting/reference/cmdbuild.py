"""Build shell command lines for a job runner."""
import shlex


def build_command(program, args):
    """Return a shell command string for ``program`` with ``args``."""
    return " ".join(shlex.quote(part) for part in [program, *args])
