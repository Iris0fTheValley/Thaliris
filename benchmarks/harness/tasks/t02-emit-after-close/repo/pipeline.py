"""Queue messages and deliver them over a Channel."""


class Pipeline:
    def __init__(self, channel):
        self.channel = channel
        self._pending = []

    def submit(self, message):
        self._pending.append(message)

    def flush(self):
        """Deliver pending messages in submission order."""
        while self._pending:
            self.channel.send(self._pending.pop(0))

    def shutdown(self):
        self.channel.close()
