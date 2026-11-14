import unittest

from router import choose_backend


class VisibleTests(unittest.TestCase):
    def test_defaults_unchanged(self):
        self.assertEqual(choose_backend({}), "standard")
        self.assertEqual(choose_backend({"size": 5000}), "batch")
        self.assertEqual(choose_backend({"priority": "high"}), "fast")

    def test_explicit_backend_is_used(self):
        self.assertEqual(choose_backend({"backend": "local"}), "local")
        self.assertEqual(choose_backend({"backend": "fast", "size": 10}), "fast")

    def test_unknown_backend_rejected(self):
        with self.assertRaises(ValueError):
            choose_backend({"backend": "quantum"})
