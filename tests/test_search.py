import logging

from ash.actions import search
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.nlu import context
from ash.registry.schema import IntentConfig, Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _no_real_launches(monkeypatch):
    launched = []
    monkeypatch.setattr(search._browser_launcher, "launch", lambda launch: launched.append(launch))
    return launched


def _registry(profile_directory=None) -> Registry:
    launch = {"type": "browser_search", "engine_url": "https://example.com/search?q={query}", "browser": "default"}
    if profile_directory:
        launch["profile_directory"] = profile_directory
    return Registry(intents={"search": IntentConfig(verbs=["search"], launch=launch)})


def test_no_search_intent_configured():
    tts = FakeTts()
    result = search.handle_search("weather", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert any("isn't configured" in msg for msg in tts.said)


def test_search_with_no_profiles_runs_directly(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {})
    tts = FakeTts()

    result = search.handle_search("weather", _registry(), tts, log, Config())

    assert result == HandlerResult()
    assert launched[0]["url"] == "https://example.com/search?q=weather"
    assert launched[0]["profile_directory"] is None


def test_search_with_configured_profile_resolves_it(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "resolve_profile", lambda browser, spoken: "Profile 2")
    tts = FakeTts()

    result = search.handle_search("weather", _registry(profile_directory="Work"), tts, log, Config())

    assert result == HandlerResult()
    assert launched[0]["profile_directory"] == "Profile 2"


def test_search_remembers_the_query(monkeypatch):
    _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {})

    search.handle_search("weather tomorrow", _registry(), FakeTts(), log, Config())

    assert context.resolve_target("search", "that") == "weather tomorrow"


def test_search_with_multiple_profiles_and_none_configured_asks(monkeypatch):
    _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {"work": "Profile 1", "personal": "Profile 2"})
    tts = FakeTts()

    result = search.handle_search("weather", _registry(), tts, log, Config())

    assert result.done is False
    assert tts.said == []


def test_search_profile_follow_up_resolves_and_runs(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {"work": "Profile 1", "personal": "Profile 2"})
    tts = FakeTts()
    result = search.handle_search("weather", _registry(), tts, log, Config())

    final = result.resume("personal")

    assert final == HandlerResult()
    assert launched[0]["profile_directory"] == "Profile 2"


def test_search_profile_follow_up_unresolved_says_never_mind(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {"work": "Profile 1", "personal": "Profile 2"})
    tts = FakeTts()
    result = search.handle_search("weather", _registry(), tts, log, Config())

    final = result.resume("something unrelated")

    assert final == HandlerResult()
    assert launched == []
    assert tts.said == ["Never mind."]
