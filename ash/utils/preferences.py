"""Small personal settings you give Ash by voice (and, later, in the
desktop app's settings) -- for now your city, for the weather. Stored
encrypted (ash/privacy/secure_store.py) in
%LOCALAPPDATA%\\Ash\\preferences.json and listed in the data inventory,
since a home city is personal information.
"""
import threading

from ash.privacy import secure_store
from ash.utils.paths import PREFERENCES_PATH

_lock = threading.Lock()


def _load() -> dict:
    try:
        data = secure_store.read_json(PREFERENCES_PATH, default={})
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default=None):
    return _load().get(key, default)


def set(key: str, value) -> None:  # noqa: A001 - reads naturally as preferences.set(...)
    with _lock:
        data = _load()
        data[key] = value
        secure_store.write_json(PREFERENCES_PATH, data)


def delete(key: str) -> bool:
    with _lock:
        data = _load()
        if key not in data:
            return False
        del data[key]
        secure_store.write_json(PREFERENCES_PATH, data)
        return True
