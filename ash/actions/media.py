"""Play, pause, skip and "what's playing" for whatever is playing on this
PC -- any app that shows up in Windows' media overlay (the Spotify app,
a YouTube tab in Chrome or Edge, VLC, Windows Media Player...). Uses
Windows' own media session API (GlobalSystemMediaTransportControls),
so it needs no account, works offline, and sends nothing anywhere --
unlike the Spotify skills, which go through Spotify's Web API.

If the media session API isn't available, play/pause/skip fall back to
pressing the virtual media keys (which can only toggle play/pause, and
can't say what's playing).
"""
import asyncio
import ctypes
import logging

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy.redact import said
from ash.registry.schema import Registry

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _SessionManager,
    )
except ImportError:  # pragma: no cover - depends on the installed packages
    _SessionManager = None

_VK_MEDIA_NEXT_TRACK = 0xB0
_VK_MEDIA_PREV_TRACK = 0xB1
_VK_MEDIA_PLAY_PAUSE = 0xB3
_KEYEVENTF_KEYUP = 0x2

# Friendly names for the app ids Windows reports for common players.
_APP_NAMES = {
    "spotify": "Spotify", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
    "vlc": "VLC", "zunemusic": "Media Player", "microsoft.media": "Media Player", "brave": "Brave",
}


def _app_name(app_id: str) -> str | None:
    lowered = app_id.lower()
    return next((name for key, name in _APP_NAMES.items() if key in lowered), None)


async def _session():
    manager = await _SessionManager.request_async()
    return manager.get_current_session()


def _press(virtual_key: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, _KEYEVENTF_KEYUP, 0)


def _control(action: str, fallback_key: int | None, done: str, nothing: str,
             tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    """Run `action` ("try_pause_async", ...) on the current media session."""
    if _SessionManager is None:
        if fallback_key is None:
            tts.say("I can't control media players on this PC.")
        else:
            _press(fallback_key)
            tts.say(done)
        return HandlerResult()

    async def run() -> bool | None:
        session = await _session()
        if session is None:
            return None
        return await getattr(session, action)()

    try:
        ok = asyncio.run(run())
    except Exception:
        log.exception("Media control %s failed", action)
        tts.say("Something went wrong controlling the media player.")
        return HandlerResult()
    if ok is None:
        tts.say(nothing)
    elif not ok:
        tts.say("The player didn't accept that.")
    else:
        tts.say(done)
    return HandlerResult()


def handle_media_pause(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _control("try_pause_async", _VK_MEDIA_PLAY_PAUSE, "Paused.", "Nothing is playing.", tts, log)


def handle_media_resume(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _control("try_play_async", _VK_MEDIA_PLAY_PAUSE, "Resuming.", "There's nothing to resume.", tts, log)


def handle_media_next(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _control("try_skip_next_async", _VK_MEDIA_NEXT_TRACK, "Skipping.", "Nothing is playing.", tts, log)


def handle_media_previous(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _control("try_skip_previous_async", _VK_MEDIA_PREV_TRACK, "Going back.", "Nothing is playing.", tts, log)


def handle_media_now_playing(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if _SessionManager is None:
        tts.say("I can't see what's playing on this PC.")
        return HandlerResult()

    async def run():
        session = await _session()
        if session is None:
            return None
        properties = await session.try_get_media_properties_async()
        return properties.title, properties.artist, _app_name(session.source_app_user_model_id or "")

    try:
        info = asyncio.run(run())
    except Exception:
        log.exception("Reading what's playing failed")
        tts.say("I couldn't tell what's playing.")
        return HandlerResult()
    if info is None or not info[0]:
        tts.say("Nothing is playing.")
        return HandlerResult()

    title, artist, app = info
    log.info("Now playing: %s", said(title))
    reply = f"{title} by {artist}" if artist else title
    tts.say(f"{reply}, in {app}." if app else f"{reply}.")
    return HandlerResult()
