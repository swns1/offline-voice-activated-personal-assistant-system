"""Centralizes "should this action ask before doing it?" so a
destructive/write intent opts in with one line here instead of every
handler hand-rolling its own ask-then-resume dance. dispatch() checks
needs_confirmation() before calling a handler at all -- see
ash/actions/dispatcher.py.

This covers the common case: a static intent with a fixed yes/no gate
(shutdown). Confirmations whose question depends on what's actually
being done (e.g. "add 'Team Meeting' to your calendar at 3pm?") don't
fit a static per-intent string -- those handlers keep building their
own HandlerResult(done=False, question=..., resume=...) directly, the
same general mechanism this just wraps for the static case.
"""
import logging
from typing import Callable

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

Handler = Callable[[str, Registry, TtsWorker, logging.Logger, Config], HandlerResult | None]

# intent -> spoken confirmation question. Add to this to gate a new
# intent behind a yes/no confirmation without touching dispatch().
_CONFIRM_REQUIRED: dict[str, str] = {
    "shutdown": "Are you sure you want to shut down? Say yes to confirm.",
}

AFFIRMATIVE_ANSWERS = {"yes", "yeah", "yep", "yes please", "confirm", "do it", "sure"}


def needs_confirmation(intent: str) -> bool:
    return intent in _CONFIRM_REQUIRED


def wrap_with_confirmation(
    intent: str, handler: Handler, target: str,
    registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config,
) -> HandlerResult:
    def resume(answer: str) -> HandlerResult:
        if answer.strip().lower() not in AFFIRMATIVE_ANSWERS:
            log.info("Confirmation declined for intent %r: %r", intent, answer)
            tts.say("Never mind.")
            return HandlerResult()
        result = handler(target, registry, tts, log, config)
        return result if result is not None else HandlerResult()

    return HandlerResult(done=False, question=_CONFIRM_REQUIRED[intent], resume=resume)
