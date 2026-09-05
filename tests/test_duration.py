from ash.nlu.duration import format_duration, parse_duration


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
