"""The one door out of this PC. Every HTTP request Ash makes goes through
get()/post() here -- a test (tests/test_architecture.py) fails if any
other module imports `requests` directly -- so these rules can't be
bypassed by accident:

1. Requests to this PC itself (the local Ollama server) always go
   through and aren't logged: nothing leaves the machine.
2. Anything else must belong to a declared online feature (FEATURES
   below: what it sends, to whom, and why), and only to that feature's
   declared websites.
3. Offline mode blocks it.
4. A feature you haven't allowed (ash/privacy/consent.py) is blocked.
5. Each request that does leave is written to the network log
   (ash/privacy/network_log.py) -- which feature, which website, what
   kind of data, never the data itself.

Handlers ask for permission up front with
ash/privacy/permission.py's ask_permission_if_needed(), which can ask
you out loud the first time; the checks here are the backstop that
makes a missed check fail safe (blocked) instead of silently leaking.

Libraries that make their own network calls (spotipy) can't be routed
through here; their features check permission the same way and call
record_use() per command instead.
"""
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from ash.privacy import consent, network_log

# Re-exported so callers never need to import requests themselves.
NetworkUnreachable = requests.exceptions.ConnectionError
RequestError = requests.exceptions.RequestException


@dataclass(frozen=True)
class OnlineFeature:
    key: str
    name: str            # how it's spoken: "allow web search"
    service: str         # who receives the data
    sends: str           # what kind of data leaves the PC
    purpose: str
    domains: tuple[str, ...] = ()
    # The website comes from your own config (e.g. an Ollama server on
    # another machine) rather than being fixed in code.
    any_domain: bool = False
    # No per-feature yes/no: consent comes from your own setup instead
    # (configuring an Ollama server on another machine; installing Ash,
    # for its one-time model download). Still logged, and still blocked
    # by offline mode. `fixed_reason` says why, when you try to toggle it.
    consent_by_config: bool = False
    fixed_reason: str = ""


FEATURES: dict[str, OnlineFeature] = {}


def register(feature: OnlineFeature) -> OnlineFeature:
    FEATURES[feature.key] = feature
    return feature


WEB_SEARCH = register(OnlineFeature(
    key="web_search", name="web search", service="DuckDuckGo",
    sends="the words you search for",
    purpose="answer \"what is\" and \"search for\" questions",
    domains=("api.duckduckgo.com",),
))
SPOTIFY = register(OnlineFeature(
    key="spotify", name="Spotify", service="Spotify",
    sends="the songs you ask for and your playback commands",
    purpose="control Spotify playback on your account",
    domains=("api.spotify.com", "accounts.spotify.com"),
))
LOCAL_AI = register(OnlineFeature(
    key="local_ai", name="the AI server", service="your Ollama server",
    sends="what you say to the AI, and screenshots when you ask about your screen",
    purpose="answer questions and understand commands with a language model",
    any_domain=True, consent_by_config=True,
    fixed_reason="is controlled by your Ollama settings",
))
MODEL_DOWNLOAD = register(OnlineFeature(
    key="model_download", name="model downloads", service="Hugging Face",
    sends="a request for the speech-recognition model (nothing about you)",
    purpose="download the speech-recognition model, once, the first time Ash starts",
    domains=("huggingface.co",), consent_by_config=True,
    fixed_reason="only happens once, the first time Ash starts, to download its speech-recognition model",
))


class NetworkBlocked(Exception):
    """A request was refused by your privacy settings."""

    def __init__(self, feature: OnlineFeature, reason: str):
        super().__init__(f"{feature.key}: {reason}")
        self.feature = feature
        self.reason = reason


class OfflineModeError(NetworkBlocked):
    pass


class ConsentMissing(NetworkBlocked):
    pass


def is_local_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check(feature_key: str, url: str | None = None) -> None:
    """Raise NetworkBlocked unless `feature_key` may send a request (to
    `url`, if given) right now."""
    feature = FEATURES[feature_key]
    if url is not None:
        host = urlparse(url).hostname or ""
        if not feature.any_domain and host not in feature.domains:
            # A programming error, not a privacy setting: code tried to
            # contact a website its feature never declared.
            raise ValueError(f"{feature_key} has not declared {host!r} (declared: {feature.domains})")
    if consent.offline_mode():
        raise OfflineModeError(feature, "offline mode is on")
    if not feature.consent_by_config and consent.status(feature_key) != consent.GRANTED:
        raise ConsentMissing(feature, "not allowed")


def record_use(feature_key: str, domain: str | None = None) -> None:
    feature = FEATURES[feature_key]
    network_log.record(
        feature_key, feature.name, feature.service,
        domain or (feature.domains[0] if feature.domains else "?"), feature.sends,
    )


def get(url: str, *, feature: str, **kwargs) -> requests.Response:
    return _send(requests.get, url, feature, **kwargs)


def post(url: str, *, feature: str, **kwargs) -> requests.Response:
    return _send(requests.post, url, feature, **kwargs)


def _send(method, url: str, feature_key: str, **kwargs) -> requests.Response:
    if is_local_url(url):
        return method(url, **kwargs)  # stays on this PC
    check(feature_key, url)
    record_use(feature_key, urlparse(url).hostname)
    return method(url, **kwargs)
