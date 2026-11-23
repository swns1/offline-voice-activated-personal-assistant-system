"""Your PC: battery, storage, screenshots, screen brightness, and dark or
light mode. All of it local -- nothing is sent anywhere.

- "what's my battery" / "how much storage do I have"
- "take a screenshot" (saved to Pictures\\Screenshots)
- "set the brightness to 60" / "brightness up" / "brightness down"
  (built-in laptop screens; most desktop monitors can't be dimmed by
  software, and Ash says so)
- "turn on dark mode" / "switch to light mode"
"""
import ctypes
import logging
import re
from datetime import datetime
from pathlib import Path

import psutil

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_BRIGHTNESS_STEP = 10
_WMI_PATH = "winmgmts:\\\\.\\root\\WMI"
_THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_GB = 1024 ** 3


# --- battery and storage ---------------------------------------------------------------

def handle_battery(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    battery = psutil.sensors_battery()
    if battery is None:
        tts.say("This PC doesn't have a battery.")
        return HandlerResult()
    percent = round(battery.percent)
    if battery.power_plugged:
        state = "and charging" if percent < 100 else "and plugged in"
        tts.say(f"Your battery is at {percent}%, {state}.")
    elif battery.secsleft not in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED) and battery.secsleft > 0:
        hours, minutes = divmod(battery.secsleft // 60, 60)
        left = f"{hours} hour{'' if hours == 1 else 's'} and {minutes} minutes" if hours else f"{minutes} minutes"
        tts.say(f"Your battery is at {percent}%, about {left} left.")
    else:
        tts.say(f"Your battery is at {percent}%.")
    return HandlerResult()


def _fixed_drives() -> list[str]:
    drives = []
    for partition in psutil.disk_partitions(all=False):
        if "cdrom" in partition.opts or not partition.fstype:
            continue
        drives.append(partition.mountpoint)
    return drives


def handle_storage(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    parts = []
    for mount in _fixed_drives():
        try:
            usage = psutil.disk_usage(mount)
        except OSError:
            continue  # e.g. a card reader with no card
        letter = mount.rstrip(":\\/")
        parts.append(f"{round(usage.free / _GB)} gigabytes free on drive {letter}, out of {round(usage.total / _GB)}")
    if not parts:
        tts.say("I couldn't read your drives.")
    else:
        tts.say("You have " + "; and ".join(parts) + ".")
    return HandlerResult()


# --- screenshots ------------------------------------------------------------------------------

def _pictures_dir() -> Path:
    try:
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Pictures))
    except Exception:
        return Path.home() / "Pictures"


def handle_screenshot(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    from PIL import ImageGrab

    folder = _pictures_dir() / "Screenshots"
    path = folder / f"Ash screenshot {datetime.now():%Y-%m-%d %H%M%S}.png"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(all_screens=True).save(path)
    except Exception:
        log.exception("Screenshot failed")
        tts.say("I couldn't take a screenshot.")
        return HandlerResult()
    log.info("Saved a screenshot to the Pictures folder")
    tts.say("Saved a screenshot to your Pictures folder, in Screenshots.")
    return HandlerResult()


# --- brightness -------------------------------------------------------------------------------

def _wmi():
    import win32com.client
    return win32com.client.GetObject(_WMI_PATH)


def get_brightness() -> int | None:
    """The built-in screen's brightness (0-100), or None if this PC's
    screen can't be controlled by software."""
    try:
        screens = list(_wmi().InstancesOf("WmiMonitorBrightness"))
    except Exception:
        return None
    return int(screens[0].CurrentBrightness) if screens else None


def set_brightness(level: int) -> bool:
    try:
        methods = list(_wmi().InstancesOf("WmiMonitorBrightnessMethods"))
        if not methods:
            return False
        methods[0].WmiSetBrightness(0, max(0, min(100, level)))
    except Exception:
        return False
    return True


def _change_brightness(level_for, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    current = get_brightness()
    if current is None:
        tts.say("I can't change the brightness of this screen. Most desktop monitors have to be "
                "adjusted with their own buttons.")
        return HandlerResult()
    level = max(0, min(100, level_for(current)))
    if not set_brightness(level):
        log.warning("Setting brightness failed")
        tts.say("I couldn't change the brightness.")
        return HandlerResult()
    tts.say(f"Brightness set to {level}%.")
    return HandlerResult()


def handle_brightness_set(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    match = re.search(r"\d+", target)
    if not match:
        tts.say("What brightness, from 0 to 100?")
        return HandlerResult()
    level = int(match.group())
    return _change_brightness(lambda current: level, tts, log)


def handle_brightness_up(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _change_brightness(lambda current: current + _BRIGHTNESS_STEP, tts, log)


def handle_brightness_down(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _change_brightness(lambda current: current - _BRIGHTNESS_STEP, tts, log)


# --- dark and light mode ------------------------------------------------------------------------

def _set_theme(light: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _THEME_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1 if light else 0)
    # Tell open windows (taskbar, Explorer, apps) to repaint in the new
    # theme now rather than at next sign-in.
    hwnd_broadcast, wm_settingchange, smto_abortifhung = 0xFFFF, 0x001A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        hwnd_broadcast, wm_settingchange, 0, "ImmersiveColorSet", smto_abortifhung, 200, None,
    )


def _theme(light: bool, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    try:
        _set_theme(light)
    except OSError:
        log.exception("Changing the Windows theme failed")
        tts.say("I couldn't change the theme.")
        return HandlerResult()
    tts.say("Light mode is on." if light else "Dark mode is on.")
    return HandlerResult()


def handle_dark_mode(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _theme(light=False, tts=tts, log=log)


def handle_light_mode(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _theme(light=True, tts=tts, log=log)
