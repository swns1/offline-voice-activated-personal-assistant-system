"""Speech-to-text via faster-whisper.

The model is loaded once and kept resident — reloading per call would
dominate latency for what should feel like an instant response.

Loading never goes online once the model is on this PC. By default
faster-whisper's loader (huggingface_hub) contacts huggingface.co on
every start to check for a newer model version -- a network request
Ash's privacy gate (ash/privacy/egress.py) never saw. So the cached
model is loaded with local_files_only=True, and only the one-time
first download goes online: checked against offline mode and written
to the network log like any other request.
"""
import numpy as np
from faster_whisper import WhisperModel

from ash.privacy import egress

SAMPLE_RATE = 16_000


def load_whisper_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type, local_files_only=True)
    except FileNotFoundError:
        pass  # not downloaded yet (huggingface_hub's LocalEntryNotFoundError)
    egress.check(egress.MODEL_DOWNLOAD.key)  # raises OfflineModeError in offline mode
    egress.record_use(egress.MODEL_DOWNLOAD.key)
    return WhisperModel(model_size, device=device, compute_type=compute_type)


class SpeechToText:
    def __init__(self, model_size: str = "small", device: str = "cpu",
                 compute_type: str = "int8"):
        self._model = load_whisper_model(model_size, device, compute_type)

    def transcribe(self, audio: np.ndarray, initial_prompt: str | None = None) -> str:
        """audio: mono float32 PCM at SAMPLE_RATE."""
        segments, _info = self._model.transcribe(
            audio, language="en", initial_prompt=initial_prompt
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
