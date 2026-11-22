import logging

import requests

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


class FakeResponse:
    def __init__(self, data, status_ok=True):
        self._data = data
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.exceptions.HTTPError("500")

    def json(self):
        return self._data


def _no_real_launches(monkeypatch):
    launched = []
    monkeypatch.setattr(search._browser_launcher, "launch", lambda launch: launched.append(launch))
    return launched


def _registry(profile_directory=None) -> Registry:
    launch = {"type": "browser_search", "engine_url": "https://example.com/search?q={query}", "browser": "default"}
    if profile_directory:
        launch["profile_directory"] = profile_directory
    return Registry(intents={"search": IntentConfig(verbs=["search"], launch=launch)})


# --- handle_search (DuckDuckGo answer path) ---

def test_search_speaks_ddg_answer(monkeypatch):
    monkeypatch.setattr(requests, "get",
                         lambda url, params, timeout: FakeResponse({"Answer": "", "AbstractText": "Paris is the capital of France.", "Definition": ""}))
    tts = FakeTts()

    result = search.handle_search("capital of france", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Paris is the capital of France."]


def test_search_field_priority_order(monkeypatch):
    monkeypatch.setattr(requests, "get",
                         lambda url, params, timeout: FakeResponse({"Answer": "4", "AbstractText": "should not use this", "Definition": ""}))
    tts = FakeTts()

    search.handle_search("2+2", Registry(), tts, log, Config())

    assert tts.said == ["4"]


def test_search_falls_back_to_related_topics(monkeypatch):
    monkeypatch.setattr(requests, "get",
                         lambda url, params, timeout: FakeResponse({
                             "Answer": "", "AbstractText": "", "Definition": "",
                             "RelatedTopics": [{"Text": "Something related"}],
                         }))
    tts = FakeTts()

    search.handle_search("obscure topic", Registry(), tts, log, Config())

    assert tts.said == ["Something related"]


def test_search_no_answer_suggests_browser_search(monkeypatch):
    monkeypatch.setattr(requests, "get",
                         lambda url, params, timeout: FakeResponse({"Answer": "", "AbstractText": "", "Definition": ""}))
    tts = FakeTts()

    result = search.handle_search("weather in paris", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "couldn't find" in tts.said[-1]
    assert "search in browser for weather in paris" in tts.said[-1]


def test_search_connection_failure_returns_none_gracefully(monkeypatch):
    def boom(url, params, timeout):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", boom)
    tts = FakeTts()

    result = search.handle_search("anything", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "couldn't find" in tts.said[-1]


def test_search_disabled_by_config_skips_network_call(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))
    config = Config()
    config.search.enabled = False
    tts = FakeTts()

    result = search.handle_search("anything", Registry(), tts, log, config)

    assert result == HandlerResult()
    assert calls == []
    assert "turned off" in tts.said[-1]


def test_search_remembers_the_query_on_success(monkeypatch):
    monkeypatch.setattr(requests, "get",
                         lambda url, params, timeout: FakeResponse({"Answer": "", "AbstractText": "France is a country.", "Definition": ""}))

    search.handle_search("france", Registry(), FakeTts(), log, Config())

    assert context.resolve_target("search", "that") == "france"


# --- handle_browser_search (explicit "search in browser for X") ---

def test_no_search_intent_configured():
    tts = FakeTts()
    result = search.handle_browser_search("weather", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert any("isn't configured" in msg for msg in tts.said)


def test_browser_search_with_no_profiles_runs_directly(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {})
    tts = FakeTts()

    result = search.handle_browser_search("weather", _registry(), tts, log, Config())

    assert result == HandlerResult()
    assert launched[0]["url"] == "https://example.com/search?q=weather"
    assert launched[0]["profile_directory"] is None


def test_browser_search_with_configured_profile_resolves_it(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "resolve_profile", lambda browser, spoken: "Profile 2")
    tts = FakeTts()

    result = search.handle_browser_search("weather", _registry(profile_directory="Work"), tts, log, Config())

    assert result == HandlerResult()
    assert launched[0]["profile_directory"] == "Profile 2"


def test_browser_search_remembers_the_query(monkeypatch):
    _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {})

    search.handle_browser_search("weather tomorrow", _registry(), FakeTts(), log, Config())

    assert context.resolve_target("search", "that") == "weather tomorrow"


def test_browser_search_with_multiple_profiles_and_none_configured_asks(monkeypatch):
    _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {"work": "Profile 1", "personal": "Profile 2"})
    tts = FakeTts()

    result = search.handle_browser_search("weather", _registry(), tts, log, Config())

    assert result.done is False
    assert tts.said == []


def test_browser_search_profile_follow_up_resolves_and_runs(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {"work": "Profile 1", "personal": "Profile 2"})
    tts = FakeTts()
    result = search.handle_browser_search("weather", _registry(), tts, log, Config())

    final = result.resume("personal")

    assert final == HandlerResult()
    assert launched[0]["profile_directory"] == "Profile 2"


def test_browser_search_profile_follow_up_unresolved_says_never_mind(monkeypatch):
    launched = _no_real_launches(monkeypatch)
    monkeypatch.setattr(search, "list_profiles", lambda browser: {"work": "Profile 1", "personal": "Profile 2"})
    tts = FakeTts()
    result = search.handle_browser_search("weather", _registry(), tts, log, Config())

    final = result.resume("something unrelated")

    assert final == HandlerResult()
    assert launched == []
    assert tts.said == ["Never mind."]
