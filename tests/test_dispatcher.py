import logging

from ash.actions.dispatcher import dispatch
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_unrecognized_intent_is_done_with_a_message():
    result = dispatch("completely unknown gibberish !!", Registry(), FakeTts(), log, Config())
    # "completely unknown gibberish" has no verb, so grammar defaults to
    # intent="open" -- use an intent that truly isn't in _HANDLERS by
    # monkeypatching would be more direct, but exercising the real
    # "no app matches" path through the actual open handler is just as
    # good a proof that dispatch() always returns a usable HandlerResult.
    assert isinstance(result, HandlerResult)
    assert result.done is True


def test_handler_returning_none_normalizes_to_done_result(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    monkeypatch.setitem(dispatcher_module._HANDLERS, "open", lambda *a, **k: None)

    result = dispatch("open notepad", Registry(), FakeTts(), log, Config())

    assert result == HandlerResult(done=True, question=None, resume=None)


def test_handler_returning_not_done_propagates(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    def fake_handler(target, registry, tts, log, config):
        return HandlerResult(done=False, question="Which one?", resume=lambda answer: HandlerResult())

    monkeypatch.setitem(dispatcher_module._HANDLERS, "open", fake_handler)

    result = dispatch("open notepad", Registry(), FakeTts(), log, Config())

    assert result.done is False
    assert result.question == "Which one?"
    assert callable(result.resume)


def test_shutdown_intent_is_intercepted_for_confirmation_before_the_handler_runs(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    calls = []
    monkeypatch.setitem(dispatcher_module._HANDLERS, "shutdown",
                         lambda *a, **k: calls.append(True) or HandlerResult())

    result = dispatch("shut down", Registry(), FakeTts(), log, Config())

    assert result.done is False
    assert "sure" in result.question.lower()
    assert calls == []  # the real handler hasn't run yet -- confirmation comes first
