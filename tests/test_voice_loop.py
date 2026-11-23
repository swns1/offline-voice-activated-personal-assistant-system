"""VoiceLoop (ash/voice.py): microphone -> AssistantCore, with
follow-up answers by voice -- and noticing when the window answered
first. The microphone and speech-to-text are scripted fakes: an
"utterance" is just the text it should transcribe to."""
import logging
from contextlib import contextmanager

import pytest

from ash.actions.results import YES_NO, HandlerResult
from ash.config import Config
from ash.core import (STATUS_LISTENING, STATUS_MIC_OFF, STATUS_READY, STATUS, TYPED, VOICE, AssistantCore)
from ash.registry.schema import Registry
from ash.voice import VOICE_MISMATCH_REPLY, VoiceLoop

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def is_speaking(self):
        return False


class FakeListener:
    """utterances: what you say after each wake word. followups: what
    each listen_for_followup() returns -- text, None (silence), or a
    callable run at that moment (e.g. a click in the window)."""

    def __init__(self, utterances=(), followups=()):
        self.utterances = list(utterances)
        self.followups = list(followups)
        self.followup_calls = 0
        self.mic_enabled = True

    @contextmanager
    def open_stream(self):
        yield

    def listen(self, on_state_change=None):
        for utterance in self.utterances:
            on_state_change("listening")
            on_state_change("idle")
            yield utterance
        on_state_change("mic_off")

    def listen_for_followup(self, timeout_seconds, on_state_change=None):
        self.followup_calls += 1
        item = self.followups.pop(0)
        return item() if callable(item) else item

    def set_mic_enabled(self, enabled):
        self.mic_enabled = enabled


class EchoStt:
    def transcribe(self, audio):
        return audio


def _confirming(calls):
    def dispatch(text, registry, tts, log, config):
        calls.append(("command", text))
        if text != "delete it":
            tts.say(f"ok {text}")
            return None

        def resume(answer):
            calls.append(("answer", answer))
            return HandlerResult()
        return HandlerResult(done=False, question="Sure?", resume=resume, choices=YES_NO,
                             timeout_reply="Never mind.")
    return dispatch


@pytest.fixture
def make_core():
    cores = []

    def make(dispatch):
        core = AssistantCore(Registry(), FakeTts(), log, Config(), dispatch_fn=dispatch)
        core.events = []
        core.subscribe(core.events.append)
        core.start()
        cores.append(core)
        return core

    yield make
    for core in cores:
        core.stop()


@pytest.fixture
def run_voice(make_core):
    def run(listener, dispatch, verify=lambda audio, config, log: True):
        core = make_core(dispatch)
        VoiceLoop(core, listener, EchoStt(), Config(), log, verify=verify).run(greet=False)
        return core, core.events
    return run


def _voice(core, listener):
    VoiceLoop(core, listener, EchoStt(), Config(), log).run(greet=False)


def test_a_spoken_command_and_a_spoken_answer(run_voice):
    calls = []
    run_voice(FakeListener(["delete it"], ["yes"]), _confirming(calls))
    assert calls == [("command", "delete it"), ("answer", "yes")]


def test_no_answer_in_time_says_the_timeout_reply(run_voice):
    calls = []
    core, _ = run_voice(FakeListener(["delete it", "next"], [None]), _confirming(calls))
    assert calls == [("command", "delete it"), ("command", "next")]
    assert core.tts._inner.said == ["Sure?", "Never mind.", "ok next"]


def test_answered_in_the_window_while_listening(make_core):
    """You click Yes while the mic is waiting for a spoken answer: the
    click wins, and what the mic then hears isn't run a second time."""
    calls = []
    core = make_core(_confirming(calls))

    def click_yes_then_mumble():
        core.submit("Yes", TYPED).result(timeout=5)
        return "uh"
    listener = FakeListener(["delete it"], [click_yes_then_mumble])

    _voice(core, listener)

    assert calls == [("command", "delete it"), ("answer", "Yes")]
    assert listener.followup_calls == 1


def test_a_voice_that_doesnt_match_cancels_the_confirmation(run_voice):
    def dispatch(text, registry, tts, log, config):
        return HandlerResult(done=False, question="Sure?", resume=lambda a: pytest.fail("ran"),
                             requires_voice_match=True, choices=YES_NO)
    core, _ = run_voice(FakeListener(["shut down"], ["yes"]), dispatch,
                        verify=lambda audio, config, log: False)
    assert core.tts._inner.said[-1] == VOICE_MISMATCH_REPLY
    assert core.question is None


def test_a_question_left_open_by_typing_isnt_listened_for(make_core):
    """A typed command's question is still open; a spoken command that
    doesn't answer it (blank transcript) mustn't start a follow-up."""
    core = make_core(_confirming([]))
    core.submit("delete it", TYPED).result(timeout=5)
    listener = FakeListener([""], [])

    _voice(core, listener)

    assert listener.followup_calls == 0
    assert core.question is not None


def test_listener_states_become_core_statuses(run_voice):
    _, events = run_voice(FakeListener(["hi"]), _confirming([]))
    statuses = [e.text for e in events if e.kind == STATUS]
    assert statuses[:3] == [STATUS_READY, STATUS_LISTENING, STATUS_READY]
    assert statuses[-1] == STATUS_MIC_OFF


def test_spoken_commands_are_marked_as_voice(run_voice):
    calls = []
    _, events = run_voice(FakeListener(["hi"]), _confirming(calls))
    assert [(e.text, e.source) for e in events if e.kind == "heard"] == [("hi", VOICE)]
