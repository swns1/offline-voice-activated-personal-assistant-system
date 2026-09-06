"""System volume/mute control via pycaw (Windows Core Audio COM API).

Follows the same CoInitialize/CoUninitialize-per-call-unit pattern as
ash/registry/start_menu_scan.py -- comtypes (pycaw's COM binding) is a
different binding from pywin32's pythoncom, but the apartment-init
discipline is the same.
"""
import logging
import re

import comtypes
from pycaw.pycaw import AudioUtilities

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_STEP = 0.10  # 10 percentage points per "volume up"/"volume down"
_PERCENT_RE = re.compile(r"\d{1,3}")


def _with_volume_interface(fn):
    comtypes.CoInitialize()
    try:
        interface = AudioUtilities.GetSpeakers().EndpointVolume
        return fn(interface)
    finally:
        comtypes.CoUninitialize()


def _adjust(delta: float) -> float:
    def do(interface) -> float:
        current = interface.GetMasterVolumeLevelScalar()
        new_level = max(0.0, min(1.0, current + delta))
        interface.SetMasterVolumeLevelScalar(new_level, None)
        return new_level
    return _with_volume_interface(do)


def _set_scalar(level: float) -> None:
    _with_volume_interface(lambda interface: interface.SetMasterVolumeLevelScalar(level, None))


def _set_mute(muted: bool) -> None:
    _with_volume_interface(lambda interface: interface.SetMute(1 if muted else 0, None))


def _get_mute() -> bool:
    return bool(_with_volume_interface(lambda interface: interface.GetMute()))


def toggle_mute(tts: TtsWorker, log: logging.Logger) -> None:
    """For the global keyboard hotkey (ash/utils/hotkey.py) -- no voice
    command triggers this, so no target/registry/config plumbing, just
    enough to give spoken feedback."""
    try:
        muted = _get_mute()
        _set_mute(not muted)
    except Exception:
        log.exception("Toggle mute failed")
        tts.say("I couldn't toggle mute.")
        return
    tts.say("Muted." if not muted else "Unmuted.")


def handle_volume_up(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    try:
        new_level = _adjust(_STEP)
    except Exception:
        log.exception("Volume up failed")
        tts.say("I couldn't change the volume.")
        return HandlerResult()
    log.info("Volume up -> %.0f%%", new_level * 100)
    tts.say("Volume up.")
    return HandlerResult()


def handle_volume_down(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    try:
        new_level = _adjust(-_STEP)
    except Exception:
        log.exception("Volume down failed")
        tts.say("I couldn't change the volume.")
        return HandlerResult()
    log.info("Volume down -> %.0f%%", new_level * 100)
    tts.say("Volume down.")
    return HandlerResult()


def handle_volume_set(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    match = _PERCENT_RE.search(target)
    if match is None:
        tts.say("I didn't catch a number.")
        return HandlerResult()

    percent = max(0, min(100, int(match.group())))
    try:
        _set_scalar(percent / 100)
    except Exception:
        log.exception("Volume set failed")
        tts.say("I couldn't change the volume.")
        return HandlerResult()
    log.info("Volume set -> %d%%", percent)
    tts.say(f"Volume set to {percent} percent.")
    return HandlerResult()


def handle_mute(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    try:
        _set_mute(True)
    except Exception:
        log.exception("Mute failed")
        tts.say("I couldn't mute.")
        return HandlerResult()
    tts.say("Muted.")
    return HandlerResult()


def handle_unmute(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    try:
        _set_mute(False)
    except Exception:
        log.exception("Unmute failed")
        tts.say("I couldn't unmute.")
        return HandlerResult()
    tts.say("Unmuted.")
    return HandlerResult()
