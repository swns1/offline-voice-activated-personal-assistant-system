import json

from ash.actions import semantic_fallback
from ash.config import Config
from ash.nlu.intents import ParsedCommand


class FakeResponse:
    def __init__(self, content, status_ok=True):
        self._content = content
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("500")

    def json(self):
        return {"message": {"content": self._content}}


def test_classifies_a_confident_match(monkeypatch):
    reply = json.dumps({"intent": "shutdown", "target": ""})
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse(reply))

    result = semantic_fallback.classify_intent("shut this thing down", Config())

    assert result == ParsedCommand(intent="shutdown", target="")


def test_classifies_a_match_with_a_target(monkeypatch):
    reply = json.dumps({"intent": "timer_set", "target": "in ten minutes"})
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse(reply))

    result = semantic_fallback.classify_intent("wake me up in ten minutes", Config())

    assert result == ParsedCommand(intent="timer_set", target="in ten minutes")


def test_null_intent_returns_none(monkeypatch):
    reply = json.dumps({"intent": None})
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse(reply))

    assert semantic_fallback.classify_intent("tell me a joke", Config()) is None


def test_intent_outside_allowlist_returns_none(monkeypatch):
    # "open" is deliberately not in _CLASSIFIABLE_INTENTS -- it's the
    # existing default, not something worth "reclassifying" into.
    reply = json.dumps({"intent": "open", "target": "notepad"})
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse(reply))

    assert semantic_fallback.classify_intent("whatever", Config()) is None


def test_malformed_json_returns_none(monkeypatch):
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse("not json {{{"))

    assert semantic_fallback.classify_intent("whatever", Config()) is None


def test_non_object_json_returns_none(monkeypatch):
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse("[1, 2, 3]"))

    assert semantic_fallback.classify_intent("whatever", Config()) is None


def test_non_string_target_returns_none(monkeypatch):
    reply = json.dumps({"intent": "volume_set", "target": 50})
    monkeypatch.setattr(semantic_fallback.requests, "post", lambda url, json, timeout: FakeResponse(reply))

    assert semantic_fallback.classify_intent("whatever", Config()) is None


def test_connection_failure_returns_none(monkeypatch):
    def boom(url, json, timeout):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(semantic_fallback.requests, "post", boom)

    assert semantic_fallback.classify_intent("whatever", Config()) is None


def test_bad_status_returns_none(monkeypatch):
    reply = json.dumps({"intent": "shutdown", "target": ""})
    monkeypatch.setattr(semantic_fallback.requests, "post",
                         lambda url, json, timeout: FakeResponse(reply, status_ok=False))

    assert semantic_fallback.classify_intent("whatever", Config()) is None
