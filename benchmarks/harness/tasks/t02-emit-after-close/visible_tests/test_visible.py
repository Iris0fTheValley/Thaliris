import unittest

from channel import Channel
from pipeline import Pipeline


def make():
    channel = Channel()
    events = []
    channel.subscribe(lambda kind, payload: events.append((kind, payload)))
    return Pipeline(channel), events


class VisibleTests(unittest.TestCase):
    def test_shutdown_delivers_pending_and_closes(self):
        pipe, events = make()
        pipe.submit("a")
        pipe.submit("b")
        pipe.shutdown()
        self.assertEqual([p for k, p in events if k == "message"], ["a", "b"])
        self.assertEqual([k for k, _ in events].count("closed"), 1)

    def test_submit_after_shutdown_raises(self):
        pipe, _ = make()
        pipe.shutdown()
        with self.assertRaises(RuntimeError):
            pipe.submit("late")

    def test_shutdown_twice_is_harmless(self):
        pipe, events = make()
        pipe.submit("a")
        pipe.shutdown()
        pipe.shutdown()
        self.assertEqual([k for k, _ in events].count("closed"), 1)
