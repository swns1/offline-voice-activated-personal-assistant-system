import numpy as np

from ash.audio.wake_word import WakeWordDetector


def test_silence_does_not_trigger():
    detector = WakeWordDetector(keyword="hey_jarvis")
    silent_frame = np.zeros(detector.frame_length, dtype="int16")

    # Feed several frames -- openWakeWord buffers internally, so a single
    # frame isn't representative of steady-state behavior.
    triggered = any(detector.process(silent_frame) for _ in range(10))

    assert triggered is False
    detector.delete()


def test_frame_length_matches_recommended_chunk_size():
    detector = WakeWordDetector(keyword="hey_jarvis")
    assert detector.frame_length == 1280  # 80ms @ 16kHz
    assert detector.sample_rate == 16_000
    detector.delete()
