"""Pydantic config models + loader for config.yaml, and save_settings()
for the desktop window's Settings tab."""
import io
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

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


class EmailConfig(BaseModel):
    # Read your inbox (sender and subject only) and send emails through
    # desktop Outlook -- see ash/actions/email.py. Off by default: it
    # touches personal data and needs Outlook installed and set up.
    enabled: bool = False


class CalendarConfig(BaseModel):
    # Reads/writes your local desktop Outlook calendar via COM -- no
    # account setup on Ash's side (unlike Spotify/Ollama), but it only
    # works if Outlook itself is installed and configured, and it
    # touches real personal data, so it defaults off like the others.
    enabled: bool = False
    # Opt-in: Ash is otherwise 100% reactive (never speaks unprompted).
    # With this on, it polls your calendar in the background and speaks/
    # toasts a heads-up shortly before a meeting starts -- see
    # ash/actions/proactive.py. Independent of `enabled` above; needs
    # both on to do anything.
    proactive_reminders: bool = False
    # How far ahead a meeting has to be to trigger a nudge, and how often
    # the background check runs. Each event is only ever announced once.
    proactive_lookahead_minutes: int = 5
    proactive_poll_seconds: int = 60


class TrayConfig(BaseModel):
    # A system tray icon with a Quit option -- lets Ash run with no
    # visible console window (the point of `autostart` below, which
    # launches it via pythonw.exe). Harmless to leave on even when
    # running from a terminal.
    enabled: bool = True


class GuiConfig(BaseModel):
    # The desktop window (chat, settings, privacy dashboard, "what can I
    # say"). Needs PySide6; without it, or with this off, Ash runs
    # voice-only (as does `python -m ash --console`).
    enabled: bool = True
    # Start hidden in the system tray -- what autostart at login does.
    start_minimized: bool = False


class HotkeyConfig(BaseModel):
    # A global keyboard shortcut (works even when Ash isn't the focused
    # window) that toggles mute -- set to null to disable it.
    toggle_mute: str | None = "ctrl+alt+m"


class SecurityConfig(BaseModel):
    # Extra voice-match check before *confirming* a risky action
    # (shutdown, force-closing an app, click/type) -- on top of, not instead of, the
    # existing spoken yes/no. Needs one-time enrollment first
    # (scripts/enroll_voice.py); silently skipped (falls back to
    # yes/no-only) if nothing's enrolled. See ash/security/voice_gate.py
    # for important accuracy caveats -- this is a classical
    # MFCC-similarity check, not a trained deep speaker-embedding model,
    # and should be treated as a soft additional check on a
    # single-user machine, not a strong biometric guarantee.
    voice_gate_enabled: bool = False
    # Cosine similarity (0-1) the confirmation audio must reach against
    # the enrolled voiceprint. Lower = more lenient (more false accepts),
    # higher = stricter (more false rejects of your own voice, especially
    # on a short answer like a single word "yes").
    voice_match_threshold: float = 0.85


class DesktopControlConfig(BaseModel):
    # Lets Ash click/type on your screen based on OCR'd text labels
    # ("click Save") -- the one feature in this codebase that directly
    # manipulates your desktop. Off by default, on top of every action
    # still requiring spoken confirmation even when enabled (and,
    # if security.voice_gate_enabled, a voice-match check on that
    # confirmation too). See ash/actions/desktop_control.py -- text-label
    # only, can't target a bare icon; that's an intentional scope limit.
    enabled: bool = False


class RegistryConfig(BaseModel):
    # Rescans the Start Menu + Steam library and rewrites
    # registry.auto.yaml on every startup, so a game/app installed since
    # Ash last started is voice-launchable without a manual
    # scripts/build_registry_auto.py run. Takes about a second; set to
    # false to skip it (e.g. if you'd rather control exactly when the
    # scan runs).
    auto_rescan_on_startup: bool = True


class OllamaConfig(BaseModel):
    # true/false force the local-AI features on/off; "auto" uses them
    # only while Ollama is actually running with `model` downloaded. Read
    # it through ash.utils.ollama.ai_enabled(), never directly.
    enabled: bool | Literal["auto"] = "auto"
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


