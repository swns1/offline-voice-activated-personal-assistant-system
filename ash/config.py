"""Pydantic config models + loader for config.yaml."""
from pathlib import Path

import yaml
from pydantic import BaseModel

from ash.utils.paths import CONFIG_PATH


class WakeWordConfig(BaseModel):
    engine: str = "openwakeword"
    # A bundled pretrained openWakeWord model name (e.g. "hey_jarvis").
    # A real "Hey Ash" phrase would need openWakeWord's local training
    # pipeline; no instant online compiler exists like Picovoice's.
    keyword: str = "hey_jarvis"
    threshold: float = 0.5


class AudioConfig(BaseModel):
    input_device: int | None = None
    silence_ms: int = 900
    max_record_seconds: float = 8.0


class BrowserConfig(BaseModel):
    default: str = "chrome"
    # Spoken/display profile name (e.g. "Work"), resolved to the browser's
    # internal profile folder key at launch time -- see
    # ash/launchers/browser_profiles.py.
    profile_directory: str | None = None


class SpotifyConfig(BaseModel):
    enabled: bool = False
    # Not secret in the same sense as client_secret (which comes from the
    # SPOTIPY_CLIENT_SECRET env var instead, see ash/actions/spotify.py) --
    # a client_id is meant to be paired with a registered redirect_uri.
    client_id: str | None = None
    redirect_uri: str = "http://127.0.0.1:8888/callback"


class SearchConfig(BaseModel):
    # DuckDuckGo's Instant Answer API -- free, no account/key needed,
    # but it IS a real network call, a small departure from fully-offline
    # operation. On by default since (unlike Spotify/Ollama) it needs no
    # setup to work; set to false to keep "search for X" fully offline
    # (it'll just point you at "search in browser for X" instead).
    enabled: bool = True


class CalendarConfig(BaseModel):
    # Reads/writes your local desktop Outlook calendar via COM -- no
    # account setup on Ash's side (unlike Spotify/Ollama), but it only
    # works if Outlook itself is installed and configured, and it
    # touches real personal data, so it defaults off like the others.
    enabled: bool = False


class OllamaConfig(BaseModel):
    enabled: bool = False
    host: str = "http://localhost:11434"
    model: str = "llama3.2"
    system_prompt: str = (
        "You are Ash, a local voice assistant running entirely offline on "
        "the user's PC. Keep answers brief (1-3 sentences) since they will "
        "be read aloud by text-to-speech. Do not use markdown, bullet "
        "points, or any formatting -- plain spoken sentences only."
    )


class Config(BaseModel):
    wake_word: WakeWordConfig = WakeWordConfig()
    audio: AudioConfig = AudioConfig()
    browser: BrowserConfig = BrowserConfig()
    spotify: SpotifyConfig = SpotifyConfig()
    search: SearchConfig = SearchConfig()
    calendar: CalendarConfig = CalendarConfig()
    ollama: OllamaConfig = OllamaConfig()


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)
