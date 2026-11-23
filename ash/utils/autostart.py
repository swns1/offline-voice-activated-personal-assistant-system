"""Launch Ash automatically at login, via the per-user Windows Registry
Run key (HKCU -- no admin rights needed, unlike the machine-wide HKLM
Run key). Uses pythonw.exe (no console window) rather than python.exe,
since the whole point of autostart is running unattended.
"""
import sys
import winreg
from pathlib import Path

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Ash"


def _command() -> str:
    if getattr(sys, "frozen", False):  # the packaged Ash.exe (PyInstaller)
        return f'"{sys.executable}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    # --minimized: at login, start in the tray rather than opening the window.
    return f'"{pythonw}" -m ash --minimized'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        return value == _command()
    except FileNotFoundError:
        return False


def sync_autostart(enabled: bool) -> None:
    """Idempotent -- makes the registry match `enabled`. Called on every
    startup so editing config.yaml's `autostart` and restarting Ash is
    enough; no separate step needed."""
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass  # already not set -- nothing to remove
