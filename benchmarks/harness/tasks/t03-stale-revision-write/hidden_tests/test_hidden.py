import unittest

from store import KVStore, StaleRevision


class HiddenTests(unittest.TestCase):
    def test_create_only_succeeds_on_missing_key(self):
        store = KVStore()
        self.assertEqual(store.put("k", "v", expected_rev=0), 1)

    def test_create_only_fails_on_existing_key(self):
        store = KVStore()
        store.put("k", "v1")
        with self.assertRaises(StaleRevision):
            store.put("k", "v2", expected_rev=0)
        self.assertEqual(store.get("k"), ("v1", 1))

    def test_future_revision_is_rejected_too(self):
        store = KVStore()
        store.put("k", "v1")
        with self.assertRaises(StaleRevision):
            store.put("k", "v2", expected_rev=5)
        self.assertEqual(store.get("k"), ("v1", 1))

    def test_expected_rev_on_missing_key_other_than_zero_fails(self):
        store = KVStore()
        with self.assertRaises(StaleRevision):
            store.put("k", "v", expected_rev=1)
        self.assertEqual(store.get("k"), (None, 0))

    def test_rejected_write_does_not_bump_revision(self):
        store = KVStore()
        store.put("k", "v1")
        with self.assertRaises(StaleRevision):
            store.put("k", "x", expected_rev=7)
        self.assertEqual(store.put("k", "v2", expected_rev=1), 2)
