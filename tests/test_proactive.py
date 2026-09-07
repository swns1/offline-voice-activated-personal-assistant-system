import logging
from datetime import datetime, timedelta

import pytest

from ash.actions import proactive
from ash.config import Config

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeTimer:
    instances: list["FakeTimer"] = []

    def __init__(self, seconds, fn):
        self.seconds = seconds
        self.fn = fn
        self.daemon = False
        self.started = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def trigger(self):
        self.fn()


@pytest.fixture(autouse=True)
def _reset_proactive_state(monkeypatch):
    proactive._announced.clear()
    FakeTimer.instances.clear()
    monkeypatch.setattr(proactive.threading, "Timer", FakeTimer)
    monkeypatch.setattr(proactive, "show_toast", lambda title, body, log=None: None)


def _enabled_config(**overrides) -> Config:
    config = Config()
    config.calendar.enabled = True
    config.calendar.proactive_reminders = True
    for key, value in overrides.items():
        setattr(config.calendar, key, value)
    return config


def test_disabled_by_default_does_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(proactive, "list_upcoming", lambda hours: calls.append(hours) or [])

    proactive.start(Config(), FakeTts(), log)

    assert calls == []
    assert FakeTimer.instances == []


def test_calendar_enabled_but_not_proactive_does_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(proactive, "list_upcoming", lambda hours: calls.append(hours) or [])
    config = Config()
    config.calendar.enabled = True
    config.calendar.proactive_reminders = False

    proactive.start(config, FakeTts(), log)

    assert calls == []


def test_enabled_announces_an_imminent_meeting(monkeypatch):
    start_time = datetime.now() + timedelta(minutes=3)
    monkeypatch.setattr(proactive, "list_upcoming",
                         lambda hours: [{"subject": "team sync", "start": start_time}])
    tts = FakeTts()

    proactive.start(_enabled_config(), tts, log)

    assert len(tts.said) == 1
    assert "team sync" in tts.said[0]
    assert FakeTimer.instances[0].started is True  # reschedules itself


def test_same_event_is_not_announced_twice(monkeypatch):
    start_time = datetime.now() + timedelta(minutes=3)
    monkeypatch.setattr(proactive, "list_upcoming",
                         lambda hours: [{"subject": "team sync", "start": start_time}])
    tts = FakeTts()

    proactive.start(_enabled_config(), tts, log)
    FakeTimer.instances[0].trigger()  # second poll, same event still in the window

    assert len(tts.said) == 1


def test_no_upcoming_events_says_nothing(monkeypatch):
    monkeypatch.setattr(proactive, "list_upcoming", lambda hours: [])
    tts = FakeTts()

    proactive.start(_enabled_config(), tts, log)

    assert tts.said == []


def test_list_upcoming_returning_none_is_handled_gracefully(monkeypatch):
    # Outlook unreachable -- list_upcoming returns None, same as
    # handle_calendar_list's own failure path.
    monkeypatch.setattr(proactive, "list_upcoming", lambda hours: None)
    tts = FakeTts()

    proactive.start(_enabled_config(), tts, log)  # must not raise

    assert tts.said == []


def test_poll_exception_does_not_break_the_reschedule(monkeypatch):
    def boom(hours):
        raise RuntimeError("COM failure")
    monkeypatch.setattr(proactive, "list_upcoming", boom)
    tts = FakeTts()

    proactive.start(_enabled_config(), tts, log)  # must not raise

    assert FakeTimer.instances[0].started is True


def test_lookahead_and_poll_seconds_are_passed_through(monkeypatch):
    captured = []
    monkeypatch.setattr(proactive, "list_upcoming", lambda hours: captured.append(hours) or [])

    proactive.start(_enabled_config(proactive_lookahead_minutes=10, proactive_poll_seconds=30), FakeTts(), log)

    assert captured == [10 / 60]
    assert FakeTimer.instances[0].seconds == 30
