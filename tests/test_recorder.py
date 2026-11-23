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


def _speech_frame(length: int = _VAD_FRAME_SAMPLES) -> np.ndarray:
    return np.ones(length, dtype="int16")


def _silence_frame(length: int = _VAD_FRAME_SAMPLES) -> np.ndarray:
    return np.zeros(length, dtype="int16")


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


_REAL_WAKE_FRAME_LEN = 1280  # the real WakeWordDetector.frame_length, not the test default


def _make_barge_in_listener(is_speaking, on_barge_in) -> ContinuousListener:
    wake = _FakeWake(frame_length=_REAL_WAKE_FRAME_LEN)  # never triggers unless fed its exact frame
    listener = ContinuousListener(wake, is_speaking=is_speaking, on_barge_in=on_barge_in)
    listener._vad.is_speech = _content_based_is_speech
    return listener


def test_default_barge_in_hooks_are_noop():
    listener = ContinuousListener(_FakeWake())
    assert listener._is_speaking() is False
    listener._on_barge_in()  # must not raise


def test_frame_has_speech_detects_uniform_speech_frame():
    listener = _make_barge_in_listener(lambda: True, lambda: None)
    frame = _speech_frame(_REAL_WAKE_FRAME_LEN)
    assert listener._frame_has_speech(frame) is True


def test_frame_has_speech_returns_false_for_silence():
    listener = _make_barge_in_listener(lambda: True, lambda: None)
    frame = _silence_frame(_REAL_WAKE_FRAME_LEN)
    assert listener._frame_has_speech(frame) is False


def test_wait_for_wake_barge_in_triggers_on_consecutive_speech():
    calls = []
    listener = _make_barge_in_listener(lambda: True, lambda: calls.append(1))
    for _ in range(2):  # _BARGE_IN_FRAMES_NEEDED
        listener._queue.put(_speech_frame(_REAL_WAKE_FRAME_LEN))

    listener._wait_for_wake(_REAL_WAKE_FRAME_LEN)  # must return via barge-in, not hang

    assert calls == [1]


def test_wait_for_wake_no_barge_in_when_tts_not_speaking():
    calls = []
    listener = _make_barge_in_listener(lambda: False, lambda: calls.append(1))
    speech = _speech_frame(_REAL_WAKE_FRAME_LEN)
    for _ in range(3):
        listener._queue.put(speech)
    # A real wake-triggering frame so the loop terminates via the normal
    # path (barge-in must not have fired, or this frame is unreachable).
    wake_frame = _silence_frame(_REAL_WAKE_FRAME_LEN)
    listener._wake = _FakeWake(frame_length=_REAL_WAKE_FRAME_LEN, triggers_on_frame=wake_frame.tobytes())
    listener._queue.put(wake_frame)

    listener._wait_for_wake(_REAL_WAKE_FRAME_LEN)

    assert calls == []


def test_wait_for_wake_barge_in_streak_resets_on_silence():
    calls = []
    listener = _make_barge_in_listener(lambda: True, lambda: calls.append(1))
    # speech, silence (resets the streak), speech -- never two in a row.
    listener._queue.put(_speech_frame(_REAL_WAKE_FRAME_LEN))
    listener._queue.put(_silence_frame(_REAL_WAKE_FRAME_LEN))
    listener._queue.put(_speech_frame(_REAL_WAKE_FRAME_LEN))
    wake_frame = np.full(_REAL_WAKE_FRAME_LEN, 2, dtype="int16")  # distinct from speech(1)/silence(0)
    listener._wake = _FakeWake(frame_length=_REAL_WAKE_FRAME_LEN, triggers_on_frame=wake_frame.tobytes())
    listener._queue.put(wake_frame)

    listener._wait_for_wake(_REAL_WAKE_FRAME_LEN)

    assert calls == []  # streak never reached 2 in a row


def test_wait_for_wake_prefers_actual_wake_word_over_barge_in():
    calls = []
    speech = _speech_frame(_REAL_WAKE_FRAME_LEN)
    listener = _make_barge_in_listener(lambda: True, lambda: calls.append(1))
    listener._wake = _FakeWake(frame_length=_REAL_WAKE_FRAME_LEN, triggers_on_frame=speech.tobytes())
    listener._queue.put(speech)  # matches the wake word AND looks like speech

    listener._wait_for_wake(_REAL_WAKE_FRAME_LEN)

    assert calls == []  # wake-word check runs first and returns immediately


def test_wait_for_speech_barge_in_stops_tts_when_speaking():
    calls = []
    listener = _make_barge_in_listener(lambda: True, lambda: calls.append(1))
    listener._queue.put(_speech_frame())

    found = listener._wait_for_speech(timeout_seconds=1.0)

    assert found is True
    assert calls == [1]


