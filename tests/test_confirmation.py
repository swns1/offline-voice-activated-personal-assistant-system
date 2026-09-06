import logging

from ash.actions.confirmation import needs_confirmation, wrap_with_confirmation
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_needs_confirmation_true_for_shutdown():
    assert needs_confirmation("shutdown") is True


def test_needs_confirmation_false_for_ordinary_intent():
    assert needs_confirmation("open") is False


def test_wrap_asks_before_running_handler():
    calls = []
    handler = lambda target, registry, tts, log, config: calls.append(target) or HandlerResult()
    tts = FakeTts()

    result = wrap_with_confirmation("shutdown", handler, "", Registry(), tts, log, Config())

    assert result.done is False
    assert "sure" in result.question.lower()
    assert calls == []  # not run yet
    assert tts.said == []


def test_wrap_confirmed_runs_the_real_handler():
    calls = []
    handler = lambda target, registry, tts, log, config: calls.append(target) or HandlerResult()
    tts = FakeTts()
    result = wrap_with_confirmation("shutdown", handler, "some target", Registry(), tts, log, Config())

    final = result.resume("yes")

    assert final == HandlerResult()
    assert calls == ["some target"]


def test_wrap_declined_never_runs_the_real_handler():
    calls = []
    handler = lambda target, registry, tts, log, config: calls.append(target) or HandlerResult()
    tts = FakeTts()
    result = wrap_with_confirmation("shutdown", handler, "", Registry(), tts, log, Config())

    final = result.resume("no thanks")

    assert final == HandlerResult()
    assert calls == []
    assert tts.said == ["Never mind."]


def test_wrap_handler_returning_none_still_normalizes():
    handler = lambda target, registry, tts, log, config: None
    tts = FakeTts()
    result = wrap_with_confirmation("shutdown", handler, "", Registry(), tts, log, Config())

    final = result.resume("yes")

    assert final == HandlerResult()
