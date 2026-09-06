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
    # Lets you talk over Ash mid-response instead of waiting it out --
    # no wake word needed, it just stops and listens. Detects "the user
    # is making sound", not "and it isn't an echo of Ash's own voice"
    # (no acoustic echo cancellation), so on hardware where the mic
    # picks up the speakers (no headset, close-range laptop mic+
    # speakers), Ash's own voice can occasionally trigger a false
    # barge-in -- set to false if that happens on your setup.
    barge_in_enabled: bool = True


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


class TrayConfig(BaseModel):
    # A system tray icon with a Quit option -- lets Ash run with no
    # visible console window (the point of `autostart` below, which
    # launches it via pythonw.exe). Harmless to leave on even when
    # running from a terminal.
    enabled: bool = True


class HotkeyConfig(BaseModel):
    # A global keyboard shortcut (works even when Ash isn't the focused
    # window) that toggles mute -- set to null to disable it.
    toggle_mute: str | None = "ctrl+alt+m"


class OllamaConfig(BaseModel):
    enabled: bool = False
    host: str = "http://localhost:11434"
    model: str = "llama3.2"
    # A separate pull from `model` -- vision-capable models (llama3.2
    # ITSELF is text-only) are a different, usually larger download.
    # Only used for "what's on my screen"-style requests.
    vision_model: str = "llama3.2-vision"
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
    tray: TrayConfig = TrayConfig()
    hotkey: HotkeyConfig = HotkeyConfig()
    # Launch Ash automatically at login (via the Windows Registry Run
    # key -- see ash/utils/autostart.py). Applied on every startup, so
    # editing this and restarting Ash is enough; no separate script
    # needed (though scripts/apply_autostart.py exists for convenience).
    autostart: bool = False


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)
