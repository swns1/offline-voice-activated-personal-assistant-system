import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

from ash.actions import calendar
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeOutlookItem:
    def __init__(self, subject, start):
        self.Subject = subject
        self.Start = start


def _enabled_config() -> Config:
    config = Config()
    config.calendar.enabled = True
    return config


def test_calendar_disabled_says_so():
    tts = FakeTts()

    result = calendar.handle_calendar_list("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Calendar isn't set up."]


def test_list_upcoming_filters_to_window():
    now = datetime.now()
    items = [
        FakeOutlookItem("Team meeting", now + timedelta(hours=2)),
        FakeOutlookItem("Next week's thing", now + timedelta(days=10)),
        FakeOutlookItem("Yesterday's thing", now - timedelta(days=1)),
    ]

    events = calendar._list_upcoming(24, item_source=lambda: items)

    assert [e["subject"] for e in events] == ["Team meeting"]


def test_list_upcoming_sorts_by_start_time():
    now = datetime.now()
    items = [
        FakeOutlookItem("Later", now + timedelta(hours=5)),
        FakeOutlookItem("Sooner", now + timedelta(hours=1)),
    ]

    events = calendar._list_upcoming(24, item_source=lambda: items)

    assert [e["subject"] for e in events] == ["Sooner", "Later"]


def test_list_upcoming_source_failure_returns_none():
    def boom():
        raise RuntimeError("Outlook not installed")

    assert calendar._list_upcoming(24, item_source=boom) is None


def test_list_upcoming_skips_malformed_items():
    now = datetime.now()
    good = FakeOutlookItem("Good", now + timedelta(hours=1))
    bad = SimpleNamespace(Subject="Bad", Start="not a real COM datetime")

    events = calendar._list_upcoming(24, item_source=lambda: [bad, good])

    assert [e["subject"] for e in events] == ["Good"]


def test_handle_calendar_list_speaks_events(monkeypatch):
    now = datetime.now()
    monkeypatch.setattr(calendar, "_list_upcoming",
                         lambda hours: [{"subject": "Team meeting", "start": now + timedelta(hours=2)}])
    tts = FakeTts()

    result = calendar.handle_calendar_list("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert "Team meeting" in tts.said[-1]


def test_handle_calendar_list_nothing_upcoming(monkeypatch):
    monkeypatch.setattr(calendar, "_list_upcoming", lambda hours: [])
    tts = FakeTts()

    calendar.handle_calendar_list("", Registry(), tts, log, _enabled_config())

    assert tts.said == ["You have nothing coming up."]


def test_handle_calendar_list_outlook_unreachable(monkeypatch):
    monkeypatch.setattr(calendar, "_list_upcoming", lambda hours: None)
    tts = FakeTts()

    result = calendar.handle_calendar_list("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert "can't reach" in tts.said[-1]


def test_calendar_add_disabled_says_so():
    tts = FakeTts()

    result = calendar.handle_calendar_add("team meeting at 3pm", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Calendar isn't set up."]


def test_calendar_add_no_time_asks():
    tts = FakeTts()

    result = calendar.handle_calendar_add("team meeting", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert tts.said == ["What time should I add that for?"]


def test_calendar_add_asks_for_confirmation_with_details():
    tts = FakeTts()

    result = calendar.handle_calendar_add("team meeting at 3pm", Registry(), tts, log, _enabled_config())

    assert result.done is False
    assert "team meeting" in result.question.lower()
    assert "3pm" in result.question.lower()
    assert tts.said == []  # nothing created yet


def test_calendar_add_confirmed_creates_event(monkeypatch):
    calls = []
    monkeypatch.setattr(calendar, "_create_event", lambda subject, start: calls.append((subject, start)) or True)
    tts = FakeTts()
    result = calendar.handle_calendar_add("team meeting at 3pm", Registry(), tts, log, _enabled_config())

    final = result.resume("yes")

    assert final == HandlerResult()
    assert len(calls) == 1
    assert calls[0][0] == "team meeting"
    assert "Added team meeting" in tts.said[-1]


def test_calendar_add_declined_creates_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(calendar, "_create_event", lambda subject, start: calls.append(1) or True)
    tts = FakeTts()
    result = calendar.handle_calendar_add("team meeting at 3pm", Registry(), tts, log, _enabled_config())

    final = result.resume("no thanks")

    assert final == HandlerResult()
    assert calls == []
    assert tts.said == ["Never mind."]


def test_calendar_add_creation_failure_reported(monkeypatch):
    monkeypatch.setattr(calendar, "_create_event", lambda subject, start: False)
    tts = FakeTts()
    result = calendar.handle_calendar_add("team meeting at 3pm", Registry(), tts, log, _enabled_config())

    final = result.resume("yes")

    assert final == HandlerResult()
    assert "couldn't add" in tts.said[-1]


def test_create_event_swallows_exceptions():
    def boom(subject, start):
        raise RuntimeError("COM error")

    assert calendar._create_event("subject", datetime.now(), creator=boom) is False
