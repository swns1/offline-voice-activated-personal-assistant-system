import json
import logging

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
        return {"message": {"content": self._content}}


def test_looks_like_chain_detects_then():
    assert chain.looks_like_chain("open spotify and then play jazz") is True
    assert chain.looks_like_chain("remind me in 5 minutes then close discord") is True


def test_looks_like_chain_false_for_ordinary_and():
    # Deliberately not triggering on bare "and" -- too many false
    # positives against legitimate single-command phrases.
    assert chain.looks_like_chain("search for bed and breakfast") is False


def test_looks_like_chain_false_for_plain_command():
    assert chain.looks_like_chain("open notepad") is False


def test_resolve_chain_parses_valid_steps(monkeypatch):
    steps_json = json.dumps([
        {"intent": "open", "target": "spotify"},
        {"intent": "spotify_play", "target": "jazz"},
    ])
    monkeypatch.setattr(chain.requests, "post", lambda url, json, timeout: FakeResponse(steps_json))

    steps = chain.resolve_chain("open spotify and then play jazz", Config())

    assert steps == [
        {"intent": "open", "target": "spotify"},
        {"intent": "spotify_play", "target": "jazz"},
    ]


def test_resolve_chain_rejects_unknown_intent(monkeypatch):
    steps_json = json.dumps([{"intent": "shutdown", "target": ""}])
    monkeypatch.setattr(chain.requests, "post", lambda url, json, timeout: FakeResponse(steps_json))

    assert chain.resolve_chain("shut down then open notepad", Config()) is None


def test_resolve_chain_rejects_malformed_json(monkeypatch):
    monkeypatch.setattr(chain.requests, "post", lambda url, json, timeout: FakeResponse("not json {{{"))

    assert chain.resolve_chain("whatever", Config()) is None


def test_resolve_chain_rejects_empty_list(monkeypatch):
    monkeypatch.setattr(chain.requests, "post", lambda url, json, timeout: FakeResponse("[]"))

    assert chain.resolve_chain("whatever", Config()) is None


def test_resolve_chain_rejects_non_list(monkeypatch):
    monkeypatch.setattr(chain.requests, "post", lambda url, json, timeout: FakeResponse('{"intent": "open"}'))

    assert chain.resolve_chain("whatever", Config()) is None


def test_resolve_chain_connection_failure_returns_none(monkeypatch):
    def boom(url, json, timeout):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(chain.requests, "post", boom)

    assert chain.resolve_chain("whatever", Config()) is None


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
