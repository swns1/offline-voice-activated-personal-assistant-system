import logging

import pytest

from ash.actions.confirmation import is_affirmative, needs_confirmation, wrap_with_confirmation
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
    assert tts.said == ["Okay, I won't shut down."]


def test_wrap_handler_returning_none_still_normalizes():
    handler = lambda target, registry, tts, log, config: None
    tts = FakeTts()
    result = wrap_with_confirmation("shutdown", handler, "", Registry(), tts, log, Config())

    final = result.resume("yes")

    assert final == HandlerResult()


def test_requires_voice_match_false_by_default():
    handler = lambda target, registry, tts, log, config: HandlerResult()
    result = wrap_with_confirmation("shutdown", handler, "", Registry(), FakeTts(), log, Config())

    assert result.requires_voice_match is False


def test_requires_voice_match_true_when_voice_gate_enabled():
    handler = lambda target, registry, tts, log, config: HandlerResult()
    config = Config()
    config.security.voice_gate_enabled = True

    result = wrap_with_confirmation("shutdown", handler, "", Registry(), FakeTts(), log, config)

    assert result.requires_voice_match is True


@pytest.mark.parametrize("answer", ["Yes.", "yes", " Yeah! ", "YES please.", "Sure.", "I'm sure.", "Go ahead."])
def test_speech_to_text_style_yes_counts(answer):
    # Regression: speech-to-text writes "Yes." -- the old exact match
    # turned every real yes into "Never mind".
    assert is_affirmative(answer) is True


@pytest.mark.parametrize("answer", ["no", "No.", "nope", "yes and no", "", "wait"])
def test_anything_but_a_clear_yes_is_no(answer):
    assert is_affirmative(answer) is False


def test_wrap_accepts_punctuated_yes():
    calls = []
    handler = lambda target, registry, tts, log, config: calls.append(target) or HandlerResult()
    result = wrap_with_confirmation("shutdown", handler, "", Registry(), FakeTts(), log, Config())

    result.resume("Yes.")

    assert calls == [""]


def test_shutdown_question_explains_what_will_happen():
    result = wrap_with_confirmation("shutdown", lambda *a: None, "", Registry(), FakeTts(), log, Config())

    question = result.question.lower()
    assert "close all your apps" in question
    assert "haven't saved will be lost" in question
    assert "are you sure" in question
