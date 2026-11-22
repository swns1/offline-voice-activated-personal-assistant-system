"""The network gate (ash/privacy/egress.py), your privacy choices
(consent.py), the network log (network_log.py), asking for permission
(permission.py) and the voice commands that control them
(ash/actions/privacy_controls.py)."""
import ast
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests

from ash.actions import privacy_controls, search, spotify
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.nlu.grammar import parse
from ash.privacy import consent, egress, network_log, secure_store
from ash.privacy.permission import ask_permission_if_needed
from ash.registry.schema import Registry
from ash.utils import ollama

log = logging.getLogger("test")
ASH_PACKAGE = Path(__file__).resolve().parents[1] / "ash"


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeResponse:
    def __init__(self, data=None):
        self._data = data or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def unasked():
    """Start from a fresh install: no online feature allowed or refused yet."""
    consent.PRIVACY_STATE_PATH.unlink()


@pytest.fixture
def sent(monkeypatch):
    """Record requests that would actually go out, instead of sending them."""
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, **kw: calls.append(url) or FakeResponse({"AbstractText": "An answer."}))
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.append(url) or FakeResponse())
    return calls


# --- architecture -----------------------------------------------------------

def test_only_the_egress_module_imports_requests():
    offenders = []
    for path in ASH_PACKAGE.rglob("*.py"):
        if path == ASH_PACKAGE / "privacy" / "egress.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n == "requests" or n.startswith("requests.") for n in names):
                offenders.append(str(path.relative_to(ASH_PACKAGE)))
    assert offenders == [], f"These must use ash.privacy.egress instead of requests: {offenders}"


# --- the gate ---------------------------------------------------------------

@pytest.mark.parametrize("url, local", [
    ("http://localhost:11434/api/tags", True),
    ("http://127.0.0.1:11434/api/chat", True),
    ("http://[::1]:11434/", True),
    ("https://api.duckduckgo.com/", False),
    ("http://192.168.1.20:11434/", False),
])
def test_is_local_url(url, local):
    assert egress.is_local_url(url) is local


def test_local_requests_pass_even_offline_and_are_not_logged(sent, unasked):
    consent.set_offline_mode(True)

    egress.get("http://localhost:11434/api/tags", feature=egress.LOCAL_AI.key)

    assert sent == ["http://localhost:11434/api/tags"]
    assert network_log.entries() == []


def test_offline_mode_blocks_and_sends_nothing(sent):
    consent.set_offline_mode(True)
    with pytest.raises(egress.OfflineModeError):
        egress.get("https://api.duckduckgo.com/", feature=egress.WEB_SEARCH.key)
    assert sent == []


def test_feature_not_allowed_blocks_and_sends_nothing(sent, unasked):
    with pytest.raises(egress.ConsentMissing):
        egress.get("https://api.duckduckgo.com/", feature=egress.WEB_SEARCH.key)
    consent.deny(egress.WEB_SEARCH.key)
    with pytest.raises(egress.ConsentMissing):
        egress.get("https://api.duckduckgo.com/", feature=egress.WEB_SEARCH.key)
    assert sent == []


def test_undeclared_website_is_refused(sent):
    with pytest.raises(ValueError, match="has not declared"):
        egress.get("https://tracker.example.com/collect", feature=egress.WEB_SEARCH.key)
    assert sent == []


def test_allowed_request_goes_out_and_is_logged_without_content(sent):
    egress.get("https://api.duckduckgo.com/", feature=egress.WEB_SEARCH.key,
               params={"q": "symptoms of diabetes"})

    assert sent == ["https://api.duckduckgo.com/"]
    [entry] = network_log.entries()
    assert entry["feature"] == "web_search"
    assert entry["domain"] == "api.duckduckgo.com"
    assert entry["sends"] == "the words you search for"
    assert "diabetes" not in str(entry)


def test_remote_ai_server_is_logged_and_blocked_offline(sent):
    egress.post("http://192.168.1.20:11434/api/chat", feature=egress.LOCAL_AI.key)
    assert network_log.entries()[0]["domain"] == "192.168.1.20"

    consent.set_offline_mode(True)
    with pytest.raises(egress.OfflineModeError):
        egress.post("http://192.168.1.20:11434/api/chat", feature=egress.LOCAL_AI.key)


def test_ai_features_off_offline_only_when_server_is_another_machine(monkeypatch):
    monkeypatch.setattr(ollama, "_probe", lambda host, model: ollama.READY)
    consent.set_offline_mode(True)

    assert ollama.ai_enabled(Config()) is True  # localhost: nothing leaves the PC
    remote = Config()
    remote.ollama.host = "http://192.168.1.20:11434"
    assert ollama.ai_enabled(remote) is False


# --- consent storage ----------------------------------------------------------

def test_consent_starts_unasked_and_remembers_answers(unasked):
    assert consent.status("web_search") == consent.UNASKED
    consent.grant("web_search")
    assert consent.status("web_search") == consent.GRANTED
    consent.deny("web_search")
    assert consent.status("web_search") == consent.DENIED
    assert consent.all_consents()["web_search"]["granted"] is False
    assert consent.all_consents()["web_search"]["at"]  # when you said so


def test_privacy_state_is_encrypted(unasked):
    consent.grant("web_search")
    assert secure_store.is_encrypted(consent.PRIVACY_STATE_PATH)


def test_offline_mode_toggle_persists(unasked):
    assert consent.offline_mode() is False
    consent.set_offline_mode(True)
    assert consent.offline_mode() is True
    consent.set_offline_mode(False)
    assert consent.offline_mode() is False


# --- network log ---------------------------------------------------------------

