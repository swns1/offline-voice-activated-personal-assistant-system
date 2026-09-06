from ash.audio.tts import TtsWorker


class FakeEngine:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


def test_stop_speaking_drains_queue_and_stops_engine():
    worker = TtsWorker()
    worker.say("first")
    worker.say("second")
    fake_engine = FakeEngine()
    worker._engine = fake_engine

    worker.stop_speaking()

    assert worker._queue.empty()
    assert fake_engine.stop_calls == 1


def test_stop_speaking_before_engine_exists_is_a_noop():
    worker = TtsWorker()
    worker.say("queued")

    worker.stop_speaking()  # _engine is still None -- must not raise

    assert worker._queue.empty()


def test_stop_speaking_with_empty_queue_still_stops_engine():
    worker = TtsWorker()
    fake_engine = FakeEngine()
    worker._engine = fake_engine

    worker.stop_speaking()

    assert fake_engine.stop_calls == 1