class VoiceConfig(BaseModel):
    # "windows": the built-in Windows voice. "piper": a natural-sounding
    # neural voice, run on this PC -- an optional install (pip install
    # piper-tts; it's GPL-licensed, so it isn't bundled with Ash) plus a
    # one-time voice download. Falls back to the Windows voice if either
    # is missing. Applies the next time Ash starts.
    engine: Literal["windows", "piper"] = "windows"
    # One of PIPER_VOICES in ash/setup_models.py (or any Piper voice name).
    piper_voice: str = "en_US-ljspeech-medium"


class WeatherConfig(BaseModel):
    # Your city is set by voice ("my city is Manila") and stored encrypted
    # -- see ash/actions/weather.py -- not here.
    units: Literal["celsius", "fahrenheit"] = "celsius"


class PrivacyConfig(BaseModel):
    # Include what you say (transcripts, search queries, reminder text,
    # ...) in the log files. Off by default: logs then show which command
    # ran, not its content (see ash/privacy/redact.py). Typed text and
    # remembered facts are never logged either way.
    log_transcripts: bool = False
    # Log files older than this many days are deleted automatically.
    log_retention_days: int = Field(default=7, ge=1)


class Config(BaseModel):
    wake_word: WakeWordConfig = WakeWordConfig()
    audio: AudioConfig = AudioConfig()
    browser: BrowserConfig = BrowserConfig()
    spotify: SpotifyConfig = SpotifyConfig()
    search: SearchConfig = SearchConfig()
    calendar: CalendarConfig = CalendarConfig()
    email: EmailConfig = EmailConfig()
    ollama: OllamaConfig = OllamaConfig()
    tray: TrayConfig = TrayConfig()
    gui: GuiConfig = GuiConfig()
    hotkey: HotkeyConfig = HotkeyConfig()
    registry: RegistryConfig = RegistryConfig()
    security: SecurityConfig = SecurityConfig()
    desktop_control: DesktopControlConfig = DesktopControlConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    weather: WeatherConfig = WeatherConfig()
    voice: VoiceConfig = VoiceConfig()
    # Launch Ash automatically at login (via the Windows Registry Run
    # key -- see ash/utils/autostart.py). Applied on every startup, so
    # editing this and restarting Ash is enough; no separate script
    # needed (though scripts/apply_autostart.py exists for convenience).
    autostart: bool = False


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)


def save_settings(updates: dict[str, Any], path: Path = CONFIG_PATH) -> Config:
    """Write changed settings into config.yaml -- keys are dotted paths
    ("weather.units", "autostart") -- keeping every comment and every
    setting you didn't change exactly as it was. The result is checked
    (pydantic) before anything is written, so a bad value raises
    pydantic.ValidationError and leaves the file untouched. Returns the
    new Config."""
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap

    rt = YAML()  # round-trip mode: keeps comments, order and quoting
    rt.preserve_quotes = True
    rt.width = 4096  # never re-wrap long values
    rt.indent(mapping=2, sequence=4, offset=2)
    # Write None as "null" (ruamel's default is an empty value), as the file has it.
    rt.representer.add_representer(
        type(None), lambda representer, _: representer.represent_scalar("tag:yaml.org,2002:null", "null"))
    data = rt.load(path.read_text(encoding="utf-8")) if path.exists() else None
    if data is None:
        data = CommentedMap()

    for dotted, value in updates.items():
        *sections, key = dotted.split(".")
        node = data
        for section in sections:
            if not isinstance(node.get(section), dict):
                node[section] = CommentedMap()
            node = node[section]
        node[key] = value

    config = Config.model_validate(_plain(data))

    buffer = io.StringIO()
    rt.dump(data, buffer)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(buffer.getvalue(), encoding="utf-8")
    os.replace(tmp, path)
    return config


def _plain(node):
    if isinstance(node, dict):
        return {key: _plain(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_plain(value) for value in node]
    return node
