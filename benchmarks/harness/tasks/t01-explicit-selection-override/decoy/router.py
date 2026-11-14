"""Pick a processing backend for a request."""

KNOWN_BACKENDS = ("standard", "fast", "batch", "local")


def _is_large(request):
    return request.get("size", 0) > 1000


def _is_urgent(request):
    return request.get("priority") == "high"


DEFAULT_RULES = [
    (_is_large, "batch"),
    (_is_urgent, "fast"),
]


def choose_backend(request):
    """Return the backend name for ``request`` (a dict)."""
    for matches, backend in DEFAULT_RULES:
        if matches(request):
            return backend
    if "backend" in request:
        if request["backend"] not in KNOWN_BACKENDS:
            raise ValueError(f"unknown backend: {request['backend']!r}")
        return request["backend"]
    return "standard"
