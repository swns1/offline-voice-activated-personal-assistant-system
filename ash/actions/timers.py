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

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.duration import format_duration, parse_duration
from ash.registry.schema import Registry
from ash.utils.notifications import show_toast
from ash.utils.paths import TIMERS_STATE_PATH, ensure_app_data_dirs

_MAX_ACTIVE_TIMERS = 20

_lock = threading.Lock()
_active: dict[int, "_ActiveTimer"] = {}
_ids = itertools.count(1)


class _ActiveTimer:
    def __init__(self, timer_id: int, label: str, seconds: int, timer: threading.Timer):
        self.id = timer_id
        self.label = label
        self.fires_at = time.monotonic() + seconds
        # Wall-clock equivalent, for persistence across restarts --
        # time.monotonic() has no stable meaning across process runs.
        self.fires_at_wall = time.time() + seconds
        self.timer = timer

    def seconds_remaining(self) -> int:
        return max(0, round(self.fires_at - time.monotonic()))


def _persist() -> None:
    with _lock:
        snapshot = [{"label": a.label, "fires_at_wall": a.fires_at_wall} for a in _active.values()]
    try:
        ensure_app_data_dirs()
        with open(TIMERS_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)
    except OSError:
        pass  # best-effort -- losing persistence shouldn't break the timer itself


def rehydrate(tts: TtsWorker, log: logging.Logger) -> None:
    """Reschedules timers/reminders that were still pending the last time
    Ash ran. Anything that should have already fired while Ash was down
    is announced immediately instead of silently dropped."""
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
        if remaining <= 0:
            message = label or "Time's up."
            tts.say(message)
            show_toast("Ash", message, log)
            log.info("Rehydrated timer had already elapsed while Ash was down: %r", label)
        else:
            _schedule(round(remaining), label, tts, log)
            log.info("Rehydrated timer, %d seconds remaining: %r", round(remaining), label)

    # Elapsed entries were never re-added to _active -- persist now so
    # they're dropped from disk too, instead of being re-announced on
    # every future restart.
    _persist()


def _schedule(seconds: int, label: str, tts: TtsWorker, log: logging.Logger) -> int | None:
    with _lock:
        if len(_active) >= _MAX_ACTIVE_TIMERS:
            return None
        timer_id = next(_ids)

    def fire():
        with _lock:
            _active.pop(timer_id, None)
        _persist()
        message = label or "Time's up."
        tts.say(message)
        show_toast("Ash", message, log)
        log.info("Timer %d fired: %r", timer_id, label)

    t = threading.Timer(seconds, fire)
    t.daemon = True
    with _lock:
        _active[timer_id] = _ActiveTimer(timer_id, label, seconds, t)
    _persist()
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

    descriptions = [
        f"{a.label} ({format_duration(a.seconds_remaining())} left)" if a.label
        else f"{format_duration(a.seconds_remaining())} left"
        for a in active
    ]
    tts.say("You have " + ", ".join(descriptions) + ".")
    return HandlerResult()
