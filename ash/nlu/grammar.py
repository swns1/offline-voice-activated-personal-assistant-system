"""Splits a transcript into (intent, target) via an ordered list of verb
phrases. Longest phrase first within a group so "search for" matches
before the bare "search" prefix would swallow it. New verb groups
(media, system, assistant control) are added in later phases as pure
data here, not a redesign.
"""
import re

from ash.nlu.intents import ParsedCommand

# Order matters: groups are tried top-to-bottom, first match wins.
_VERB_GROUPS: list[tuple[str, list[str]]] = [
    ("search", ["search for", "search", "look up", "what is", "what's",
                "who is", "who's", "google"]),
    ("open", ["open", "launch", "start", "run", "play"]),
]


def parse(text: str) -> ParsedCommand:
    normalized = _normalize(text)
    if not normalized:
        return ParsedCommand(intent="unknown", target="")

    for intent, phrases in _VERB_GROUPS:
        for phrase in sorted(phrases, key=len, reverse=True):
            if normalized == phrase or normalized.startswith(phrase + " "):
                target = normalized[len(phrase):].strip()
                if target:
                    return ParsedCommand(intent=intent, target=target)

    # No verb recognized: default to "open" on the whole utterance, the
    # most permissive interpretation, per the plan's grammar design.
    return ParsedCommand(intent="open", target=normalized)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
