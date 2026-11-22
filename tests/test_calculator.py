"""Maths and unit conversions worked out on this PC
(ash/actions/calculator.py), and the number-friendly text cleanup that
makes them -- and "9:30am", "1.5 minutes" -- reach Ash intact."""
import builtins
import logging

import pytest

from ash.actions import calculator
from ash.actions.dispatcher import dispatch
from ash.config import Config
from ash.nlu.duration import parse_absolute_time, parse_duration
from ash.nlu.grammar import parse
from ash.privacy import consent, network_log
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture(autouse=True)
def no_eval(monkeypatch):
    """The calculator must never use eval()/exec(), whatever it's asked.
    (pint, the unit library, uses eval while building its unit tables --
    so that's done first, before the trap is set.)"""
    calculator._ureg()
    calculator.convert("1 mile to km")

    def _forbidden(*args, **kwargs):
        raise AssertionError("eval/exec must never be used")
    monkeypatch.setattr(builtins, "eval", _forbidden)
    monkeypatch.setattr(builtins, "exec", _forbidden)


@pytest.mark.parametrize("text, value", [
    ("2+2", 4), ("12 times 7", 84), ("12 x 7", 84), ("10 - 3", 7), ("3.5 divided by 2", 1.75),
    ("144 over 12", 12), ("2 to the power of 10", 1024), ("5 squared", 25), ("3 cubed", 27),
    ("15% of 80", 12), ("15 percent of 80", 12), ("the square root of 144", 12),
    ("(2 + 3) times 4", 20), ("twenty five times four", 100), ("two hundred plus one", 201),
    ("1,000 times 3", 3000), ("-5 plus 2", -3), ("7 minus -3", 10),
])
def test_calculations(text, value):
    assert calculator.calculate(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["5", "the eiffel tower", "python 3.13", "covid-19", "", "what"])
def test_not_calculations(text):
    assert calculator.calculate(text) is None


@pytest.mark.parametrize("text", [
    "__import__('os').system('calc')", "import os", "open('secrets.txt')", "x * 2",
    "lambda: 1", "[1, 2] * 3", "().__class__", "1 if 1 else 2",
])
def test_code_is_never_run(text):
    assert calculator.calculate(text) is None


@pytest.mark.parametrize("text, reply", [
    ("10 divided by 0", "You can't divide by zero."),
    ("9 to the power of 9 to the power of 9", "That number's too big for me to say."),
    ("10 to the power of 5000", "That number's too big for me to say."),
    ("the square root of -4", None),  # "-4" after "of": not a calculation it accepts
])
def test_maths_without_a_sensible_answer(text, reply):
    assert calculator.answer(text) == reply


@pytest.mark.parametrize("value, spoken", [
    (12, "12"), (12.0, "12"), (1.75, "1.75"), (1 / 3, "0.3333"), (12345, "12,345"), (1234.567, "1,234.6"),
])
def test_format_number(value, spoken):
    assert calculator.format_number(value) == spoken


@pytest.mark.parametrize("text, reply", [
    ("5 miles to kilometers", "5 miles is 8.047 kilometers."),
    ("convert 100 degrees fahrenheit to celsius", "100 degrees Fahrenheit is 37.78 degrees Celsius."),
    ("30 celsius in fahrenheit", "30 degrees Celsius is 86 degrees Fahrenheit."),
    ("60 mph in kilometers per hour", "60 mph is 96.56 kilometers per hour."),
    ("how many feet are in a mile", "There are 5280 feet in a mile."),
    ("how many grams in a pound", "There are 453.6 grams in a pound."),
    ("convert 100 dollars to pesos",
     "I can't convert dollars to pesos. I can do units like distance, weight, volume, speed and temperature."),
    ("a way to get to manila", None),        # not a conversion: left for web search
    ("5 miles to happiness", None),
])
def test_conversions(text, reply):
    assert calculator.convert(text) == reply


# --- through the whole command path ---------------------------------------------

def _ask(text: str) -> tuple[str | None, object]:
    tts = FakeTts()
    result = dispatch(text, Registry(), tts, log, Config())
    return (tts.said[-1] if tts.said else None), result


@pytest.mark.parametrize("said, reply", [
    ("What's 15% of 80?", "15% of 80 is 12."),
    ("What is 2+2?", "2+2 is 4."),
    ("Calculate 2 to the power of 10.", "2 to the power of 10 is 1024."),
    ("Convert 5 miles to kilometers.", "5 miles is 8.047 kilometers."),
    ("How many feet are in a mile?", "There are 5280 feet in a mile."),
    ("What's 100 degrees Fahrenheit in Celsius?", "100 degrees Fahrenheit is 37.78 degrees Celsius."),
])
def test_spoken_questions_answered_offline(said, reply):
    consent.PRIVACY_STATE_PATH.unlink()  # web search never allowed...
    consent.set_offline_mode(True)       # ...and offline: still answered, nothing sent

    answer, result = _ask(said)

    assert answer == reply
    assert result.done is True           # no permission question
    assert network_log.entries() == []


def test_a_real_question_still_goes_to_web_search(monkeypatch):
    from ash.actions import search
    monkeypatch.setattr(search, "_query_duckduckgo", lambda query: f"(searched: {query})")

    assert _ask("How many people live in Manila?")[0] == "(searched: how many people live in manila)"
    assert _ask("What is the Eiffel Tower?")[0] == "(searched: the eiffel tower)"


# --- text cleanup keeps what numbers need ------------------------------------------

@pytest.mark.parametrize("said, target", [
    ("Remind me at 9:30am to call mom.", "at 9:30am to call mom"),
    ("Set a timer for 1.5 minutes.", "1.5 minutes"),
    ("What's 15% of 80?", "15% of 80"),
    ("What is 2+2?", "2+2"),
    ("open python 3.13", "python 3.13"),
    ("open x-ray viewer", "xray viewer"),     # hyphen between letters: dropped, as before
    ("set the volume to 50.", "50"),           # sentence-ending period: dropped
])
def test_normalization_keeps_numbers_intact(said, target):
    assert parse(said).target == target


@pytest.mark.parametrize("said, intent", [("Pause.", "spotify_pause"), ("Stop!", "stop"), ("What time is it?", "time_now")])
def test_normalization_still_matches_phrases(said, intent):
    assert parse(said).intent == intent


def test_half_minute_timers_are_no_longer_misheard_as_15_minutes():
    # Regression: "1.5 minutes" used to reach the timer as "15 minutes".
    assert parse_duration(parse("set a timer for 1.5 minutes").target).seconds == 90


def test_reminders_at_9_30_work_by_voice():
    # Regression: the colon was stripped ("930am"), so this never parsed.
    assert parse_absolute_time(parse("remind me at 9:30am to call mom").target) is not None
