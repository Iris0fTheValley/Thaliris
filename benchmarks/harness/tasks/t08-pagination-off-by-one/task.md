The list screen is paginating wrongly. Fix `page_count` and `get_page` in `pagination.py`.

Pages are 1-based. `page_count(total, per_page)` is the number of pages needed to show `total` items (0 when there are no items, and a partly filled last page counts as a page). `get_page(items, page, per_page)` returns the items on that page; a page past the last one returns `[]`. Raise `ValueError` when `page < 1` or `per_page < 1` (in both functions where `per_page` is used).
