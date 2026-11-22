"""Compound/chained commands ("open spotify and play some jazz, then
remind me in 30 minutes to take a break") -- one utterance, multiple
actions. The existing rule-based grammar stays the primary, fast path
for every ordinary single command; this only engages when the
utterance contains an explicit sequencing word ("then"/"and then") and
local AI is available (ash.utils.ollama.ai_enabled), since resolving a
chain needs a real model call and would be wasted latency on the common
case.

Destructive/confirm-gated intents (shutdown) and session-interrupting
power actions (lock, sleep) are deliberately excluded from the
chainable set -- composing per-step confirmation with a multi-step
chain is a real design problem, not solved here. run_chain() still
routes any confirm-gated step through the same confirmation as a
spoken command, though -- it also runs user-defined routines, which
can contain any intent (shutdown included). If a chain step
itself needs a follow-up (e.g. an ambiguous app match), the chain ends
there rather than trying to interleave a pending question with the
remaining steps; the user answers that one question normally.
"""
import json
import logging

import requests

from ash.actions.confirmation import needs_confirmation, wrap_with_confirmation
from ash.actions.results import HandlerResult
from ash.privacy.redact import said
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_TIMEOUT_SECONDS = 30.0
_CHAIN_MARKERS = (" and then ", " then ", " after that ")

_CHAINABLE_INTENTS = [
    "open", "search",
    "spotify_play", "spotify_pause", "spotify_resume", "spotify_skip", "spotify_previous",
    "volume_up", "volume_down", "volume_set", "mute", "unmute",
    "timer_set", "reminder_set",
    "close_app", "close_window", "minimize_window",
    "memory_remember", "memory_forget", "memory_recall",
]

_SYSTEM_PROMPT = (
    "You break a spoken command into a sequence of steps for a voice "
    "assistant. Each step's intent must be exactly one of: "
    + ", ".join(_CHAINABLE_INTENTS) + ". "
    "Respond with ONLY a JSON array of objects, each shaped "
    '{"intent": "...", "target": "..."}, no other text. "target" is '
    "whatever that intent needs (an app/song name, search query, volume "
    "number, timer duration and message, etc.), or an empty string if "
    "the intent needs nothing. If the command isn't actually multiple "
    "steps, respond with a single-element array."
)


def looks_like_chain(text: str) -> bool:
    normalized = f" {text.lower()} "
    return any(marker in normalized for marker in _CHAIN_MARKERS)


def resolve_chain(text: str, config: Config) -> list[dict] | None:
    """Returns a list of {"intent", "target"} steps, or None if Ollama
    couldn't produce a usable chain -- callers fall back to treating the
    whole utterance as a single ordinary command in that case."""
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
        steps = json.loads(content)
    except Exception:
        return None

    return _validate_steps(steps)


def _validate_steps(steps) -> list[dict] | None:
    if not isinstance(steps, list) or not steps:
        return None

    valid_steps = []
    for step in steps:
        if not isinstance(step, dict):
            return None
        intent = step.get("intent")
        target = step.get("target", "")
        if intent not in _CHAINABLE_INTENTS or not isinstance(target, str):
            return None
        valid_steps.append({"intent": intent, "target": target})
    return valid_steps


def run_chain(
    steps: list[dict], handlers: dict, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config,
) -> HandlerResult:
    for step in steps:
        handler = handlers.get(step["intent"])
        if handler is None:
            continue
        log.info("Chain step: %s(%s)", step["intent"], said(step["target"]))
        if needs_confirmation(step["intent"]):
            # Same gate as a spoken command -- a routine step must never
            # skip it. Asking ends the chain here, like any follow-up.
            return wrap_with_confirmation(step["intent"], handler, step["target"], registry, tts, log, config)
        result = handler(step["target"], registry, tts, log, config)
        if result is not None and not result.done:
            return result  # a step needs a follow-up -- stop chaining, let the user answer it
    return HandlerResult()
