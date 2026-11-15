import unittest

from store import KVStore, StaleRevision


class VisibleTests(unittest.TestCase):
    def test_matching_revision_writes(self):
        store = KVStore()
        self.assertEqual(store.put("k", "v1"), 1)
        self.assertEqual(store.put("k", "v2", expected_rev=1), 2)
        self.assertEqual(store.get("k"), ("v2", 2))

    def test_stale_writer_is_rejected(self):
        store = KVStore()
        store.put("k", "v1")
        store.put("k", "v2", expected_rev=1)
        with self.assertRaises(StaleRevision):
            store.put("k", "from-slow-client", expected_rev=1)
        self.assertEqual(store.get("k"), ("v2", 2))

    def test_unconditional_put_still_works(self):
        store = KVStore()
        store.put("k", "a")
        self.assertEqual(store.put("k", "b"), 2)
