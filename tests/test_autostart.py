import sys
from pathlib import Path

import pytest

from ash.utils import autostart


class _FakeKeyHandle:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeRegistry:
    """Stands in for the real winreg module -- tests must never touch
    the actual Windows registry."""

    def __init__(self, key_exists=True):
        self.values = {}
        self.key_exists = key_exists

    def CreateKey(self, hive, path):
        self.key_exists = True
        return _FakeKeyHandle()

    def OpenKey(self, hive, path, *args):
        if not self.key_exists:
            raise FileNotFoundError()
        return _FakeKeyHandle()

    def SetValueEx(self, key, name, reserved, type_, data):
        self.values[name] = data

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError()
        return self.values[name], 1

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError()
        del self.values[name]


def _install_fake_registry(monkeypatch, key_exists=True) -> FakeRegistry:
    fake = FakeRegistry(key_exists=key_exists)
    monkeypatch.setattr(autostart.winreg, "CreateKey", fake.CreateKey)
    monkeypatch.setattr(autostart.winreg, "OpenKey", fake.OpenKey)
    monkeypatch.setattr(autostart.winreg, "SetValueEx", fake.SetValueEx)
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", fake.QueryValueEx)
    monkeypatch.setattr(autostart.winreg, "DeleteValue", fake.DeleteValue)
    return fake


def test_command_uses_pythonw_and_module_flag():
    command = autostart._command()
    assert "pythonw.exe" in command
    assert command.endswith("-m ash")
    assert sys.executable.rsplit("\\", 1)[0] in command  # same directory as the running interpreter


def test_sync_autostart_true_writes_the_expected_command(monkeypatch):
    fake = _install_fake_registry(monkeypatch, key_exists=False)

    autostart.sync_autostart(True)

    assert fake.values[autostart._VALUE_NAME] == autostart._command()


def test_sync_autostart_false_removes_existing_value(monkeypatch):
    fake = _install_fake_registry(monkeypatch, key_exists=True)
    fake.values[autostart._VALUE_NAME] = autostart._command()

    autostart.sync_autostart(False)

    assert autostart._VALUE_NAME not in fake.values


def test_sync_autostart_false_when_nothing_set_is_a_noop(monkeypatch):
    _install_fake_registry(monkeypatch, key_exists=False)

    autostart.sync_autostart(False)  # must not raise


def test_is_autostart_enabled_true_when_value_matches(monkeypatch):
    fake = _install_fake_registry(monkeypatch, key_exists=True)
    fake.values[autostart._VALUE_NAME] = autostart._command()

    assert autostart.is_autostart_enabled() is True


def test_is_autostart_enabled_false_when_key_missing(monkeypatch):
    _install_fake_registry(monkeypatch, key_exists=False)

    assert autostart.is_autostart_enabled() is False


def test_is_autostart_enabled_false_when_value_is_stale(monkeypatch):
    # e.g. the venv moved, or a different Python interpreter is now used
    fake = _install_fake_registry(monkeypatch, key_exists=True)
    fake.values[autostart._VALUE_NAME] = '"C:\\old\\path\\pythonw.exe" -m ash'

    assert autostart.is_autostart_enabled() is False


def test_sync_autostart_true_then_is_enabled_round_trips(monkeypatch):
    _install_fake_registry(monkeypatch, key_exists=False)

    autostart.sync_autostart(True)

    assert autostart.is_autostart_enabled() is True
