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
    # Commands are matched without commas ("Remind me, at 3pm..." still
    # starts with "remind me"), but the target keeps them, so a list like
    # "bread, butter and milk" reaches the handler as three things.
    with_commas = _normalize(text)
    words = [w for w in with_commas.split() if w.strip(",")]
    plain_words = [w.replace(",", "") for w in words]
    start, end = _without_politeness(plain_words)
    words, plain_words = words[start:end], plain_words[start:end]
    normalized = " ".join(plain_words)
    if not normalized:
        return ParsedCommand(intent="unknown", target="")

    from ash.skills import registry  # lazy: the catalog imports modules that use parse()

    bare_intent = registry.bare_phrases().get(normalized)
    if bare_intent:
        return ParsedCommand(intent=bare_intent, target="")

    for phrase, intent in registry.verb_phrases():
        if normalized.startswith(phrase + " "):
            target = " ".join(words[len(phrase.split()):]).strip(" ,")
            if target:
                return ParsedCommand(intent=intent, target=target)

    # No verb recognized: default to "open" on the whole utterance, the
    # most permissive interpretation, per the plan's grammar design.
    # explicit=False flags this as a guess rather than something the user
    # actually said -- see ash/actions/semantic_fallback.py.
    return ParsedCommand(intent="open", target=normalized, explicit=False)


# Politeness around a command, ignored when matching: "can you set a
# timer for 5 minutes", "please pause", "open spotify for me thanks".
_POLITE_OPENERS = [
    "hey ash", "ash", "ok", "okay", "please", "can you please", "could you please",
    "would you please", "will you please", "can you", "could you", "would you", "will you",
    "i want you to", "i need you to", "i'd like you to",
]
_POLITE_CLOSERS = ["please", "for me", "thanks", "thank you", "thanks ash", "thank you ash"]
_OPENER_WORDS = sorted((o.split() for o in _POLITE_OPENERS), key=len, reverse=True)
_CLOSER_WORDS = sorted((c.split() for c in _POLITE_CLOSERS), key=len, reverse=True)


def _without_politeness(words: list[str]) -> tuple[int, int]:
    """(start, end) of `words` once polite openers/closers are dropped --
    never all of it ("thank you" on its own is itself a command)."""
    start, end = 0, len(words)
    changed = True
    while changed:
        changed = False
        for opener in _OPENER_WORDS:
            n = len(opener)
            if end - start > n and words[start:start + n] == opener:
                start += n
                changed = True
                break
        for closer in _CLOSER_WORDS:
            n = len(closer)
            if end - start > n and words[end - n:end] == closer:
                end -= n
                changed = True
                break
    return start, end


def _normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse spaces -- but keep what
    numbers need: speech-to-text writes "9:30am", "1.5 minutes",
    "15% of 80" and "2+2", and stripping all punctuation turned those
    into "930am", "15 minutes", "15 of 80" and "22". Commas are kept too
    (parse() matches without them, but hands them on in the target).
    Command phrases contain none of these characters."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s'%+*/^×÷.:,\-]", "", text)
    text = re.sub(r"(?<!\d)[.:]|[.:](?!\d)", "", text)  # "." and ":" only inside numbers
    text = re.sub(r"-(?!\s*\d)", "", text)              # "-" only as a minus sign
    text = re.sub(r"\s+", " ", text)
    return text.strip()
