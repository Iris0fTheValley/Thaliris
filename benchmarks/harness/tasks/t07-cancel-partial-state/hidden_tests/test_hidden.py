import unittest

from importer import import_records


class HiddenTests(unittest.TestCase):
    def test_invalid_record_midway_leaves_store_unchanged(self):
        store = [{"id": 0}]
        with self.assertRaises(ValueError):
            import_records(store, [{"id": 1}, {"id": 2}, {"name": "no id"}, {"id": 4}])
        self.assertEqual(store, [{"id": 0}])

    def test_non_dict_record_midway_leaves_store_unchanged(self):
        store = []
        with self.assertRaises(ValueError):
            import_records(store, [{"id": 1}, "oops"])
        self.assertEqual(store, [])

    def test_cancel_check_raising_rolls_back_and_propagates(self):
        store = [{"id": 0}]
        calls = {"n": 0}

        def should_cancel():
            calls["n"] += 1
            if calls["n"] == 3:
                raise TimeoutError("took too long")
            return False

        with self.assertRaises(TimeoutError):
            import_records(store, [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}], should_cancel)
        self.assertEqual(store, [{"id": 0}])

    def test_store_is_modified_in_place(self):
        store = [{"id": 0}]
        alias = store
        import_records(store, [{"id": 1}])
        self.assertIs(alias, store)
        self.assertEqual(alias, [{"id": 0}, {"id": 1}])

    def test_preexisting_records_survive_failure(self):
        existing = {"id": 0}
        store = [existing]
        with self.assertRaises(ValueError):
            import_records(store, [{"id": 1}, None])
        self.assertEqual(len(store), 1)
        self.assertIs(store[0], existing)
