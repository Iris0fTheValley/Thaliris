"""Import records into an in-memory store (a list)."""


def import_records(store, records, should_cancel=lambda: False):
    """Append each record to ``store`` atomically: all of them or none."""
    original_length = len(store)
    try:
        for record in records:
            if should_cancel():
                del store[original_length:]
                return False
            if not isinstance(record, dict) or "id" not in record:
                raise ValueError(f"invalid record: {record!r}")
            store.append(record)
    except BaseException:
        del store[original_length:]
        raise
    return True
