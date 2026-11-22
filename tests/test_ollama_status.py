"""ash.utils.ollama: the single place that decides whether local-AI
features are on. conftest.py stubs _probe to NOT_RUNNING for every test;
tests here override it where they need a running server."""
import pytest
import requests
import yaml

from ash.config import Config
from ash.utils import ollama

# Captured at import, before conftest's autouse fixture stubs it out.
_REAL_PROBE = ollama._probe


def _config(enabled) -> Config:
    config = Config()
    config.ollama.enabled = enabled
    return config


def test_default_setting_is_auto():
    assert Config().ollama.enabled == "auto"


@pytest.mark.parametrize("raw, expected", [("auto", "auto"), ("true", True), ("false", False)])
def test_config_yaml_values_parse(raw, expected):
    data = yaml.safe_load(f"ollama:\n  enabled: {raw}\n")
    assert Config(**data).ollama.enabled == expected


def test_forced_on_and_off_never_probe(monkeypatch):
    def _must_not_probe(host, model):
        raise AssertionError("forced settings must not probe")

    monkeypatch.setattr(ollama, "_probe", _must_not_probe)
    assert ollama.ai_enabled(_config(True)) is True
    assert ollama.ai_enabled(_config(False)) is False


def test_auto_is_off_when_ollama_not_running():
    assert ollama.ai_enabled(Config()) is False


def test_auto_is_on_when_ollama_ready(monkeypatch):
    monkeypatch.setattr(ollama, "_probe", lambda host, model: ollama.READY)
    assert ollama.ai_enabled(Config()) is True


def test_auto_is_off_when_model_not_downloaded(monkeypatch):
    monkeypatch.setattr(ollama, "_probe", lambda host, model: ollama.MODEL_MISSING)
    assert ollama.ai_enabled(Config()) is False


def test_status_is_cached_between_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(ollama, "_probe", lambda host, model: calls.append(1) or ollama.READY)

    ollama.ai_enabled(Config())
    ollama.ai_enabled(Config())

    assert len(calls) == 1


def test_cache_expires_so_a_late_start_is_noticed(monkeypatch):
    statuses = iter([ollama.NOT_RUNNING, ollama.READY])
    monkeypatch.setattr(ollama, "_probe", lambda host, model: next(statuses))
    clock = iter([1000.0, 1000.0 + ollama._CACHE_SECONDS + 1])
    monkeypatch.setattr(ollama.time, "monotonic", lambda: next(clock))

    assert ollama.ai_enabled(Config()) is False
    assert ollama.ai_enabled(Config()) is True  # Ollama started after Ash did


def test_fresh_bypasses_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(ollama, "_probe", lambda host, model: calls.append(1) or ollama.READY)

    ollama.server_status(Config())
    ollama.server_status(Config(), fresh=True)

    assert len(calls) == 2


@pytest.mark.parametrize("installed, model, expected", [
    ({"llama3.2:latest"}, "llama3.2", True),
    ({"llama3.2:3b"}, "llama3.2:3b", True),
    ({"llama3.2:3b"}, "llama3.2", False),
    ({"llama3.2-vision:latest"}, "llama3.2", False),
    (set(), "llama3.2", False),
])
def test_has_model(installed, model, expected):
    assert ollama.has_model(installed, model) is expected


class _FakeTagsResponse:
    def __init__(self, names):
        self._names = names

    def raise_for_status(self):
        pass

    def json(self):
        return {"models": [{"name": n} for n in self._names]}


def test_real_probe_reads_installed_models(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout: _FakeTagsResponse(["llama3.2:latest"]))
    assert _REAL_PROBE("http://localhost:11434", "llama3.2") == ollama.READY
    assert _REAL_PROBE("http://localhost:11434", "mistral") == ollama.MODEL_MISSING


def test_real_probe_connection_refused_is_not_running(monkeypatch):
    def _refused(url, timeout):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", _refused)
    assert _REAL_PROBE("http://localhost:11434", "llama3.2") == ollama.NOT_RUNNING
