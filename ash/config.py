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


class Config(BaseModel):
    wake_word: WakeWordConfig = WakeWordConfig()
    audio: AudioConfig = AudioConfig()
    browser: BrowserConfig = BrowserConfig()
    spotify: SpotifyConfig = SpotifyConfig()


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)
