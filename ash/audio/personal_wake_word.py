"""Your own wake word, trained on your voice (scripts/train_wake_word.py).

openWakeWord turns every 80 ms of audio into a 96-number "embedding"
with a model trained on thousands of hours of speech; its wake words are
small classifiers over the last 16 of those (~1.3 s). Yours is the same:
a small neural network over those 16 x 96 numbers, trained with
scikit-learn on your recordings (ash/audio/wake_training.py).

The model is derived from your voice, so it's personal data: stored
encrypted (ash/privacy/secure_store.py) in Ash's data folder, listed in
the data inventory, and erased by "delete all my data" -- after which
Ash goes back to the built-in "hey Jarvis". It's stored as plain numbers
(JSON), never as a pickle, so loading it can't run code.
"""
import logging

import numpy as np

from ash.privacy import secure_store
from ash.utils.paths import PERSONAL_WAKE_WORD_PATH

log = logging.getLogger("ash")

WINDOW_FRAMES = 16
FRAME_LENGTH = 1280  # 80 ms at 16 kHz, as openWakeWord streams
FALLBACK_KEYWORD = "hey_jarvis"
# Embeddings need a little audio before they mean anything, and one
# "Okay Ash" mustn't wake Ash twice.
_WARM_UP_FRAMES = 16
_REFRACTORY_FRAMES = 12  # ~1 s
# Wake only once the score has stayed above the threshold this many
# frames in a row (240 ms). Measured: your phrase stays above it for 8-10
# frames; the false triggers ("okay" on its own) for 1-2.
CONSECUTIVE_FRAMES = 3


def load_model() -> dict | None:
    try:
        model = secure_store.read_json(PERSONAL_WAKE_WORD_PATH, default=None)
    except (OSError, ValueError):
        log.warning("Couldn't read your wake word model", exc_info=True)
        return None
    return model if isinstance(model, dict) and "layers" in model else None


def save_model(model: dict) -> None:
    secure_store.write_json(PERSONAL_WAKE_WORD_PATH, model)


def keyword_of(phrase: str) -> str:
    """"okay ash" -> "okay_ash", the value of wake_word.keyword."""
    return "_".join(phrase.lower().split())


def is_personal(keyword: str) -> bool:
    """A keyword that isn't a built-in openWakeWord model or an .onnx file."""
    import openwakeword

    return not keyword.endswith(".onnx") and keyword not in openwakeword.MODELS


def effective_keyword(keyword: str) -> str:
    """The keyword Ash can actually use: your personal one if its model
    exists (it may have been deleted with the rest of your data), else
    the built-in fallback."""
    if not is_personal(keyword):
        return keyword
    model = load_model()
    if model is not None and keyword_of(model.get("phrase", "")) == keyword:
        return keyword
    log.warning("No trained model for wake word %r; using %r", keyword, FALLBACK_KEYWORD)
    return FALLBACK_KEYWORD


def score(model: dict, windows: np.ndarray) -> np.ndarray:
    """Probability that each (16, 96) embedding window ends with the wake
    word. A small multilayer perceptron: standardise, ReLU hidden
    layers, logistic output -- the same maths as scikit-learn's
    MLPClassifier.predict_proba, from its exported weights."""
    x = windows.reshape(len(windows), -1).astype(np.float32)
    x = (x - np.asarray(model["mean"], dtype=np.float32)) / np.asarray(model["scale"], dtype=np.float32)
    layers = model["layers"]
    for i, layer in enumerate(layers):
        x = x @ np.asarray(layer["weights"], dtype=np.float32) + np.asarray(layer["bias"], dtype=np.float32)
        if i < len(layers) - 1:
            x = np.maximum(x, 0)
    return 1 / (1 + np.exp(-x[:, 0]))


class PersonalWakeWord:
    """Same interface as ash.audio.wake_word.WakeWordDetector."""

    def __init__(self, model: dict, features=None):
        from openwakeword.utils import AudioFeatures

        self._model = model
        self._threshold = float(model["threshold"])
        self._features = features or AudioFeatures(inference_framework="onnx")
        self._consecutive = int(model.get("consecutive", CONSECUTIVE_FRAMES))
        self._frames_seen = 0
        self._quiet_until = 0
        self._run = 0

    @property
    def frame_length(self) -> int:
        return FRAME_LENGTH

    @property
    def sample_rate(self) -> int:
        return 16_000

    def process(self, frame) -> bool:
        """frame: FRAME_LENGTH int16 samples."""
        self._features(frame)
        self._frames_seen += 1
        if self._frames_seen < _WARM_UP_FRAMES or self._frames_seen < self._quiet_until:
            return False
        window = self._features.get_features(WINDOW_FRAMES)
        self._run = self._run + 1 if score(self._model, window)[0] >= self._threshold else 0
        if self._run < self._consecutive:
            return False
        self._run = 0
        self._quiet_until = self._frames_seen + _REFRACTORY_FRAMES
        return True

    def delete(self) -> None:
        pass
