"""Every voice command Ash understands, declared once.

To add a command: write its handler, then add one Skill here. The
grammar (ash/nlu/grammar.py), the dispatcher's handler table, the
confirmation gates, the lists the local AI may choose from (multi-step
commands, loosely phrased commands), and "what can you do" are all
built from this list by ash/skills/registry.py.

Phrase matching (see ash/nlu/grammar.py): a whole-utterance `phrase`
wins outright; otherwise the longest `verb` the utterance starts with
wins, if something follows it. Two skills may not claim the same phrase
(a test checks).
"""
from ash.actions.calculator import handle_calculate, handle_how_many
from ash.actions.calendar import handle_calendar_add, handle_calendar_list
from ash.actions.clock import handle_date_today, handle_day_of, handle_days_until, handle_time_now
from ash.actions.desktop_control import handle_screen_click, handle_screen_type
from ash.actions.diagnostics import handle_diagnostics
from ash.actions.help import handle_help, handle_thanks
from ash.actions.media import (
    handle_media_next,
    handle_media_now_playing,
    handle_media_pause,
    handle_media_previous,
    handle_media_resume,
)
from ash.actions.memory import handle_memory_forget, handle_memory_recall, handle_memory_remember
from ash.actions.notes import (
    handle_list_add,
    handle_list_clear,
    handle_list_read,
    handle_list_remove,
    handle_lists_list,
    handle_note_add,
    handle_note_clear,
    handle_note_read,
)
from ash.actions.open_app import handle_open, handle_open_guess
from ash.actions.privacy_controls import (
    handle_allow,
    handle_disallow,
    handle_network_activity,
    handle_offline_off,
    handle_offline_on,
)
from ash.actions.privacy_rights import (
    handle_data_inventory,
    handle_delete_all,
    handle_delete_voiceprint,
    handle_export,
)
from ash.actions.routines import handle_routine_run
from ash.actions.screen_text import handle_screen_read_text
from ash.actions.search import handle_browser_search, handle_search
from ash.actions.spotify import (
    handle_spotify_now_playing,
    handle_spotify_pause,
    handle_spotify_play,
    handle_spotify_previous,
    handle_spotify_resume,
    handle_spotify_skip,
)
from ash.actions.stop import handle_stop
from ash.actions.system_power import handle_lock, handle_shutdown, handle_sleep
from ash.actions.timers import handle_reminder_set, handle_timer_cancel, handle_timer_list, handle_timer_set
from ash.actions.vision import handle_screen_describe
from ash.actions.volume import handle_mute, handle_unmute, handle_volume_down, handle_volume_set, handle_volume_up
from ash.actions.weather import (
    handle_forget_city,
    handle_rain,
    handle_set_city,
    handle_weather,
    handle_whats_my_city,
)
from ash.actions.window import handle_close_app, handle_close_window, handle_minimize_window
from ash.skills.skill import Gate, Skill

APPS = "Apps and windows"
SEARCH = "Questions and search"
QUICK = "Quick answers"
MUSIC = "Music"
SYSTEM = "Your PC"
TIMERS = "Timers, reminders and routines"
CALENDAR = "Calendar"
SCREEN = "Your screen"
MEMORY = "Memory"
NOTES = "Notes and lists"
PRIVACY = "Privacy"
ASSISTANT = "Ash itself"

