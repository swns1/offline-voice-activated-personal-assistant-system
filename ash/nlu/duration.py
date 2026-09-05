"""Parses a relative duration ("5 minutes", "1 hour and 30 minutes") out
of a spoken phrase. Deliberately scoped to relative durations only --
"remind me at 3pm" would need real time-of-day parsing, out of scope
for this pass.
"""
import re
from dataclasses import dataclass

_COMPONENT_RE = re.compile(
    r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", re.IGNORECASE
)
_FILLER_RE = re.compile(r"\b(in|for|to|and)\b", re.IGNORECASE)

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
