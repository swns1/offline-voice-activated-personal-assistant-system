from datetime import datetime

from ash.nlu.duration import format_duration, parse_absolute_time, parse_duration


def test_simple_minutes():
    result = parse_duration("5 minutes")
    assert result.seconds == 300
    assert result.remainder == ""


def test_seconds_abbreviation():
    result = parse_duration("30 secs")
    assert result.seconds == 30


def test_compound_duration():
    result = parse_duration("1 hour and 30 minutes")
    assert result.seconds == 5400


def test_extracts_trailing_message():
    result = parse_duration("5 minutes to check the oven")
    assert result.seconds == 300
    assert result.remainder == "check the oven"


def test_extracts_leading_message():
    result = parse_duration("call mom in 5 minutes")
    assert result.seconds == 300
    assert result.remainder == "call mom"


def test_no_duration_returns_none():
    assert parse_duration("check the oven") is None


def test_empty_text_returns_none():
    assert parse_duration("") is None


def test_zero_duration_returns_none():
    assert parse_duration("0 minutes") is None


def test_format_seconds_only():
    assert format_duration(10) == "10 seconds"


def test_format_singular():
    assert format_duration(60) == "1 minute"
    assert format_duration(1) == "1 second"


def test_format_minutes_and_seconds():
    assert format_duration(90) == "1 minute and 30 seconds"


def test_format_hours_minutes_seconds():
    assert format_duration(3725) == "1 hour, 2 minutes and 5 seconds"


def test_format_exact_minutes_has_no_trailing_zero_seconds():
    assert format_duration(300) == "5 minutes"


def _at(hour, minute=0, second=0):
    return datetime(2026, 6, 15, hour, minute, second)  # a Monday


def test_absolute_time_later_today_12h():
    result = parse_absolute_time("3pm", now=_at(9, 0))
    assert result.seconds == 6 * 3600


def test_absolute_time_with_minutes_and_am():
    result = parse_absolute_time("9:30am", now=_at(9, 0))
    assert result.seconds == 30 * 60


def test_absolute_time_24_hour_format():
    result = parse_absolute_time("15:30", now=_at(15, 0))
    assert result.seconds == 30 * 60


def test_absolute_time_noon_and_midnight():
    assert parse_absolute_time("12pm", now=_at(0, 0)).seconds == 12 * 3600
    assert parse_absolute_time("12am tomorrow", now=_at(0, 0)).seconds == 24 * 3600


def test_absolute_time_already_passed_rolls_to_tomorrow():
    result = parse_absolute_time("3pm", now=_at(17, 0))  # 5pm, so 3pm has passed
    assert result.seconds == 22 * 3600  # 5pm -> next day 3pm


def test_absolute_time_explicit_tomorrow_even_if_not_yet_passed():
    result = parse_absolute_time("tomorrow at 9am", now=_at(8, 0))
    assert result.seconds == 25 * 3600  # 8am -> next day 9am, not today's 9am


def test_absolute_time_extracts_message():
    result = parse_absolute_time("check the oven at 3pm", now=_at(9, 0))
    assert result.remainder == "check the oven"


def test_absolute_time_no_time_present_returns_none():
    assert parse_absolute_time("check the oven", now=_at(9, 0)) is None


def test_absolute_time_bare_number_without_am_pm_or_colon_returns_none():
    assert parse_absolute_time("in 15", now=_at(9, 0)) is None
