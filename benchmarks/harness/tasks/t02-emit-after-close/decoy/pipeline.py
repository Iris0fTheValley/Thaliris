"""Queue messages and deliver them over a Channel."""


class Pipeline:
    def __init__(self, channel):
        self.channel = channel
        self._pending = []
        self._shut = False

    def submit(self, message):
        if self._shut:
            raise RuntimeError("pipeline is shut down")
        self._pending.append(message)

    def flush(self):
        """Deliver pending messages in submission order."""
        while self._pending:
            self.channel.send(self._pending.pop(0))

    def shutdown(self):
        if self._shut:
            return
        self._shut = True
        self.channel.close()
        self.flush()
