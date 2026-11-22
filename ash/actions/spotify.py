"""Spotify playback control via the Web API (spotipy). Requires a
Spotify Developer Dashboard app (client_id/redirect_uri in config.yaml's
spotify: block, client_secret from the SPOTIPY_CLIENT_SECRET env var --
spotipy reads that automatically when client_secret isn't passed) and a
Premium account (the Web API's playback-control endpoints 403 on free
accounts). See README for setup.

The client is built lazily on first Spotify command, not at startup, so
users who never configure Spotify pay no cost and don't see an
unexpected browser popup during otherwise-unattended operation -- the
first-ever call requires an interactive OAuth consent screen, which is
inherent to the Authorization Code flow (Client Credentials can't
control playback, it has no user token).
"""
import functools
import logging
import time

import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.launchers.uri_launcher import UriLauncher
from ash.nlu.context import remember_spotify_track
from ash.privacy.redact import said
from ash.privacy import egress, secure_store
from ash.privacy.permission import ask_permission_if_needed
from ash.registry.schema import Registry
from ash.utils.paths import SECRETS_DIR, ensure_app_data_dirs

_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"
_CACHE_PATH = SECRETS_DIR / ".spotify_cache"

_uri_launcher = UriLauncher()
_client: spotipy.Spotify | None = None


def _online(handler):
    """Spotify commands reach Spotify through spotipy's own HTTP calls,
    which can't pass through ash/privacy/egress.py -- so each command
    checks permission (asking the first time) and is written to the
    network log here instead. Not set up at all: no network, no need to
    ask -- the handler just says so."""
    @functools.wraps(handler)
    def wrapper(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config):
        if not config.spotify.enabled or not config.spotify.client_id:
            return handler(target, registry, tts, log, config)
        blocked = ask_permission_if_needed(
            egress.SPOTIFY.key, lambda: wrapper(target, registry, tts, log, config), tts=tts, log=log,
        )
        if blocked is not None:
            return blocked
        egress.record_use(egress.SPOTIFY.key)
        return handler(target, registry, tts, log, config)
    return wrapper


class _EncryptedTokenCache(CacheHandler):
    """spotipy's default cache writes your Spotify OAuth token (which
    grants control of your account's playback) as plain JSON. This keeps
    it in the same encrypted store as Ash's other personal data; an
    existing plain-text cache is migrated on first read."""

    def __init__(self, path):
        self._path = path

    def get_cached_token(self):
        try:
            return secure_store.read_json(self._path)
        except (OSError, ValueError):
            return None  # spotipy treats this as "not authorized yet"

    def save_token_to_cache(self, token_info):
        try:
            secure_store.write_json(self._path, token_info)
        except OSError:
            pass  # best-effort, like spotipy's own cache: you'd just re-authorize


def _get_client(config: Config, tts: TtsWorker) -> spotipy.Spotify | None:
    global _client
    if _client is not None:
        return _client
    if not config.spotify.enabled or not config.spotify.client_id:
        tts.say("Spotify isn't set up yet.")
        return None

    ensure_app_data_dirs()
    if not _CACHE_PATH.exists():
        tts.say("Opening a browser to connect Spotify.")

    auth_manager = SpotifyOAuth(
        client_id=config.spotify.client_id,
        redirect_uri=config.spotify.redirect_uri,
        scope=_SCOPE,
        cache_handler=_EncryptedTokenCache(_CACHE_PATH),
    )
    _client = spotipy.Spotify(auth_manager=auth_manager)
    return _client


@_online
def handle_spotify_play(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    client = _get_client(config, tts)
    if client is None:
        return
    try:
        _play(client, target, tts, log)
    except Exception:
        log.exception("Spotify play failed")
        tts.say("I couldn't play that on Spotify.")


def _play(client: spotipy.Spotify, target: str, tts: TtsWorker, log: logging.Logger) -> None:
    results = client.search(q=target, type="track", limit=1)
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        log.info("No Spotify track found for %s", said(target))
        tts.say(f"I couldn't find {target} on Spotify.")
        return
    track = tracks[0]

    if not client.devices().get("devices"):
        # No Spotify Connect device is active anywhere -- launch the
        # desktop app (registered steam://-style protocol handler) and
        # give it a moment to come up before retrying once.
        _uri_launcher.launch({"type": "uri", "uri_template": "spotify:"})
        time.sleep(3)
        if not client.devices().get("devices"):
            tts.say("Open Spotify on a device first.")
            return

    client.start_playback(uris=[track["uri"]])
    log.info("Playing on Spotify: %s", said(track["name"]))
    remember_spotify_track(track["name"])
    tts.say(f"Playing {track['name']}.")


def _execute(client: spotipy.Spotify, action, spoken: str, tts: TtsWorker, log: logging.Logger) -> None:
    try:
        action(client)
    except Exception:
        log.exception("Spotify action failed")
        tts.say("Something went wrong with Spotify.")
        return
    tts.say(spoken)


def _run_simple(action, spoken: str, config: Config, tts: TtsWorker, log: logging.Logger) -> None:
    client = _get_client(config, tts)
    if client is None:
        return
    _execute(client, action, spoken, tts, log)


@_online
def handle_spotify_pause(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    _run_simple(lambda c: c.pause_playback(), "Paused.", config, tts, log)


@_online
def handle_spotify_resume(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    _run_simple(lambda c: c.start_playback(), "Resuming.", config, tts, log)


@_online
def handle_spotify_skip(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    _run_simple(lambda c: c.next_track(), "Skipping.", config, tts, log)


@_online
def handle_spotify_previous(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    _run_simple(lambda c: c.previous_track(), "Playing the previous track.", config, tts, log)


@_online
def handle_spotify_now_playing(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    client = _get_client(config, tts)
    if client is None:
        return
    try:
        _now_playing(client, tts)
    except Exception:
        log.exception("Spotify now-playing check failed")
        tts.say("Something went wrong with Spotify.")


def _now_playing(client: spotipy.Spotify, tts: TtsWorker) -> None:
    playback = client.current_playback()
    if not playback or not playback.get("item"):
        tts.say("Nothing is playing.")
        return
    item = playback["item"]
    artist = item["artists"][0]["name"] if item.get("artists") else ""
    tts.say(f"{item['name']} by {artist}." if artist else item["name"])
