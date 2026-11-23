import logging

import requests

from ash.actions import chain
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
            raise RuntimeError("500")

    def json(self):
        return {"message": self._content}


def test_looks_like_chain_detects_then():
    assert chain.looks_like_chain("open spotify and then play jazz") is True
    assert chain.looks_like_chain("remind me in 5 minutes then close discord") is True


def test_looks_like_chain_false_for_ordinary_and():
    # Deliberately not triggering on bare "and" -- too many false
    # positives against legitimate single-command phrases.
    assert chain.looks_like_chain("search for bed and breakfast") is False


def test_looks_like_chain_false_for_plain_command():
    assert chain.looks_like_chain("open notepad") is False


def _calls(*calls):
    return {"tool_calls": [{"function": {"name": name, "arguments": args}} for name, args in calls]}


def test_resolve_chain_parses_valid_steps(monkeypatch):
    sent = []

    def post(url, json, timeout):
        sent.append(json)
        return FakeResponse(_calls(("open", {"target": "spotify"}), ("timer_set", {"target": "10 minutes"})))
    monkeypatch.setattr(requests, "post", post)

    steps = chain.resolve_chain("open spotify then set a timer for 10 minutes", Config())

    assert steps == [{"intent": "open", "target": "spotify"}, {"intent": "timer_set", "target": "10 minutes"}]
    offered = {tool["function"]["name"] for tool in sent[0]["tools"]}
    assert "timer_set" in offered and "shutdown" not in offered  # risky actions are never chain steps


def test_resolve_chain_rejects_a_step_it_wasnt_offered(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: FakeResponse(
        _calls(("open", {"target": "spotify"}), ("shutdown", {}))))
    assert chain.resolve_chain("open spotify then shut down", Config()) is None


def test_resolve_chain_with_no_tool_calls(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: FakeResponse({"content": "Sure!"}))
    assert chain.resolve_chain("do a thing then another", Config()) is None


def test_resolve_chain_connection_failure_returns_none(monkeypatch):
    def boom(url, json, timeout):
        raise requests.exceptions.ConnectionError("refused")
    monkeypatch.setattr(requests, "post", boom)
    assert chain.resolve_chain("open spotify then pause", Config()) is None


def test_run_chain_executes_each_step_in_order():
    calls = []
    handlers = {
        "open": lambda target, registry, tts, log, config: calls.append(("open", target)) or HandlerResult(),
        "spotify_play": lambda target, registry, tts, log, config: calls.append(("spotify_play", target)) or HandlerResult(),
    }
    steps = [{"intent": "open", "target": "spotify"}, {"intent": "spotify_play", "target": "jazz"}]

    result = chain.run_chain(steps, handlers, Registry(), FakeTts(), log, Config())

    assert result == HandlerResult()
    assert calls == [("open", "spotify"), ("spotify_play", "jazz")]


def test_run_chain_stops_at_a_step_needing_a_followup():
    calls = []

    def ambiguous_open(target, registry, tts, log, config):
        calls.append("open")
        return HandlerResult(done=False, question="Which one?", resume=lambda answer: HandlerResult())

    def never_called(target, registry, tts, log, config):
        calls.append("should not run")
        return HandlerResult()

    handlers = {"open": ambiguous_open, "spotify_play": never_called}
    steps = [{"intent": "open", "target": "app"}, {"intent": "spotify_play", "target": "jazz"}]

    result = chain.run_chain(steps, handlers, Registry(), FakeTts(), log, Config())

    assert result.done is False
    assert calls == ["open"]  # the second step never ran


def test_run_chain_skips_unknown_handler_gracefully():
    calls = []
    handlers = {"open": lambda target, registry, tts, log, config: calls.append("open") or HandlerResult()}
    steps = [{"intent": "does_not_exist", "target": ""}, {"intent": "open", "target": "app"}]

    result = chain.run_chain(steps, handlers, Registry(), FakeTts(), log, Config())

    assert result == HandlerResult()
    assert calls == ["open"]


def test_confirm_gated_step_asks_instead_of_running():
    # Routines run through run_chain and may contain any intent -- a
    # shutdown step must still ask, never shut down straight away.
    calls = []
    handlers = {
        "volume_set": lambda target, registry, tts, log, config: calls.append("volume_set") or HandlerResult(),
        "shutdown": lambda target, registry, tts, log, config: calls.append("shutdown") or HandlerResult(),
    }
    steps = [{"intent": "volume_set", "target": "20"}, {"intent": "shutdown", "target": ""}]

    result = chain.run_chain(steps, handlers, Registry(), FakeTts(), log, Config())

    assert calls == ["volume_set"]  # the safe step ran; shutdown is waiting on a yes
    assert result.done is False
    assert "are you sure" in result.question.lower()

    result.resume("Yes.")
    assert calls == ["volume_set", "shutdown"]
