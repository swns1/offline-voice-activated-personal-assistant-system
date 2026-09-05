"""openWakeWord wrapper: fully open-source, no account/API key required
(unlike Picovoice Porcupine). Feed 16kHz mono int16 frames, get True
back once any configured model's score crosses `threshold`.

Model files aren't bundled in the pip package -- they're fetched once
from the openWakeWord GitHub releases via `openwakeword.utils.download_models`
(see scripts/download_wake_word_models.py). No custom-phrase compiler
exists like Porcupine's Console: starting on a pretrained word (e.g.
"hey_jarvis") is the practical v1 choice; a real "Hey Ash" phrase would
need openWakeWord's local training pipeline.

Windows note: tflite_runtime has no Windows wheels, so this always uses
the "onnx" inference framework.
"""
from openwakeword.model import Model

FRAME_LENGTH = 1280  # 80ms @ 16kHz -- openWakeWord's recommended chunk size
SAMPLE_RATE = 16_000


class WakeWordDetector:
    def __init__(self, keyword: str = "hey_jarvis", threshold: float = 0.5):
        self._model = Model(wakeword_models=[keyword], inference_framework="onnx")
        self._threshold = threshold

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    @property
    def frame_length(self) -> int:
        return FRAME_LENGTH

    def process(self, frame) -> bool:
        """frame: exactly `frame_length` int16 samples."""
        scores = self._model.predict(frame)
        return any(score >= self._threshold for score in scores.values())

    def delete(self) -> None:
        pass  # no explicit resource cleanup needed
