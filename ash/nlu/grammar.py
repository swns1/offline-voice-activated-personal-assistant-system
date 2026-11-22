"""Splits a transcript into (intent, target).

The phrases come from the skill catalog (ash/skills/catalog.py), not
from here: each skill declares its whole-utterance `phrases` ("pause")
and its `verbs` ("set a timer for" + target).

1. A whole-utterance phrase wins outright.
2. Otherwise the longest verb the utterance starts with wins, if
   something follows it -- so "search in browser for X" beats
   "search X", and "run my X routine" beats "run X", with no
   hand-maintained ordering.
3. Otherwise it's a guess: "open <whole utterance>", marked
   explicit=False (see ash/actions/semantic_fallback.py and
   ash/actions/open_app.py's handle_open_guess).
"""
import re

from ash.nlu.intents import ParsedCommand


def parse(text: str) -> ParsedCommand:
    normalized = _normalize(text)
    if not normalized:
        return ParsedCommand(intent="unknown", target="")

    from ash.skills import registry  # lazy: the catalog imports modules that use parse()

    bare_intent = registry.bare_phrases().get(normalized)
    if bare_intent:
        return ParsedCommand(intent=bare_intent, target="")

    for phrase, intent in registry.verb_phrases():
        if normalized.startswith(phrase + " "):
            target = normalized[len(phrase):].strip()
            if target:
                return ParsedCommand(intent=intent, target=target)

    # No verb recognized: default to "open" on the whole utterance, the
    # most permissive interpretation, per the plan's grammar design.
    # explicit=False flags this as a guess rather than something the user
    # actually said -- see ash/actions/semantic_fallback.py.
    return ParsedCommand(intent="open", target=normalized, explicit=False)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
