from ash.nlu.matcher import match_app, match_candidates, word_coverage
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


# --- a single shared word must not count as a match ---------------------

def _registry_with_python_docs() -> Registry:
    return Registry(apps=[
        AppEntry(id="python_3_13_64_bit",
                 names=["python 3.13 (64-bit)", "python 3.13 module docs (64-bit)"],
                 launch={"type": "exe", "target": "python.exe"}),
        AppEntry(id="elden_ring", names=["elden ring"],
                 launch={"type": "uri", "protocol": "steam",
                         "uri_template": "steam://rungameid/{appid}", "appid": "1245620"}),
    ])


def test_sentence_sharing_one_word_with_an_app_name_does_not_match():
    # Regression: WRatio scores this 85.5 against "python 3.13 module
    # docs (64-bit)" purely on "bit" -- it used to launch Python.
    registry = _registry_with_python_docs()
    assert match_app("turn it down a bit", registry) is None
    assert match_app("turn it down a bit", registry, guessed=True) is None
    assert match_candidates("turn it down a bit", registry) == []


def test_explicit_open_still_tolerates_loose_phrasing():
    result = match_app("my elden ring game", _registry_with_python_docs())
    assert result is not None and result.entry.id == "elden_ring"


def test_explicit_open_of_a_short_name_inside_a_long_one():
    result = match_app("python", _registry_with_python_docs())
    assert result is not None and result.entry.id == "python_3_13_64_bit"


def test_guessed_open_needs_every_meaningful_word_in_the_name():
    registry = _registry_with_python_docs()
    # "game" is filler, so everything meaningful is in the name.
    assert match_app("elden ring game", registry, guessed=True).entry.id == "elden_ring"
    # "tell"/"about" aren't in any app's name -- this is a sentence, not an app.
    assert match_app("tell me about elden ring", registry, guessed=True) is None


def test_guessed_open_tolerates_a_small_transcription_slip():
    registry = Registry(apps=[AppEntry(id="spotify", names=["spotify"],
                                       launch={"type": "exe", "target": "spotify.exe"})])
    result = match_app("spotfy", registry, guessed=True)
    assert result is not None and result.entry.id == "spotify"


def test_word_coverage():
    assert word_coverage("my elden ring game", "elden ring") == 1.0
    assert word_coverage("turn it down a bit", "python 3.13 module docs (64-bit)") == 1 / 3
    assert word_coverage("the app", "app a") == 0.5  # all-filler target falls back to every word
