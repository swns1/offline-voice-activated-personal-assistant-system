import logging

import requests

from ash.actions import vision
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
    def __init__(self, content, status_ok=True):
        self._content = content
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.exceptions.HTTPError("500")

    def json(self):
        return {"message": {"content": self._content}}


def _enabled_config() -> Config:
    config = Config()
    config.ollama.enabled = True
    return config


def test_ollama_unavailable_says_so():
    tts = FakeTts()

    # Default "auto" + conftest's stubbed probe: Ollama isn't running.
    result = vision.handle_screen_describe("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "needs Ollama running" in tts.said[-1]


def test_screenshot_capture_failure_reported(monkeypatch):
    def boom():
        raise RuntimeError("no display")
    monkeypatch.setattr(vision, "_capture_screenshot_base64", boom)
    tts = FakeTts()

    result = vision.handle_screen_describe("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert "couldn't capture" in tts.said[-1]


def test_describes_screen_with_default_question(monkeypatch):
    monkeypatch.setattr(vision, "_capture_screenshot_base64", lambda: "fakebase64")
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return FakeResponse("A code editor with a Python file open.")

    monkeypatch.setattr(vision.requests, "post", fake_post)
    tts = FakeTts()

    result = vision.handle_screen_describe("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert tts.said == ["Let me look.", "A code editor with a Python file open."]
    message = captured["json"]["messages"][0]
    assert message["images"] == ["fakebase64"]
    assert "Describe" in message["content"]


def test_uses_specific_question_when_given(monkeypatch):
    monkeypatch.setattr(vision, "_capture_screenshot_base64", lambda: "fakebase64")
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return FakeResponse("It's a file not found error.")

    monkeypatch.setattr(vision.requests, "post", fake_post)

    vision.handle_screen_describe("what this error means", Registry(), FakeTts(), log, _enabled_config())

    assert captured["json"]["messages"][0]["content"] == "what this error means"


def test_uses_configured_vision_model(monkeypatch):
    monkeypatch.setattr(vision, "_capture_screenshot_base64", lambda: "fakebase64")
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return FakeResponse("ok")

    monkeypatch.setattr(vision.requests, "post", fake_post)
    config = _enabled_config()
    config.ollama.vision_model = "custom-vision-model"

    vision.handle_screen_describe("", Registry(), FakeTts(), log, config)

    assert captured["json"]["model"] == "custom-vision-model"


def test_connection_error_says_cant_reach(monkeypatch):
    monkeypatch.setattr(vision, "_capture_screenshot_base64", lambda: "fakebase64")

    def boom(url, json, timeout):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(vision.requests, "post", boom)
    tts = FakeTts()

    result = vision.handle_screen_describe("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert "can't reach" in tts.said[-1]


def test_other_exception_says_generic_error(monkeypatch):
    monkeypatch.setattr(vision, "_capture_screenshot_base64", lambda: "fakebase64")

    def boom(url, json, timeout):
        raise ValueError("unexpected")
    monkeypatch.setattr(vision.requests, "post", boom)
    tts = FakeTts()

    result = vision.handle_screen_describe("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert "went wrong" in tts.said[-1]


def test_empty_model_response_has_fallback_text(monkeypatch):
    monkeypatch.setattr(vision, "_capture_screenshot_base64", lambda: "fakebase64")
    monkeypatch.setattr(vision.requests, "post", lambda url, json, timeout: FakeResponse(""))
    tts = FakeTts()

    vision.handle_screen_describe("", Registry(), tts, log, _enabled_config())

    assert tts.said[-1] == "I don't have anything to say about that."
