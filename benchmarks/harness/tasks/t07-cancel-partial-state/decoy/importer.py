"""Import records into an in-memory store (a list)."""


def import_records(store, records, should_cancel=lambda: False):
    """Append each record to ``store``. Rolls back when cancelled."""
    added = 0
    for record in records:
        if should_cancel():
            for _ in range(added):
                store.pop()
            return False
        if not isinstance(record, dict) or "id" not in record:
            raise ValueError(f"invalid record: {record!r}")
        store.append(record)
        added += 1
    return True
