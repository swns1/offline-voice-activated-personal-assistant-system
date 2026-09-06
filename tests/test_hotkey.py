import logging

from ash.utils import hotkey

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_register_mute_hotkey_calls_keyboard_add_hotkey(monkeypatch):
    calls = []
    monkeypatch.setattr(hotkey.keyboard, "add_hotkey", lambda combo, callback: calls.append((combo, callback)))

    hotkey.register_mute_hotkey("ctrl+alt+m", FakeTts(), log)

    assert len(calls) == 1
    assert calls[0][0] == "ctrl+alt+m"


def test_registered_callback_toggles_mute(monkeypatch):
    captured = {}
    monkeypatch.setattr(hotkey.keyboard, "add_hotkey", lambda combo, callback: captured.setdefault("cb", callback))
    toggle_calls = []
    monkeypatch.setattr(hotkey, "toggle_mute", lambda tts, log: toggle_calls.append((tts, log)))
    tts = FakeTts()

    hotkey.register_mute_hotkey("ctrl+alt+m", tts, log)
    captured["cb"]()  # simulate the hotkey firing

    assert toggle_calls == [(tts, log)]


def test_register_mute_hotkey_failure_is_swallowed(monkeypatch):
    def boom(combo, callback):
        raise RuntimeError("hook requires elevation")
    monkeypatch.setattr(hotkey.keyboard, "add_hotkey", boom)

    hotkey.register_mute_hotkey("ctrl+alt+m", FakeTts(), log)  # must not raise
