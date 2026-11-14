import unittest

from pagination import get_page, page_count


class VisibleTests(unittest.TestCase):
    def test_page_count_with_partial_last_page(self):
        self.assertEqual(page_count(10, 3), 4)

    def test_first_and_last_page(self):
        items = list(range(10))
        self.assertEqual(get_page(items, 1, 3), [0, 1, 2])
        self.assertEqual(get_page(items, 4, 3), [9])

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            get_page([1, 2, 3], 0, 2)
        with self.assertRaises(ValueError):
            get_page([1, 2, 3], 1, 0)
        with self.assertRaises(ValueError):
            page_count(5, 0)
