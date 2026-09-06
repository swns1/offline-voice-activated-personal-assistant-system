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


def test_bare_mute_and_unmute():
    assert parse("mute").intent == "mute"
    assert parse("unmute").intent == "unmute"


def test_volume_up_down_bare_phrases():
    assert parse("turn the volume up").intent == "volume_up"
    assert parse("turn the volume down").intent == "volume_down"


def test_volume_set_verb_group():
    cmd = parse("set the volume to 50")
    assert cmd.intent == "volume_set"
    assert cmd.target == "50"


def test_bare_lock_sleep_shutdown():
    assert parse("lock my computer").intent == "lock"
    assert parse("go to sleep").intent == "sleep"
    assert parse("shut down").intent == "shutdown"


def test_bare_sleep_alone_is_not_a_trigger():
    # A single generic word is intentionally not enough to trigger sleep --
    # it falls through to the default "open" interpretation like any other
    # unrecognized single word would.
    cmd = parse("sleep")
    assert cmd.intent == "open"


def test_reminder_set_verb_group():
    cmd = parse("remind me in 5 minutes to check the oven")
    assert cmd.intent == "reminder_set"
    assert cmd.target == "5 minutes to check the oven"


def test_reminder_set_with_absolute_time_phrasing():
    cmd = parse("remind me at 3pm to check the oven")
    assert cmd.intent == "reminder_set"
    assert cmd.target == "at 3pm to check the oven"


def test_timer_set_verb_group_does_not_collide_with_open():
    cmd = parse("start a timer for 5 minutes")
    assert cmd.intent == "timer_set"
    assert cmd.target == "5 minutes"


def test_bare_timer_cancel_and_list():
    assert parse("cancel my timer").intent == "timer_cancel"
    assert parse("list my timers").intent == "timer_list"


def test_bare_stop_and_cancel():
    assert parse("stop").intent == "stop"
    assert parse("cancel").intent == "stop"
    assert parse("be quiet").intent == "stop"


def test_cancel_my_timer_does_not_collide_with_bare_cancel():
    # "cancel" alone -> stop, but the longer exact phrase "cancel my
    # timer" is a distinct dict key and must still resolve separately.
    assert parse("cancel my timer").intent == "timer_cancel"


def test_close_app_verb_group():
    cmd = parse("close discord")
    assert cmd.intent == "close_app"
    assert cmd.target == "discord"


def test_quit_and_exit_also_close_app():
    assert parse("quit spotify").intent == "close_app"
    assert parse("exit notepad").intent == "close_app"


def test_bare_close_this_window():
    assert parse("close this window").intent == "close_window"
    assert parse("close this").intent == "close_window"


def test_bare_minimize():
    assert parse("minimize").intent == "minimize_window"
    assert parse("minimize this window").intent == "minimize_window"
