"""Speech-to-text via faster-whisper.

The model is loaded once and kept resident — reloading per call would
dominate latency for what should feel like an instant response.
"""
import numpy as np
from faster_whisper import WhisperModel

SAMPLE_RATE = 16_000


class SpeechToText:
    def __init__(self, model_size: str = "small", device: str = "cpu",
                 compute_type: str = "int8"):
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray, initial_prompt: str | None = None) -> str:
        """audio: mono float32 PCM at SAMPLE_RATE."""
        segments, _info = self._model.transcribe(
            audio, language="en", initial_prompt=initial_prompt
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
