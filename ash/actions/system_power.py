"""Lock/sleep/shut down the PC. Lock and sleep are cheap to undo (log
back in, wake the PC) so they run immediately; shut down closes every
open app and any unsaved work, so it requires a spoken yes/no
confirmation via the HandlerResult follow-up mechanism -- the same
shape open_app.py already uses for "did you mean X or Y", just with a
yes/no check instead of a candidate lookup.
"""
import ctypes
import logging
import subprocess
import time

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

# TtsWorker.say() only queues the phrase -- without a short pause here,
# the OS call below can suspend/kill the process before the queued
# speech actually plays, cutting it off audibly.
_SPEAK_GUARD_SECONDS = 1.5

_AFFIRMATIVE = {"yes", "yeah", "yep", "yes please", "confirm", "do it", "sure"}


def handle_lock(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    try:
        tts.say("Locking.")
        ctypes.windll.user32.LockWorkStation()
        log.info("Locked workstation")
    except Exception:
        log.exception("Lock failed")
        tts.say("I couldn't lock the computer.")
    return HandlerResult()


def handle_sleep(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    try:
        tts.say("Going to sleep.")
        time.sleep(_SPEAK_GUARD_SECONDS)
        ctypes.windll.powrprof.SetSuspendState(False, True, False)
        log.info("Suspended (sleep)")
    except Exception:
        log.exception("Sleep failed")
        tts.say("I couldn't put the computer to sleep.")
    return HandlerResult()


def handle_shutdown(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    def resume(answer: str) -> HandlerResult:
        if answer.strip().lower() in _AFFIRMATIVE:
            tts.say("Shutting down.")
            time.sleep(_SPEAK_GUARD_SECONDS)
            try:
                subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
                log.info("Shutdown command issued")
            except Exception:
                log.exception("Shutdown command failed")
                tts.say("I couldn't shut down.")
        else:
            log.info("Shutdown not confirmed: %r", answer)
            tts.say("Never mind.")
        return HandlerResult()

    return HandlerResult(
        done=False,
        question="Are you sure you want to shut down? Say yes to confirm.",
        resume=resume,
    )
