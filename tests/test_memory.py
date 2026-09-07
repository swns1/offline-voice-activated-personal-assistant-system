import json
import logging

import pytest

from ash.actions import memory
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture(autouse=True)
def _isolated_memory_store(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(memory, "ensure_app_data_dirs", lambda: None)


def test_remember_persists_a_fact():
    tts = FakeTts()

    result = memory.handle_memory_remember("that I'm vegetarian", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "I'll remember that I'm vegetarian" in tts.said[0]
    saved = json.loads(memory.MEMORY_PATH.read_text(encoding="utf-8"))
    assert saved == {"facts": ["I'm vegetarian"]}


def test_remember_without_leading_that_still_works():
    memory.handle_memory_remember("my dog's name is rex", Registry(), FakeTts(), log, Config())

    assert memory._load_facts() == ["my dog's name is rex"]


def test_remember_duplicate_fact_is_not_added_twice():
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())

    assert memory._load_facts() == ["I'm vegetarian"]


def test_remember_empty_target_asks_what_to_remember():
    tts = FakeTts()

    result = memory.handle_memory_remember("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "What should I remember" in tts.said[0]
    assert memory._load_facts() == []


def test_recall_speaks_all_remembered_facts():
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())
    memory.handle_memory_remember("my dog's name is rex", Registry(), FakeTts(), log, Config())
    tts = FakeTts()

    memory.handle_memory_recall("", Registry(), tts, log, Config())

    assert "I'm vegetarian" in tts.said[0]
    assert "my dog's name is rex" in tts.said[0]


def test_recall_with_nothing_remembered_says_so():
    tts = FakeTts()

    memory.handle_memory_recall("", Registry(), tts, log, Config())

    assert "don't have anything remembered" in tts.said[0]


def test_forget_specific_fact_via_fuzzy_match():
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())
    memory.handle_memory_remember("my dog's name is rex", Registry(), FakeTts(), log, Config())
    tts = FakeTts()

    memory.handle_memory_forget("that I'm vegetarian", Registry(), tts, log, Config())

    assert "I've forgotten that I'm vegetarian" in tts.said[0]
    assert memory._load_facts() == ["my dog's name is rex"]


def test_forget_everything_clears_all_facts():
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())
    memory.handle_memory_remember("my dog's name is rex", Registry(), FakeTts(), log, Config())
    tts = FakeTts()

    memory.handle_memory_forget("everything", Registry(), tts, log, Config())

    assert tts.said == ["I've forgotten everything."]
    assert memory._load_facts() == []


def test_forget_with_no_facts_stored_says_so():
    tts = FakeTts()

    memory.handle_memory_forget("something", Registry(), tts, log, Config())

    assert "don't have anything remembered" in tts.said[0]


def test_forget_no_fuzzy_match_says_so():
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())
    tts = FakeTts()

    memory.handle_memory_forget("the moon landing", Registry(), tts, log, Config())

    assert "don't remember anything like that" in tts.said[0]
    assert memory._load_facts() == ["I'm vegetarian"]


def test_facts_context_empty_when_nothing_remembered():
    assert memory.facts_context() == ""


def test_facts_context_includes_remembered_facts():
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())

    assert "I'm vegetarian" in memory.facts_context()


def test_malformed_memory_file_is_treated_as_empty():
    memory.MEMORY_PATH.write_text("not valid json {{{", encoding="utf-8")

    assert memory._load_facts() == []
    # And a subsequent remember still works despite the corrupt file.
    memory.handle_memory_remember("I'm vegetarian", Registry(), FakeTts(), log, Config())
    assert memory._load_facts() == ["I'm vegetarian"]
