import logging

from ash.actions import open_app
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.launchers.exe_launcher import ExeLauncher
from ash.nlu import context
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


def _no_new_entries_on_rescan(monkeypatch, registry: Registry):
    """A no-match test isn't exercising the rescan-on-miss path -- stub
    it out to a no-op rescan that finds nothing new, instead of doing a
    real Start Menu/Steam scan and a real registry.auto.yaml write."""
    monkeypatch.setattr(open_app, "refresh_registry_auto", lambda: 0)
    monkeypatch.setattr(open_app, "load_registry", lambda: registry)


def test_exact_match_launches_directly(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    tts = FakeTts()

    result = open_app.handle_open("notepad", _registry(), tts, log, Config())

    assert result == HandlerResult()
    assert len(launched) == 1
    assert any("Opening notepad" in msg for msg in tts.said)


def test_no_match_says_so(monkeypatch):
    _no_real_launches(monkeypatch)
    registry = _registry()
    _no_new_entries_on_rescan(monkeypatch, registry)
    tts = FakeTts()

    result = open_app.handle_open("something nobody has heard of", registry, tts, log, Config())

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


def test_successful_launch_remembers_the_app(monkeypatch):
    _no_real_launches(monkeypatch)
    tts = FakeTts()

    open_app.handle_open("notepad", _registry(), tts, log, Config())

    assert context.resolve_target("open", "it") == "notepad"


def test_no_match_with_ollama_enabled_falls_back_to_converse(monkeypatch):
    calls = []
    monkeypatch.setattr(open_app, "handle_converse",
                         lambda target, registry, tts, log, config: calls.append(target) or HandlerResult())
    registry = _registry()
    _no_new_entries_on_rescan(monkeypatch, registry)
    config = Config()
    config.ollama.enabled = True
    tts = FakeTts()

    result = open_app.handle_open("what is the capital of france", registry, tts, log, config)

    assert result == HandlerResult()
    assert calls == ["what is the capital of france"]
    assert tts.said == []  # handle_open itself says nothing -- the fallback owns the reply


def test_no_match_retries_after_rescan_and_finds_it(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    registry = _registry()  # doesn't have "elden ring" yet
    rescanned = Registry(apps=[
        *registry.apps,
        AppEntry(id="steam_123", names=["elden ring"], launch={"type": "exe", "target": "elden.exe"}),
    ])
    calls = []
    monkeypatch.setattr(open_app, "refresh_registry_auto", lambda: calls.append("rescan") or 1)
    monkeypatch.setattr(open_app, "load_registry", lambda: rescanned)
    tts = FakeTts()

    result = open_app.handle_open("elden ring", registry, tts, log, Config())

    assert result == HandlerResult()
    assert calls == ["rescan"]
    assert launched[0]["target"] == "elden.exe"
    assert any("Opening steam 123" in msg for msg in tts.said)
    # the passed-in registry object was updated in place, not just a local copy
    assert any(entry.id == "steam_123" for entry in registry.apps)


def test_no_match_rescan_still_not_found_says_so(monkeypatch):
    _no_real_launches(monkeypatch)
    registry = _registry()
    _no_new_entries_on_rescan(monkeypatch, registry)
    tts = FakeTts()

    result = open_app.handle_open("something nobody has heard of", registry, tts, log, Config())

    assert result == HandlerResult()
    assert any("not sure" in msg for msg in tts.said)


def test_no_match_rescan_failure_is_swallowed(monkeypatch):
    _no_real_launches(monkeypatch)

    def _boom():
        raise RuntimeError("scan failed")

    monkeypatch.setattr(open_app, "refresh_registry_auto", _boom)
    tts = FakeTts()

    result = open_app.handle_open("something nobody has heard of", _registry(), tts, log, Config())

    assert result == HandlerResult()
    assert any("not sure" in msg for msg in tts.said)
