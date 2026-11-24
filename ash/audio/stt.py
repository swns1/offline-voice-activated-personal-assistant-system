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
import logging

import numpy as np
from faster_whisper import WhisperModel

from ash.audio import gpu
from ash.audio.vocabulary import hotwords
from ash.privacy import egress

log = logging.getLogger("ash")

SAMPLE_RATE = 16_000


def load_whisper_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type, local_files_only=True)
    except FileNotFoundError:
        pass  # not downloaded yet (huggingface_hub's LocalEntryNotFoundError)
    egress.check(egress.MODEL_DOWNLOAD.key)  # raises OfflineModeError in offline mode
    egress.record_use(egress.MODEL_DOWNLOAD.key)
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _load_on_gpu(model_size: str) -> WhisperModel:
    """Raises if the GPU can't actually run it. A missing NVIDIA library
    only shows up at the first transcription, not when loading, so this
    transcribes half a second of silence to find out now."""
    model = load_whisper_model(model_size, "cuda", gpu.GPU_COMPUTE_TYPE)
    segments, _info = model.transcribe(np.zeros(SAMPLE_RATE // 2, dtype=np.float32), language="en")
    list(segments)
    return model


class SpeechToText:
    def __init__(self, model_size: str = "small", device: str = "auto", command_hints: bool = True):
        """device: "auto" (the NVIDIA GPU if it works, else the CPU),
        "cuda" or "cpu". `self.device` says which is in use."""
        self.model_size = model_size
        self.device = "cpu"
        self._model = None
        if device == "cuda" or (device == "auto" and gpu.cuda_available()):
            try:
                self._model = _load_on_gpu(model_size)
                self.device = "cuda"
            except egress.NetworkBlocked:
                raise
            except Exception:
                log.warning("Speech recognition couldn't use the GPU; using the CPU", exc_info=True)
        if self._model is None:
            self._model = load_whisper_model(model_size, "cpu", gpu.CPU_COMPUTE_TYPE)
        log.info("Speech recognition: Whisper %s on the %s", model_size, "GPU" if self.device == "cuda" else "CPU")
        # Ash's command words, as Whisper hotwords (see ash/audio/vocabulary.py).
        self._hotwords = hotwords() if command_hints else None

    def transcribe(self, audio: np.ndarray, initial_prompt: str | None = None) -> str:
        """audio: mono float32 PCM at SAMPLE_RATE."""
        segments, _info = self._model.transcribe(
            audio, language="en", initial_prompt=initial_prompt, hotwords=self._hotwords,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
