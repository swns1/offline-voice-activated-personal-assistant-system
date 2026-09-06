from ash.actions.routines import find_routine, resolve_routine_name
from ash.registry.schema import Registry


def _registry_with_routine() -> Registry:
    return Registry(routines={
        "good morning": [
            {"intent": "volume_set", "target": "30"},
            {"intent": "open", "target": "spotify"},
        ],
    })


def test_resolve_routine_name_strips_trailing_routine_word():
    assert resolve_routine_name("good morning routine") == "good morning"


def test_resolve_routine_name_without_trailing_word():
    assert resolve_routine_name("good morning") == "good morning"


def test_resolve_routine_name_lowercases_and_strips():
    assert resolve_routine_name("  Good Morning Routine  ") == "good morning"


def test_find_routine_exact_match():
    steps = find_routine("good morning", _registry_with_routine())
    assert steps == [
        {"intent": "volume_set", "target": "30"},
        {"intent": "open", "target": "spotify"},
    ]


def test_find_routine_fuzzy_match():
    steps = find_routine("good mornin", _registry_with_routine())
    assert steps is not None


def test_find_routine_no_match_returns_none():
    assert find_routine("bedtime", _registry_with_routine()) is None


def test_find_routine_empty_name_returns_none():
    assert find_routine("", _registry_with_routine()) is None


def test_find_routine_no_routines_configured_returns_none():
    assert find_routine("good morning", Registry()) is None
