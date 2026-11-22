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


@cache
def bare_phrases() -> dict[str, str]:
    """Whole-utterance phrase -> intent."""
    return {phrase: skill.intent for skill in all_skills() for phrase in skill.phrases}


@cache
def verb_phrases() -> tuple[tuple[str, str], ...]:
    """(verb phrase, intent), longest phrase first: the longest verb an
    utterance starts with wins, so "search in browser for X" beats
    "search X" and "run my X routine" beats "run X" without any
    hand-maintained ordering."""
    pairs = [(verb, skill.intent) for skill in all_skills() for verb in skill.verbs]
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
