"""Encrypted-at-rest JSON files for the personal data Ash keeps
(remembered facts, timers, the voiceprint, the Spotify token, ...).

Uses Windows DPAPI (CryptProtectData) -- the same mechanism Windows
itself uses for saved Wi-Fi and browser passwords. The key is derived
from your Windows login, so the files are unreadable to other Windows
accounts on this PC and to anyone who copies them off it, with no
password for you to manage. In line with RA 10173 Sec. 20 (security of
personal information): proportionate protection for a single-user
desktop app.

What it does NOT protect against: software already running as *you*
can call DPAPI too, so malware on your account could read these files
just as Ash does. See docs/PRIVACY.md's threat model.

Files written before encryption existed are plain JSON. read_json()
recognizes them (no header), returns their contents, and rewrites them
encrypted in the same call -- so existing data migrates the first time
Ash reads it, with nothing for you to do.
"""
import json
import os
from pathlib import Path
from typing import Any

import pywintypes
import win32crypt

# Marks a file as DPAPI-encrypted by Ash (versioned, so the format can
# change later without guessing).
_HEADER = b"ASH-DPAPI-1\n"
# Extra app-specific secret mixed into the DPAPI key: another program
# running as you can't decrypt Ash's files with a bare
# CryptUnprotectData call without also knowing this.
_ENTROPY = b"Ash personal data store v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1  # never pop up a Windows dialog


def write_json(path: Path, data: Any) -> None:
    """Encrypt and save `data` as JSON. Written to a temporary file and
    then swapped into place, so a crash mid-write can't leave a
    half-written (undecryptable) file behind."""
    raw = json.dumps(data).encode("utf-8")
    try:
        blob = win32crypt.CryptProtectData(raw, "Ash", _ENTROPY, None, None, _CRYPTPROTECT_UI_FORBIDDEN)
    except pywintypes.error as e:
        # OSError, like any other failed write -- callers already treat
        # persistence as best-effort on OSError.
        raise OSError(f"Can't encrypt {path.name}: {e.strerror}") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(_HEADER + blob)
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    """Load and decrypt `path`; `default` if it doesn't exist. A legacy
    plain-JSON file is returned and re-saved encrypted.

    Raises ValueError if the file exists but can't be decrypted or
    parsed (corrupt, or encrypted under a different Windows account) --
    the same exception type a bad JSON file already raised, so callers'
    existing error handling covers both."""
    if not path.exists():
        return default
    content = path.read_bytes()

    if content.startswith(_HEADER):
        try:
            _description, raw = win32crypt.CryptUnprotectData(
                content[len(_HEADER):], _ENTROPY, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
            )
        except pywintypes.error as e:
            raise ValueError(f"Can't decrypt {path.name}: {e.strerror}") from e
        return json.loads(raw.decode("utf-8"))

    data = json.loads(content.decode("utf-8"))  # legacy plain JSON
    write_json(path, data)
    return data


def is_encrypted(path: Path) -> bool:
    """True if `path` exists and is in the encrypted format."""
    if not path.exists():
        return False
    with open(path, "rb") as f:
        return f.read(len(_HEADER)) == _HEADER
