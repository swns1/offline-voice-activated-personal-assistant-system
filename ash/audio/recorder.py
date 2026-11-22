"""Mic input. `record_fixed` is a simple fixed-duration recorder, used
by scripts/enroll_voice.py to capture a voiceprint sample. `ContinuousListener` is the
real Phase 5+ pipeline: one continuous sounddevice.InputStream (not
repeatedly opened/closed, per the plan) multiplexed between wake-word
detection and VAD-gated command recording.

Barge-in (talking over an in-progress TTS response, no wake word
needed): _wait_for_wake()/_wait_for_speech() also watch for sustained
speech while TtsWorker.is_speaking() is true, via the SAME
single-threaded frame-consumption loop that's already processing every
incoming frame -- no second thread or queue needed, so no new
cross-thread access to self._pending (the one piece of state that
would be genuinely unsafe to touch from two threads at once). This
only detects "the user is making sound", not "and it isn't an echo of
Ash's own voice" -- there's no acoustic echo cancellation here, so on
hardware where the mic picks up the speakers (no headset, close-range
laptop mic+speakers), Ash's own voice can occasionally trigger a false
barge-in. config.audio.barge_in_enabled is the escape hatch if that
happens on your setup.
"""
import queue
import time
from contextlib import contextmanager
from typing import Callable

import numpy as np
import sounddevice as sd
import webrtcvad

from ash.audio.stt import SAMPLE_RATE
from ash.audio.wake_word import WakeWordDetector

_VAD_FRAME_MS = 30
_VAD_FRAME_SAMPLES = SAMPLE_RATE * _VAD_FRAME_MS // 1000  # 480 samples at 16kHz

# Sub-framing for barge-in checks specifically: wake frames are 1280
# samples (80ms), which isn't a whole multiple of the 480-sample (30ms)
# VAD frame used elsewhere -- 320 samples (20ms) is a valid webrtcvad
# frame size AND divides 1280 evenly (exactly 4 sub-frames), so barge-in
# detection uses its own frame size rather than disturbing the existing
# silence-cutoff VAD framing.
_BARGE_IN_SUBFRAME_SAMPLES = SAMPLE_RATE * 20 // 1000  # 320 samples at 16kHz
# Consecutive wake-frame-level (80ms) detections required before
# treating it as real barge-in rather than a one-off noise blip --
# 2 frames = 160ms of continuous detected speech.
_BARGE_IN_FRAMES_NEEDED = 2
# How often a quiet follow-up wait re-checks whether Ash is still talking.
_TALKING_POLL_SECONDS = 0.05


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
                 vad_aggressiveness: int = 2,
                 is_speaking: Callable[[], bool] | None = None,
                 on_barge_in: Callable[[], None] | None = None,
                 is_talking: Callable[[], bool] | None = None):
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
        # Barge-in hooks -- no-ops by default, so ContinuousListener works
        # unchanged for callers (and tests) that don't wire them up.
        self._is_speaking = is_speaking or (lambda: False)
        self._on_barge_in = on_barge_in or (lambda: None)
        # Whether Ash is talking right now, for timing only -- unlike
        # is_speaking above, which is None when barge-in is switched off.
        # A follow-up answer's time limit only starts once Ash has
        # finished asking (see _wait_for_speech).
        self._is_talking = is_talking or (lambda: False)

    def _callback(self, indata, frames, time_info, status):
        self._queue.put(indata[:, 0].copy())

    @contextmanager
    def open_stream(self):
        """Keep the microphone open for the duration of the block. listen()
        does this itself; use it directly to take follow-up answers
        outside listen() (e.g. ash/main.py's startup privacy questions).
        Any audio left unconsumed when the block ends is dropped, so it
        can't leak into the next stream (e.g. be mistaken for the wake
        word right after the startup questions)."""
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=self._wake.frame_length, device=self._input_device, callback=self._callback,
            ):
                yield
        finally:
            self._queue = queue.Queue()
            self._pending = np.zeros(0, dtype="int16")

    def listen(self, on_state_change=None):
        wake_frame_len = self._wake.frame_length

        with self.open_stream():
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
        barge_in_streak = 0
        while True:
            self._pending = np.concatenate([self._pending, self._queue.get()])
            while len(self._pending) >= wake_frame_len:
                frame, self._pending = self._pending[:wake_frame_len], self._pending[wake_frame_len:]
                if self._wake.process(frame):
                    return

                if self._is_speaking() and self._frame_has_speech(frame):
                    barge_in_streak += 1
                    if barge_in_streak >= _BARGE_IN_FRAMES_NEEDED:
                        self._on_barge_in()
                        return
                else:
                    barge_in_streak = 0

    def _frame_has_speech(self, frame: np.ndarray) -> bool:
        """frame: wake_frame_len (1280) int16 samples -- webrtcvad needs
        10/20/30ms frames, not 80ms, so this checks it in 20ms
        sub-frames (320 samples, dividing 1280 evenly) rather than
        reusing the 30ms framing _record_until_silence()/_wait_for_speech()
        use for the (differently-sized) command-recording buffer."""
        for start in range(0, len(frame) - _BARGE_IN_SUBFRAME_SAMPLES + 1, _BARGE_IN_SUBFRAME_SAMPLES):
            sub_frame = frame[start:start + _BARGE_IN_SUBFRAME_SAMPLES]
            if self._vad.is_speech(sub_frame.tobytes(), SAMPLE_RATE):
                return True
        return False

    def _wait_for_speech(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while True:
            while len(self._pending) < _VAD_FRAME_SAMPLES:
                if self._is_talking():
                    # Still asking the question: the answer window starts
                    # when Ash stops talking, not when it starts. (A 9-second
                    # question would otherwise use up a 6-second window
                    # before you could politely answer.)
                    deadline = time.monotonic() + timeout_seconds
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                try:
                    chunk = self._queue.get(timeout=min(remaining, _TALKING_POLL_SECONDS))
                except queue.Empty:
                    continue  # re-check the deadline and whether Ash is still talking
                self._pending = np.concatenate([self._pending, chunk])

            frame = self._pending[:_VAD_FRAME_SAMPLES]
            if self._vad.is_speech(frame.tobytes(), SAMPLE_RATE):
                if self._is_speaking():
                    self._on_barge_in()
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
