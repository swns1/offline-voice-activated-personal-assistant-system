import time

import numpy as np

import ash.audio.recorder as recorder_module
from ash.audio.recorder import _VAD_FRAME_SAMPLES, ContinuousListener
from ash.audio.stt import SAMPLE_RATE


class _FakeWake:
    """triggers_on_frame: raw bytes of the one frame that should trigger
    detection; any other frame is treated as not-the-wake-word."""

    def __init__(self, frame_length=_VAD_FRAME_SAMPLES, triggers_on_frame=None):
        self.frame_length = frame_length
        self._triggers_on_frame = triggers_on_frame

    def process(self, frame) -> bool:
        return self._triggers_on_frame is not None and frame.tobytes() == self._triggers_on_frame


class _NullStream:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _content_based_is_speech(frame_bytes, rate):
    """Stands in for webrtcvad: any nonzero sample counts as speech, so
    tests can build utterances out of plain ones/zeros frames instead of
    depending on webrtcvad's real classification of synthetic audio."""
    frame = np.frombuffer(frame_bytes, dtype="int16")
    return bool(np.any(frame != 0))


def _speech_frame() -> np.ndarray:
    return np.ones(_VAD_FRAME_SAMPLES, dtype="int16")


def _silence_frame() -> np.ndarray:
    return np.zeros(_VAD_FRAME_SAMPLES, dtype="int16")


def _make_listener(silence_ms=90, max_record_seconds=10.0) -> ContinuousListener:
    listener = ContinuousListener(_FakeWake(), silence_ms=silence_ms, max_record_seconds=max_record_seconds)
    listener._vad.is_speech = _content_based_is_speech
    return listener


def test_record_until_silence_stops_after_configured_silence_run():
    listener = _make_listener(silence_ms=90)  # 3 frames of silence needed
    for _ in range(2):
        listener._queue.put(_speech_frame())
    for _ in range(3):
        listener._queue.put(_silence_frame())
    listener._queue.put(_speech_frame())  # queued but never reached

    utterance = listener._record_until_silence()

    assert len(utterance) == 5 * _VAD_FRAME_SAMPLES
    assert utterance.dtype == np.float32


def test_record_until_silence_stops_at_max_duration():
    max_seconds = 3 * _VAD_FRAME_SAMPLES / SAMPLE_RATE
    listener = _make_listener(silence_ms=30_000, max_record_seconds=max_seconds)
    for _ in range(10):
        listener._queue.put(_speech_frame())

    utterance = listener._record_until_silence()

    assert len(utterance) == 3 * _VAD_FRAME_SAMPLES


def test_wait_for_speech_returns_true_and_keeps_frame_pending():
    listener = _make_listener()
    listener._queue.put(_speech_frame())

    found = listener._wait_for_speech(timeout_seconds=1.0)

    assert found is True
    assert len(listener._pending) == _VAD_FRAME_SAMPLES


def test_wait_for_speech_discards_leading_silence():
    listener = _make_listener()
    listener._queue.put(_silence_frame())
    listener._queue.put(_silence_frame())
    listener._queue.put(_speech_frame())

    found = listener._wait_for_speech(timeout_seconds=1.0)

    assert found is True
    assert len(listener._pending) == _VAD_FRAME_SAMPLES  # silence frames were dropped


def test_wait_for_speech_times_out_with_no_audio():
    listener = _make_listener()

    start = time.monotonic()
    found = listener._wait_for_speech(timeout_seconds=0.2)
    elapsed = time.monotonic() - start

    assert found is False
    assert elapsed >= 0.2


def test_wait_for_wake_returns_once_matching_frame_arrives():
    speech = _speech_frame()
    wake = _FakeWake(triggers_on_frame=speech.tobytes())
    listener = ContinuousListener(wake)
    listener._queue.put(_silence_frame())
    listener._queue.put(speech)

    listener._wait_for_wake(_VAD_FRAME_SAMPLES)  # must return, not hang


def test_listen_for_followup_returns_none_on_timeout():
    listener = _make_listener()

    result = listener.listen_for_followup(timeout_seconds=0.2)

    assert result is None


def test_listen_for_followup_records_when_speech_detected():
    listener = _make_listener(silence_ms=30)  # 1 frame of silence cuts off
    listener._queue.put(_speech_frame())
    listener._queue.put(_silence_frame())

    utterance = listener.listen_for_followup(timeout_seconds=1.0)

    assert utterance is not None
    assert len(utterance) == 2 * _VAD_FRAME_SAMPLES


def test_listen_yields_one_utterance_per_wake_cycle(monkeypatch):
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: _NullStream())

    speech = _speech_frame()
    wake = _FakeWake(triggers_on_frame=speech.tobytes())
    listener = ContinuousListener(wake, silence_ms=30)
    listener._vad.is_speech = _content_based_is_speech

    listener._queue.put(_silence_frame())  # doesn't trigger the wake word
    listener._queue.put(speech)  # triggers it
    listener._queue.put(speech)  # start of the command
    listener._queue.put(_silence_frame())  # cuts the command off

    gen = listener.listen()
    utterance = next(gen)
    gen.close()

    assert len(utterance) == 2 * _VAD_FRAME_SAMPLES
