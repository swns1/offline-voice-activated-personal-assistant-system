"""Self-test / diagnostics: checks mic input availability, and (if
enabled) whether Ollama and Spotify look reachable/configured -- so a
stopped Ollama server or a stale Spotify auth token shows up as an
explicit, on-demand check instead of a failure mid-command.

The Spotify check deliberately doesn't construct a real spotipy client
(that could trigger an OAuth browser popup on first use) -- it just
looks at whether a cached token file exists and looks well-formed.
"""
import logging

import requests
import sounddevice as sd

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import secure_store
from ash.registry.schema import Registry
from ash.utils import ollama
from ash.utils.paths import SECRETS_DIR

_TIMEOUT_SECONDS = 3.0


def run_diagnostics(config: Config) -> list[tuple[str, bool, str]]:
    """Returns (name, ok, detail) per check -- shared by the voice
    command and scripts/selftest.py."""
    return [
        _check_microphone(),
        _check_ollama(config),
        _check_spotify(config),
    ]


def _check_microphone() -> tuple[str, bool, str]:
    try:
        devices = sd.query_devices()
        has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
    except Exception:
        return ("Microphone", False, "couldn't query audio devices")
    return ("Microphone", has_input, "found" if has_input else "no input device found")


def _check_ollama(config: Config) -> tuple[str, bool, str]:
    setting = config.ollama.enabled
    if setting is False:
        return ("Ollama", True, "disabled")
    if setting == "auto":
        status = ollama.server_status(config, fresh=True)
        if status == ollama.READY:
            return ("Ollama", True, "running, AI features on")
        if status == ollama.MODEL_MISSING:
            return ("Ollama", False, f"running, but the {config.ollama.model} model isn't downloaded")
        # Optional in auto mode -- not running isn't a failure.
        return ("Ollama", True, "not running, AI features off")
    try:
        response = requests.get(f"{config.ollama.host}/api/tags", timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        return ("Ollama", False, "not reachable")
    except Exception:
        return ("Ollama", False, "error checking")
    return ("Ollama", True, "reachable")


def _check_spotify(config: Config) -> tuple[str, bool, str]:
    if not config.spotify.enabled:
        return ("Spotify", True, "disabled")

    cache_path = SECRETS_DIR / ".spotify_cache"
    if not cache_path.exists():
        return ("Spotify", False, "not yet authorized")
    try:
        data = secure_store.read_json(cache_path)
    except (OSError, ValueError):
        return ("Spotify", False, "cached token unreadable")
    if not isinstance(data, dict) or "access_token" not in data:
        return ("Spotify", False, "cached token looks invalid")
    return ("Spotify", True, "connected")


def handle_diagnostics(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    results = run_diagnostics(config)
    for name, ok, detail in results:
        log.info("Diagnostics: %s -> %s (%s)", name, "OK" if ok else "FAIL", detail)

    tts.say(". ".join(f"{name}: {detail}" for name, _ok, detail in results) + ".")
    return HandlerResult()
