from ash.nlu.matcher import match_app
from ash.registry.schema import AppEntry, Registry


def _registry() -> Registry:
    return Registry(
        apps=[
            AppEntry(id="notepad", names=["notepad", "note pad"],
                     launch={"type": "exe", "target": "notepad.exe"}),
            AppEntry(id="elden_ring", names=["elden ring", "ring game"],
                     launch={"type": "uri", "protocol": "steam",
                             "uri_template": "steam://rungameid/{appid}", "appid": "1245620"}),
        ]
    )


def test_exact_match():
    result = match_app("notepad", _registry())
    assert result is not None
    assert result.entry.id == "notepad"
    assert result.score == 100.0


def test_fuzzy_match_on_loose_phrasing():
    result = match_app("elden rings", _registry())
    assert result is not None
    assert result.entry.id == "elden_ring"
    assert result.score >= 80.0


def test_fuzzy_match_via_alias():
    result = match_app("the ring game", _registry())
    assert result is not None
    assert result.entry.id == "elden_ring"


def test_no_match_below_cutoff():
    result = match_app("some totally unrelated phrase", _registry())
    assert result is None


def test_empty_target_no_match():
    assert match_app("", _registry()) is None


def test_empty_registry_no_match():
    assert match_app("notepad", Registry()) is None
