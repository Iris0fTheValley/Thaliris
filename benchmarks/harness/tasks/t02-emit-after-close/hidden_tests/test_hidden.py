import unittest

from channel import Channel
from pipeline import Pipeline


class HiddenTests(unittest.TestCase):
    def test_closed_is_the_last_event(self):
        channel = Channel()
        events = []
        channel.subscribe(lambda kind, payload: events.append((kind, payload)))
        pipe = Pipeline(channel)
        pipe.submit("a")
        pipe.submit("b")
        pipe.shutdown()
        self.assertEqual(events, [("message", "a"), ("message", "b"), ("closed", None)])

    def test_follow_ups_are_delivered_before_close(self):
        channel = Channel()
        events = []
        pipe = Pipeline(channel)

        def listener(kind, payload):
            events.append((kind, payload))
            if kind == "message" and payload == "a":
                pipe.submit("a-followup")

        channel.subscribe(listener)
        pipe.submit("a")
        pipe.shutdown()
        self.assertEqual(
            events, [("message", "a"), ("message", "a-followup"), ("closed", None)]
        )

    def test_nothing_after_closed_even_with_late_follow_up(self):
        channel = Channel()
        events = []
        pipe = Pipeline(channel)

        def listener(kind, payload):
            events.append((kind, payload))
            if kind == "closed":
                try:
                    pipe.submit("after-close")
                    pipe.flush()
                except RuntimeError:
                    pass

        channel.subscribe(listener)
        pipe.submit("a")
        pipe.shutdown()
        self.assertEqual(events[-1], ("closed", None))
        self.assertNotIn(("message", "after-close"), events)

    def test_second_shutdown_emits_nothing(self):
        channel = Channel()
        events = []
        channel.subscribe(lambda kind, payload: events.append((kind, payload)))
        pipe = Pipeline(channel)
        pipe.submit("a")
        pipe.shutdown()
        count = len(events)
        pipe.shutdown()
        self.assertEqual(len(events), count)
