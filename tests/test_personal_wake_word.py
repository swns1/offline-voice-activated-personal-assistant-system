"""Your own wake word (ash/audio/personal_wake_word.py, wake_training.py),
with openWakeWord's audio features stood in for: no recordings needed."""
import random

import numpy as np
import pytest

from ash.audio import personal_wake_word as pww
from ash.audio import wake_training as wt
from ash.privacy import secure_store


def _model(threshold=0.9, consecutive=3):
    """A one-layer model whose score is high when the window's mean is high."""
    return {
        "phrase": "okay ash", "threshold": threshold, "consecutive": consecutive,
        "mean": [0.0] * (16 * 96), "scale": [1.0] * (16 * 96),
        "layers": [{"weights": [[0.01]] * (16 * 96), "bias": [0.0]}],
    }


class FakeFeatures:
    """Stands in for openWakeWord's AudioFeatures: each frame's 'loudness'
    becomes the next window's values."""

    def __init__(self):
        self.level = 0.0

    def __call__(self, frame):
        self.level = float(frame[0])

    def get_features(self, frames):
        return np.full((1, frames, 96), self.level, dtype=np.float32)


def _detector(model):
    return pww.PersonalWakeWord(model, features=FakeFeatures())


def _frames(levels):
    return [np.full(pww.FRAME_LENGTH, level, dtype=np.int16) for level in levels]


def test_scoring_is_a_logistic_network():
    windows = np.stack([np.full((16, 96), v, dtype=np.float32) for v in (-5, 0, 5)])
    scores = pww.score(_model(), windows)
    assert scores[0] < 0.01 and abs(scores[1] - 0.5) < 1e-6 and scores[2] > 0.99


def test_wakes_only_after_three_frames_in_a_row_and_not_during_warm_up():
    detector = _detector(_model())
    quiet, loud = -5, 5
    results = [detector.process(f) for f in _frames([loud] * 20)]
    assert results.index(True) == pww._WARM_UP_FRAMES - 1 + 2  # third loud frame after warm-up

    detector = _detector(_model())
    for f in _frames([quiet] * 20):
        detector.process(f)
    spikes = [loud, loud, quiet] * 5  # two frames at a time: "okay" alone
    assert not any(detector.process(f) for f in _frames(spikes))


def test_one_phrase_wakes_it_once():
    detector = _detector(_model())
    for f in _frames([-5] * 20):
        detector.process(f)
    assert sum(detector.process(f) for f in _frames([5] * 10)) == 1


def test_the_model_is_stored_encrypted_and_found_by_its_keyword():
    assert pww.effective_keyword("okay_ash") == pww.FALLBACK_KEYWORD  # nothing trained yet
    pww.save_model(_model())
    assert secure_store.is_encrypted(pww.PERSONAL_WAKE_WORD_PATH)
    assert pww.load_model()["phrase"] == "okay ash"
    assert pww.effective_keyword("okay_ash") == "okay_ash"
    assert pww.effective_keyword("hey_jarvis") == "hey_jarvis"  # built-ins pass straight through
    assert pww.keyword_of("Okay  Ash") == "okay_ash"


def test_ash_picks_the_personal_detector(monkeypatch):
    from ash.audio import wake_word

    pww.save_model(_model())
    monkeypatch.setattr(pww, "PersonalWakeWord", lambda model: ("personal", model["phrase"]))
    assert wake_word.make_wake_detector("okay_ash") == ("personal", "okay ash")


def test_delete_all_my_data_removes_it_and_ash_falls_back_to_hey_jarvis():
    import logging

    from ash.actions.privacy_rights import delete_everything
    from ash.privacy import inventory

    pww.save_model(_model())
    assert inventory.is_stored(inventory.by_key("wake_word"))
    delete_everything(logging.getLogger("test"))
    assert not pww.PERSONAL_WAKE_WORD_PATH.exists()
    assert pww.effective_keyword("okay_ash") == pww.FALLBACK_KEYWORD


def test_it_is_listed_but_never_exported():
    from ash.actions.privacy_rights import build_export
    from ash.privacy import inventory

    pww.save_model(_model())
    item = inventory.by_key("wake_word")
    assert item.sensitive and item.encrypted and not item.exportable
    assert "layers" not in str(build_export())


# --- training -------------------------------------------------------------------------

def test_speech_bounds_find_the_loud_part():
    audio = np.zeros(16000, dtype=np.float32)
    audio[4000:9000] = 0.5 * np.sin(np.arange(5000) / 3)
    start, end = wt.speech_bounds(audio)
    assert abs(start - 4000) <= 320 and abs(end - 9000) <= 320


def test_examples_are_labelled_by_when_the_phrase_ends(monkeypatch):
    """Positive in the half second after the phrase; negative before it and
    once it's out of view; the first half alone is never positive."""
    seen = {}

    def fake_stream(audio):
        seen["seconds"] = len(audio) / 16000
        return np.zeros((len(audio) // pww.FRAME_LENGTH - wt.WARM_UP_FRAMES + 1, 16, 96), dtype=np.float32)
    monkeypatch.setattr(wt, "stream_features", fake_stream)
    clip = np.zeros(24000, dtype=np.float32)
    clip[4000:16000] = 0.5 * np.sin(np.arange(12000) / 3)

    positives, negatives = wt.phrase_examples(clip, random.Random(0), None)
    assert 5 <= len(positives) <= 8          # ~0.5 s of 80 ms steps
    assert len(negatives) > len(positives)

    positives, negatives = wt.phrase_examples(clip, random.Random(0), None, first_half_only=True)
    assert positives == [] and negatives


def test_the_classifier_learns_a_separable_problem():
    rng = np.random.default_rng(0)
    positives = rng.normal(1.0, 0.3, (60, 16, 96)).astype(np.float32)
    negatives = rng.normal(-1.0, 0.3, (300, 16, 96)).astype(np.float32)
    model = wt.train_classifier(positives, negatives)
    assert pww.score(model, positives).mean() > 0.9 and pww.score(model, negatives).mean() < 0.1


def test_training_needs_enough_recordings(tmp_path):
    import json
    (tmp_path / "manifest.json").write_text(json.dumps({"phrase": "okay ash", "clips": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="at least 8"):
        wt.train_and_evaluate(tmp_path, synthetic=False)
