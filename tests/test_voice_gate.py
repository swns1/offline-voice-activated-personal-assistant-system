import logging

import numpy as np
import pytest

from ash.config import Config
from ash.security import voice_gate

log = logging.getLogger("test")


@pytest.fixture(autouse=True)
def _isolated_voiceprint_store(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_gate, "VOICEPRINT_PATH", tmp_path / "voiceprint.json")


def _tone(freq_hz: float, seconds: float = 2.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(16000 * seconds), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _noise(seconds: float = 2.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (0.3 * rng.standard_normal(int(16000 * seconds))).astype(np.float32)


def test_extract_features_none_for_very_short_audio():
    assert voice_gate._extract_features(np.zeros(10, dtype=np.float32)) is None


def test_extract_features_shape_for_normal_audio():
    features = voice_gate._extract_features(_tone(200))
    assert features is not None
    assert features.shape == (voice_gate._NUM_MFCC,)


def test_is_enrolled_false_before_enrollment():
    assert voice_gate.is_enrolled() is False


def test_enroll_then_is_enrolled_true():
    assert voice_gate.enroll(_tone(200)) is True
    assert voice_gate.is_enrolled() is True


def test_enroll_too_short_audio_returns_false_and_writes_nothing():
    assert voice_gate.enroll(np.zeros(10, dtype=np.float32)) is False
    assert voice_gate.is_enrolled() is False


def test_verify_matches_the_same_voice(monkeypatch):
    voice_gate.enroll(_tone(200))
    config = Config()

    # A second, independently-generated sample of the "same speaker"
    # (same tone) should match comfortably above the default threshold.
    assert voice_gate.verify(_tone(200, seconds=1.5), config, log) is True


def test_verify_rejects_a_clearly_different_voice():
    voice_gate.enroll(_tone(200))
    config = Config()

    assert voice_gate.verify(_noise(), config, log) is False


def test_verify_with_nothing_enrolled_fails_open():
    config = Config()

    assert voice_gate.verify(_tone(200), config, log) is True


def test_verify_with_corrupt_voiceprint_file_fails_open():
    voice_gate.VOICEPRINT_PATH.write_text("not valid json {{{", encoding="utf-8")
    config = Config()

    assert voice_gate.verify(_tone(200), config, log) is True


def test_verify_with_too_short_confirmation_audio_fails_open():
    voice_gate.enroll(_tone(200))
    config = Config()

    assert voice_gate.verify(np.zeros(10, dtype=np.float32), config, log) is True


def test_verify_respects_configured_threshold():
    voice_gate.enroll(_tone(200))
    # A near-identical tone should score very high similarity -- an
    # unreasonably strict threshold should still reject it.
    config = Config()
    config.security.voice_match_threshold = 0.999999

    assert voice_gate.verify(_tone(201, seconds=1.5), config, log) is False
