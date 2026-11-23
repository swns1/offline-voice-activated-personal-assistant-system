"""AssistantCore (ash/core.py): one worker thread runs every command,
from any input; follow-up questions can be answered from any input."""
import logging
import threading

import pytest

from ash.actions.results import YES_NO, HandlerResult
from ash.config import Config
from ash.core import BUTTON, FAILED_REPLY, HEARD, QUESTION, QUESTION_CLOSED, SAID, SYSTEM, TYPED, VOICE, AssistantCore, ReplyTts
from ash.privacy import consent
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def is_speaking(self):
        return False

    def stop_speaking(self):
        pass


@pytest.fixture
def make_core():
    cores = []

    def make(dispatch_fn=None, config=None):
        kwargs = {"dispatch_fn": dispatch_fn} if dispatch_fn else {}
        core = AssistantCore(Registry(), FakeTts(), log, config or Config(), **kwargs)
        events = []
        core.subscribe(events.append)
        core.start()
        cores.append(core)
        return core, events

    yield make
    for core in cores:
        core.stop()


def _confirming_dispatch(calls):
    """A command that asks "Sure?" and records each answer."""
    def dispatch(text, registry, tts, log, config):
        calls.append(("command", text))

        def resume(answer):
            calls.append(("answer", answer))
            tts.say("Done." if answer.lower() == "yes" else "Okay, not doing it.")
            return HandlerResult()
        return HandlerResult(done=False, question="Sure?", resume=resume, choices=YES_NO)
    return dispatch


def _said(core):
    return core.tts._inner.said


def test_a_typed_command_runs_and_its_reply_is_published(make_core):
    def dispatch(text, registry, tts, log, config):
        tts.say(f"You said {text}.")
    core, events = make_core(dispatch)

    assert core.submit("hello", TYPED).result(timeout=5) is None

    assert [(e.kind, e.text, e.source) for e in events] == [
        (HEARD, "hello", TYPED), (SAID, "You said hello.", "")]
    assert _said(core) == ["You said hello."]


def test_commands_run_one_at_a_time_on_the_worker_thread(make_core):
    seen = []

    def dispatch(text, registry, tts, log, config):
        seen.append((text, threading.current_thread().name))
    core, _ = make_core(dispatch)

    futures = [core.submit(str(i), VOICE if i % 2 else TYPED) for i in range(20)]
    for f in futures:
        f.result(timeout=5)

    assert [text for text, _ in seen] == [str(i) for i in range(20)]
    assert {name for _, name in seen} == {"ash-core"}
    assert core.call(lambda: threading.current_thread().name).result(timeout=5) == "ash-core"


def test_a_question_can_be_answered_from_another_input(make_core):
    calls = []
    core, events = make_core(_confirming_dispatch(calls))

    question = core.submit("delete it", VOICE).result(timeout=5)

    assert question.text == "Sure?" and question.choices == YES_NO and question.source == VOICE
    assert core.question == question
    assert [e for e in events if e.kind == QUESTION][0].question == question
    assert _said(core) == ["Sure?"]

    # Clicking "Yes" in the window answers the question the voice command asked.
    assert core.submit("Yes", BUTTON).result(timeout=5) is None
    assert calls == [("command", "delete it"), ("answer", "Yes")]
    assert core.question is None
    assert QUESTION_CLOSED in [e.kind for e in events]
    assert _said(core)[-1] == "Done."


def test_a_late_answer_to_an_already_answered_question_is_dropped(make_core):
    calls = []
    core, _ = make_core(_confirming_dispatch(calls))
    question = core.submit("delete it", VOICE).result(timeout=5)
    core.submit("no", TYPED).result(timeout=5)

    # The voice follow-up recorded meanwhile arrives afterwards.
    core.submit("yes", VOICE, answering=question.id).result(timeout=5)

    assert calls == [("command", "delete it"), ("answer", "no")]  # not run as a new command either


