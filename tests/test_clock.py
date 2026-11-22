"""Time and date questions (ash/actions/clock.py), answered offline."""
import logging
from datetime import date, datetime

import pytest

from ash.actions import clock
from ash.actions.dispatcher import dispatch
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")
TODAY = date(2026, 11, 23)  # a Monday


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 23, 15, 5)

    monkeypatch.setattr(clock, "date", FixedDate)
    monkeypatch.setattr(clock, "datetime", FixedDateTime)


def _ask(text: str) -> str:
    tts = FakeTts()
    dispatch(text, Registry(), tts, log, Config())
    return tts.said[-1]


@pytest.mark.parametrize("text, expected", [
    ("today", date(2026, 11, 23)),
    ("tomorrow", date(2026, 11, 24)),
    ("yesterday", date(2026, 11, 22)),
    ("friday", date(2026, 11, 27)),
    ("next monday", date(2026, 11, 30)),      # a weekday name means the next one, not today
    ("christmas", date(2026, 12, 25)),
    ("new year's day", date(2027, 1, 1)),
    ("halloween", date(2027, 10, 31)),        # already passed this year
    ("december 25th", date(2026, 12, 25)),
    ("the 1st of january", date(2027, 1, 1)),
    ("25 december 2030", date(2030, 12, 25)),
    ("november 23", date(2026, 11, 23)),      # today counts
    ("feb 14", date(2027, 2, 14)),
])
def test_parse_day(text, expected):
    assert clock.parse_day(text, TODAY) == expected


@pytest.mark.parametrize("text", ["february 30", "smarch 3", "someday", ""])
def test_parse_day_rejects_nonsense(text):
    assert clock.parse_day(text, TODAY) is None


@pytest.mark.parametrize("said, reply", [
    ("What time is it?", "It's 3:05pm."),
    ("what is the time", "It's 3:05pm."),
    ("What's the date?", "Today is Monday, November 23, 2026."),
    ("what day is it", "Today is Monday, November 23, 2026."),
    ("What day is Christmas?", "Christmas is on Friday, December 25."),
    ("what day is december 25", "December 25 is a Friday."),
    ("what day is the 1st of january 2027", "January 1, 2027 is a Friday."),
    ("what day is friday", "Next Friday is November 27."),
    ("what day is tomorrow", "Tomorrow is Tuesday, November 24."),
    ("how many days until christmas", "32 days until Christmas, on Friday, December 25."),
    ("how long until tomorrow", "That's tomorrow, Tuesday, November 24."),
    ("how many days until today", "That's today!"),
    ("what day is february 30", "I'm not sure which day February 30 is."),
])
def test_spoken_answers(said, reply):
    assert _ask(said) == reply


def test_how_long_until_my_timer_lists_timers():
    assert _ask("how long until my timer goes off") == "You don't have any timers running."


def test_nothing_goes_online():
    from ash.privacy import network_log
    for q in ("what time is it", "what's the date", "what day is christmas", "how many days until christmas"):
        _ask(q)
    assert network_log.entries() == []
