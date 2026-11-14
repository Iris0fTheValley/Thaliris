import unittest

from router import choose_backend


class HiddenTests(unittest.TestCase):
    def test_explicit_beats_size_rule(self):
        self.assertEqual(choose_backend({"backend": "local", "size": 5000}), "local")

    def test_explicit_beats_priority_rule(self):
        self.assertEqual(choose_backend({"backend": "standard", "priority": "high"}), "standard")

    def test_explicit_beats_every_rule_at_once(self):
        self.assertEqual(
            choose_backend({"backend": "fast", "size": 9999, "priority": "high"}), "fast"
        )

    def test_unknown_backend_rejected_even_when_rules_match(self):
        with self.assertRaises(ValueError):
            choose_backend({"backend": "quantum", "size": 5000})
