"""Parses either a relative duration ("5 minutes", "1 hour and 30
minutes") or an absolute time-of-day ("3pm", "9:30am", "tomorrow at
9am") out of a spoken phrase, both into the same ParsedDuration shape
so callers (ash/actions/timers.py) don't need to care which form was
used. Deliberately scoped to what's directly sayable -- no day-of-week
("next Monday") parsing yet.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_COMPONENT_RE = re.compile(
    r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", re.IGNORECASE
)
_FILLER_RE = re.compile(r"\b(in|for|to|and)\b", re.IGNORECASE)

_TIME_12H_RE = re.compile(r"\b(\d{1,2})(?::([0-5]\d))?\s*(am|pm)\b", re.IGNORECASE)
_TIME_24H_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
_AT_RE = re.compile(r"\bat\b", re.IGNORECASE)
_RECURRENCE_RE = re.compile(r"\bevery\s+(day|weekday|morning|night)\b", re.IGNORECASE)

_UNIT_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}


@dataclass
class ParsedDuration:
    seconds: int
    remainder: str  # leftover text after removing duration components -- the reminder message, if any


def parse_duration(text: str) -> ParsedDuration | None:
    matches = list(_COMPONENT_RE.finditer(text))
    if not matches:
        return None

    total_seconds = sum(int(amount) * _UNIT_SECONDS[unit.lower()] for amount, unit in
                         (m.groups() for m in matches))
    if total_seconds <= 0:
        return None

    remainder = _COMPONENT_RE.sub("", text)
    remainder = _FILLER_RE.sub(" ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()

    return ParsedDuration(seconds=total_seconds, remainder=remainder)


def _extract_time_of_day(text: str) -> tuple[int, int] | None:
    match = _TIME_12H_RE.search(text)
    if match:
        hour = int(match.group(1)) % 12
        minute = int(match.group(2) or 0)
        if match.group(3).lower() == "pm":
            hour += 12
        return hour, minute

    match = _TIME_24H_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def _strip_time_of_day(text: str) -> str:
    remainder = _TIME_12H_RE.sub("", text)
    remainder = _TIME_24H_RE.sub("", remainder)
    return remainder


def parse_absolute_time(text: str, now: datetime | None = None) -> ParsedDuration | None:
    """"3pm", "9:30am", "15:30", optionally with "tomorrow". If the
    resulting time has already passed today (and "tomorrow" wasn't
    said), rolls forward to the next day -- "remind me at 3pm" said at
    5pm means tomorrow's 3pm, not a negative/expired reminder."""
    if now is None:
        now = datetime.now()

    time_of_day = _extract_time_of_day(text)
    if time_of_day is None:
        return None
    hour, minute = time_of_day

    tomorrow = bool(_TOMORROW_RE.search(text))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow or target <= now:
        target += timedelta(days=1)

    seconds = round((target - now).total_seconds())
    if seconds <= 0:
        return None

    remainder = _strip_time_of_day(text)
    remainder = _TOMORROW_RE.sub("", remainder)
    remainder = _FILLER_RE.sub(" ", remainder)
    remainder = _AT_RE.sub(" ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()

    return ParsedDuration(seconds=seconds, remainder=remainder)


@dataclass
class ParsedRecurrence:
    schedule: str  # "daily" or "weekdays"
    hour: int
    minute: int
    remainder: str


def parse_recurrence(text: str) -> ParsedRecurrence | None:
    """"every day at 8am", "every weekday at 9:30am". Requires an
    explicit time -- "every day" alone with no time isn't schedulable."""
    match = _RECURRENCE_RE.search(text)
    if match is None:
        return None
    schedule = "weekdays" if match.group(1).lower() == "weekday" else "daily"

    stripped = _RECURRENCE_RE.sub("", text)
    time_of_day = _extract_time_of_day(stripped)
    if time_of_day is None:
        return None
    hour, minute = time_of_day

    remainder = _strip_time_of_day(stripped)
    remainder = _FILLER_RE.sub(" ", remainder)
    remainder = _AT_RE.sub(" ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()

    return ParsedRecurrence(schedule=schedule, hour=hour, minute=minute, remainder=remainder)


def next_occurrence(hour: int, minute: int, schedule: str, now: datetime | None = None) -> datetime:
    """Next datetime at hour:minute honoring "daily"/"weekdays", always
    strictly after `now` (never returns `now` itself even if it happens
    to match exactly)."""
    if now is None:
        now = datetime.now()

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    if schedule == "weekdays":
        while target.weekday() >= 5:  # Saturday=5, Sunday=6
            target += timedelta(days=1)
    return target


def format_time_of_day(hour: int, minute: int) -> str:
    period = "am" if hour < 12 else "pm"
    display_hour = hour % 12 or 12
    if minute:
        return f"{display_hour}:{minute:02d}{period}"
    return f"{display_hour}{period}"


def format_duration(seconds: int) -> str:
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if seconds or not parts:
        parts.append(f"{seconds} second" + ("s" if seconds != 1 else ""))

    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]
