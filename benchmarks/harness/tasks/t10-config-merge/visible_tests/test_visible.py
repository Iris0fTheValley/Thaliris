import unittest

from config import merge_config


class VisibleTests(unittest.TestCase):
    def test_nested_sections_are_merged(self):
        base = {"db": {"host": "localhost", "port": 5432}, "debug": False}
        override = {"db": {"port": 6000}}
        self.assertEqual(
            merge_config(base, override),
            {"db": {"host": "localhost", "port": 6000}, "debug": False},
        )

    def test_override_wins_for_scalars(self):
        self.assertEqual(merge_config({"a": 1}, {"a": 2, "b": 3}), {"a": 2, "b": 3})

    def test_inputs_not_modified(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        merge_config(base, override)
        self.assertEqual(base, {"a": {"x": 1}})
        self.assertEqual(override, {"a": {"y": 2}})
