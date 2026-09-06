from ash.nlu import context


def test_resolve_target_passes_through_non_pronoun():
    assert context.resolve_target("open", "notepad") == "notepad"


def test_resolve_target_it_resolves_to_last_app_for_open():
    context.remember_app("discord")
    assert context.resolve_target("open", "it") == "discord"


def test_resolve_target_it_resolves_to_last_app_for_close():
    context.remember_app("discord")
    assert context.resolve_target("close_app", "it") == "discord"


def test_resolve_target_that_and_this_also_work():
    context.remember_app("discord")
    assert context.resolve_target("open", "that") == "discord"
    assert context.resolve_target("open", "this") == "discord"


def test_resolve_target_is_case_and_whitespace_insensitive():
    context.remember_app("discord")
    assert context.resolve_target("open", " It ") == "discord"


def test_resolve_target_search_uses_last_search():
    context.remember_search("weather tomorrow")
    assert context.resolve_target("search", "that") == "weather tomorrow"


def test_resolve_target_spotify_play_uses_last_track():
    context.remember_spotify_track("Bohemian Rhapsody")
    assert context.resolve_target("spotify_play", "it") == "Bohemian Rhapsody"


def test_resolve_target_pronoun_with_no_context_falls_through_unresolved():
    # Nothing remembered yet -- pass the literal pronoun through rather
    # than resolving to None/empty, so the handler's own "no match"
    # message still makes sense.
    assert context.resolve_target("open", "it") == "it"


def test_resolve_target_pronoun_for_untracked_intent_passes_through():
    context.remember_app("discord")
    assert context.resolve_target("volume_set", "it") == "it"


def test_resolve_target_strips_trailing_again():
    context.remember_search("pizza near me")
    assert context.resolve_target("search", "that again") == "pizza near me"


def test_resolve_target_strips_trailing_please():
    context.remember_app("discord")
    assert context.resolve_target("open", "it please") == "discord"


def test_context_is_independent_per_field():
    context.remember_app("discord")
    context.remember_search("weather")
    context.remember_spotify_track("some song")

    assert context.resolve_target("open", "it") == "discord"
    assert context.resolve_target("search", "it") == "weather"
    assert context.resolve_target("spotify_play", "it") == "some song"
