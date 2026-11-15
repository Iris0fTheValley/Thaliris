import unittest

from config import merge_config


class HiddenTests(unittest.TestCase):
    def test_lists_and_none_replace(self):
        merged = merge_config({"paths": ["a", "b"], "x": 1}, {"paths": ["c"], "x": None})
        self.assertEqual(merged, {"paths": ["c"], "x": None})

    def test_dict_replaced_by_scalar_and_back(self):
        self.assertEqual(merge_config({"a": {"x": 1}}, {"a": 5}), {"a": 5})
        self.assertEqual(merge_config({"a": 5}, {"a": {"x": 1}}), {"a": {"x": 1}})

    def test_deep_nesting(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        merged = merge_config(base, {"a": {"b": {"c": 9}}})
        self.assertEqual(merged, {"a": {"b": {"c": 9, "d": 2}}})
        self.assertEqual(base, {"a": {"b": {"c": 1, "d": 2}}})

    def test_result_shares_no_nested_dicts_with_inputs(self):
        base = {"a": {"x": 1}, "only_base": {"k": 1}}
        override = {"b": {"y": 2}}
        merged = merge_config(base, override)
        merged["a"]["x"] = 100
        merged["only_base"]["k"] = 100
        merged["b"]["y"] = 100
        self.assertEqual(base, {"a": {"x": 1}, "only_base": {"k": 1}})
        self.assertEqual(override, {"b": {"y": 2}})

    def test_empty_inputs(self):
        self.assertEqual(merge_config({}, {}), {})
        self.assertEqual(merge_config({"a": 1}, {}), {"a": 1})
