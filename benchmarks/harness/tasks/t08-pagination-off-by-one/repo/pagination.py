"""Helpers for paginating a list of items."""


def page_count(total, per_page):
    """Number of pages needed for ``total`` items."""
    return total // per_page


def get_page(items, page, per_page):
    """Return the items on the given page."""
    start = page * per_page
    return items[start:start + per_page]
