"""Routes one utterance to the skill that handles it: multi-step
commands (local AI), the grammar, loose-phrasing fallback (local AI),
pronoun resolution ("close it"), and confirmation gates. Which skills
exist, and how each is triggered, lives in ash/skills/catalog.py.
"""
import logging

from ash.actions.chain import looks_like_chain, resolve_chain, run_chain
from ash.actions.confirmation import needs_confirmation, wrap_with_confirmation
from ash.actions.results import HandlerResult
from ash.actions.semantic_fallback import classify_intent
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.context import resolve_target, set_utterance
from ash.nlu.grammar import parse
from ash.privacy.redact import said
from ash.registry.schema import Registry
from ash.skills import registry as skills
from ash.utils.ollama import ai_enabled

# intent -> handler, from the skill catalog. A plain module-level dict so
# routines (ash/actions/routines.py) and tests share one table.
_HANDLERS = skills.handlers()


def dispatch(text: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    set_utterance(text)
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
