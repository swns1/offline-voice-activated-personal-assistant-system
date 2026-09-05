import itertools
import logging

import pytest

from ash.actions import timers
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeTimer:
    """Stands in for threading.Timer -- captures the schedule instead of
    running a real background thread; tests fire it manually."""
    instances: list["FakeTimer"] = []

    def __init__(self, seconds, fn):
        self.seconds = seconds
        self.fn = fn
        self.daemon = False
        self.started = False
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def trigger(self):
        self.fn()


@pytest.fixture(autouse=True)
def _reset_timers_state(monkeypatch):
    timers._active.clear()
    monkeypatch.setattr(timers, "_ids", itertools.count(1))
    FakeTimer.instances.clear()
    monkeypatch.setattr(timers.threading, "Timer", FakeTimer)
    yield


def test_timer_set_schedules_and_confirms():
    tts = FakeTts()

    result = timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Timer set for 5 minutes."]
    assert len(FakeTimer.instances) == 1
    assert FakeTimer.instances[0].seconds == 300
    assert FakeTimer.instances[0].started is True


def test_timer_fires_and_speaks_message_then_clears():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes to check the oven", Registry(), tts, log, Config())

    FakeTimer.instances[0].trigger()

    assert "check the oven" in tts.said[-1]
    assert len(timers._active) == 0


def test_timer_with_no_message_says_times_up():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())

    FakeTimer.instances[0].trigger()

    assert tts.said[-1] == "Time's up."


def test_timer_set_no_duration_asks_follow_up():
    tts = FakeTts()

    result = timers.handle_timer_set("please", Registry(), tts, log, Config())

    assert result.done is False
    assert "how long" in result.question.lower()
    assert tts.said == []


def test_timer_set_follow_up_resolves():
    tts = FakeTts()
    result = timers.handle_timer_set("please", Registry(), tts, log, Config())

    final = result.resume("10 seconds")

    assert final == HandlerResult()
    assert "10 seconds" in tts.said[-1]
    assert len(FakeTimer.instances) == 1


def test_timer_set_follow_up_unresolved_says_never_mind():
    tts = FakeTts()
    result = timers.handle_timer_set("please", Registry(), tts, log, Config())

    final = result.resume("I don't know")

    assert final == HandlerResult()
    assert tts.said == ["Never mind."]
    assert FakeTimer.instances == []


def test_reminder_set_speaks_message_and_time():
    tts = FakeTts()

    result = timers.handle_reminder_set("5 minutes to call mom", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "call mom" in tts.said[-1]
    assert "5 minutes" in tts.said[-1]


def test_reminder_set_with_no_message():
    tts = FakeTts()

    timers.handle_reminder_set("5 minutes", Registry(), tts, log, Config())

    assert tts.said == ["I'll remind you in 5 minutes."]


def test_timer_cancel_cancels_all_active():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())
    timers.handle_timer_set("10 minutes", Registry(), tts, log, Config())

    result = timers.handle_timer_cancel("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert all(t.cancelled for t in FakeTimer.instances)
    assert len(timers._active) == 0
    assert tts.said[-1] == "Cancelled 2 timers."


def test_timer_cancel_with_none_active():
    tts = FakeTts()

    timers.handle_timer_cancel("", Registry(), tts, log, Config())

    assert tts.said == ["You don't have any timers running."]


def test_timer_list_speaks_active_timers():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes to check the oven", Registry(), tts, log, Config())

    result = timers.handle_timer_list("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "check the oven" in tts.said[-1]


def test_timer_list_with_none_active():
    tts = FakeTts()

    timers.handle_timer_list("", Registry(), tts, log, Config())

    assert tts.said == ["You don't have any timers running."]


def test_max_active_timers_enforced():
    tts = FakeTts()
    for _ in range(timers._MAX_ACTIVE_TIMERS):
        timers.handle_timer_set("1 minute", Registry(), tts, log, Config())

    result = timers.handle_timer_set("1 minute", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said[-1] == "You already have too many timers running."
    assert len(FakeTimer.instances) == timers._MAX_ACTIVE_TIMERS
