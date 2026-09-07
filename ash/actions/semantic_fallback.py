"""When the rule-based grammar (ash/nlu/grammar.py) doesn't recognize
any verb phrase in an utterance, it defaults to treating the whole
thing as "open <utterance>" -- the most permissive interpretation, but
wrong for natural phrasing that doesn't match a literal template ("dim
the volume a bit", "shut this thing down"). Before that guess is acted
on, ash/actions/dispatcher.py asks the already-running local Ollama
model (only if config.ollama.enabled) to classify the utterance against
Ash's other known intents; if it's confident, that replaces the "open"
guess. If Ollama is disabled, unreachable, times out, or isn't
confident, the existing "open" -> app-match -> converse fallback chain
(see ash/actions/open_app.py) proceeds completely unchanged -- this is
purely additive.

Deliberately a separate, smaller intent list from
ash/actions/chain.py's _CHAINABLE_INTENTS: this classifies one single
command, not a multi-step sequence, so confirm-gated intents (shutdown)
are safe to include here -- whatever intent comes back still passes
through dispatcher.py's normal needs_confirmation()/
wrap_with_confirmation() before its handler runs, same as if the user
had said the literal template phrase.
"""
import json
import logging

import requests

from ash.config import Config
from ash.nlu.intents import ParsedCommand

# Short relative to converse.py's 30s -- this sits in front of every
# unmatched command (when enabled), not just ones already headed for a
# conversational reply, so a slow/hung Ollama should fall back to the
# existing "open" guess quickly rather than add a long stall in front of it.
_TIMEOUT_SECONDS = 10.0

_CLASSIFIABLE_INTENTS = [
    "search", "browser_search",
    "spotify_play", "spotify_pause", "spotify_resume", "spotify_skip",
    "spotify_previous", "spotify_now_playing",
    "volume_up", "volume_down", "volume_set", "mute", "unmute",
    "lock", "sleep", "shutdown",
    "timer_set", "reminder_set", "timer_cancel", "timer_list",
    "close_app", "close_window", "minimize_window",
    "diagnostics", "calendar_list", "calendar_add", "screen_describe",
    "memory_remember", "memory_forget", "memory_recall",
]

_SYSTEM_PROMPT = (
    "A voice assistant's rule-based command parser found no match for "
    "this utterance. Decide whether it actually means one of these "
    "known actions: " + ", ".join(_CLASSIFIABLE_INTENTS) + ". "
    'Respond with ONLY JSON shaped {"intent": "...", "target": "..."} '
    'if you are confident it matches one of those actions -- "target" is '
    "whatever that action needs (a search query, volume number, timer "
    "duration and message, etc.), or an empty string if it needs "
    "nothing. If it is a question, a request to open/launch/play "
    "something, a general conversational remark, or does not clearly "
    'match any of those actions, respond with ONLY {"intent": null}.'
)


def classify_intent(text: str, config: Config) -> ParsedCommand | None:
    """Returns a reclassified ParsedCommand, or None if Ollama couldn't
    (or wouldn't) name a confident match -- callers keep treating the
    utterance as the grammar's original "open" guess in that case."""
    try:
        response = requests.post(
            f"{config.ollama.host}/api/chat",
            json={
                "model": config.ollama.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "format": "json",
                "stream": False,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        parsed = json.loads(content)
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None
    intent = parsed.get("intent")
    if intent not in _CLASSIFIABLE_INTENTS:
        return None
    target = parsed.get("target", "")
    if not isinstance(target, str):
        return None
    return ParsedCommand(intent=intent, target=target)
