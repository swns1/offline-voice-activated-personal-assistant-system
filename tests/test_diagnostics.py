import json
import logging

import requests

from ash.actions import diagnostics
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeResponse:
    def raise_for_status(self):
        pass


def _no_devices_issue(monkeypatch, has_input=True):
    devices = [{"max_input_channels": 2 if has_input else 0}]
    monkeypatch.setattr(diagnostics.sd, "query_devices", lambda: devices)


def test_microphone_check_finds_input_device(monkeypatch):
    _no_devices_issue(monkeypatch, has_input=True)
    name, ok, detail = diagnostics._check_microphone()
    assert ok is True
    assert detail == "found"


def test_microphone_check_no_input_device(monkeypatch):
    _no_devices_issue(monkeypatch, has_input=False)
    name, ok, detail = diagnostics._check_microphone()
    assert ok is False


def test_microphone_check_query_failure(monkeypatch):
    def boom():
        raise RuntimeError("no audio subsystem")
    monkeypatch.setattr(diagnostics.sd, "query_devices", boom)
    name, ok, detail = diagnostics._check_microphone()
    assert ok is False


def test_ollama_check_disabled_reports_ok():
    config = Config()
    config.ollama.enabled = False
    name, ok, detail = diagnostics._check_ollama(config)
    assert ok is True
    assert detail == "disabled"


def test_ollama_check_auto_not_running_is_not_a_failure():
    # Default "auto" + conftest's stubbed probe (Ollama not running):
    # optional, so it reports OK with an explanation rather than FAIL.
    name, ok, detail = diagnostics._check_ollama(Config())
    assert ok is True
    assert "not running" in detail


def test_ollama_check_auto_running(monkeypatch):
    from ash.utils import ollama
    monkeypatch.setattr(ollama, "_probe", lambda host, model: ollama.READY)
    name, ok, detail = diagnostics._check_ollama(Config())
    assert ok is True
    assert "AI features on" in detail


def test_ollama_check_auto_model_missing_is_a_failure(monkeypatch):
    from ash.utils import ollama
    monkeypatch.setattr(ollama, "_probe", lambda host, model: ollama.MODEL_MISSING)
    name, ok, detail = diagnostics._check_ollama(Config())
    assert ok is False
    assert "llama3.2" in detail


def test_ollama_check_reachable(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout: FakeResponse())
    config = Config()
    config.ollama.enabled = True

    name, ok, detail = diagnostics._check_ollama(config)

    assert ok is True
    assert detail == "reachable"


def test_ollama_check_connection_error(monkeypatch):
    def boom(url, timeout):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", boom)
    config = Config()
    config.ollama.enabled = True

    name, ok, detail = diagnostics._check_ollama(config)

    assert ok is False
    assert detail == "not reachable"


def test_spotify_check_disabled_reports_ok():
    config = Config()
    name, ok, detail = diagnostics._check_spotify(config)
    assert ok is True
    assert detail == "disabled"


def test_spotify_check_no_cache_file(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "SECRETS_DIR", tmp_path)
    config = Config()
    config.spotify.enabled = True

    name, ok, detail = diagnostics._check_spotify(config)

    assert ok is False
    assert detail == "not yet authorized"


def test_spotify_check_valid_cache_file(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "SECRETS_DIR", tmp_path)
    (tmp_path / ".spotify_cache").write_text(json.dumps({"access_token": "abc"}), encoding="utf-8")
    config = Config()
    config.spotify.enabled = True

    name, ok, detail = diagnostics._check_spotify(config)

    assert ok is True
    assert detail == "connected"


def test_spotify_check_malformed_cache_file(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "SECRETS_DIR", tmp_path)
    (tmp_path / ".spotify_cache").write_text("not valid json {{{", encoding="utf-8")
    config = Config()
    config.spotify.enabled = True

    name, ok, detail = diagnostics._check_spotify(config)

    assert ok is False
    assert detail == "cached token unreadable"


def test_handle_diagnostics_speaks_a_summary(monkeypatch):
    monkeypatch.setattr(diagnostics, "run_diagnostics", lambda config: [
        ("Microphone", True, "found"),
        ("Ollama", True, "disabled"),
        ("Spotify", True, "disabled"),
    ])
    tts = FakeTts()

    result = diagnostics.handle_diagnostics("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Microphone: found. Ollama: disabled. Spotify: disabled."]
