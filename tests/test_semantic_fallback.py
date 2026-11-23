"""Loose phrasing understood by the local AI, which picks one of Ash's
commands as a tool call (ash/actions/semantic_fallback.py). Ollama is
faked at the HTTP level."""
import requests

from ash.actions import semantic_fallback
from ash.config import Config
from ash.nlu.intents import ParsedCommand


class FakeResponse:
    def __init__(self, message, status_ok=True):
        self._message = message
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("500")

    def json(self):
        return {"message": self._message}


def _calls(*calls):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}} for name, args in calls]}


def _reply(monkeypatch, message, sent=None):
    def post(url, json, timeout):
        if sent is not None:
            sent.append(json)
        return FakeResponse(message)
    monkeypatch.setattr(requests, "post", post)


def test_classifies_a_confident_match(monkeypatch):
    sent = []
    _reply(monkeypatch, _calls(("shutdown", {})), sent)

    assert semantic_fallback.classify_intent("shut this thing down", Config()) == ParsedCommand("shutdown", "")
    tool_names = {tool["function"]["name"] for tool in sent[0]["tools"]}
    assert "shutdown" in tool_names and "volume_down" in tool_names
    assert sent[0]["messages"][-1] == {"role": "user", "content": "shut this thing down"}


def test_classifies_a_match_with_a_target(monkeypatch):
    _reply(monkeypatch, _calls(("volume_set", {"target": 30})))
    assert semantic_fallback.classify_intent("make it thirty percent", Config()) == ParsedCommand("volume_set", "30")


def test_no_tool_call_returns_none(monkeypatch):
    _reply(monkeypatch, {"role": "assistant", "content": ""})
    assert semantic_fallback.classify_intent("tell me a joke", Config()) is None


def test_a_tool_it_wasnt_offered_returns_none(monkeypatch):
    _reply(monkeypatch, _calls(("format_hard_drive", {})))
    assert semantic_fallback.classify_intent("wipe it", Config()) is None


def test_more_than_one_command_returns_none(monkeypatch):
    _reply(monkeypatch, _calls(("volume_up", {}), ("media_pause", {})))
    assert semantic_fallback.classify_intent("louder and pause", Config()) is None


def test_arguments_sent_as_a_json_string(monkeypatch):
    _reply(monkeypatch, _calls(("timer_set", '{"target": "10 minutes"}')))
    assert semantic_fallback.classify_intent("ten minute timer", Config()) == ParsedCommand("timer_set", "10 minutes")


def test_malformed_arguments_return_none(monkeypatch):
    _reply(monkeypatch, _calls(("timer_set", "not json {{{")))
    assert semantic_fallback.classify_intent("ten minute timer", Config()) is None


def test_non_string_target_returns_none(monkeypatch):
    _reply(monkeypatch, _calls(("timer_set", {"target": ["10", "minutes"]})))
    assert semantic_fallback.classify_intent("ten minute timer", Config()) is None


def test_connection_failure_returns_none(monkeypatch):
    def boom(url, json, timeout):
        raise requests.exceptions.ConnectionError("refused")
    monkeypatch.setattr(requests, "post", boom)
    assert semantic_fallback.classify_intent("dim it", Config()) is None


def test_bad_status_returns_none(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: FakeResponse({}, status_ok=False))
    assert semantic_fallback.classify_intent("dim it", Config()) is None
