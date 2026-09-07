"""Opt-in proactive calendar nudges -- Ash is otherwise 100% reactive,
never speaking unless spoken to first. Deliberately narrow: this polls
only the existing calendar read path (ash/actions/calendar.py's
list_upcoming), not general ambient monitoring, and gated behind both
config.calendar.enabled and config.calendar.proactive_reminders so it's
opt-in on top of opt-in.

Runs as a self-rescheduling threading.Timer chain (same primitive
ash/actions/timers.py already uses), started once from ash/main.py and
left running for the life of the process. Each event is only ever
announced once (see _announced) -- otherwise the same meeting would get
re-announced on every poll until it starts.
"""
import logging
import threading

from ash.actions.calendar import list_upcoming
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.duration import format_time_of_day
from ash.utils.notifications import show_toast

_announced: set[str] = set()


def _event_key(event: dict) -> str:
    return f"{event['subject']}|{event['start'].isoformat()}"


def _poll_once(config: Config, tts: TtsWorker, log: logging.Logger) -> None:
    events = list_upcoming(config.calendar.proactive_lookahead_minutes / 60)
    if not events:
        return
    for event in events:
        key = _event_key(event)
        if key in _announced:
            continue
        _announced.add(key)
        when = format_time_of_day(event["start"].hour, event["start"].minute)
        message = f"Heads up, {event['subject']} starts at {when}."
        log.info("Proactive calendar nudge: %r", event["subject"])
        tts.say(message)
        show_toast("Ash", message, log)


def start(config: Config, tts: TtsWorker, log: logging.Logger) -> None:
    """No-op unless both calendar.enabled and calendar.proactive_reminders
    are set -- safe to call unconditionally from main.py."""
    if not (config.calendar.enabled and config.calendar.proactive_reminders):
        return

    def loop() -> None:
        try:
            _poll_once(config, tts, log)
        except Exception:
            log.exception("Proactive calendar poll failed")
        timer = threading.Timer(config.calendar.proactive_poll_seconds, loop)
        timer.daemon = True
        timer.start()

    loop()
    log.info("Proactive calendar nudges enabled (checking every %ds, %dmin ahead)",
              config.calendar.proactive_poll_seconds, config.calendar.proactive_lookahead_minutes)
