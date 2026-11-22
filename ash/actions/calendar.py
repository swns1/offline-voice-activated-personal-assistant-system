"""Reads (and, with confirmation, adds to) your local Outlook calendar
via COM -- the same pywin32 pattern already used for Start Menu
scanning. Gated behind config.calendar.enabled (like Spotify/Ollama):
unlike DuckDuckGo search, this touches real personal data, and it only
works at all if desktop Outlook is installed and configured. Every COM
call is wrapped defensively -- Outlook not installed, no default
profile, or any other COM failure degrades to "I can't reach your
calendar" rather than crashing, since most machines running Ash won't
have Outlook at all.

Adding an event always asks for confirmation first, spoken with the
actual event details -- this is a dynamic confirmation (the question
depends on what's being added), so it builds its own
HandlerResult(done=False, ...) directly rather than going through
ash/actions/confirmation.py's static per-intent map.
"""
import logging
from datetime import datetime, timedelta
from typing import Callable

import pythoncom
import win32com.client

from ash.actions.confirmation import is_affirmative
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.duration import format_time_of_day, parse_absolute_time
from ash.registry.schema import Registry

_OL_FOLDER_CALENDAR = 9
_OL_APPOINTMENT_ITEM = 1
_LOOKAHEAD_HOURS = 24


def _default_calendar_items() -> list:
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        folder = namespace.GetDefaultFolder(_OL_FOLDER_CALENDAR)
        items = folder.Items
        items.IncludeRecurrences = True
        items.Sort("[Start]")
        return list(items)
    finally:
        pythoncom.CoUninitialize()


def list_upcoming(hours_ahead: float, item_source: Callable[[], list] = _default_calendar_items) -> list[dict] | None:
    try:
        raw_items = item_source()
    except Exception:
        return None

    now = datetime.now()
    end = now + timedelta(hours=hours_ahead)
    events = []
    for item in raw_items:
        try:
            start = datetime(item.Start.year, item.Start.month, item.Start.day,
                              item.Start.hour, item.Start.minute)
            subject = str(item.Subject)
        except Exception:
            continue
        if now <= start <= end:
            events.append({"subject": subject, "start": start})
    events.sort(key=lambda e: e["start"])
    return events


def handle_calendar_list(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if not config.calendar.enabled:
        tts.say("Calendar isn't set up.")
        return HandlerResult()

    events = list_upcoming(_LOOKAHEAD_HOURS)
    if events is None:
        log.warning("Could not reach Outlook calendar")
        tts.say("I can't reach your calendar right now.")
        return HandlerResult()

    if not events:
        tts.say("You have nothing coming up.")
        return HandlerResult()

    descriptions = [f"{e['subject']} at {format_time_of_day(e['start'].hour, e['start'].minute)}" for e in events[:5]]
    tts.say("You have " + "; ".join(descriptions) + ".")
    return HandlerResult()


def _default_create_event(subject: str, start: datetime) -> None:
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        appointment = outlook.CreateItem(_OL_APPOINTMENT_ITEM)
        appointment.Subject = subject
        appointment.Start = start
        appointment.Duration = 30
        appointment.Save()
    finally:
        pythoncom.CoUninitialize()


def _create_event(subject: str, start: datetime, creator: Callable[[str, datetime], None] = _default_create_event) -> bool:
    try:
        creator(subject, start)
        return True
    except Exception:
        return False


def handle_calendar_add(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if not config.calendar.enabled:
        tts.say("Calendar isn't set up.")
        return HandlerResult()

    parsed = parse_absolute_time(target)
    if parsed is None:
        tts.say("What time should I add that for?")
        return HandlerResult()

    subject = parsed.remainder or "New event"
    start = parsed.target_time
    when = format_time_of_day(start.hour, start.minute)

    def resume(answer: str) -> HandlerResult:
        if not is_affirmative(answer):
            log.info("Calendar add declined: %r", answer)
            tts.say("Never mind.")
            return HandlerResult()
        if not _create_event(subject, start):
            log.warning("Failed to add calendar event %r", subject)
            tts.say("I couldn't add that to your calendar.")
            return HandlerResult()
        log.info("Added calendar event %r at %s", subject, start)
        tts.say(f"Added {subject} at {when}.")
        return HandlerResult()

    return HandlerResult(done=False, question=f"Add '{subject}' to your calendar at {when}?", resume=resume)
