"""Durable local facts ("remember I'm vegetarian"), separate from
ash/actions/converse.py's rolling chat history -- that history resets
every conversation and restart; this persists across both, in a flat
%LOCALAPPDATA%\\Ash\\memory.json list, encrypted at rest (see
ash/privacy/secure_store.py) (no vector store/embeddings --
overkill for a personal-scale fact list; rapidfuzz already does
per-fact matching for "forget" the same way ash/nlu/matcher.py does for
app names).

facts_context() is consumed by converse.py to fold what's remembered
into every Ollama call's system prompt, so it's available to freeform
chat automatically, not just on explicit "what do you know about me".
Pure local storage -- works with ollama disabled too, since remembering/
recalling/forgetting a fact needs no model call at all.
"""
import logging

from rapidfuzz import fuzz, process

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import secure_store
from ash.registry.schema import Registry
from ash.utils.paths import MEMORY_PATH

_FORGET_ALL_PHRASES = {"everything", "it all", "all of it", "all"}
_FUZZY_SCORE_CUTOFF = 60.0


def _load_facts() -> list[str]:
    try:
        data = secure_store.read_json(MEMORY_PATH, default={})
    except (OSError, ValueError):
        return []
    facts = data.get("facts") if isinstance(data, dict) else None
    return facts if isinstance(facts, list) else []


def _save_facts(facts: list[str]) -> None:
    try:
        secure_store.write_json(MEMORY_PATH, {"facts": facts})
    except OSError:
        pass  # best-effort -- losing persistence shouldn't break the command itself


def facts_context() -> str:
    """Appended to converse.py's system prompt -- empty string (a no-op
    append) when nothing's been remembered yet."""
    facts = _load_facts()
    if not facts:
        return ""
    return ("\n\nThings the user has told you to remember about them, in "
            "their own words -- use naturally if relevant, don't force "
            "them in: " + "; ".join(facts) + ".")


def handle_memory_remember(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    fact = target.strip()
    if fact.lower().startswith("that "):
        fact = fact[len("that "):].strip()
    if not fact:
        tts.say("What should I remember?")
        return HandlerResult()

    facts = _load_facts()
    if fact not in facts:
        facts.append(fact)
        _save_facts(facts)
    log.info("Remembered a new fact")
    tts.say(f"I'll remember that {fact}.")
    return HandlerResult()


def handle_memory_forget(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    facts = _load_facts()
    if not facts:
        tts.say("I don't have anything remembered.")
        return HandlerResult()

    normalized = target.strip().lower()
    if normalized.startswith("that "):
        normalized = normalized[len("that "):].strip()
    if not normalized or normalized in _FORGET_ALL_PHRASES:
        _save_facts([])
        log.info("Forgot all %d remembered facts", len(facts))
        tts.say("I've forgotten everything.")
        return HandlerResult()

    match = process.extractOne(normalized, facts, scorer=fuzz.WRatio, score_cutoff=_FUZZY_SCORE_CUTOFF)
    if match is None:
        tts.say("I don't remember anything like that.")
        return HandlerResult()

    matched_fact = match[0]
    facts.remove(matched_fact)
    _save_facts(facts)
    log.info("Forgot a fact")
    tts.say(f"I've forgotten that {matched_fact}.")
    return HandlerResult()


def handle_memory_recall(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    facts = _load_facts()
    if not facts:
        tts.say("I don't have anything remembered about you yet.")
        return HandlerResult()
    tts.say("Here's what I remember: " + "; ".join(facts) + ".")
    return HandlerResult()