def test_network_log_prunes_old_entries():
    now = datetime(2026, 11, 22, 12, 0)
    network_log.record("web_search", "web search", "DuckDuckGo", "api.duckduckgo.com", "x",
                       now=now - timedelta(days=network_log.RETENTION_DAYS + 1))
    network_log.record("web_search", "web search", "DuckDuckGo", "api.duckduckgo.com", "x", now=now)

    assert len(network_log.entries()) == 1
    assert secure_store.is_encrypted(network_log.NETWORK_LOG_PATH)


def test_network_log_summary():
    now = datetime(2026, 11, 22, 12, 0)
    assert "haven't sent anything" in network_log.summary(now=now)
    for _ in range(2):
        network_log.record("web_search", "web search", "DuckDuckGo", "api.duckduckgo.com", "x", now=now)
    network_log.record("spotify", "Spotify", "Spotify", "api.spotify.com", "x", now=now)

    text = network_log.summary(now=now)
    assert text.startswith("In the last 7 days, I went online 3 times")
    assert "2 times to DuckDuckGo for web search" in text
    assert "1 time to Spotify for Spotify" in text


# --- asking for permission -------------------------------------------------------

def test_first_use_explains_and_asks(unasked):
    tts = FakeTts()
    result = ask_permission_if_needed("web_search", lambda: None, tts=tts, log=log)

    assert result.done is False
    assert "the words you search for" in result.question
    assert "DuckDuckGo" in result.question
    assert "internet" in result.question


def test_yes_is_remembered_and_the_command_runs(unasked):
    ran = []
    result = ask_permission_if_needed("web_search", lambda: ran.append(1) or HandlerResult(), tts=FakeTts(), log=log)

    result.resume("Yes.")

    assert ran == [1]
    assert consent.status("web_search") == consent.GRANTED


def test_no_is_remembered_and_not_asked_again(unasked):
    tts = FakeTts()
    ran = []
    ask_permission_if_needed("web_search", lambda: ran.append(1), tts=tts, log=log).resume("no")
    assert consent.status("web_search") == consent.DENIED

    again = ask_permission_if_needed("web_search", lambda: ran.append(1), tts=tts, log=log)

    assert again.done is True  # no second question
    assert "allow web search" in tts.said[-1]
    assert ran == []


def test_offline_mode_explains_how_to_get_back_online():
    consent.set_offline_mode(True)
    tts = FakeTts()
    result = ask_permission_if_needed("web_search", lambda: None, tts=tts, log=log)
    assert result.done is True
    assert "go online" in tts.said[-1]


# --- features use it ---------------------------------------------------------------

def test_web_search_asks_first_then_answers(sent, unasked):
    tts = FakeTts()
    result = search.handle_search("eiffel tower", Registry(), tts, log, Config())
    assert result.done is False and sent == []  # nothing sent before you agree

    result.resume("yes")

    assert sent == ["https://api.duckduckgo.com/"]
    assert tts.said[-1] == "An answer."


def test_spotify_not_set_up_never_asks(unasked):
    tts = FakeTts()
    result = spotify.handle_spotify_pause("", Registry(), tts, log, Config())
    assert result is None  # handled as before: "Spotify isn't set up yet."
    assert tts.said == ["Spotify isn't set up yet."]


def test_spotify_set_up_asks_first(unasked):
    config = Config()
    config.spotify.enabled = True
    config.spotify.client_id = "abc"
    result = spotify.handle_spotify_pause("", Registry(), FakeTts(), log, config)
    assert result.done is False
    assert "Spotify" in result.question


# --- voice commands ------------------------------------------------------------------

@pytest.mark.parametrize("said, intent, target", [
    ("Go offline.", "privacy_offline_on", ""),
    ("turn off offline mode", "privacy_offline_off", ""),
    ("allow web search", "consent_grant", "web search"),
    ("stop allowing Spotify", "consent_revoke", "spotify"),
    ("don't allow duckduckgo", "consent_revoke", "duckduckgo"),
    ("What have you sent online?", "network_activity", ""),
])
def test_grammar(said, intent, target):
    command = parse(said)
    assert (command.intent, command.target) == (intent, target)


def test_go_offline_then_search_is_refused(sent):
    tts = FakeTts()
    privacy_controls.handle_offline_on("", Registry(), tts, log, Config())
    search.handle_search("eiffel tower", Registry(), tts, log, Config())

    assert sent == []
    assert "offline mode" in tts.said[-1]

    privacy_controls.handle_offline_off("", Registry(), tts, log, Config())
    search.handle_search("eiffel tower", Registry(), tts, log, Config())
    assert sent == ["https://api.duckduckgo.com/"]


@pytest.mark.parametrize("spoken", ["web search", "duckduckgo", "the web search"])
def test_allow_and_disallow_by_name_or_service(unasked, spoken):
    privacy_controls.handle_disallow(spoken, Registry(), FakeTts(), log, Config())
    assert consent.status("web_search") == consent.DENIED
    privacy_controls.handle_allow(spoken, Registry(), FakeTts(), log, Config())
    assert consent.status("web_search") == consent.GRANTED


def test_unknown_feature_lists_the_real_ones():
    tts = FakeTts()
    privacy_controls.handle_allow("telepathy", Registry(), tts, log, Config())
    assert "web search" in tts.said[-1] and "Spotify" in tts.said[-1]


def test_ai_server_is_not_toggled_by_voice():
    tts = FakeTts()
    privacy_controls.handle_disallow("the AI server", Registry(), tts, log, Config())
    assert "Ollama settings" in tts.said[-1]


def test_network_activity_command_speaks_the_summary():
    network_log.record("web_search", "web search", "DuckDuckGo", "api.duckduckgo.com", "x")
    tts = FakeTts()
    privacy_controls.handle_network_activity("", Registry(), tts, log, Config())
    assert "1 time to DuckDuckGo for web search" in tts.said[-1]
