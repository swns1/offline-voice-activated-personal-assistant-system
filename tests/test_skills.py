"""The skill catalog (ash/skills/catalog.py) and what's built from it."""
import inspect
import logging
from collections import Counter

import pytest

from ash.actions import dispatcher
from ash.actions.help import handle_help
from ash.config import Config
from ash.nlu.grammar import parse
from ash.privacy.egress import FEATURES
from ash.registry.schema import Registry
from ash.skills import registry
from ash.skills.catalog import SKILLS


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_intents_are_unique():
    duplicates = [i for i, n in Counter(s.intent for s in SKILLS).items() if n > 1]
    assert duplicates == []


def test_no_phrase_is_claimed_by_two_skills():
    phrases = Counter(p for s in SKILLS for p in s.phrases)
    verbs = Counter(v for s in SKILLS for v in s.verbs)
    assert [p for p, n in phrases.items() if n > 1] == []
    assert [v for v, n in verbs.items() if n > 1] == []


def test_phrases_are_stored_normalized():
    """The grammar lowercases and strips punctuation (except apostrophes)
    before matching, so a phrase written any other way could never match."""
    for skill in SKILLS:
        for phrase in skill.phrases + skill.verbs:
            assert phrase == phrase.lower().strip(), (skill.intent, phrase)
            assert all(ch.isalnum() or ch in " '" for ch in phrase), (skill.intent, phrase)


@pytest.mark.parametrize("skill", [s for s in SKILLS if not s.hidden], ids=lambda s: s.intent)
def test_every_visible_skill_is_documented(skill):
    assert skill.description and skill.category
    assert skill.examples, f"{skill.intent}: add at least one example"
    assert skill.phrases or skill.verbs, f"{skill.intent}: how is it triggered?"


@pytest.mark.parametrize(
    "skill, example",
    [(s, e) for s in SKILLS for e in s.examples],
    ids=lambda v: v if isinstance(v, str) else v.intent,
)
def test_every_example_is_understood_as_its_own_command(skill, example):
    assert parse(example).intent == skill.intent


def test_hidden_skills_have_no_phrases():
    for skill in SKILLS:
        if skill.hidden:
            assert not skill.phrases and not skill.verbs, skill.intent


def test_online_features_exist():
    for skill in SKILLS:
        for key in skill.online:
            assert key in FEATURES, (skill.intent, key)


def test_confirmations_explain_before_asking():
    for skill in SKILLS:
        if skill.confirm:
            question = skill.confirm.question
            assert "are you sure" in question.lower(), skill.intent
            assert len(question.split(".")) >= 3, f"{skill.intent}: say what will happen, then ask"
            assert skill.confirm.declined_reply


def test_handlers_take_the_standard_arguments():
    for skill in SKILLS:
        params = inspect.signature(skill.handler).parameters
        assert len(params) == 5, skill.intent  # target, registry, tts, log, config


def test_dispatcher_table_covers_every_skill():
    assert set(dispatcher._HANDLERS) == {s.intent for s in SKILLS}


def test_verbs_are_tried_longest_first():
    lengths = [len(phrase) for phrase, _ in registry.verb_phrases()]
    assert lengths == sorted(lengths, reverse=True)


@pytest.mark.parametrize("said, intent", [
    ("search in browser for pizza", "browser_search"),
    ("search for pizza", "search"),
    ("run my good morning routine", "routine_run"),
    ("run notepad", "open"),
    ("play on spotify some jazz", "spotify_play"),
    ("play elden ring", "open"),
    ("What can you do?", "help"),
])
def test_longest_matching_phrase_wins(said, intent):
    assert parse(said).intent == intent


def test_help_lists_each_category_with_an_example():
    tts = FakeTts()
    handle_help("", Registry(), tts, logging.getLogger("t"), Config())

    from ash.skills.catalog import ASSISTANT

    reply = tts.said[-1]
    for category in registry.categories():
        if category != ASSISTANT:
            assert f"{category}: '" in reply
    assert "Apps and windows: 'open Spotify'." in reply
    assert "open_guess" not in reply
