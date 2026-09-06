"""Timers and reminders via threading.Timer -- in-memory only, no
persistence across restarts (same as a kitchen timer app). The fired
callback runs on its own thread and only ever calls tts.say(), which is
just a queue.Queue.put on TtsWorker's own independent queue -- no
shared state with ContinuousListener's queue, so this is safe no matter
what the main thread is blocked on.
"""
import itertools
import logging
import threading
import time

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.duration import format_duration, parse_duration
from ash.registry.schema import Registry
from ash.utils.notifications import show_toast

_MAX_ACTIVE_TIMERS = 20

_lock = threading.Lock()
_active: dict[int, "_ActiveTimer"] = {}
_ids = itertools.count(1)


class _ActiveTimer:
    def __init__(self, timer_id: int, label: str, seconds: int, timer: threading.Timer):
        self.id = timer_id
        self.label = label
        self.fires_at = time.monotonic() + seconds
        self.timer = timer

    def seconds_remaining(self) -> int:
        return max(0, round(self.fires_at - time.monotonic()))


def _schedule(seconds: int, label: str, tts: TtsWorker, log: logging.Logger) -> int | None:
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

    t = threading.Timer(seconds, fire)
    t.daemon = True
    with _lock:
        _active[timer_id] = _ActiveTimer(timer_id, label, seconds, t)
    t.start()
    return timer_id


def handle_timer_set(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    parsed = parse_duration(target)
    if parsed is None:
        def resume(answer: str) -> HandlerResult:
            reparsed = parse_duration(answer)
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
    parsed = parse_duration(target)
    if parsed is None:
        def resume(answer: str) -> HandlerResult:
            reparsed = parse_duration(answer)
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


def handle_timer_cancel(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    with _lock:
        cancelled = list(_active.values())
        _active.clear()
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

    descriptions = [
        f"{a.label} ({format_duration(a.seconds_remaining())} left)" if a.label
        else f"{format_duration(a.seconds_remaining())} left"
        for a in active
    ]
    tts.say("You have " + ", ".join(descriptions) + ".")
    return HandlerResult()
