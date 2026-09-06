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


def parse_absolute_time(text: str, now: datetime | None = None) -> ParsedDuration | None:
    """"3pm", "9:30am", "15:30", optionally with "tomorrow". If the
    resulting time has already passed today (and "tomorrow" wasn't
    said), rolls forward to the next day -- "remind me at 3pm" said at
    5pm means tomorrow's 3pm, not a negative/expired reminder."""
    if now is None:
        now = datetime.now()

    match = _TIME_12H_RE.search(text)
    if match:
        hour = int(match.group(1)) % 12
        minute = int(match.group(2) or 0)
        if match.group(3).lower() == "pm":
            hour += 12
    else:
        match = _TIME_24H_RE.search(text)
        if match is None:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))

    tomorrow = bool(_TOMORROW_RE.search(text))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow or target <= now:
        target += timedelta(days=1)

    seconds = round((target - now).total_seconds())
    if seconds <= 0:
        return None

    remainder = _TIME_12H_RE.sub("", text)
    remainder = _TIME_24H_RE.sub("", remainder)
    remainder = _TOMORROW_RE.sub("", remainder)
    remainder = _FILLER_RE.sub(" ", remainder)
    remainder = _AT_RE.sub(" ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()

    return ParsedDuration(seconds=seconds, remainder=remainder)


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
