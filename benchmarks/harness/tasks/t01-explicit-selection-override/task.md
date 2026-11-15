Requests passed to `choose_backend(request)` in `router.py` can now carry an optional `"backend"` key. When it is present, the caller has explicitly picked a backend, and `choose_backend` must return exactly that backend.

An explicit selection always wins over the automatic routing rules (size, priority, or any rule added later). If the selected backend is not in `KNOWN_BACKENDS`, raise `ValueError`. Requests without a `"backend"` key must keep today's behaviour.
