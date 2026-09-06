"""Interrupts whatever Ash is currently saying and clears anything
queued but not yet spoken. A pending clarifying question left
unanswered by "stop" already resolves as declined via each handler's
own resume() closure (none of them match "stop" as a valid answer,
so they all fall through to their existing "Never mind" path) -- this
handler only needs to stop speech itself.
"""
import logging

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry


def handle_stop(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    tts.stop_speaking()
    log.info("Stopped speaking on request")
    tts.say("OK.")
    return HandlerResult()
