from ash.nlu.matcher import match_app, match_candidates
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


def _spiderman_registry() -> Registry:
    return Registry(
        apps=[
            AppEntry(id="spider_man", names=["spider man"],
                     launch={"type": "exe", "target": "spiderman.exe"}),
            AppEntry(id="spider_man_remastered", names=["spider man remastered"],
                     launch={"type": "exe", "target": "spiderman_remastered.exe"}),
            AppEntry(id="notepad", names=["notepad"],
                     launch={"type": "exe", "target": "notepad.exe"}),
        ]
    )


def test_match_candidates_returns_multiple_above_cutoff():
    candidates = match_candidates("spider man", _spiderman_registry())

    ids = [c.entry.id for c in candidates]
    assert "spider_man" in ids
    assert "spider_man_remastered" in ids
    assert "notepad" not in ids


def test_match_candidates_respects_limit():
    candidates = match_candidates("spider man", _spiderman_registry(), limit=1)
    assert len(candidates) == 1


def test_match_candidates_dedupes_by_entry_id():
    registry = Registry(apps=[
        AppEntry(id="notepad", names=["notepad", "note pad", "notepad exe"],
                 launch={"type": "exe", "target": "notepad.exe"}),
    ])
    candidates = match_candidates("notepad", registry, limit=5)
    assert len(candidates) == 1


def test_match_candidates_empty_target():
    assert match_candidates("", _spiderman_registry()) == []


def test_match_candidates_below_cutoff_returns_empty():
    assert match_candidates("totally unrelated phrase", _spiderman_registry()) == []

