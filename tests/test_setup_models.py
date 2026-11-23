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


# --- Piper voices ----------------------------------------------------------------------

def test_piper_voice_urls_follow_the_voice_library_layout():
    assert setup_models.piper_voice_urls("en_US-ljspeech-medium") == [
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx.json",
    ]


class _Download:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body


def test_a_voice_downloads_through_the_network_gate(monkeypatch):
    requested = []

    def fake_get(url, *, feature, **kwargs):
        requested.append((url.rsplit("/", 1)[-1], feature, kwargs.get("stream")))
        return _Download(b"model" if url.endswith(".onnx") else b"{}")
    monkeypatch.setattr(setup_models.egress, "get", fake_get)

    setup_models.download_piper_voice("en_GB-alba-medium")

    path = setup_models.piper_voice_path("en_GB-alba-medium")
    assert path.read_bytes() == b"model" and path.with_suffix(".onnx.json").read_bytes() == b"{}"
    assert not list(path.parent.glob("*.part"))
    assert requested == [("en_GB-alba-medium.onnx", "model_download", True),
                         ("en_GB-alba-medium.onnx.json", "model_download", True)]
    assert not setup_models.piper_voice_missing("en_GB-alba-medium")


def test_offline_mode_blocks_a_voice_download():
    consent.set_offline_mode(True)
    with pytest.raises(OfflineModeError):
        setup_models.download_piper_voice("en_US-ljspeech-medium")
    assert setup_models.piper_voice_missing("en_US-ljspeech-medium")


def test_the_voice_is_only_offered_when_piper_is_in_use_and_installed(monkeypatch, nothing_downloaded):
    monkeypatch.setattr(setup_models, "piper_installed", lambda: True)
    assert any("en_US-ljspeech-medium voice" in m
               for m in setup_models.missing_downloads("hey_jarvis", piper_voice="en_US-ljspeech-medium"))
    assert not any("voice (" in m for m in setup_models.missing_downloads("hey_jarvis"))
    monkeypatch.setattr(setup_models, "piper_installed", lambda: False)
    assert not any("voice (" in m
                   for m in setup_models.missing_downloads("hey_jarvis", piper_voice="en_US-ljspeech-medium"))


def test_three_downloads_read_naturally():
    question = setup_models.download_question(["a", "b", "c"])
    assert "download a, b and c, once" in question