SKILLS: list[Skill] = [
    # --- apps and windows ------------------------------------------------
    Skill(
        "open", handle_open, APPS, "Open an app, game or website by name.",
        examples=("open Spotify", "launch Elden Ring"),
        verbs=("open", "launch", "start", "run", "play"),
        chainable=True,
    ),
    Skill(
        # The grammar's guess when no command phrase matched: the whole
        # utterance is treated as an app name, but only a close match opens.
        "open_guess", handle_open_guess, APPS, "Open an app when you just say its name.",
        hidden=True,
    ),
    Skill(
        "close_app", handle_close_app, APPS, "Force-quit an app by name (asks first).",
        examples=("close Discord",),
        verbs=("close", "quit", "exit"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "close_window", handle_close_window, APPS, "Close the window you're looking at.",
        examples=("close this window",),
        phrases=("close this window", "close the window", "close this"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "minimize_window", handle_minimize_window, APPS, "Minimize the window you're looking at.",
        examples=("minimize this window",),
        phrases=("minimize this window", "minimize the window", "minimize this", "minimize"),
        chainable=True, classifiable=True,
    ),

    # --- questions and search ----------------------------------------------
    Skill(
        "search", handle_search, SEARCH, "Answer a \"what is\" question using DuckDuckGo.",
        examples=("what is the Eiffel Tower", "who is Ada Lovelace"),
        verbs=("search for", "search", "look up", "what is", "what's", "who is", "who's", "google"),
        chainable=True, classifiable=True, online=("web_search",),
    ),
    Skill(
        "browser_search", handle_browser_search, SEARCH, "Open a web search in your browser.",
        examples=("search in browser for pizza near me",),
        verbs=("search in browser for", "browser search for", "search the web for"),
        classifiable=True,
    ),

    # --- quick answers (offline) ----------------------------------------------
    Skill(
        "time_now", handle_time_now, QUICK, "Say the time.",
        examples=("what time is it",),
        phrases=("what time is it", "what time is it now", "what time is it right now", "what's the time",
                 "whats the time", "what is the time", "tell me the time", "time"),
        classifiable=True,
    ),
    Skill(
        "date_today", handle_date_today, QUICK, "Say today's date.",
        examples=("what's the date",),
        phrases=("what's the date", "whats the date", "what is the date", "what's the date today",
                 "what's today's date", "whats todays date", "what is today's date", "what day is it",
                 "what day is today", "what day is it today", "what's today", "whats today"),
        classifiable=True,
    ),
    Skill(
        "day_of", handle_day_of, QUICK, "Say which day of the week a date or holiday falls on.",
        examples=("what day is Christmas", "what day is December 25"),
        verbs=("what day is", "what day of the week is", "which day is"),
        classifiable=True,
    ),
    Skill(
        "days_until", handle_days_until, QUICK, "Count the days until a date or holiday.",
        examples=("how many days until Christmas",),
        verbs=("how many days until", "how many days till", "how many days are left until",
               "how long until", "how long till", "how long is it until", "days until"),
        classifiable=True,
    ),

    Skill(
        "calculate", handle_calculate, QUICK,
        "Do maths or convert units, on this PC (\"what's\" questions are tried as maths first).",
        # "what's 15% of 80" works too, via web search's maths-first check.
        examples=("calculate 15% of 80", "convert 5 miles to kilometers", "how much is 12 times 7"),
        verbs=("calculate", "compute", "how much is", "convert"),
        classifiable=True,
    ),
    Skill(
        "how_many", handle_how_many, QUICK, "Answer \"how many X in a Y\" conversions (or search the web).",
        examples=("how many feet are in a mile",),
        verbs=("how many",),
        online=("web_search",),
    ),

    Skill(
        "weather", handle_weather, QUICK, "The weather for today or the next few days, where you live or anywhere.",
        examples=("what's the weather", "what's the weather tomorrow", "weather in Cebu"),
        phrases=("what's the weather", "whats the weather", "what is the weather", "how's the weather",
                 "hows the weather", "weather", "what's the weather like", "whats the weather like",
                 "what's the weather today", "what's the weather like today", "weather today",
                 "what's it like outside", "whats it like outside", "what's the forecast", "whats the forecast",
                 "forecast", "what's the temperature", "whats the temperature", "what is the temperature"),
        verbs=("what's the weather", "whats the weather", "what is the weather", "how's the weather",
               "hows the weather", "weather", "what's the forecast", "whats the forecast", "forecast",
               "what's the temperature", "whats the temperature", "what is the temperature"),
        classifiable=True, online=("weather",),
    ),
    Skill(
        "rain", handle_rain, QUICK, "Whether it's likely to rain today or on another day.",
        examples=("will it rain tomorrow", "do I need an umbrella"),
        phrases=("will it rain", "will it rain today", "is it going to rain", "is it going to rain today",
                 "do i need an umbrella", "do i need an umbrella today"),
        verbs=("will it rain", "is it going to rain", "do i need an umbrella"),
        classifiable=True, online=("weather",),
    ),
    Skill(
        "set_city", handle_set_city, QUICK, "Tell Ash your city, for the weather.",
        examples=("my city is Manila",),
        verbs=("my city is", "set my city to", "change my city to", "i live in", "my location is"),
        online=("weather",),
    ),
    Skill(
        "whats_my_city", handle_whats_my_city, QUICK, "Say which city Ash uses for the weather.",
        examples=("what's my city",),
        phrases=("what's my city", "whats my city", "where do i live"),
    ),
    Skill(
        "forget_city", handle_forget_city, QUICK, "Forget your city.",
        examples=("forget my city",),
        phrases=("forget my city", "delete my city", "forget my location"),
    ),

    # --- music --------------------------------------------------------------
    # Any player on this PC (Spotify app, YouTube tab, VLC...), through
    # Windows' media controls: offline, no account.
    Skill(
        "media_pause", handle_media_pause, MUSIC, "Pause whatever is playing, in any app.",
        examples=("pause the music",),
        phrases=("pause", "pause it", "pause that", "pause the music", "pause music", "pause the video",
                 "stop the music", "stop music"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "media_resume", handle_media_resume, MUSIC, "Resume what was playing, in any app.",
        examples=("resume",),
        phrases=("resume", "resume it", "resume that", "unpause", "resume the music", "resume music",
                 "play music", "play the music", "continue playing", "keep playing"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "media_next", handle_media_next, MUSIC, "Skip to the next song or video, in any app.",
        examples=("next song",),
        phrases=("skip", "skip it", "skip that", "skip song", "skip this song", "next song", "next track", "next"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "media_previous", handle_media_previous, MUSIC, "Go back to the previous song, in any app.",
        examples=("previous song",),
        phrases=("previous song", "previous track", "last song", "go back a song"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "media_now_playing", handle_media_now_playing, MUSIC, "Say what's playing, in any app.",
        examples=("what song is this",),
        phrases=("what's playing", "whats playing", "what song is this", "what's this song", "whats this song",
                 "what song is playing", "who sings this"),
        classifiable=True,
    ),
    Skill(
        "spotify_play", handle_spotify_play, MUSIC, "Play a song, artist or playlist on Spotify.",
        examples=("Spotify play some jazz",),
        verbs=("play something on spotify", "play on spotify", "spotify play"),
        chainable=True, classifiable=True, online=("spotify",),
    ),
    Skill(
        "spotify_pause", handle_spotify_pause, MUSIC, "Pause Spotify through your Spotify account.",
        examples=("pause Spotify",),
        phrases=("pause spotify",),
        chainable=True, classifiable=True, online=("spotify",),
    ),
    Skill(
        "spotify_resume", handle_spotify_resume, MUSIC, "Resume Spotify through your Spotify account.",
        examples=("resume Spotify",),
        phrases=("resume spotify",),
        chainable=True, classifiable=True, online=("spotify",),
    ),
    Skill(
        "spotify_skip", handle_spotify_skip, MUSIC, "Skip to the next song on Spotify, through your account.",
        examples=("next song on Spotify",),
        phrases=("next song on spotify", "skip on spotify", "skip spotify"),
        chainable=True, classifiable=True, online=("spotify",),
    ),
    Skill(
        "spotify_previous", handle_spotify_previous, MUSIC, "Go back a song on Spotify, through your account.",
        examples=("previous song on Spotify",),
        phrases=("previous song on spotify",),
        chainable=True, classifiable=True, online=("spotify",),
    ),
    Skill(
        "spotify_now_playing", handle_spotify_now_playing, MUSIC, "Say what's playing on your Spotify account.",
        examples=("what's playing on Spotify",),
        phrases=("what's playing on spotify", "whats playing on spotify"),
        classifiable=True, online=("spotify",),
    ),

    # --- your PC ------------------------------------------------------------
    Skill(
        "volume_up", handle_volume_up, SYSTEM, "Turn the volume up.",
        examples=("volume up",),
        phrases=("volume up", "turn the volume up", "turn up the volume"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "volume_down", handle_volume_down, SYSTEM, "Turn the volume down.",
        examples=("volume down",),
        phrases=("volume down", "turn the volume down", "turn down the volume"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "volume_set", handle_volume_set, SYSTEM, "Set the volume to a level from 0 to 100.",
        examples=("set the volume to 50",),
        verbs=("set the volume to", "set volume to", "volume to"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "mute", handle_mute, SYSTEM, "Mute the sound.",
        examples=("mute",),
        phrases=("mute", "mute the volume"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "unmute", handle_unmute, SYSTEM, "Unmute the sound.",
        examples=("unmute",),
        phrases=("unmute", "unmute the volume"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "lock", handle_lock, SYSTEM, "Lock the PC.",
        examples=("lock my computer",),
        phrases=("lock my computer", "lock the computer", "lock my pc", "lock computer"),
        classifiable=True,
    ),
    Skill(
        "sleep", handle_sleep, SYSTEM, "Put the PC to sleep.",
        examples=("go to sleep",),
        phrases=("go to sleep", "put the computer to sleep"),
        classifiable=True,
    ),
    Skill(
        "shutdown", handle_shutdown, SYSTEM, "Shut down the PC (asks first).",
        examples=("shut down",),
        phrases=("shut down", "shut down the computer", "shutdown", "turn off the computer"),
        confirm=Gate(
            question=("Shutting down will close all your apps, and anything you "
                      "haven't saved will be lost. Are you sure? Say yes to shut down."),
            declined_reply="Okay, I won't shut down.",
        ),
        classifiable=True,
    ),
    Skill(
        "diagnostics", handle_diagnostics, SYSTEM, "Check the microphone, local AI and Spotify.",
        examples=("are you working",),
        phrases=("are you working", "are you ok", "run diagnostics", "run a diagnostic", "self test"),
        classifiable=True,
    ),

    # --- timers, reminders and routines --------------------------------------
    Skill(
        "timer_set", handle_timer_set, TIMERS, "Set a timer.",
        examples=("set a timer for 10 minutes",),
        verbs=("set a timer for", "set timer for", "start a timer for", "timer for",
               "set an alarm for", "set alarm for", "start an alarm for"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "reminder_set", handle_reminder_set, TIMERS, "Remind you of something later, once or every day.",
        examples=("remind me at 3pm to call mom", "remind me every weekday at 8am to stretch"),
        verbs=("remind me to", "remind me in", "remind me"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "timer_cancel", handle_timer_cancel, TIMERS, "Cancel your timers and reminders.",
        examples=("cancel my timer",),
        phrases=("cancel my timer", "cancel my timers", "cancel the timer", "stop my timer"),
        classifiable=True,
    ),
    Skill(
        "timer_list", handle_timer_list, TIMERS, "List your timers and reminders.",
        examples=("list my timers",),
        phrases=("list my timers", "what timers do i have", "how much time is left"),
        classifiable=True,
    ),
    Skill(
        "routine_run", handle_routine_run, TIMERS, "Run one of your named routines.",
        examples=("run my good morning routine",),
        verbs=("run my", "run the", "start my", "start the"),
    ),

    # --- calendar --------------------------------------------------------------
    Skill(
        "calendar_list", handle_calendar_list, CALENDAR, "Say what's on your Outlook calendar.",
        examples=("what's on my calendar",),
        phrases=("what's on my calendar", "whats on my calendar", "what's my next meeting",
                 "whats my next meeting", "do i have any meetings today", "check my calendar"),
        classifiable=True,
    ),
    Skill(
        "calendar_add", handle_calendar_add, CALENDAR, "Add an event to your Outlook calendar (asks first).",
        examples=("add to my calendar team meeting at 3pm",),
        verbs=("add to my calendar", "add to calendar", "schedule an event"),
        classifiable=True,
    ),

    # --- your screen -------------------------------------------------------------
    Skill(
        "screen_describe", handle_screen_describe, SCREEN, "Describe what's on your screen (local AI).",
        examples=("what's on my screen", "look at my screen and tell me what this error means"),
        verbs=("what does my screen say about", "look at my screen and tell me", "check my screen and tell me"),
        phrases=("what's on my screen", "whats on my screen", "describe my screen", "describe the screen",
                 "what am i looking at", "look at my screen"),
        classifiable=True,
    ),
    Skill(
        # "read" means exact text -- OCR, not a vision model's paraphrase --
        # so these are deliberately kept apart from screen_describe.
        "screen_read_text", handle_screen_read_text, SCREEN, "Read out the exact text on your screen.",
        examples=("read my screen",),
        phrases=("read my screen", "read the screen", "read this screen", "read the text on my screen",
                 "read the text on the screen", "what does my screen say", "whats my screen say"),
        classifiable=True,
    ),
    Skill(
        "screen_click", handle_screen_click, SCREEN, "Click a button or menu item by its label (asks first).",
        examples=("click Save",),
        verbs=("click on", "click the", "click"),
        classifiable=True,
    ),
    Skill(
        "screen_type", handle_screen_type, SCREEN, "Type text into the active window (asks first).",
        examples=("type hello world",),
        verbs=("type",),
        classifiable=True,
    ),

    # --- memory ----------------------------------------------------------------------
    Skill(
        "memory_remember", handle_memory_remember, MEMORY, "Remember a fact about you.",
        examples=("remember that I'm vegetarian",),
        verbs=("remember that", "please remember that", "remember"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "memory_forget", handle_memory_forget, MEMORY, "Forget a remembered fact, or everything.",
        examples=("forget that I'm vegetarian",),
        verbs=("forget that", "forget about", "forget"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "memory_recall", handle_memory_recall, MEMORY, "Say everything you've asked Ash to remember.",
        examples=("what do you know about me",),
        phrases=("what do you know about me", "what do you remember about me", "what do you remember",
                 "what have you remembered"),
        chainable=True, classifiable=True,
    ),

    # --- notes and lists --------------------------------------------------------------------
    Skill(
        "note_add", handle_note_add, NOTES, "Take a note.",
        examples=("take a note buy flowers for mom",),
        verbs=("take a note", "make a note", "add a note", "take note", "note that", "write down", "jot down"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "note_read", handle_note_read, NOTES, "Read your latest notes.",
        examples=("read my notes",),
        phrases=("read my notes", "read me my notes", "what are my notes", "show my notes", "what did i note"),
        classifiable=True,
    ),
    Skill(
        "note_clear", handle_note_clear, NOTES, "Delete all your notes (asks first).",
        examples=("delete my notes",),
        phrases=("delete my notes", "delete all my notes", "clear my notes", "erase my notes"),
    ),
    Skill(
        "list_add", handle_list_add, NOTES, "Add things to a list, like your shopping list.",
        examples=("add milk and eggs to my shopping list",),
        verbs=("add", "put"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "list_read", handle_list_read, NOTES, "Read a list.",
        examples=("what's on my shopping list",),
        verbs=("what's on my", "whats on my", "what is on my", "read my", "read me my", "show me my"),
        classifiable=True,
    ),
    Skill(
        "list_remove", handle_list_remove, NOTES, "Take things off a list.",
        examples=("remove milk from my shopping list",),
        # Not "take": "take me to YouTube", "take a picture" aren't list commands.
        verbs=("remove", "cross", "delete"),
        chainable=True, classifiable=True,
    ),
    Skill(
        "list_clear", handle_list_clear, NOTES, "Delete a whole list (asks first).",
        examples=("clear my shopping list",),
        verbs=("clear my", "clear the", "empty my", "delete my"),
    ),
    Skill(
        "lists_list", handle_lists_list, NOTES, "Say which lists you have.",
        examples=("what lists do I have",),
        phrases=("what lists do i have", "read my lists", "show my lists"),
        classifiable=True,
    ),

    # --- privacy -------------------------------------------------------------------------
    Skill(
        "privacy_offline_on", handle_offline_on, PRIVACY, "Turn on offline mode: nothing leaves this PC.",
        examples=("go offline",),
        phrases=("go offline", "offline mode", "turn on offline mode", "enable offline mode"),
        classifiable=True,
    ),
    Skill(
        "privacy_offline_off", handle_offline_off, PRIVACY, "Turn offline mode off.",
        examples=("go online",),
        phrases=("go online", "turn off offline mode", "disable offline mode"),
        classifiable=True,
    ),
    Skill(
        "consent_grant", handle_allow, PRIVACY, "Allow an online feature.",
        examples=("allow web search",),
        verbs=("allow",),
    ),
    Skill(
        "consent_revoke", handle_disallow, PRIVACY, "Stop allowing an online feature.",
        examples=("stop allowing Spotify",),
        verbs=("stop allowing", "don't allow", "dont allow", "disallow", "revoke"),
    ),
    Skill(
        "network_activity", handle_network_activity, PRIVACY, "Say what Ash has sent online recently.",
        examples=("what have you sent online",),
        phrases=("what have you sent online", "what did you send online", "show my network activity",
                 "network activity"),
        classifiable=True,
    ),
    Skill(
        "privacy_data_inventory", handle_data_inventory, PRIVACY, "Say what data Ash keeps about you.",
        examples=("what data do you have",),
        phrases=("what data do you have", "what data do you have about me", "what data do you keep",
                 "what do you store about me", "what are you storing about me", "show my data"),
        classifiable=True,
    ),
    Skill(
        "privacy_export", handle_export, PRIVACY, "Save a readable copy of your data to Documents.",
        examples=("export my data",),
        phrases=("export my data", "export all my data", "download my data", "give me a copy of my data"),
        classifiable=True,
    ),
    Skill(
        "privacy_delete_voiceprint", handle_delete_voiceprint, PRIVACY, "Delete your voiceprint (asks first).",
        examples=("delete my voiceprint",),
        phrases=("delete my voiceprint", "delete my voice print", "forget my voice"),
    ),
    Skill(
        "privacy_delete_all", handle_delete_all, PRIVACY, "Delete everything Ash keeps about you (asks first).",
        examples=("delete all my data",),
        phrases=("delete all my data", "erase all my data", "wipe all my data",
                 "delete everything you know about me"),
    ),

    # --- Ash itself -------------------------------------------------------------------------
    Skill(
        "stop", handle_stop, ASSISTANT, "Stop talking.",
        examples=("stop",),
        phrases=("stop", "cancel", "stop talking", "be quiet", "quiet"),
    ),
    Skill(
        "help", handle_help, ASSISTANT, "Say what Ash can do.",
        examples=("what can you do",),
        phrases=("what can you do", "what can i say", "what can i ask you", "help"),
    ),
    Skill(
        "thanks", handle_thanks, ASSISTANT, "You're welcome.",
        examples=("thank you",),
        phrases=("thank you", "thanks", "thanks ash", "thank you ash", "thank you so much", "thanks a lot"),
    ),
]
