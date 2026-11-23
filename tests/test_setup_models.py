"""First-run model downloads (ash/setup_models.py): asked about, blocked
by offline mode, and logged."""
import pytest

from ash import setup_models
from ash.privacy import consent, network_log
from ash.privacy.egress import OfflineModeError


@pytest.fixture
def nothing_downloaded(monkeypatch):
    monkeypatch.setattr("openwakeword.get_pretrained_model_paths", lambda inference_framework: [])
    import faster_whisper.utils

    def not_cached(size, local_files_only=False):
        raise FileNotFoundError(size)
    monkeypatch.setattr(faster_whisper.utils, "download_model", not_cached)


def test_lists_what_still_has_to_be_downloaded(nothing_downloaded):
    missing = setup_models.missing_downloads("hey_jarvis")
    assert len(missing) == 2
    question = setup_models.download_question(missing)
    assert "wake-word model" in question and "speech-recognition model" in question
    assert "Nothing about you is sent" in question and question.endswith("Download now?")


def test_nothing_to_download_once_both_are_here(monkeypatch, tmp_path):
    model = tmp_path / "hey_jarvis_v0.1.onnx"
    model.write_bytes(b"x")
    monkeypatch.setattr("openwakeword.get_pretrained_model_paths", lambda inference_framework: [str(model)])
    import faster_whisper.utils
    monkeypatch.setattr(faster_whisper.utils, "download_model", lambda size, local_files_only=False: "path")
    assert setup_models.missing_downloads("hey_jarvis") == []


def test_a_custom_wake_word_is_never_downloaded(nothing_downloaded):
    assert setup_models.wake_word_model_missing("my_model.onnx") is False
    assert setup_models.custom_wake_word_missing("my_model.onnx") is True


def test_the_wake_word_download_is_logged(monkeypatch):
    downloaded = []
    monkeypatch.setattr("openwakeword.utils.download_models", lambda names: downloaded.append(names))

    setup_models.download_wake_word_model("hey_jarvis")

    assert downloaded == [["hey_jarvis"]]
    [entry] = network_log.entries()
    assert entry["feature"] == "model_download" and entry["domain"] == "github.com"
    assert "nothing about you" in entry["sends"]


def test_offline_mode_blocks_the_download(monkeypatch):
    monkeypatch.setattr("openwakeword.utils.download_models", lambda names: pytest.fail("downloaded"))
    consent.set_offline_mode(True)
    with pytest.raises(OfflineModeError):
        setup_models.download_wake_word_model("hey_jarvis")
    assert network_log.entries() == []
