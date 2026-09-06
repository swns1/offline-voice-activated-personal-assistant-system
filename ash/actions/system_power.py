"""Lock/sleep/shut down the PC. Lock and sleep are cheap to undo (log
back in, wake the PC) so they run immediately here; shut down closes
every open app and any unsaved work, so it's gated behind a spoken
yes/no confirmation -- but that gating now lives centrally in
ash/actions/confirmation.py (dispatch() intercepts "shutdown" before
this handler ever runs), not hand-rolled in this module.
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
    tts.say("Shutting down.")
    time.sleep(_SPEAK_GUARD_SECONDS)
    try:
        subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
        log.info("Shutdown command issued")
    except Exception:
        log.exception("Shutdown command failed")
        tts.say("I couldn't shut down.")
    return HandlerResult()
