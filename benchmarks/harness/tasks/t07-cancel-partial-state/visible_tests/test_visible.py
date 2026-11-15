import unittest

from importer import import_records


def make_cancel_after(n):
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > n

    return should_cancel


class VisibleTests(unittest.TestCase):
    def test_success_returns_true_and_appends(self):
        store = [{"id": 0}]
        self.assertTrue(import_records(store, [{"id": 1}, {"id": 2}]))
        self.assertEqual(store, [{"id": 0}, {"id": 1}, {"id": 2}])

    def test_cancel_midway_rolls_back(self):
        store = [{"id": 0}]
        result = import_records(store, [{"id": 1}, {"id": 2}, {"id": 3}], make_cancel_after(2))
        self.assertIs(result, False)
        self.assertEqual(store, [{"id": 0}])

    def test_cancel_before_first_record(self):
        store = []
        self.assertIs(import_records(store, [{"id": 1}], lambda: True), False)
        self.assertEqual(store, [])
