"""Compound/chained commands ("open spotify and play some jazz, then
remind me in 30 minutes to take a break") -- one utterance, multiple
actions. The existing rule-based grammar stays the primary, fast path
for every ordinary single command; this only engages when the
utterance contains an explicit sequencing word ("then"/"and then") and
local AI is available (ash.utils.ollama.ai_enabled), since resolving a
chain needs a real model call and would be wasted latency on the common
case. The model picks the steps by calling Ash's commands as tools
(Ollama's native tool calling, see ash/nlu/tools.py).

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
import logging

from ash.actions.confirmation import needs_confirmation, wrap_with_confirmation
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.tools import plan
from ash.privacy.redact import said
from ash.registry.schema import Registry
from ash.skills import registry as skills

_TIMEOUT_SECONDS = 30.0
_CHAIN_MARKERS = (" and then ", " then ", " after that ")

_SYSTEM = (
    "You break a spoken request into steps for a voice assistant. Call one tool per step, in the order "
    "they should happen. Use only the available tools; if part of the request matches none, leave that "
    "part out."
)


def looks_like_chain(text: str) -> bool:
    normalized = f" {text.lower()} "
    return any(marker in normalized for marker in _CHAIN_MARKERS)


def resolve_chain(text: str, config: Config) -> list[dict] | None:
    """The steps, as {"intent", "target"}, or None if the local AI
    couldn't produce a usable chain -- callers then treat the whole
    utterance as a single ordinary command."""
    try:
        commands = plan(text, config, skills.chainable_intents(), _SYSTEM, _TIMEOUT_SECONDS)
    except Exception:
        return None
    if not commands:
        return None
    return [{"intent": c.intent, "target": c.target} for c in commands]


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
