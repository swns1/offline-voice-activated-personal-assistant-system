"""Everything Ash stores, in one list: what it is, why it's kept, for how
long, whether it's sensitive, and whether it's encrypted.

This single list drives:
- "what data do you have" (RA 10173 Sec. 16(a)-(c): your rights to be
  informed -- including each item's purpose and how long it's kept --
  and to access),
- "export my data" (Sec. 18: data portability),
- "delete all my data" (Sec. 16(e): erasure),
- the privacy dashboard, and the table in docs/PRIVACY.md.

tests/test_privacy_rights.py fails if a file Ash writes under
%LOCALAPPDATA%\\Ash is missing from it, so nothing can be stored without
being listed here first.

File locations are looked up through the module that owns each file at
call time (not copied here), so there's exactly one source of truth
for where each file lives.
"""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ash.privacy import secure_store


@dataclass(frozen=True)
class StoredData:
    key: str
    name: str                       # spoken: "remembered facts"
    purpose: str
    kept: str                       # how long: "until you ask me to forget it"
    sensitive: bool
    encrypted: bool
    paths: Callable[[], list[Path]]
    # Included in "export my data" -- False for secrets (login tokens)
    # and the biometric voiceprint, which are listed but not copied out.
    exportable: bool = True
    export_note: str = ""
    # Erased by "delete all my data". False only for things that aren't
    # about you and are rebuilt automatically (the installed-apps list).
    erasable: bool = True


def _memory() -> list[Path]:
    from ash.actions import memory
    return [memory.MEMORY_PATH]


def _notes() -> list[Path]:
    from ash.actions import notes
    return [notes.NOTES_PATH]


def _preferences() -> list[Path]:
    from ash.utils import preferences
    return [preferences.PREFERENCES_PATH]


def _timers() -> list[Path]:
    from ash.actions import timers
    return [timers.TIMERS_STATE_PATH]


def _wake_word() -> list[Path]:
    from ash.audio import personal_wake_word
    return [personal_wake_word.PERSONAL_WAKE_WORD_PATH]


def _voiceprint() -> list[Path]:
    from ash.security import voice_gate
    return [voice_gate.VOICEPRINT_PATH]


def _spotify_token() -> list[Path]:
    from ash.actions import spotify
    return [spotify._CACHE_PATH]


def _privacy_state() -> list[Path]:
    from ash.privacy import consent
    return [consent.PRIVACY_STATE_PATH]


def _network_log() -> list[Path]:
    from ash.privacy import network_log
    return [network_log.NETWORK_LOG_PATH]


def _logs() -> list[Path]:
    from ash.utils import logging_setup
    return sorted(logging_setup.LOG_DIR.glob(logging_setup.LOG_FILE_NAME + "*"))


def _installed_apps() -> list[Path]:
    from ash.utils.paths import REGISTRY_AUTO_PATH
    return [REGISTRY_AUTO_PATH]


INVENTORY: list[StoredData] = [
    StoredData(
        key="memory", name="remembered facts",
        purpose="facts you asked me to remember, used to personalize answers",
        kept="until you ask me to forget them", sensitive=False, encrypted=True, paths=_memory,
    ),
    StoredData(
        key="notes", name="notes and lists",
        purpose="notes you dictate, and lists like your shopping list",
        kept="until you delete them", sensitive=False, encrypted=True, paths=_notes,
    ),
    StoredData(
        key="preferences", name="your city",
        purpose="the weather where you live (you tell Ash; it never works out your location)",
        kept="until you change or delete it", sensitive=False, encrypted=True, paths=_preferences,
    ),
    StoredData(
        key="timers", name="timers and reminders",
        purpose="so pending timers and reminders survive a restart",
        kept="until they go off or you cancel them", sensitive=False, encrypted=True, paths=_timers,
    ),
    StoredData(
        key="voiceprint", name="your voiceprint",
        purpose="checking it's really you before risky actions, if voice-verified confirmation is on",
        kept="until you delete it", sensitive=True, encrypted=True, paths=_voiceprint,
        exportable=False, export_note="Biometric data: listed, but not copied into the export file for safety.",
    ),
    StoredData(
        key="wake_word", name="your wake word model",
        purpose="recognising your own wake word (\"Okay Ash\"); trained on recordings of your voice, "
                "which aren't kept by Ash",
        kept="until you delete it", sensitive=True, encrypted=True, paths=_wake_word,
        exportable=False, export_note="Derived from your voice: listed, but not copied into the export file.",
    ),
    StoredData(
        key="spotify_token", name="your Spotify login",
        purpose="controlling Spotify without signing in every time",
        kept="until you delete it", sensitive=True, encrypted=True, paths=_spotify_token,
        exportable=False, export_note="A login secret: listed, but never copied into the export file.",
    ),
    StoredData(
        key="privacy_state", name="your privacy choices",
        purpose="remembering which online features you allowed, and offline mode",
        kept="until you change or delete them", sensitive=False, encrypted=True, paths=_privacy_state,
    ),
    StoredData(
        key="network_log", name="the network log",
        purpose="a record of when and where I went online, so you can check",
        kept="30 days", sensitive=False, encrypted=True, paths=_network_log,
    ),
    StoredData(
        key="logs", name="troubleshooting logs",
        purpose="diagnosing problems; they don't include what you say unless you turn that on",
        kept="the number of days set in privacy.log_retention_days (7 by default)",
        sensitive=False, encrypted=False, paths=_logs,
        exportable=False, export_note="Plain-text files you can open directly; see 'files' for where they are.",
    ),
    StoredData(
        key="installed_apps", name="the list of installed apps",
        purpose="knowing which apps and games you can open by voice",
        kept="rebuilt from your Start Menu and Steam library every time Ash starts",
        sensitive=False, encrypted=False, paths=_installed_apps,
        exportable=False, erasable=False,
        export_note="Not about you: a list of the apps installed on this PC.",
    ),
]


def by_key(key: str) -> StoredData:
    return next(item for item in INVENTORY if item.key == key)


def existing_files(item: StoredData) -> list[Path]:
    return [p for p in item.paths() if p.exists()]


def is_stored(item: StoredData) -> bool:
    return bool(existing_files(item))


def read_contents(item: StoredData) -> Any:
    """Decrypted contents of a single-file encrypted item, for export and
    counting. None if not stored or unreadable."""
    files = existing_files(item)
    if not item.encrypted or len(files) != 1:
        return None
    try:
        return secure_store.read_json(files[0])
    except (OSError, ValueError):
        return None
