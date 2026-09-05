import logging

from ash.actions import open_app
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.launchers.exe_launcher import ExeLauncher
from ash.registry.schema import AppEntry, Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _no_real_launches(monkeypatch):
    """handle_open ultimately calls a real Launcher, which would
    subprocess.Popen a real executable -- record instead of executing."""
    launched = []
    monkeypatch.setattr(ExeLauncher, "launch", lambda self, launch: launched.append(launch))
    return launched


def _registry() -> Registry:
    return Registry(apps=[
        AppEntry(id="notepad", names=["notepad"], launch={"type": "exe", "target": "notepad.exe"}),
    ])


def _ambiguous_registry() -> Registry:
    # "app" scores identically (90.0, WRatio) against both -- a genuine
    # tie, not a marginal best-match.
    return Registry(apps=[
        AppEntry(id="app_a", names=["app a"], launch={"type": "exe", "target": "a.exe"}),
        AppEntry(id="app_b", names=["app b"], launch={"type": "exe", "target": "b.exe"}),
    ])


def test_exact_match_launches_directly(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    tts = FakeTts()

    result = open_app.handle_open("notepad", _registry(), tts, log, Config())

    assert result == HandlerResult()
    assert len(launched) == 1
    assert any("Opening notepad" in msg for msg in tts.said)


def test_no_match_says_so(monkeypatch):
    _no_real_launches(monkeypatch)
    tts = FakeTts()

    result = open_app.handle_open("something nobody has heard of", _registry(), tts, log, Config())

    assert result == HandlerResult()
    assert any("not sure" in msg for msg in tts.said)


def test_ambiguous_close_scores_asks_a_follow_up(monkeypatch):
    _no_real_launches(monkeypatch)
    tts = FakeTts()

    result = open_app.handle_open("app", _ambiguous_registry(), tts, log, Config())

    assert result.done is False
    assert "app a" in result.question and "app b" in result.question
    assert tts.said == []  # no launch/failure message yet -- only after the follow-up


def test_ambiguous_follow_up_resolves_to_chosen_app(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    tts = FakeTts()
    result = open_app.handle_open("app", _ambiguous_registry(), tts, log, Config())

    final = result.resume("app b")

    assert final == HandlerResult()
    assert launched[0]["target"] == "b.exe"
    assert any("Opening app b" in msg for msg in tts.said)


def test_ambiguous_follow_up_unresolved_says_never_mind(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    tts = FakeTts()
    result = open_app.handle_open("app", _ambiguous_registry(), tts, log, Config())

    final = result.resume("something else entirely")

    assert final == HandlerResult()
    assert launched == []
    assert tts.said == ["Never mind."]
