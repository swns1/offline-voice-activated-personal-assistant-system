from ash.nlu.grammar import parse


def test_open_verb():
    cmd = parse("open notepad")
    assert cmd.intent == "open"
    assert cmd.target == "notepad"


def test_search_verb_prefers_longest_phrase():
    cmd = parse("search for the meaning of ubiquitous")
    assert cmd.intent == "search"
    assert cmd.target == "the meaning of ubiquitous"


def test_what_is_phrase():
    cmd = parse("what is the meaning of ubiquitous")
    assert cmd.intent == "search"
    assert cmd.target == "the meaning of ubiquitous"


def test_no_verb_defaults_to_open():
    cmd = parse("elden ring")
    assert cmd.intent == "open"
    assert cmd.target == "elden ring"


def test_empty_text_is_unknown():
    cmd = parse("   ")
    assert cmd.intent == "unknown"


def test_punctuation_and_case_normalized():
    cmd = parse("Open, Notepad!")
    assert cmd.intent == "open"
    assert cmd.target == "notepad"


def test_bare_play_still_opens_app_or_game():
    cmd = parse("play elden ring")
    assert cmd.intent == "open"
    assert cmd.target == "elden ring"


def test_spotify_play_leading_disambiguator():
    cmd = parse("spotify play bohemian rhapsody")
    assert cmd.intent == "spotify_play"
    assert cmd.target == "bohemian rhapsody"


def test_spotify_play_on_spotify_phrasing():
    cmd = parse("play on spotify bohemian rhapsody")
    assert cmd.intent == "spotify_play"
    assert cmd.target == "bohemian rhapsody"


def test_bare_pause_is_spotify_pause():
    cmd = parse("pause")
    assert cmd.intent == "spotify_pause"
    assert cmd.target == ""


def test_bare_skip_is_spotify_skip():
    cmd = parse("skip")
    assert cmd.intent == "spotify_skip"


def test_whats_playing_is_spotify_now_playing():
    cmd = parse("what's playing")
    assert cmd.intent == "spotify_now_playing"
