import logging

from ash.actions.open_app import handle_open
from ash.actions.search import handle_search
from ash.actions.spotify import (
    handle_spotify_now_playing,
    handle_spotify_pause,
    handle_spotify_play,
    handle_spotify_previous,
    handle_spotify_resume,
    handle_spotify_skip,
)
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.grammar import parse
from ash.registry.schema import Registry

_HANDLERS = {
    "open": handle_open,
    "search": handle_search,
    "spotify_play": handle_spotify_play,
    "spotify_pause": handle_spotify_pause,
    "spotify_resume": handle_spotify_resume,
    "spotify_skip": handle_spotify_skip,
    "spotify_previous": handle_spotify_previous,
    "spotify_now_playing": handle_spotify_now_playing,
}


def dispatch(text: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    command = parse(text)
    handler = _HANDLERS.get(command.intent)
    if handler is None:
        log.info("Unrecognized command: %r", text)
        tts.say("I didn't catch that.")
        return
    handler(command.target, registry, tts, log, config)
