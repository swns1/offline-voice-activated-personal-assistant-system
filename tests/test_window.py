import logging

from ash.actions import window
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import AppEntry, Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeProcess:
    def __init__(self, name, pid=1):
        self._name = name
        self.pid = pid
        self.terminated = False

    @property
    def info(self):
        return {"name": self._name}

    def terminate(self):
        self.terminated = True


def _registry_with_discord() -> Registry:
    return Registry(apps=[
        AppEntry(id="discord", names=["discord"],
                 launch={"type": "exe", "target": r"C:\Users\me\AppData\Local\Discord\Discord.exe"}),
    ])


def test_close_app_terminates_matching_process(monkeypatch):
    proc = FakeProcess("Discord.exe")
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([proc]))
    tts = FakeTts()

    result = window.handle_close_app("discord", _registry_with_discord(), tts, log, Config())

    assert result == HandlerResult()
    assert proc.terminated is True
    assert "Closing discord" in tts.said[-1]


def test_close_app_uses_registry_to_resolve_process_name(monkeypatch):
    # Process name differs from what the user says, but matches the
    # registry's launch target basename.
    proc = FakeProcess("Discord.exe")
    other = FakeProcess("notepad.exe")
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([proc, other]))
    tts = FakeTts()

    window.handle_close_app("discord", _registry_with_discord(), tts, log, Config())

    assert proc.terminated is True
    assert other.terminated is False


def test_close_app_no_match_says_so(monkeypatch):
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([]))
    tts = FakeTts()

    result = window.handle_close_app("nonexistent app", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "don't see" in tts.said[-1]


def test_close_app_empty_target_asks():
    tts = FakeTts()

    result = window.handle_close_app("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Close what?"]


def test_close_window_sends_wm_close(monkeypatch):
    calls = []
    monkeypatch.setattr(window.win32gui, "GetForegroundWindow", lambda: 12345)
    monkeypatch.setattr(window.win32gui, "PostMessage", lambda hwnd, msg, w, l: calls.append((hwnd, msg)))
    tts = FakeTts()

    result = window.handle_close_window("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert calls == [(12345, window.win32con.WM_CLOSE)]
    assert tts.said == ["Closing."]


def test_close_window_no_foreground_window(monkeypatch):
    monkeypatch.setattr(window.win32gui, "GetForegroundWindow", lambda: 0)
    tts = FakeTts()

    result = window.handle_close_window("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "can't tell" in tts.said[-1]


def test_minimize_window_shows_minimized(monkeypatch):
    calls = []
    monkeypatch.setattr(window.win32gui, "GetForegroundWindow", lambda: 999)
    monkeypatch.setattr(window.win32gui, "ShowWindow", lambda hwnd, cmd: calls.append((hwnd, cmd)))
    tts = FakeTts()

    result = window.handle_minimize_window("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert calls == [(999, window.win32con.SW_MINIMIZE)]
    assert tts.said == ["Minimized."]
