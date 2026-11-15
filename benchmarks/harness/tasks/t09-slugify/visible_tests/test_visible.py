import unittest

from textutil import slugify


class VisibleTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_digits_kept(self):
        self.assertEqual(slugify("Release 2024 notes"), "release-2024-notes")

    def test_empty(self):
        self.assertEqual(slugify(""), "")
