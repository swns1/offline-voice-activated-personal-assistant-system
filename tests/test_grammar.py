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
