import logging

from ash.actions import system_power
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _no_sleep(monkeypatch):
    monkeypatch.setattr(system_power.time, "sleep", lambda seconds: None)


def test_lock_calls_lock_workstation(monkeypatch):
    calls = []
    monkeypatch.setattr(system_power.ctypes.windll.user32, "LockWorkStation", lambda: calls.append(True))
    tts = FakeTts()

    result = system_power.handle_lock("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert calls == [True]
    assert tts.said == ["Locking."]


def test_lock_swallows_exceptions(monkeypatch):
    def boom():
        raise RuntimeError("no can do")
    monkeypatch.setattr(system_power.ctypes.windll.user32, "LockWorkStation", boom)
    tts = FakeTts()

    result = system_power.handle_lock("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Locking.", "I couldn't lock the computer."]


def test_sleep_calls_set_suspend_state(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []
    monkeypatch.setattr(system_power.ctypes.windll.powrprof, "SetSuspendState",
                         lambda a, b, c: calls.append((a, b, c)))
    tts = FakeTts()

    result = system_power.handle_sleep("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert calls == [(False, True, False)]


def test_shutdown_asks_for_confirmation():
    tts = FakeTts()

    result = system_power.handle_shutdown("", Registry(), tts, log, Config())

    assert result.done is False
    assert "sure" in result.question.lower()
    assert tts.said == []  # nothing spoken/executed until confirmed


def test_shutdown_confirmed_runs_shutdown_command(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []
    monkeypatch.setattr(system_power.subprocess, "run", lambda args, **kwargs: calls.append(args))
    tts = FakeTts()
    result = system_power.handle_shutdown("", Registry(), tts, log, Config())

    final = result.resume("yes")

    assert final == HandlerResult()
    assert calls == [["shutdown", "/s", "/t", "0"]]
    assert "Shutting down." in tts.said


def test_shutdown_declined_does_not_run_shutdown_command(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []
    monkeypatch.setattr(system_power.subprocess, "run", lambda args, **kwargs: calls.append(args))
    tts = FakeTts()
    result = system_power.handle_shutdown("", Registry(), tts, log, Config())

    final = result.resume("no thanks")

    assert final == HandlerResult()
    assert calls == []
    assert tts.said == ["Never mind."]


def test_shutdown_command_failure_is_swallowed(monkeypatch):
    _no_sleep(monkeypatch)

    def boom(args, **kwargs):
        raise RuntimeError("access denied")
    monkeypatch.setattr(system_power.subprocess, "run", boom)
    tts = FakeTts()
    result = system_power.handle_shutdown("", Registry(), tts, log, Config())

    final = result.resume("yes")

    assert final == HandlerResult()
    assert "I couldn't shut down." in tts.said
