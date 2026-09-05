import logging

from ash.actions.open_app import handle_open
from ash.actions.search import handle_search
from ash.audio.tts import TtsWorker
from ash.nlu.grammar import parse
from ash.registry.schema import Registry

_HANDLERS = {
    "open": handle_open,
    "search": handle_search,
}


def dispatch(text: str, registry: Registry, tts: TtsWorker, log: logging.Logger) -> None:
    command = parse(text)
    handler = _HANDLERS.get(command.intent)
    if handler is None:
        log.info("Unrecognized command: %r", text)
        tts.say("I didn't catch that.")
        return
    handler(command.target, registry, tts, log)
