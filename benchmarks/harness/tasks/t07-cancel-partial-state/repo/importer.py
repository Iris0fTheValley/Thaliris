"""Import records into an in-memory store (a list)."""


def import_records(store, records, should_cancel=lambda: False):
    """Append each record to ``store``. Stops early when cancelled."""
    for record in records:
        if should_cancel():
            break
        if not isinstance(record, dict) or "id" not in record:
            raise ValueError(f"invalid record: {record!r}")
        store.append(record)
