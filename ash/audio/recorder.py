"""Mic input. `record_fixed` is the Phase 2 fixed-duration recorder,
kept for the standalone STT smoke test. `ContinuousListener` is the
real Phase 5+ pipeline: one continuous sounddevice.InputStream (not
repeatedly opened/closed, per the plan) multiplexed between wake-word
detection and VAD-gated command recording.
"""
import queue

import numpy as np
import sounddevice as sd
import webrtcvad

from ash.audio.stt import SAMPLE_RATE
from ash.audio.wake_word import WakeWordDetector

_VAD_FRAME_MS = 30
_VAD_FRAME_SAMPLES = SAMPLE_RATE * _VAD_FRAME_MS // 1000  # 480 samples at 16kHz


def record_fixed(seconds: float = 4.0) -> np.ndarray:
    frames = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return frames.reshape(-1)


class ContinuousListener:
    """Owns the mic stream. listen() is a blocking generator yielding one
    float32 mono utterance (at SAMPLE_RATE) per wake -> record -> silence
    cycle, until the caller stops iterating."""

    def __init__(self, wake_detector: WakeWordDetector, input_device: int | None = None,
                 silence_ms: int = 900, max_record_seconds: float = 8.0,
                 vad_aggressiveness: int = 2):
        self._wake = wake_detector
        self._input_device = input_device
        self._silence_frames_needed = max(1, silence_ms // _VAD_FRAME_MS)
        self._max_record_samples = int(max_record_seconds * SAMPLE_RATE)
        self._vad = webrtcvad.Vad(vad_aggressiveness)
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()

    def _callback(self, indata, frames, time_info, status):
        self._queue.put(indata[:, 0].copy())

    def listen(self, on_state_change=None):
        wake_frame_len = self._wake.frame_length
        pending = np.zeros(0, dtype="int16")

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=wake_frame_len, device=self._input_device, callback=self._callback,
        ):
            while True:
                pending = self._wait_for_wake(pending, wake_frame_len)
                if on_state_change:
                    on_state_change("listening")
                utterance, pending = self._record_until_silence(pending)
                if on_state_change:
                    on_state_change("idle")
                yield utterance

    def _wait_for_wake(self, pending: np.ndarray, wake_frame_len: int) -> np.ndarray:
        while True:
            pending = np.concatenate([pending, self._queue.get()])
            while len(pending) >= wake_frame_len:
                frame, pending = pending[:wake_frame_len], pending[wake_frame_len:]
                if self._wake.process(frame):
                    return pending

    def _record_until_silence(self, pending: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        chunks: list[np.ndarray] = []
        total_samples = 0
        silence_run = 0

        while True:
            while len(pending) < _VAD_FRAME_SAMPLES:
                pending = np.concatenate([pending, self._queue.get()])
            frame, pending = pending[:_VAD_FRAME_SAMPLES], pending[_VAD_FRAME_SAMPLES:]

            chunks.append(frame)
            total_samples += len(frame)

            is_speech = self._vad.is_speech(frame.tobytes(), SAMPLE_RATE)
            silence_run = 0 if is_speech else silence_run + 1

            if silence_run >= self._silence_frames_needed or total_samples >= self._max_record_samples:
                break

        utterance_int16 = np.concatenate(chunks)
        utterance_float32 = utterance_int16.astype(np.float32) / 32768.0
        return utterance_float32, pending
