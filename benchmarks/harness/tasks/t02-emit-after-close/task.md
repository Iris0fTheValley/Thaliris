`Pipeline.shutdown()` in `pipeline.py` currently closes the channel and silently drops any messages that are still pending. Fix it.

`shutdown()` must deliver every pending message in submission order and then close the channel exactly once. Listeners may submit follow-up messages while they are receiving a message; those follow-ups must also be delivered, and still before the channel is closed. Nothing may be delivered to listeners after the `"closed"` event. After `shutdown()`, `submit()` raises `RuntimeError`. Calling `shutdown()` a second time is harmless.
