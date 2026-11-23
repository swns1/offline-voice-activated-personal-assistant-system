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


def test_close_app_explains_and_asks_before_closing(monkeypatch):
    proc = FakeProcess("Discord.exe")
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([proc]))
    tts = FakeTts()

    result = window.handle_close_app("discord", _registry_with_discord(), tts, log, Config())

    assert result.done is False
    assert "force discord to quit" in result.question
    assert "unsaved" in result.question
    assert result.question.endswith("Are you sure?")
    assert proc.terminated is False  # nothing happens until you say yes


def test_close_app_terminates_after_yes(monkeypatch):
    proc = FakeProcess("Discord.exe")
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([proc]))
    tts = FakeTts()
    result = window.handle_close_app("discord", _registry_with_discord(), tts, log, Config())

    final = result.resume("Yes.")

    assert final == HandlerResult()
    assert proc.terminated is True
    assert tts.said[-1] == "Closed discord."


def test_close_app_declined_leaves_it_running(monkeypatch):
    proc = FakeProcess("Discord.exe")
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([proc]))
    tts = FakeTts()
    result = window.handle_close_app("discord", _registry_with_discord(), tts, log, Config())

    final = result.resume("No.")

    assert final == HandlerResult()
    assert proc.terminated is False
    assert tts.said[-1] == "Okay, I'll leave discord open."


def test_close_app_names_every_program_a_loose_match_would_close(monkeypatch):
    # "code" substring-matches several different programs -- the question
    # must say so, so you can refuse before the wrong things get killed.
    procs = [FakeProcess("Code.exe"), FakeProcess("Code.exe", pid=2), FakeProcess("CodeHelper.exe", pid=3)]
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter(procs))

    result = window.handle_close_app("code", Registry(), FakeTts(), log, Config())

    assert "2 programs" in result.question
    assert "Code and CodeHelper" in result.question


def test_spoken_list_caps_long_lists():
    assert window._spoken_list(["a", "b", "c", "d", "e"]) == "a, b, c, and 2 more"
    assert window._spoken_list(["a", "b"]) == "a and b"


def test_close_app_uses_registry_to_resolve_process_name(monkeypatch):
    # Process name differs from what the user says, but matches the
    # registry's launch target basename.
    proc = FakeProcess("Discord.exe")
    other = FakeProcess("notepad.exe")
    monkeypatch.setattr(window.psutil, "process_iter", lambda attrs: iter([proc, other]))
    tts = FakeTts()

    result = window.handle_close_app("discord", _registry_with_discord(), tts, log, Config())
    result.resume("yes")

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
    monkeypatch.setattr(window.win32gui, "PostMessage", lambda hwnd, msg, wparam, lparam: calls.append((hwnd, msg)))
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
