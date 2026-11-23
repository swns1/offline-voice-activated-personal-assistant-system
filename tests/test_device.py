"""Battery, storage, screenshots, brightness and dark/light mode
(ash/actions/device.py) -- with the PC itself faked."""
import logging
import sys
import types
from collections import namedtuple

import psutil
import pytest

from ash.actions import device
from ash.actions.dispatcher import dispatch
from ash.config import Config
from ash.privacy import network_log
from ash.registry.schema import Registry

log = logging.getLogger("test")
# Captured before conftest swaps it for a blocker.
_REAL_SET_THEME = device._set_theme

Battery = namedtuple("Battery", "percent secsleft power_plugged")
Partition = namedtuple("Partition", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free percent")
GB = 1024 ** 3


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _say(text: str) -> str:
    tts = FakeTts()
    dispatch(text, Registry(), tts, log, Config())
    return tts.said[-1]


# --- battery -----------------------------------------------------------------------

@pytest.mark.parametrize("battery, reply", [
    (None, "This PC doesn't have a battery."),
    (Battery(76.4, psutil.POWER_TIME_UNLIMITED, True), "Your battery is at 76%, and charging."),
    (Battery(100, psutil.POWER_TIME_UNLIMITED, True), "Your battery is at 100%, and plugged in."),
    (Battery(55, 3 * 3600 + 20 * 60, False), "Your battery is at 55%, about 3 hours and 20 minutes left."),
    (Battery(12, 25 * 60, False), "Your battery is at 12%, about 25 minutes left."),
    (Battery(40, psutil.POWER_TIME_UNKNOWN, False), "Your battery is at 40%."),
])
def test_battery(monkeypatch, battery, reply):
    monkeypatch.setattr(device.psutil, "sensors_battery", lambda: battery)
    assert _say("what's my battery") == reply


# --- storage -------------------------------------------------------------------------

def test_storage_lists_each_fixed_drive(monkeypatch):
    monkeypatch.setattr(device.psutil, "disk_partitions", lambda all=False: [
        Partition("C:\\", "C:\\", "NTFS", "rw,fixed"),
        Partition("D:\\", "D:\\", "", "cdrom"),          # empty DVD drive: skipped
        Partition("E:\\", "E:\\", "NTFS", "rw,fixed"),
    ])
    usage = {"C:\\": Usage(931 * GB, 779 * GB, 152 * GB, 84), "E:\\": Usage(2000 * GB, 500 * GB, 1500 * GB, 25)}
    monkeypatch.setattr(device.psutil, "disk_usage", lambda mount: usage[mount])

    assert _say("how much storage do I have") == (
        "You have 152 gigabytes free on drive C, out of 931; and 1500 gigabytes free on drive E, out of 2000.")


# --- screenshot ---------------------------------------------------------------------------

def test_screenshot_is_saved_to_pictures(monkeypatch, tmp_path):
    saved = []

    class FakeImage:
        def save(self, path):
            saved.append(path)

    fake_imagegrab = types.SimpleNamespace(grab=lambda all_screens: FakeImage())
    monkeypatch.setitem(sys.modules, "PIL.ImageGrab", fake_imagegrab)
    monkeypatch.setattr(sys.modules["PIL"], "ImageGrab", fake_imagegrab, raising=False)
    monkeypatch.setattr(device, "_pictures_dir", lambda: tmp_path / "Pictures")

    assert _say("take a screenshot") == "Saved a screenshot to your Pictures folder, in Screenshots."
    [path] = saved
    assert path.parent == tmp_path / "Pictures" / "Screenshots"
    assert path.name.startswith("Ash screenshot ") and path.suffix == ".png"


# --- brightness ----------------------------------------------------------------------------

@pytest.fixture
def screen(monkeypatch):
    state = {"level": 50}
    monkeypatch.setattr(device, "get_brightness", lambda: state["level"])

    def fake_set(level):
        state["level"] = level
        return True
    monkeypatch.setattr(device, "set_brightness", fake_set)
    return state


@pytest.mark.parametrize("said, level", [
    ("set the brightness to 60", 60), ("brightness up", 60), ("brightness down", 40),
    ("set brightness to 150", 100), ("dim the screen", 40),
])
def test_brightness(screen, said, level):
    assert _say(said) == f"Brightness set to {level}%."
    assert screen["level"] == level


def test_brightness_on_a_desktop_monitor(monkeypatch):
    monkeypatch.setattr(device, "get_brightness", lambda: None)
    assert "can't change the brightness of this screen" in _say("brightness up")


# --- dark and light mode ----------------------------------------------------------------------

def test_dark_and_light_mode(monkeypatch):
    calls = []
    monkeypatch.setattr(device, "_set_theme", lambda light: calls.append(light))
    assert _say("turn on dark mode") == "Dark mode is on."
    assert _say("switch to light mode") == "Light mode is on."
    assert calls == [False, True]


def test_theme_writes_both_registry_values_and_tells_windows(monkeypatch):
    written = {}

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU", KEY_SET_VALUE=2, REG_DWORD=4,
        OpenKey=lambda root, path, reserved, access: FakeKey(),
        SetValueEx=lambda key, name, reserved, kind, value: written.__setitem__(name, value),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    broadcasts = []
    monkeypatch.setattr(device.ctypes, "windll", types.SimpleNamespace(
        user32=types.SimpleNamespace(SendMessageTimeoutW=lambda *a: broadcasts.append(a[3]))))

    _REAL_SET_THEME(light=False)

    assert written == {"AppsUseLightTheme": 0, "SystemUsesLightTheme": 0}
    assert broadcasts == ["ImmersiveColorSet"]


def test_nothing_goes_online(monkeypatch, screen):
    monkeypatch.setattr(device.psutil, "sensors_battery", lambda: None)
    for said in ("what's my battery", "brightness up"):
        _say(said)
    assert network_log.entries() == []
