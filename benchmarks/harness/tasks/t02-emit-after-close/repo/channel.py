"""A tiny in-process event channel.

Listeners receive ("message", payload) events and one final ("closed", None)
event. The channel does not guard against use after close; callers must order
their operations correctly.
"""


class Channel:
    def __init__(self):
        self._listeners = []
        self.closed = False

    def subscribe(self, listener):
        self._listeners.append(listener)

    def send(self, payload):
        self._emit("message", payload)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._emit("closed", None)

    def _emit(self, kind, payload):
        for listener in list(self._listeners):
            listener(kind, payload)
