import logging

import requests

from ash.actions import converse
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
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.exceptions.HTTPError("500")

    def json(self):
        return self._payload


def test_successful_reply_is_spoken(monkeypatch):
    monkeypatch.setattr(converse.requests, "post",
                         lambda url, json, timeout: FakeResponse({"response": "Paris is the capital of France."}))
    tts = FakeTts()

    result = converse.handle_converse("what is the capital of france", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Let me think.", "Paris is the capital of France."]


def test_sends_configured_model_and_prompt(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"response": "ok"})

    monkeypatch.setattr(converse.requests, "post", fake_post)
    config = Config()
    config.ollama.model = "llama3.2"
    config.ollama.host = "http://localhost:11434"

    converse.handle_converse("hello", Registry(), FakeTts(), log, config)

    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"]["model"] == "llama3.2"
    assert captured["json"]["prompt"] == "hello"
    assert captured["json"]["stream"] is False


def test_connection_error_says_cant_reach(monkeypatch):
    def boom(url, json, timeout):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(converse.requests, "post", boom)
    tts = FakeTts()

    result = converse.handle_converse("hello", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "can't reach" in tts.said[-1]


def test_other_exception_says_generic_error(monkeypatch):
    def boom(url, json, timeout):
        raise ValueError("unexpected")
    monkeypatch.setattr(converse.requests, "post", boom)
    tts = FakeTts()

    result = converse.handle_converse("hello", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "went wrong" in tts.said[-1]


def test_http_error_status_says_generic_error(monkeypatch):
    monkeypatch.setattr(converse.requests, "post",
                         lambda url, json, timeout: FakeResponse({}, status_ok=False))
    tts = FakeTts()

    result = converse.handle_converse("hello", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "went wrong" in tts.said[-1]


def test_empty_model_response_has_fallback_text(monkeypatch):
    monkeypatch.setattr(converse.requests, "post",
                         lambda url, json, timeout: FakeResponse({"response": ""}))
    tts = FakeTts()

    converse.handle_converse("hello", Registry(), tts, log, Config())

    assert tts.said[-1] == "I don't have anything to say to that."
