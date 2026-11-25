"""Audio clip helpers shared by the measurement scripts and wake-word
training (ash/audio/wake_training.py): 16 kHz mono WAV files in and out, recording one
spoken command, and making clips with a Windows voice (for checking the
pipeline end to end; a synthetic voice is not a substitute for yours).
"""
import collections
import math
import queue
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
_FRAME = 480  # 30 ms, a frame size webrtcvad accepts


def read_wav(path: Path) -> np.ndarray:
    """Mono float32 at SAMPLE_RATE, whatever the file's own rate."""
    with wave.open(str(path), "rb") as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit audio")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        from scipy.signal import resample_poly

        divisor = math.gcd(rate, SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, rate // divisor).astype(np.float32)
    return audio


def write_wav(path: Path, audio: np.ndarray) -> None:
    samples = audio if audio.dtype == np.int16 else (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())


def record_command(max_seconds: float = 8.0, silence_ms: int = 800, start_timeout: float = 5.0) -> np.ndarray | None:
    """Record from the default microphone: waits for you to start
    speaking (None if you don't within start_timeout), keeps 300 ms from
    just before, and stops after silence_ms of silence -- the same kind
    of cut-off Ash uses."""
    import sounddevice as sd
    import webrtcvad

    vad = webrtcvad.Vad(2)
    frames: queue.Queue[np.ndarray] = queue.Queue()
    before = collections.deque(maxlen=10)
    chunks: list[np.ndarray] = []
    silence = 0
    started_at = time.monotonic()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=_FRAME,
                        callback=lambda data, *_: frames.put(data[:, 0].copy())):
        while True:
            frame = frames.get()
            speech = len(frame) == _FRAME and vad.is_speech(frame.tobytes(), SAMPLE_RATE)
            if not chunks:
                before.append(frame)
                if speech:
                    chunks.extend(before)
                elif time.monotonic() - started_at > start_timeout:
                    return None
                continue
            chunks.append(frame)
            silence = 0 if speech else silence + 1
            if silence * 30 >= silence_ms or len(chunks) * _FRAME >= max_seconds * SAMPLE_RATE:
                break
    return np.concatenate(chunks)


def synthesize(text: str, path: Path, voice_index: int = 0) -> None:
    """Say `text` with a Windows (SAPI) voice into a WAV file."""
    import pyttsx3

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    if voices:
        engine.setProperty("voice", voices[voice_index % len(voices)].id)
    with tempfile.TemporaryDirectory() as folder:
        raw = Path(folder) / "clip.wav"
        engine.save_to_file(text, str(raw))
        engine.runAndWait()
        write_wav(path, read_wav(raw))
    engine.stop()
