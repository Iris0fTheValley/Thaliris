import unittest

from textutil import slugify


class HiddenTests(unittest.TestCase):
    def test_runs_collapse_and_edges_trimmed(self):
        self.assertEqual(slugify("  --A  b__c ** "), "a-b-c")

    def test_non_ascii_is_a_separator(self):
        self.assertEqual(slugify("Café 2024"), "caf-2024")
        self.assertEqual(slugify("中文abc"), "abc")

    def test_no_alphanumerics(self):
        self.assertEqual(slugify("!!! ???"), "")

    def test_already_a_slug(self):
        self.assertEqual(slugify("already-a-slug"), "already-a-slug")
