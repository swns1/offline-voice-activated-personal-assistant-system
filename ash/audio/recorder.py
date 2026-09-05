"""Mic input. `record_fixed` is the Phase 2 fixed-duration recorder,
kept for the standalone STT smoke test. `ContinuousListener` is the
real Phase 5+ pipeline: one continuous sounddevice.InputStream (not
repeatedly opened/closed, per the plan) multiplexed between wake-word
detection and VAD-gated command recording.
"""
import queue
import time

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
    cycle, until the caller stops iterating. listen_for_followup() records
    one more utterance without requiring the wake word again, for a
    clarifying-question answer -- callable in between two listen() yields,
    since the InputStream stays open and its callback keeps queuing audio
    while the generator is suspended at yield."""

    def __init__(self, wake_detector: WakeWordDetector, input_device: int | None = None,
                 silence_ms: int = 900, max_record_seconds: float = 8.0,
                 vad_aggressiveness: int = 2):
        self._wake = wake_detector
        self._input_device = input_device
        self._silence_frames_needed = max(1, silence_ms // _VAD_FRAME_MS)
        self._max_record_samples = int(max_record_seconds * SAMPLE_RATE)
        self._vad = webrtcvad.Vad(vad_aggressiveness)
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()
        # Audio pulled from the queue but not yet consumed by whichever
        # phase (wake-word / silence-cutoff / follow-up-timeout) is
        # running. Shared instance state, not a local variable, so
        # listen_for_followup() can pick up where listen() left off.
        self._pending = np.zeros(0, dtype="int16")

    def _callback(self, indata, frames, time_info, status):
        self._queue.put(indata[:, 0].copy())

    def listen(self, on_state_change=None):
        wake_frame_len = self._wake.frame_length

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=wake_frame_len, device=self._input_device, callback=self._callback,
        ):
            while True:
                self._wait_for_wake(wake_frame_len)
                if on_state_change:
                    on_state_change("listening")
                utterance = self._record_until_silence()
                if on_state_change:
                    on_state_change("idle")
                yield utterance

    def listen_for_followup(self, timeout_seconds: float = 6.0, on_state_change=None) -> np.ndarray | None:
        """Records one VAD-gated utterance without waiting for the wake
        word. Returns None if the user hasn't started speaking within
        timeout_seconds -- once speech starts, the normal (unbounded,
        silence-cutoff-governed) recording behavior takes over."""
        if not self._wait_for_speech(timeout_seconds):
            return None
        if on_state_change:
            on_state_change("listening")
        utterance = self._record_until_silence()
        if on_state_change:
            on_state_change("idle")
        return utterance

    def _wait_for_wake(self, wake_frame_len: int) -> None:
        while True:
            self._pending = np.concatenate([self._pending, self._queue.get()])
            while len(self._pending) >= wake_frame_len:
                frame, self._pending = self._pending[:wake_frame_len], self._pending[wake_frame_len:]
                if self._wake.process(frame):
                    return

    def _wait_for_speech(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while True:
            while len(self._pending) < _VAD_FRAME_SAMPLES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                try:
                    chunk = self._queue.get(timeout=remaining)
                except queue.Empty:
                    return False
                self._pending = np.concatenate([self._pending, chunk])

            frame = self._pending[:_VAD_FRAME_SAMPLES]
            if self._vad.is_speech(frame.tobytes(), SAMPLE_RATE):
                return True
            # Silence -- discard this frame (not part of the answer) and
            # keep waiting on the same deadline.
            self._pending = self._pending[_VAD_FRAME_SAMPLES:]

    def _record_until_silence(self) -> np.ndarray:
        chunks: list[np.ndarray] = []
        total_samples = 0
        silence_run = 0

        while True:
            while len(self._pending) < _VAD_FRAME_SAMPLES:
                self._pending = np.concatenate([self._pending, self._queue.get()])
            frame, self._pending = self._pending[:_VAD_FRAME_SAMPLES], self._pending[_VAD_FRAME_SAMPLES:]

            chunks.append(frame)
            total_samples += len(frame)

            is_speech = self._vad.is_speech(frame.tobytes(), SAMPLE_RATE)
            silence_run = 0 if is_speech else silence_run + 1

            if silence_run >= self._silence_frames_needed or total_samples >= self._max_record_samples:
                break

        utterance_int16 = np.concatenate(chunks)
        utterance_float32 = utterance_int16.astype(np.float32) / 32768.0
        return utterance_float32
