"""Splits a transcript into (intent, target) via an ordered list of verb
phrases. Longest phrase first within a group so "search for" matches
before the bare "search" prefix would swallow it. New verb groups
(media, system, assistant control) are added in later phases as pure
data here, not a redesign.
"""
import re

from ash.nlu.intents import ParsedCommand

# Order matters: groups are tried top-to-bottom, first match wins. Spotify
# playback must come before "open" -- "open"'s own verb list already
# includes bare "play" (so "play elden ring" launches a game), so Spotify
# phrases need an explicit disambiguator ("spotify play X" / "play on
# spotify X") rather than reusing bare "play", which would either collide
# with or have to steal the existing game-launch phrasing.
_VERB_GROUPS: list[tuple[str, list[str]]] = [
    # Must precede "search" below -- "search in browser for X" would
    # otherwise be swallowed by "search"'s own bare "search " prefix.
    ("browser_search", ["search in browser for", "browser search for", "search the web for"]),
    ("search", ["search for", "search", "look up", "what is", "what's",
                "who is", "who's", "google"]),
    ("spotify_play", ["play something on spotify", "play on spotify", "spotify play"]),
    ("reminder_set", ["remind me to", "remind me in", "remind me"]),
    ("timer_set", ["set a timer for", "set timer for", "start a timer for", "timer for",
                   "set an alarm for", "set alarm for", "start an alarm for"]),
    ("volume_set", ["set the volume to", "set volume to", "volume to"]),
    ("calendar_add", ["add to my calendar", "add to calendar", "schedule an event"]),
    ("screen_describe", ["what does my screen say about", "look at my screen and tell me",
                          "check my screen and tell me"]),
    ("close_app", ["close", "quit", "exit"]),
    # "run"/"start" are also bare verbs in "open" below -- these phrases
    # need the extra "my"/"the" qualifier to stay ahead of it in the
    # list, or "run my good morning routine" would be swallowed as
    # "open" trying to launch an app named "my good morning routine".
    ("routine_run", ["run my", "run the", "start my", "start the"]),
    ("open", ["open", "launch", "start", "run", "play"]),
]

# Target-less commands: the whole normalized utterance is the trigger, not
# a verb prefix with something after it.
_BARE_PHRASES: dict[str, str] = {
    "pause": "spotify_pause",
    "pause it": "spotify_pause",
    "pause that": "spotify_pause",
    "pause spotify": "spotify_pause",
    "resume": "spotify_resume",
    "resume it": "spotify_resume",
    "resume that": "spotify_resume",
    "resume spotify": "spotify_resume",
    "unpause": "spotify_resume",
    "skip": "spotify_skip",
    "skip it": "spotify_skip",
    "skip that": "spotify_skip",
    "skip song": "spotify_skip",
    "next song": "spotify_skip",
    "next track": "spotify_skip",
    "previous song": "spotify_previous",
    "previous track": "spotify_previous",
    "what's playing": "spotify_now_playing",
    "whats playing": "spotify_now_playing",

    "mute": "mute",
    "mute the volume": "mute",
    "unmute": "unmute",
    "unmute the volume": "unmute",
    "volume up": "volume_up",
    "turn the volume up": "volume_up",
    "turn up the volume": "volume_up",
    "volume down": "volume_down",
    "turn the volume down": "volume_down",
    "turn down the volume": "volume_down",

    "lock my computer": "lock",
    "lock the computer": "lock",
    "lock my pc": "lock",
    "lock computer": "lock",
    "go to sleep": "sleep",
    "put the computer to sleep": "sleep",
    "shut down": "shutdown",
    "shut down the computer": "shutdown",
    "shutdown": "shutdown",
    "turn off the computer": "shutdown",

    "cancel my timer": "timer_cancel",
    "cancel my timers": "timer_cancel",
    "cancel the timer": "timer_cancel",
    "stop my timer": "timer_cancel",
    "list my timers": "timer_list",
    "what timers do i have": "timer_list",
    "how much time is left": "timer_list",

    "stop": "stop",
    "cancel": "stop",
    "stop talking": "stop",
    "be quiet": "stop",
    "quiet": "stop",

    "close this window": "close_window",
    "close the window": "close_window",
    "close this": "close_window",
    "minimize this window": "minimize_window",
    "minimize the window": "minimize_window",
    "minimize this": "minimize_window",
    "minimize": "minimize_window",

    "are you working": "diagnostics",
    "are you ok": "diagnostics",
    "run diagnostics": "diagnostics",
    "run a diagnostic": "diagnostics",
    "self test": "diagnostics",

    "what's on my calendar": "calendar_list",
    "whats on my calendar": "calendar_list",
    "what's my next meeting": "calendar_list",
    "whats my next meeting": "calendar_list",
    "do i have any meetings today": "calendar_list",
    "check my calendar": "calendar_list",

    "what's on my screen": "screen_describe",
    "whats on my screen": "screen_describe",
    "describe my screen": "screen_describe",
    "describe the screen": "screen_describe",
    "read my screen": "screen_describe",
    "what am i looking at": "screen_describe",
    "look at my screen": "screen_describe",
}


def parse(text: str) -> ParsedCommand:
    normalized = _normalize(text)
    if not normalized:
        return ParsedCommand(intent="unknown", target="")

    bare_intent = _BARE_PHRASES.get(normalized)
    if bare_intent:
        return ParsedCommand(intent=bare_intent, target="")

    for intent, phrases in _VERB_GROUPS:
        for phrase in sorted(phrases, key=len, reverse=True):
            if normalized == phrase or normalized.startswith(phrase + " "):
                target = normalized[len(phrase):].strip()
                if target:
                    return ParsedCommand(intent=intent, target=target)

    # No verb recognized: default to "open" on the whole utterance, the
    # most permissive interpretation, per the plan's grammar design.
    # explicit=False flags this as a guess rather than something the user
    # actually said -- see ash/actions/semantic_fallback.py.
    return ParsedCommand(intent="open", target=normalized, explicit=False)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
