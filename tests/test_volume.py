import logging

from ash.actions import volume
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeInterface:
    def __init__(self, scalar=0.5, muted=False):
        self.scalar = scalar
        self.muted = muted

    def GetMasterVolumeLevelScalar(self):
        return self.scalar

    def SetMasterVolumeLevelScalar(self, level, _guid):
        self.scalar = level

    def SetMute(self, muted, _guid):
        self.muted = bool(muted)


def _patched(monkeypatch, interface):
    monkeypatch.setattr(volume, "_with_volume_interface", lambda fn: fn(interface))


def test_volume_up_increases_by_step(monkeypatch):
    interface = FakeInterface(scalar=0.5)
    _patched(monkeypatch, interface)
    tts = FakeTts()

    result = volume.handle_volume_up("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert interface.scalar == 0.6
    assert tts.said == ["Volume up."]


def test_volume_up_clamps_at_max(monkeypatch):
    interface = FakeInterface(scalar=0.95)
    _patched(monkeypatch, interface)
    tts = FakeTts()

    volume.handle_volume_up("", Registry(), tts, log, Config())

    assert interface.scalar == 1.0


def test_volume_down_clamps_at_min(monkeypatch):
    interface = FakeInterface(scalar=0.05)
    _patched(monkeypatch, interface)
    tts = FakeTts()

    volume.handle_volume_down("", Registry(), tts, log, Config())

    assert interface.scalar == 0.0


def test_volume_set_parses_percent(monkeypatch):
    interface = FakeInterface(scalar=0.5)
    _patched(monkeypatch, interface)
    tts = FakeTts()

    volume.handle_volume_set("50 percent", Registry(), tts, log, Config())

    assert interface.scalar == 0.5
    assert tts.said == ["Volume set to 50 percent."]


def test_volume_set_clamps_above_100(monkeypatch):
    interface = FakeInterface()
    _patched(monkeypatch, interface)
    tts = FakeTts()

    volume.handle_volume_set("150", Registry(), tts, log, Config())

    assert interface.scalar == 1.0


def test_volume_set_no_number_says_so(monkeypatch):
    interface = FakeInterface()
    _patched(monkeypatch, interface)
    tts = FakeTts()

    result = volume.handle_volume_set("way too loud", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["I didn't catch a number."]


def test_mute(monkeypatch):
    interface = FakeInterface(muted=False)
    _patched(monkeypatch, interface)
    tts = FakeTts()

    volume.handle_mute("", Registry(), tts, log, Config())

    assert interface.muted is True
    assert tts.said == ["Muted."]


def test_unmute(monkeypatch):
    interface = FakeInterface(muted=True)
    _patched(monkeypatch, interface)
    tts = FakeTts()

    volume.handle_unmute("", Registry(), tts, log, Config())

    assert interface.muted is False
    assert tts.said == ["Unmuted."]


def test_volume_up_swallows_exceptions(monkeypatch):
    def boom(fn):
        raise RuntimeError("no audio device")
    monkeypatch.setattr(volume, "_with_volume_interface", boom)
    tts = FakeTts()

    result = volume.handle_volume_up("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["I couldn't change the volume."]
