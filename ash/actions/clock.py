"""Time and date questions, answered from this PC's clock -- nothing is
sent anywhere, so (unlike web search) they work offline and need no
permission.

- "what time is it" / "what's the date" / "what day is it"
- "what day is Christmas" / "what day is December 25"
- "how many days until Christmas" / "how long until New Year's Eve"
"""
import calendar
import logging
import re
from datetime import date, datetime, timedelta

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.duration import format_time_of_day
from ash.registry.schema import Registry

_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
_WEEKDAYS = {name.lower(): number for number, name in enumerate(calendar.day_name)}

# Fixed-date holidays only: movable ones (Easter, Holy Week) need a
# calendar of their own.
_HOLIDAYS = {
    "christmas": (12, 25), "christmas day": (12, 25), "christmas eve": (12, 24),
    "new year": (1, 1), "new years": (1, 1), "new year's": (1, 1),
    "new years day": (1, 1), "new year's day": (1, 1),
    "new years eve": (12, 31), "new year's eve": (12, 31),
    "valentines day": (2, 14), "valentine's day": (2, 14),
    "halloween": (10, 31), "all saints day": (11, 1), "all saints' day": (11, 1),
}

_ORDINAL_RE = r"(\d{1,2})(?:st|nd|rd|th)?"
_MONTH_DAY_RE = re.compile(rf"^(?P<month>[a-z]+)\s+{_ORDINAL_RE}(?:\s+(?P<year>\d{{4}}))?$")
_DAY_MONTH_RE = re.compile(rf"^{_ORDINAL_RE}\s+(?:of\s+)?(?P<month>[a-z]+)(?:\s+(?P<year>\d{{4}}))?$")


def parse_day(text: str, today: date) -> date | None:
    """A spoken day -> a date. Without a year, means the next time it
    comes round (today counts)."""
    text = text.strip().lower()
    text = re.sub(r"^(the|on)\s+", "", text)
    text = re.sub(r"\s+(this year)$", "", text)

    if text in ("today", "now"):
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "yesterday":
        return today - timedelta(days=1)

    weekday = re.sub(r"^(next|this|on)\s+", "", text)
    if weekday in _WEEKDAYS:
        ahead = (_WEEKDAYS[weekday] - today.weekday()) % 7 or 7  # "monday" on a Monday = next week's
        return today + timedelta(days=ahead)

    if text in _HOLIDAYS:
        return _next(today, *_HOLIDAYS[text])

    match = _MONTH_DAY_RE.match(text)
    if match:
        month, day, year = match.group("month"), int(match.group(2)), match.group("year")
    else:
        match = _DAY_MONTH_RE.match(text)
        if not match:
            return None
        day, month, year = int(match.group(1)), match.group("month"), match.group("year")
    if month not in _MONTHS:
        return None
    try:
        if year:
            return date(int(year), _MONTHS[month], day)
        return _next(today, _MONTHS[month], day)
    except ValueError:
        return None  # e.g. "February 30"


def _next(today: date, month: int, day: int) -> date:
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def spoken_date(d: date, today: date) -> str:
    text = f"{calendar.day_name[d.weekday()]}, {calendar.month_name[d.month]} {d.day}"
    return text if d.year == today.year else f"{text}, {d.year}"


def _label(target: str) -> str:
    """How to say back what was asked about: "Christmas", "December 25"."""
    return " ".join(word if word in ("of", "the") else word.capitalize() for word in target.strip().split())


def handle_time_now(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    now = datetime.now()
    tts.say(f"It's {format_time_of_day(now.hour, now.minute)}.")
    return HandlerResult()


def handle_date_today(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    today = date.today()
    tts.say(f"Today is {spoken_date(today, today)}, {today.year}.")
    return HandlerResult()


def handle_day_of(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    today = date.today()
    day = parse_day(target, today)
    if day is None:
        tts.say(f"I'm not sure which day {_label(target)} is.")
        return HandlerResult()

    words = re.sub(r"^(the|on)\s+", "", target.strip().lower())
    month_day = f"{calendar.month_name[day.month]} {day.day}" + ("" if day.year == today.year else f", {day.year}")
    weekday = calendar.day_name[day.weekday()]
    if day == today:
        tts.say(f"That's today, {spoken_date(day, today)}.")
    elif words in _HOLIDAYS:
        tts.say(f"{_label(words)} is on {weekday}, {month_day}.")
    elif re.sub(r"^(next|this)\s+", "", words) in _WEEKDAYS:
        tts.say(f"Next {weekday} is {month_day}.")
    elif words in ("tomorrow", "yesterday"):
        tts.say(f"{words.capitalize()} {'is' if words == 'tomorrow' else 'was'} {spoken_date(day, today)}.")
    else:
        tts.say(f"{month_day} is a {weekday}.")
    return HandlerResult()


def handle_days_until(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if re.search(r"\b(timer|timers|reminder|reminders|alarm)\b", target):
        from ash.actions.timers import handle_timer_list  # "how long until my timer goes off"
        return handle_timer_list(target, registry, tts, log, config)

    today = date.today()
    day = parse_day(target, today)
    if day is None:
        tts.say(f"I'm not sure which day {_label(target)} is.")
        return HandlerResult()
    days = (day - today).days
    relative = target.strip().lower() in ("today", "tomorrow", "yesterday", "now")
    if days == 0:
        tts.say("That's today!" if relative else f"{_label(target)} is today!")
    elif days == 1:
        tts.say(f"That's tomorrow, {spoken_date(day, today)}." if relative else f"{_label(target)} is tomorrow.")
    elif days > 1:
        tts.say(f"{days} days until {_label(target)}, on {spoken_date(day, today)}.")
    else:
        tts.say(f"{_label(target)} was {-days} day{'' if days == -1 else 's'} ago.")
    return HandlerResult()
