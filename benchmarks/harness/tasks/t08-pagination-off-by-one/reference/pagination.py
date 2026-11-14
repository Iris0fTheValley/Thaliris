"""Helpers for paginating a list of items."""


def page_count(total, per_page):
    """Number of pages needed for ``total`` items."""
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    return -(-total // per_page)


def get_page(items, page, per_page):
    """Return the items on the given 1-based page."""
    if page < 1:
        raise ValueError("page must be >= 1")
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    start = (page - 1) * per_page
    return items[start:start + per_page]
