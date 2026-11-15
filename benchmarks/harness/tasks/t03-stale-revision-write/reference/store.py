"""A small in-memory key/value store with per-key revisions."""


class StaleRevision(Exception):
    """Raised when a write is based on an out-of-date revision."""


class KVStore:
    def __init__(self):
        self._data = {}  # key -> (value, revision)

    def get(self, key):
        """Return (value, revision). A missing key is (None, 0)."""
        return self._data.get(key, (None, 0))

    def put(self, key, value, expected_rev=None):
        """Store value and return the new revision.

        If expected_rev is given the write only happens when it equals the
        key's current revision (0 for a missing key).
        """
        _, revision = self.get(key)
        if expected_rev is not None and expected_rev != revision:
            raise StaleRevision(f"{key!r}: expected {expected_rev}, current {revision}")
        self._data[key] = (value, revision + 1)
        return revision + 1
