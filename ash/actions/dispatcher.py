import logging

from ash.actions.calendar import handle_calendar_add, handle_calendar_list
from ash.actions.desktop_control import handle_screen_click, handle_screen_type
from ash.actions.memory import handle_memory_forget, handle_memory_recall, handle_memory_remember
from ash.actions.open_app import handle_open, handle_open_guess
from ash.actions.search import handle_browser_search, handle_search
from ash.actions.spotify import (
    handle_spotify_now_playing,
    handle_spotify_pause,
    handle_spotify_play,
    handle_spotify_previous,
    handle_spotify_resume,
    handle_spotify_skip,
)
from ash.actions.chain import looks_like_chain, resolve_chain, run_chain
from ash.actions.confirmation import needs_confirmation, wrap_with_confirmation
from ash.actions.diagnostics import handle_diagnostics
from ash.actions.results import HandlerResult
from ash.actions.routines import find_routine, resolve_routine_name
from ash.actions.screen_text import handle_screen_read_text
from ash.actions.semantic_fallback import classify_intent
from ash.actions.stop import handle_stop
from ash.actions.system_power import handle_lock, handle_shutdown, handle_sleep
from ash.actions.timers import (
    handle_reminder_set,
    handle_timer_cancel,
    handle_timer_list,
    handle_timer_set,
)
from ash.actions.vision import handle_screen_describe
from ash.actions.volume import (
    handle_mute,
    handle_unmute,
    handle_volume_down,
    handle_volume_set,
    handle_volume_up,
)
from ash.actions.window import handle_close_app, handle_close_window, handle_minimize_window
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.context import resolve_target
from ash.nlu.grammar import parse
from ash.privacy.redact import said
from ash.registry.schema import Registry
from ash.utils.ollama import ai_enabled

_HANDLERS = {
    "open": handle_open,
    # Not a grammar intent: dispatch() routes here when no verb was
    # recognized and the grammar fell back to guessing "open <utterance>".
    "open_guess": handle_open_guess,
    "search": handle_search,
    "browser_search": handle_browser_search,
    "spotify_play": handle_spotify_play,
    "spotify_pause": handle_spotify_pause,
    "spotify_resume": handle_spotify_resume,
    "spotify_skip": handle_spotify_skip,
    "spotify_previous": handle_spotify_previous,
    "spotify_now_playing": handle_spotify_now_playing,
    "volume_up": handle_volume_up,
    "volume_down": handle_volume_down,
    "volume_set": handle_volume_set,
    "mute": handle_mute,
    "unmute": handle_unmute,
    "lock": handle_lock,
    "sleep": handle_sleep,
    "shutdown": handle_shutdown,
    "timer_set": handle_timer_set,
    "reminder_set": handle_reminder_set,
    "timer_cancel": handle_timer_cancel,
    "timer_list": handle_timer_list,
    "stop": handle_stop,
    "close_app": handle_close_app,
    "close_window": handle_close_window,
    "minimize_window": handle_minimize_window,
    "diagnostics": handle_diagnostics,
    "calendar_list": handle_calendar_list,
    "calendar_add": handle_calendar_add,
    "screen_describe": handle_screen_describe,
    "screen_read_text": handle_screen_read_text,
    "screen_click": handle_screen_click,
    "screen_type": handle_screen_type,
    "memory_remember": handle_memory_remember,
    "memory_forget": handle_memory_forget,
    "memory_recall": handle_memory_recall,
}


def dispatch(text: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if looks_like_chain(text) and ai_enabled(config):
        steps = resolve_chain(text, config)
        if steps is not None:
            log.info("Resolved %s into a %d-step chain", said(text), len(steps))
            return run_chain(steps, _HANDLERS, registry, tts, log, config)
        log.info("Chain-like utterance %s didn't resolve to a usable chain, handling as one command", said(text))

    command = parse(text)

    if not command.explicit and ai_enabled(config):
        reclassified = classify_intent(text, config)
        if reclassified is not None:
            log.info("Semantic fallback reclassified %s as %s(%s)",
                     said(text), reclassified.intent, said(reclassified.target))
            command = reclassified
        else:
            log.info("Semantic fallback found no confident match for %s, keeping the open guess", said(text))

    if command.intent == "routine_run":
        name = resolve_routine_name(command.target)
        steps = find_routine(name, registry)
        if steps is None:
            log.info("No routine matches %s", said(name))
            tts.say(f"I don't have a routine called {name}.")
            return HandlerResult()
        log.info("Running routine %r (%d steps)", name, len(steps))
        return run_chain(steps, _HANDLERS, registry, tts, log, config)

    intent = command.intent
    if intent == "open" and not command.explicit:
        intent = "open_guess"  # you never said "open" -- only open on a close name match
    handler = _HANDLERS.get(intent)
    if handler is None:
        log.info("Unrecognized command: %s", said(text))
        tts.say("I didn't catch that.")
        return HandlerResult()
    target = resolve_target(command.intent, command.target)
    if needs_confirmation(command.intent):
        return wrap_with_confirmation(command.intent, handler, target, registry, tts, log, config)
    result = handler(target, registry, tts, log, config)
    return result if result is not None else HandlerResult()
