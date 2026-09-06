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
    def __init__(self, content, status_ok=True):
        self._content = content
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.exceptions.HTTPError("500")

    def json(self):
        return {"message": {"role": "assistant", "content": self._content}}


def test_successful_reply_is_spoken_and_offers_a_followup(monkeypatch):
    monkeypatch.setattr(converse.requests, "post",
                         lambda url, json, timeout: FakeResponse("Paris is the capital of France."))
    tts = FakeTts()

    result = converse.handle_converse("what is the capital of france", Registry(), tts, log, Config())

    assert tts.said == ["Let me think.", "Paris is the capital of France."]
    assert result.done is False
    assert result.question is None
    assert callable(result.resume)


def test_sends_full_message_history_including_system_prompt(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse("Paris.")

    monkeypatch.setattr(converse.requests, "post", fake_post)
    config = Config()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.2"

    converse.handle_converse("capital of france", Registry(), FakeTts(), log, config)

    assert captured["url"] == "http://localhost:11434/api/chat"
    messages = captured["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "capital of france"}
    assert captured["json"]["stream"] is False


def test_followup_carries_prior_history(monkeypatch):
    captured_messages = []

    def fake_post(url, json, timeout):
        captured_messages.append(json["messages"])
        return FakeResponse("some reply")

    monkeypatch.setattr(converse.requests, "post", fake_post)
    tts = FakeTts()
    result = converse.handle_converse("what is the capital of france", Registry(), tts, log, Config())

    result.resume("what's its population")

    second_call_messages = captured_messages[1]
    contents = [m["content"] for m in second_call_messages]
    assert "what is the capital of france" in contents
    assert "some reply" in contents  # the assistant's first reply carried forward
    assert "what's its population" in contents


def test_saying_stop_ends_the_conversation_without_asking_the_model(monkeypatch):
    calls = []
    monkeypatch.setattr(converse.requests, "post", lambda url, json, timeout: calls.append(1) or FakeResponse("hi"))
    tts = FakeTts()
    result = converse.handle_converse("hello", Registry(), tts, log, Config())
    calls.clear()

    final = result.resume("stop")

    assert final == HandlerResult()
    assert calls == []  # never asked the model again
    assert tts.said[-1] == "OK."


def test_conversation_ends_after_max_messages(monkeypatch):
    monkeypatch.setattr(converse.requests, "post", lambda url, json, timeout: FakeResponse("reply"))
    tts = FakeTts()
    result = converse.handle_converse("start", Registry(), tts, log, Config())

    # Keep answering until the cap is hit -- each round-trip adds a user
    # + assistant message.
    turns = 0
    while not result.done and turns < 20:
        result = result.resume(f"follow-up {turns}")
        turns += 1

    assert result.done is True


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
                         lambda url, json, timeout: FakeResponse("", status_ok=False))
    tts = FakeTts()

    result = converse.handle_converse("hello", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "went wrong" in tts.said[-1]


def test_empty_model_response_has_fallback_text(monkeypatch):
    monkeypatch.setattr(converse.requests, "post", lambda url, json, timeout: FakeResponse(""))
    tts = FakeTts()

    converse.handle_converse("hello", Registry(), tts, log, Config())

    assert tts.said[-1] == "I don't have anything to say to that."
