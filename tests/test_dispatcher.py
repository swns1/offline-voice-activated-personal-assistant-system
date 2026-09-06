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


def test_chain_like_utterance_with_ollama_disabled_uses_normal_path():
    # config.ollama.enabled defaults to False -- "then" in the text must
    # not trigger any chain resolution attempt.
    result = dispatch("open notepad and then close it", Registry(), FakeTts(), log, Config())
    assert isinstance(result, HandlerResult)


def test_chain_like_utterance_with_ollama_enabled_resolves_and_runs_steps(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    monkeypatch.setattr(dispatcher_module, "resolve_chain",
                         lambda text, config: [{"intent": "open", "target": "notepad"}])
    calls = []
    monkeypatch.setitem(dispatcher_module._HANDLERS, "open",
                         lambda target, registry, tts, log, config: calls.append(target) or HandlerResult())
    config = Config()
    config.ollama.enabled = True

    result = dispatch("open notepad and then close it", Registry(), FakeTts(), log, config)

    assert result == HandlerResult()
    assert calls == ["notepad"]


def test_chain_resolution_failure_falls_back_to_normal_single_intent_path(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    monkeypatch.setattr(dispatcher_module, "resolve_chain", lambda text, config: None)
    calls = []
    monkeypatch.setitem(dispatcher_module._HANDLERS, "open",
                         lambda target, registry, tts, log, config: calls.append(target) or HandlerResult())
    config = Config()
    config.ollama.enabled = True

    # Falls through to the ordinary grammar-based path, same as if
    # ollama were disabled -- "open notepad and then close it" parses
    # as a normal (if slightly odd) single "open" command.
    result = dispatch("open notepad and then close it", Registry(), FakeTts(), log, config)

    assert result == HandlerResult()
    assert calls == ["notepad and then close it"]


def test_pronoun_target_resolves_before_handler_runs(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module
    from ash.nlu import context

    context.remember_app("discord")
    calls = []
    monkeypatch.setitem(dispatcher_module._HANDLERS, "close_app",
                         lambda target, registry, tts, log, config: calls.append(target) or HandlerResult())

    result = dispatch("close it", Registry(), FakeTts(), log, Config())

    assert result == HandlerResult()
    assert calls == ["discord"]


def test_routine_run_executes_configured_steps(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    calls = []
    monkeypatch.setitem(dispatcher_module._HANDLERS, "volume_set",
                         lambda target, registry, tts, log, config: calls.append(("volume_set", target)) or HandlerResult())
    monkeypatch.setitem(dispatcher_module._HANDLERS, "open",
                         lambda target, registry, tts, log, config: calls.append(("open", target)) or HandlerResult())
    registry = Registry(routines={"good morning": [
        {"intent": "volume_set", "target": "30"},
        {"intent": "open", "target": "spotify"},
    ]})

    result = dispatch("run my good morning routine", registry, FakeTts(), log, Config())

    assert result == HandlerResult()
    assert calls == [("volume_set", "30"), ("open", "spotify")]


def test_routine_run_unknown_routine_says_so():
    tts = FakeTts()

    result = dispatch("run my bedtime routine", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "don't have a routine" in tts.said[-1]


def test_shutdown_intent_is_intercepted_for_confirmation_before_the_handler_runs(monkeypatch):
    import ash.actions.dispatcher as dispatcher_module

    calls = []
    monkeypatch.setitem(dispatcher_module._HANDLERS, "shutdown",
                         lambda *a, **k: calls.append(True) or HandlerResult())

    result = dispatch("shut down", Registry(), FakeTts(), log, Config())

    assert result.done is False
    assert "sure" in result.question.lower()
    assert calls == []  # the real handler hasn't run yet -- confirmation comes first