def test_time_out_says_the_questions_timeout_reply(make_core):
    def dispatch(text, registry, tts, log, config):
        return HandlerResult(done=False, question="Which one?", resume=lambda a: None,
                             timeout_reply="I'll ask again later.")
    core, _ = make_core(dispatch)
    question = core.submit("open", VOICE).result(timeout=5)

    core.time_out(question.id).result(timeout=5)

    assert core.question is None
    assert _said(core) == ["Which one?", "I'll ask again later."]
    core.time_out(question.id).result(timeout=5)  # a second (stale) timeout does nothing
    assert _said(core) == ["Which one?", "I'll ask again later."]


def test_cancel_drops_the_question_without_running_it(make_core):
    calls = []
    core, _ = make_core(_confirming_dispatch(calls))
    question = core.submit("delete it", VOICE).result(timeout=5)

    core.cancel(question.id, "That didn't sound like you.").result(timeout=5)

    assert core.question is None
    assert calls == [("command", "delete it")]
    assert _said(core)[-1] == "That didn't sound like you."


def test_a_failing_command_is_reported_and_the_worker_keeps_going(make_core):
    def dispatch(text, registry, tts, log, config):
        if text == "break":
            raise RuntimeError("boom")
        tts.say("fine")
    core, _ = make_core(dispatch)

    core.submit("break").result(timeout=5)
    core.submit("next").result(timeout=5)

    assert _said(core) == [FAILED_REPLY, "fine"]


def test_a_failing_call_reports_its_error_to_the_caller_only(make_core):
    core, _ = make_core()

    def boom():
        raise ValueError("bad")
    with pytest.raises(ValueError):
        core.call(boom).result(timeout=5)
    assert core.call(lambda: 42).result(timeout=5) == 42


def test_blank_input_is_ignored(make_core):
    calls = []
    core, events = make_core(_confirming_dispatch(calls))
    assert core.submit("   ", VOICE).result(timeout=5) is None
    assert calls == [] and events == []


def test_a_conversation_turn_keeps_the_question_open_without_saying_anything(make_core):
    def dispatch(text, registry, tts, log, config):
        tts.say("Hi there.")
        return HandlerResult(done=False, question=None, resume=lambda a: None)
    core, _ = make_core(dispatch)

    question = core.submit("hello").result(timeout=5)

    assert question.text is None
    assert _said(core) == ["Hi there."]


def test_reply_tts_can_show_replies_without_speaking():
    inner, events = FakeTts(), []
    tts = ReplyTts(inner, events.append)
    tts.speak = False
    tts.say("quiet")
    assert inner.said == [] and events[0].text == "quiet"
    assert tts.is_speaking() is False  # everything else passes through


# --- with the real dispatcher and privacy questions -------------------------------------

def test_real_command_through_the_core(make_core, monkeypatch):
    from datetime import datetime

    from ash.actions import clock

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 23, 9, 30)
    monkeypatch.setattr(clock, "datetime", FixedDateTime)
    core, _ = make_core()
    core.submit("what time is it").result(timeout=5)
    assert _said(core) == ["It's 9:30am."]


def test_a_risky_command_offers_yes_and_no_and_no_does_nothing(make_core):
    core, _ = make_core()
    question = core.submit("shut down", TYPED).result(timeout=5)
    assert question.choices == YES_NO
    assert "Are you sure?" in question.text

    core.submit("No", TYPED).result(timeout=5)
    assert core.question is None
    assert _said(core)[-1].startswith("Okay")


def test_startup_privacy_questions_are_asked_through_the_core(make_core, monkeypatch):
    monkeypatch.setattr(consent, "_load", lambda: {"offline_mode": False, "consents": {}})
    saved = []
    monkeypatch.setattr(consent, "_save", saved.append)
    core, _ = make_core()

    question = core.ask_startup_questions().result(timeout=5)

    assert question.source == SYSTEM and question.choices == YES_NO
    assert "DuckDuckGo" in question.text
