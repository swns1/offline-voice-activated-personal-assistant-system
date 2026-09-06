"""Global keyboard hotkey (works even when Ash isn't the focused
window) for toggling mute -- uses the `keyboard` package rather than a
raw Win32 RegisterHotKey + message loop, since Ash doesn't otherwise
own a window/message pump on the main thread (the tray icon's pystray
loop, when enabled, is a separate one).

Registration itself is confirmed to succeed without error (no admin
rights needed just to call add_hotkey()). Whether the hotkey actually
FIRES on a real keypress is a separate, known-flaky question with this
library -- `keyboard`'s low-level hook can silently fail to receive
events depending on privilege/session context. Tried to verify this
live (both add_hotkey() and a raw keyboard.hook(), triggered via
keyboard.send()) and neither received the injected event in this
session's execution context, which isn't running elevated -- but this
proves only that synthetic injection didn't work *here*; it doesn't
confirm real hardware keypresses will or won't reach the hook on your
desktop session. If the hotkey doesn't respond, try running Ash as
Administrator -- that's the most common fix for this library.
Registration failure is caught and logged either way, so Ash still
runs fine without it.
"""
import logging

import keyboard

from ash.actions.volume import toggle_mute
from ash.audio.tts import TtsWorker


def register_mute_hotkey(hotkey: str, tts: TtsWorker, log: logging.Logger) -> None:
    try:
        keyboard.add_hotkey(hotkey, lambda: toggle_mute(tts, log))
    except Exception:
        log.exception("Failed to register mute hotkey %r", hotkey)
        return
    log.info("Registered mute hotkey: %s", hotkey)
