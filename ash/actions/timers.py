"""Timers and reminders via threading.Timer. Active timers are mirrored
to a small JSON file so a restart/crash doesn't silently lose them --
see rehydrate(), called once at startup. The fired callback runs on its
own thread and only ever calls tts.say(), which is just a
queue.Queue.put on TtsWorker's own independent queue -- no shared state
with ContinuousListener's queue, so this is safe no matter what the
main thread is blocked on.
"""
import itertools
import json
import logging
import threading
import time
from datetime import datetime

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.duration import (
    format_duration,
    format_time_of_day,
    next_occurrence,
    parse_absolute_time,
    parse_duration,
    parse_recurrence,
)
from ash.registry.schema import Registry
from ash.utils.notifications import show_toast
from ash.utils.paths import TIMERS_STATE_PATH, ensure_app_data_dirs

_MAX_ACTIVE_TIMERS = 20

_lock = threading.Lock()
_active: dict[int, "_ActiveTimer"] = {}
_ids = itertools.count(1)


class _ActiveTimer:
    def __init__(self, timer_id: int, label: str, seconds: int, timer: threading.Timer,
                 recurrence: tuple[str, int, int] | None = None):
        self.id = timer_id
        self.label = label
        self.fires_at = time.monotonic() + seconds
        # Wall-clock equivalent, for persistence across restarts --
        # time.monotonic() has no stable meaning across process runs.
        self.fires_at_wall = time.time() + seconds
        self.timer = timer
        self.recurrence = recurrence  # (schedule, hour, minute) or None for one-shot

    def seconds_remaining(self) -> int:
        return max(0, round(self.fires_at - time.monotonic()))


def _recurrence_phrase(recurrence: tuple[str, int, int]) -> str:
    schedule, hour, minute = recurrence
    schedule_word = "every weekday" if schedule == "weekdays" else "every day"
    return f"{schedule_word} at {format_time_of_day(hour, minute)}"


def _persist() -> None:
    with _lock:
        snapshot = []
        for a in _active.values():
            entry = {"label": a.label, "fires_at_wall": a.fires_at_wall}
            if a.recurrence is not None:
                schedule, hour, minute = a.recurrence
                entry["recurrence"] = {"schedule": schedule, "hour": hour, "minute": minute}
            snapshot.append(entry)
    try:
        ensure_app_data_dirs()
        with open(TIMERS_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)
    except OSError:
        pass  # best-effort -- losing persistence shouldn't break the timer itself


