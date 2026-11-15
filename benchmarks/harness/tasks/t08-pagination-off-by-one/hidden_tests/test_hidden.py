import unittest

from pagination import get_page, page_count


class HiddenTests(unittest.TestCase):
    def test_exact_multiple_has_no_extra_page(self):
        self.assertEqual(page_count(9, 3), 3)
        self.assertEqual(page_count(3, 3), 1)

    def test_no_items_means_no_pages(self):
        self.assertEqual(page_count(0, 3), 0)

    def test_single_item(self):
        self.assertEqual(page_count(1, 50), 1)

    def test_last_full_page_and_beyond(self):
        items = list(range(9))
        self.assertEqual(get_page(items, 3, 3), [6, 7, 8])
        self.assertEqual(get_page(items, 4, 3), [])
        self.assertEqual(get_page([], 1, 3), [])

    def test_page_boundaries_cover_every_item_exactly_once(self):
        items = list(range(23))
        seen = []
        for page in range(1, page_count(len(items), 5) + 1):
            seen.extend(get_page(items, page, 5))
        self.assertEqual(seen, items)
