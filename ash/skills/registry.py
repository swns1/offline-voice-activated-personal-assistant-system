"""Everything derived from the skill catalog (ash/skills/catalog.py).

The catalog imports every action module, and several action modules
use the grammar -- so the catalog is imported lazily, on first use,
rather than when this module is imported. That keeps the import graph
acyclic no matter which module asks first.
"""
from functools import cache

from ash.skills.skill import Gate, Handler, Skill


@cache
def all_skills() -> tuple[Skill, ...]:
    from ash.skills.catalog import SKILLS
    return tuple(SKILLS)


@cache
def _by_intent() -> dict[str, Skill]:
    return {skill.intent: skill for skill in all_skills()}


def get(intent: str) -> Skill | None:
    return _by_intent().get(intent)


def handlers() -> dict[str, Handler]:
    """intent -> handler, for the dispatcher (a fresh dict each call, so
    the dispatcher -- and tests -- can patch entries safely)."""
    return {skill.intent: skill.handler for skill in all_skills()}


def _spellings(phrase: str) -> list[str]:
    """A phrase as written in the catalog, plus how speech-to-text may
    spell it: Whisper writes "what's my city" as "what is my city" as
    often as not (found by scripts/stt_accuracy.py)."""
    spellings = [phrase]
    for short, long in (("what's ", "what is "), ("whats ", "what is ")):
        if phrase.startswith(short):
            spellings.append(long + phrase[len(short):])
    return spellings


@cache
def bare_phrases() -> dict[str, str]:
    """Whole-utterance phrase -> intent. A phrase written explicitly in
    the catalog wins over another phrase's alternative spelling."""
    phrases: dict[str, str] = {}
    for skill in all_skills():
        for phrase in skill.phrases:
            for spelling in _spellings(phrase)[1:]:
                phrases.setdefault(spelling, skill.intent)
    for skill in all_skills():
        for phrase in skill.phrases:
            phrases[phrase] = skill.intent
    return phrases


@cache
def verb_phrases() -> tuple[tuple[str, str], ...]:
    """(verb phrase, intent), longest phrase first: the longest verb an
    utterance starts with wins, so "search in browser for X" beats
    "search X" and "run my X routine" beats "run X" without any
    hand-maintained ordering."""
    explicit = {verb for skill in all_skills() for verb in skill.verbs}
    pairs = [(spelling, skill.intent) for skill in all_skills() for verb in skill.verbs
             for spelling in _spellings(verb) if spelling == verb or spelling not in explicit]
    return tuple(sorted(pairs, key=lambda pair: len(pair[0]), reverse=True))


def confirmation_gate(intent: str) -> Gate | None:
    skill = get(intent)
    return skill.confirm if skill else None


@cache
def chainable_intents() -> tuple[str, ...]:
    return tuple(skill.intent for skill in all_skills() if skill.chainable)


@cache
def classifiable_intents() -> tuple[str, ...]:
    return tuple(skill.intent for skill in all_skills() if skill.classifiable)


def visible_skills() -> list[Skill]:
    return [skill for skill in all_skills() if not skill.hidden]


def categories() -> dict[str, list[Skill]]:
    """Category -> its visible skills, in catalog order."""
    grouped: dict[str, list[Skill]] = {}
    for skill in visible_skills():
        grouped.setdefault(skill.category, []).append(skill)
    return grouped
