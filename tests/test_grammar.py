from ash.nlu.grammar import parse


def test_open_verb():
    cmd = parse("open notepad")
    assert cmd.intent == "open"
    assert cmd.target == "notepad"


def test_browser_search_verb_group():
    cmd = parse("search in browser for the weather")
    assert cmd.intent == "browser_search"
    assert cmd.target == "the weather"


def test_browser_search_does_not_collide_with_plain_search():
    # "search in browser for X" must NOT be swallowed by "search"'s own
    # bare "search " prefix.
    cmd = parse("search in browser for cats")
    assert cmd.intent == "browser_search"
    assert cmd.target == "cats"


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


def test_no_verb_default_is_flagged_not_explicit():
    # Distinguishes "nothing matched, we guessed open" from an actual
    # "open X" command -- see ash/actions/semantic_fallback.py, which
    # only reconsiders the former.
    assert parse("elden ring").explicit is False


def test_matched_verb_phrase_is_flagged_explicit():
    assert parse("open notepad").explicit is True
    assert parse("volume up").explicit is True


def test_remember_verb():
    cmd = parse("remember that I'm vegetarian")
    assert cmd.intent == "memory_remember"
    assert cmd.target == "i'm vegetarian"


def test_remember_bare_verb():
    cmd = parse("remember my dog's name is rex")
    assert cmd.intent == "memory_remember"
    assert cmd.target == "my dog's name is rex"


def test_forget_verb():
    cmd = parse("forget that I'm vegetarian")
    assert cmd.intent == "memory_forget"
    assert cmd.target == "i'm vegetarian"


def test_forget_everything():
    cmd = parse("forget everything")
    assert cmd.intent == "memory_forget"
    assert cmd.target == "everything"


def test_what_do_you_know_about_me():
    cmd = parse("what do you know about me")
    assert cmd.intent == "memory_recall"


def test_read_my_screen_is_ocr_not_describe():
    # "read" specifically means exact text -- routed to OCR, distinct
    # from "describe my screen"'s vision-model prose description.
    assert parse("read my screen").intent == "screen_read_text"


def test_describe_my_screen_is_still_vision_describe():
    assert parse("describe my screen").intent == "screen_describe"


def test_click_verb():
    cmd = parse("click the save button")
    assert cmd.intent == "screen_click"
    assert cmd.target == "save button"


def test_click_on_verb():
    cmd = parse("click on cancel")
    assert cmd.intent == "screen_click"
    assert cmd.target == "cancel"


def test_type_verb():
    cmd = parse("type hello world")
    assert cmd.intent == "screen_type"
    assert cmd.target == "hello world"


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


# Everyday playback phrases control whatever's playing, in any app
# (ash/actions/media.py); only phrases naming Spotify use Spotify's API.

def test_bare_pause_controls_any_player():
    cmd = parse("pause")
    assert cmd.intent == "media_pause"
    assert cmd.target == ""


def test_bare_skip_controls_any_player():
    assert parse("skip").intent == "media_next"


def test_whats_playing_reads_any_player():
    assert parse("what's playing").intent == "media_now_playing"


def test_pause_it_and_pause_that():
    assert parse("pause it").intent == "media_pause"
    assert parse("pause that").intent == "media_pause"


def test_skip_it_and_resume_it():
    assert parse("skip it").intent == "media_next"
    assert parse("resume it").intent == "media_resume"


def test_phrases_naming_spotify_use_spotify():
    assert parse("pause spotify").intent == "spotify_pause"
    assert parse("resume spotify").intent == "spotify_resume"
    assert parse("next song on spotify").intent == "spotify_skip"
    assert parse("what's playing on spotify").intent == "spotify_now_playing"


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


def test_bare_diagnostics():
    assert parse("are you working").intent == "diagnostics"
    assert parse("run diagnostics").intent == "diagnostics"
    assert parse("self test").intent == "diagnostics"


def test_routine_run_verb_group():
    cmd = parse("run my good morning routine")
    assert cmd.intent == "routine_run"
    assert cmd.target == "good morning routine"


def test_routine_run_start_the_phrasing():
    cmd = parse("start the good morning routine")
    assert cmd.intent == "routine_run"
    assert cmd.target == "good morning routine"


def test_bare_run_still_means_open_not_routine():
    # "run notepad" has no "my"/"the" qualifier -- must stay "open",
    # not get swallowed by the routine_run verb group.
    cmd = parse("run notepad")
    assert cmd.intent == "open"
    assert cmd.target == "notepad"


def test_bare_screen_describe_phrases():
    assert parse("what's on my screen").intent == "screen_describe"
    assert parse("describe my screen").intent == "screen_describe"
    # "read my screen" is deliberately NOT here -- routed to OCR
    # (screen_read_text) instead, see test_read_my_screen_is_ocr_not_describe.


def test_screen_describe_with_specific_question():
    cmd = parse("look at my screen and tell me what this error means")
    assert cmd.intent == "screen_describe"
    assert cmd.target == "what this error means"


def test_calendar_add_verb_group():
    cmd = parse("add to my calendar team meeting at 3pm")
    assert cmd.intent == "calendar_add"
    assert cmd.target == "team meeting at 3pm"


def test_bare_calendar_list_phrases():
    assert parse("what's on my calendar").intent == "calendar_list"
    assert parse("what's my next meeting").intent == "calendar_list"
    assert parse("check my calendar").intent == "calendar_list"


def test_reminder_set_recurring_daily_phrasing():
    cmd = parse("remind me every day at 8am to take medicine")
    assert cmd.intent == "reminder_set"
    assert cmd.target == "every day at 8am to take medicine"


# --- politeness around a command is ignored ------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize("said, intent, target", [
    ("Can you set a timer for 5 minutes?", "timer_set", "5 minutes"),
    ("Pause, please.", "media_pause", ""),
    ("Could you please open Spotify for me?", "open", "spotify"),
    ("Okay, what time is it?", "time_now", ""),
    ("Hey Ash, what day is Christmas?", "day_of", "christmas"),
    ("Please remember that I am vegetarian.", "memory_remember", "i am vegetarian"),
    ("I want you to lock my computer", "lock", ""),
    ("Stop, please", "stop", ""),
])
def test_polite_phrasing_is_understood(said, intent, target):
    command = parse(said)
    assert (command.intent, command.target) == (intent, target)


@pytest.mark.parametrize("said, intent", [("Thank you.", "thanks"), ("thanks", "thanks"), ("please", "open")])
def test_politeness_alone_is_not_stripped_to_nothing(said, intent):
    assert parse(said).intent == intent
