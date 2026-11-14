Two clients read a value from `KVStore` (in `store.py`), edit it, and write it back, so one can overwrite the other's update. Add optimistic concurrency control.

`put(key, value, expected_rev=None)` gets an optional `expected_rev`. When it is given, the write only happens if the key's current revision is exactly `expected_rev`; otherwise raise `StaleRevision` and leave the store untouched. A missing key has revision 0, so `expected_rev=0` means "create only; fail if it already exists". Without `expected_rev`, `put` behaves as before. `put` still returns the new revision.
