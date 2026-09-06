from datetime import datetime

from ash.nlu.duration import (
    format_duration,
    format_time_of_day,
    next_occurrence,
    parse_absolute_time,
    parse_duration,
    parse_recurrence,
)


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


def test_absolute_time_target_time_is_exact():
    # Regression: callers needing a precise timestamp (calendar events)
    # must not have to re-derive it via datetime.now() + seconds, which
    # rounds `seconds` to a whole number and can land ~0.X seconds short
    # -- e.g. displaying "2:59pm" instead of "3pm".
    result = parse_absolute_time("3pm", now=_at(9, 0))
    assert result.target_time == datetime(2026, 6, 15, 15, 0)


def test_absolute_time_extracts_message():
    result = parse_absolute_time("check the oven at 3pm", now=_at(9, 0))
    assert result.remainder == "check the oven"


def test_absolute_time_no_time_present_returns_none():
    assert parse_absolute_time("check the oven", now=_at(9, 0)) is None


def test_absolute_time_bare_number_without_am_pm_or_colon_returns_none():
    assert parse_absolute_time("in 15", now=_at(9, 0)) is None


def test_parse_recurrence_every_day():
    result = parse_recurrence("every day at 8am to take medicine")
    assert result.schedule == "daily"
    assert result.hour == 8
    assert result.minute == 0
    assert result.remainder == "take medicine"


def test_parse_recurrence_every_weekday():
    result = parse_recurrence("every weekday at 9:30am check email")
    assert result.schedule == "weekdays"
    assert result.hour == 9
    assert result.minute == 30


def test_parse_recurrence_every_morning_means_daily():
    result = parse_recurrence("every morning at 7am")
    assert result.schedule == "daily"
    assert result.hour == 7


def test_parse_recurrence_no_every_returns_none():
    assert parse_recurrence("at 8am take medicine") is None


def test_parse_recurrence_no_time_returns_none():
    assert parse_recurrence("every day take medicine") is None


def test_next_occurrence_daily_later_today():
    # Monday 9am, asking for 3pm daily -> today at 3pm
    result = next_occurrence(15, 0, "daily", now=_at(9, 0))
    assert result == datetime(2026, 6, 15, 15, 0)


def test_next_occurrence_daily_already_passed_rolls_to_tomorrow():
    result = next_occurrence(9, 0, "daily", now=_at(15, 0))
    assert result == datetime(2026, 6, 16, 9, 0)


def test_next_occurrence_weekdays_skips_weekend():
    # 2026-06-15 is a Monday; Friday 2026-06-19 at 9am, asking again
    # after it fires should land on Monday 2026-06-22, not Saturday.
    friday_after_fire = datetime(2026, 6, 19, 9, 1)
    result = next_occurrence(9, 0, "weekdays", now=friday_after_fire)
    assert result == datetime(2026, 6, 22, 9, 0)


def test_format_time_of_day():
    assert format_time_of_day(8, 0) == "8am"
    assert format_time_of_day(15, 0) == "3pm"
    assert format_time_of_day(9, 30) == "9:30am"
    assert format_time_of_day(0, 0) == "12am"
    assert format_time_of_day(12, 0) == "12pm"
