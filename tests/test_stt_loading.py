"""Loading the speech-recognition model never goes online once it's on
this PC; the one-time first download is gated and logged
(ash/audio/stt.py)."""
import logging

import pytest

from ash.actions import privacy_controls
from ash.audio import stt
from ash.config import Config
from ash.privacy import consent, egress, network_log
from ash.registry.schema import Registry


class FakeWhisper:
    calls: list[dict] = []
    cached = True

    def __init__(self, size, device, compute_type, local_files_only=False):
        FakeWhisper.calls.append({"local_files_only": local_files_only})
        if local_files_only and not FakeWhisper.cached:
            raise FileNotFoundError("not in the local cache")  # like LocalEntryNotFoundError


@pytest.fixture(autouse=True)
def fake_whisper(monkeypatch):
    FakeWhisper.calls = []
    FakeWhisper.cached = True
    monkeypatch.setattr(stt, "WhisperModel", FakeWhisper)


def test_cached_model_loads_without_going_online():
    stt.SpeechToText()

    assert FakeWhisper.calls == [{"local_files_only": True}]
    assert network_log.entries() == []


def test_first_run_downloads_once_and_logs_it():
    FakeWhisper.cached = False

    stt.SpeechToText()

    assert FakeWhisper.calls == [{"local_files_only": True}, {"local_files_only": False}]
    [entry] = network_log.entries()
    assert entry["domain"] == "huggingface.co"
    assert "nothing about you" in entry["sends"]


def test_first_run_download_is_blocked_in_offline_mode():
    FakeWhisper.cached = False
    consent.set_offline_mode(True)

    with pytest.raises(egress.OfflineModeError):
        stt.SpeechToText()

    assert FakeWhisper.calls == [{"local_files_only": True}]  # never tried to download


class _Tts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_model_downloads_are_not_a_voice_toggle():
    tts = _Tts()
    privacy_controls.handle_disallow("model downloads", Registry(), tts, logging.getLogger("t"), Config())
    assert "only happens once" in tts.said[-1]