def test_wait_for_speech_no_barge_in_when_tts_not_speaking():
    calls = []
    listener = _make_barge_in_listener(lambda: False, lambda: calls.append(1))
    listener._queue.put(_speech_frame())

    found = listener._wait_for_speech(timeout_seconds=1.0)

    assert found is True
    assert calls == []


def test_listen_records_via_barge_in_without_the_wake_word(monkeypatch):
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: _NullStream())

    speaking_calls = []
    barge_in_calls = []

    def is_speaking():
        return len(barge_in_calls) == 0  # "speaking" only until barge-in stops it, like real TtsWorker

    def on_barge_in():
        barge_in_calls.append(1)

    wake = _FakeWake(frame_length=_REAL_WAKE_FRAME_LEN)  # never actually triggers
    listener = ContinuousListener(wake, silence_ms=30, is_speaking=is_speaking, on_barge_in=on_barge_in)
    listener._vad.is_speech = _content_based_is_speech

    speech = _speech_frame(_REAL_WAKE_FRAME_LEN)
    for _ in range(2):  # trips the barge-in streak inside _wait_for_wake
        listener._queue.put(speech)
    # _record_until_silence() re-uses whatever's left in _pending/queue at
    # its own (smaller) frame size -- feed enough to form a real command.
    listener._queue.put(_speech_frame())
    listener._queue.put(_silence_frame())

    gen = listener.listen()
    utterance = next(gen)
    gen.close()

    assert barge_in_calls == [1]
    assert len(utterance) > 0


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


def test_followup_answer_window_starts_when_ash_stops_talking():
    # Ash talks for 0.3s; the answer window is 0.2s. Counting from when Ash
    # *started* asking, it would have closed before you could answer.
    talking_until = time.monotonic() + 0.3
    listener = ContinuousListener(_FakeWake(), silence_ms=30, is_talking=lambda: time.monotonic() < talking_until)
    listener._vad.is_speech = _content_based_is_speech

    def answer_after_ash_finishes():
        time.sleep(0.4)  # 0.1s after Ash stops: inside the window
        listener._queue.put(_speech_frame())
        listener._queue.put(_silence_frame())

    import threading
    threading.Thread(target=answer_after_ash_finishes, daemon=True).start()

    assert listener.listen_for_followup(timeout_seconds=0.2) is not None


def test_followup_still_times_out_after_ash_stops_talking():
    started = time.monotonic()
    talking_until = started + 0.1
    listener = ContinuousListener(_FakeWake(), is_talking=lambda: time.monotonic() < talking_until)

    assert listener.listen_for_followup(timeout_seconds=0.2) is None
    # 0.1s of talking + the full 0.2s window, less at most one poll interval
    # (the window can start up to one poll before Ash actually stops).
    assert time.monotonic() - started >= 0.3 - recorder_module._TALKING_POLL_SECONDS


def test_open_stream_drops_unconsumed_audio_when_it_closes(monkeypatch):
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: _NullStream())
    listener = _make_listener()

    with listener.open_stream():
        listener._queue.put(_speech_frame())  # e.g. you kept talking after the last startup answer

    assert listener._queue.empty()
    assert len(listener._pending) == 0


# --- microphone switch ------------------------------------------------------------------

def test_switching_the_mic_off_stops_waiting_for_the_wake_word():
    listener = _make_listener()
    listener.set_mic_enabled(False)
    assert listener._wait_for_wake(_VAD_FRAME_SAMPLES) is False
    assert listener.mic_enabled is False


def test_mic_off_closes_the_stream_until_switched_back_on(monkeypatch):
    import threading

    opened = []

    class CountingStream(_NullStream):
        def __enter__(self):
            opened.append("open")
            return self

        def __exit__(self, *args):
            opened.append("close")
            return False

    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: CountingStream())
    speech = _speech_frame()
    listener = ContinuousListener(_FakeWake(triggers_on_frame=speech.tobytes()), silence_ms=30)
    listener._vad.is_speech = _content_based_is_speech
    states = []

    def on_state(state):
        states.append(state)
        if state == "mic_off":
            # While it's off, the stream is closed; then you switch it back
            # on and say the wake word and a command.
            assert opened == ["open", "close"]
            for frame in (speech, speech, _silence_frame()):
                listener._queue.put(frame)
            threading.Timer(0.05, listener.set_mic_enabled, args=(True,)).start()

    gen = listener.listen(on_state_change=on_state)
    # Switched off while it's waiting for the wake word (stream open).
    threading.Timer(0.05, listener.set_mic_enabled, args=(False,)).start()
    utterance = next(gen)
    gen.close()

    assert states[:2] == ["mic_off", "idle"]
    assert opened[:3] == ["open", "close", "open"]
    assert len(utterance) == 2 * _VAD_FRAME_SAMPLES
