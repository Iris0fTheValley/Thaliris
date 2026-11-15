"""A small in-memory key/value store with per-key revisions."""


class StaleRevision(Exception):
    """Raised when a write is based on an out-of-date revision."""


class KVStore:
    def __init__(self):
        self._data = {}  # key -> (value, revision)

    def get(self, key):
        """Return (value, revision). A missing key is (None, 0)."""
        return self._data.get(key, (None, 0))

    def put(self, key, value):
        """Store value and return the new revision."""
        _, revision = self.get(key)
        self._data[key] = (value, revision + 1)
        return revision + 1