def rehydrate(tts: TtsWorker, log: logging.Logger) -> None:
    """Reschedules timers/reminders that were still pending the last time
    Ash ran. Anything that should have already fired while Ash was down
    is announced immediately instead of silently dropped -- a recurring
    reminder is rescheduled for its next occurrence after being
    announced, rather than losing its recurrence."""
    if not TIMERS_STATE_PATH.exists():
        return
    try:
        with open(TIMERS_STATE_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return

    now = time.time()
    for entry in saved:
        label = entry.get("label", "")
        remaining = entry.get("fires_at_wall", 0) - now
        recurrence_data = entry.get("recurrence")
        recurrence = (
            (recurrence_data["schedule"], recurrence_data["hour"], recurrence_data["minute"])
            if recurrence_data else None
        )

        if remaining <= 0:
            message = label or "Time's up."
            tts.say(message)
            show_toast("Ash", message, log)
            log.info("Rehydrated timer had already elapsed while Ash was down: %r", label)
            if recurrence is not None:
                schedule, hour, minute = recurrence
                next_seconds = round((next_occurrence(hour, minute, schedule) - datetime.now()).total_seconds())
                _schedule(next_seconds, label, tts, log, recurrence=recurrence)
        else:
            _schedule(round(remaining), label, tts, log, recurrence=recurrence)
            log.info("Rehydrated timer, %d seconds remaining: %r", round(remaining), label)

    # Elapsed one-shot entries were never re-added to _active -- persist
    # now so they're dropped from disk too, instead of being
    # re-announced on every future restart.
    _persist()


def _schedule(seconds: int, label: str, tts: TtsWorker, log: logging.Logger,
              recurrence: tuple[str, int, int] | None = None) -> int | None:
    with _lock:
        if len(_active) >= _MAX_ACTIVE_TIMERS:
            return None
        timer_id = next(_ids)

    def fire():
        with _lock:
            _active.pop(timer_id, None)
        message = label or "Time's up."
        tts.say(message)
        show_toast("Ash", message, log)
        log.info("Timer %d fired: %r", timer_id, label)
        if recurrence is not None:
            schedule, hour, minute = recurrence
            next_seconds = round((next_occurrence(hour, minute, schedule) - datetime.now()).total_seconds())
            _schedule(next_seconds, label, tts, log, recurrence=recurrence)
        else:
            _persist()

    t = threading.Timer(seconds, fire)
    t.daemon = True
    with _lock:
        _active[timer_id] = _ActiveTimer(timer_id, label, seconds, t, recurrence=recurrence)
    _persist()
    t.start()
    return timer_id


def _parse_when(text: str):
    """Either a relative duration ("5 minutes") or an absolute
    time-of-day ("3pm") -- callers don't need to care which."""
    return parse_duration(text) or parse_absolute_time(text)


def handle_timer_set(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    parsed = _parse_when(target)
    if parsed is None:
        def resume(answer: str) -> HandlerResult:
            reparsed = _parse_when(answer)
            if reparsed is None:
                tts.say("Never mind.")
                return HandlerResult()
            return _start_timer(reparsed.seconds, reparsed.remainder, tts, log)
        return HandlerResult(done=False, question="In how long?", resume=resume)

    return _start_timer(parsed.seconds, parsed.remainder, tts, log)


def _start_timer(seconds: int, label: str, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    if _schedule(seconds, label, tts, log) is None:
        tts.say("You already have too many timers running.")
        return HandlerResult()
    tts.say(f"Timer set for {format_duration(seconds)}.")
    return HandlerResult()


def handle_reminder_set(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    recurrence = parse_recurrence(target)
    if recurrence is not None:
        return _start_recurring_reminder(recurrence, tts, log)

    parsed = _parse_when(target)
    if parsed is None:
        def resume(answer: str) -> HandlerResult:
            reparsed = parse_recurrence(answer)
            if reparsed is not None:
                return _start_recurring_reminder(reparsed, tts, log)
            reparsed = _parse_when(answer)
            if reparsed is None:
                tts.say("Never mind.")
                return HandlerResult()
            return _start_reminder(reparsed.seconds, reparsed.remainder, tts, log)
        return HandlerResult(done=False, question="In how long, and to do what?", resume=resume)

    return _start_reminder(parsed.seconds, parsed.remainder, tts, log)


def _start_reminder(seconds: int, message: str, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    if _schedule(seconds, message, tts, log) is None:
        tts.say("You already have too many timers running.")
        return HandlerResult()
    when = format_duration(seconds)
    if message:
        tts.say(f"I'll remind you to {message} in {when}.")
    else:
        tts.say(f"I'll remind you in {when}.")
    return HandlerResult()


def _start_recurring_reminder(recurrence, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    schedule_tuple = (recurrence.schedule, recurrence.hour, recurrence.minute)
    next_seconds = round((next_occurrence(recurrence.hour, recurrence.minute, recurrence.schedule)
                           - datetime.now()).total_seconds())
    if _schedule(next_seconds, recurrence.remainder, tts, log, recurrence=schedule_tuple) is None:
        tts.say("You already have too many timers running.")
        return HandlerResult()
    when = _recurrence_phrase(schedule_tuple)
    if recurrence.remainder:
        tts.say(f"I'll remind you to {recurrence.remainder} {when}.")
    else:
        tts.say(f"I'll remind you {when}.")
    return HandlerResult()


def handle_timer_cancel(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    with _lock:
        cancelled = list(_active.values())
        _active.clear()
    _persist()
    for active in cancelled:
        active.timer.cancel()

    if not cancelled:
        tts.say("You don't have any timers running.")
    else:
        tts.say("Cancelled." if len(cancelled) == 1 else f"Cancelled {len(cancelled)} timers.")
    return HandlerResult()


def handle_timer_list(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    with _lock:
        active = list(_active.values())

    if not active:
        tts.say("You don't have any timers running.")
        return HandlerResult()

    descriptions = [_describe(a) for a in active]
    tts.say("You have " + ", ".join(descriptions) + ".")
    return HandlerResult()


def _describe(active: "_ActiveTimer") -> str:
    if active.recurrence is not None:
        when = _recurrence_phrase(active.recurrence)
        return f"{active.label} ({when})" if active.label else when
    when = f"{format_duration(active.seconds_remaining())} left"
    return f"{active.label} ({when})" if active.label else when
