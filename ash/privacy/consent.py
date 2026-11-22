"""Your privacy choices: offline mode, and which online features you've
allowed. Stored encrypted (ash/privacy/secure_store.py) in
%LOCALAPPDATA%\\Ash\\privacy_state.json.

Each online feature (see FEATURES in ash/privacy/egress.py) starts out
"unasked". The first time it's needed, Ash explains what it would send
and to whom and asks; your answer is remembered with the time you gave
it (RA 10173 Sec. 12(a): consent, given freely and specifically). You
can change it any time ("allow web search" / "stop allowing web
search"), and a "no" is respected rather than asked again.

Offline mode overrides every allowance: while it's on, nothing leaves
this PC.
"""
import threading
from datetime import datetime

from ash.privacy import secure_store
from ash.utils.paths import PRIVACY_STATE_PATH

GRANTED = "granted"
DENIED = "denied"
UNASKED = "unasked"

_lock = threading.Lock()


def _load() -> dict:
    try:
        state = secure_store.read_json(PRIVACY_STATE_PATH, default={})
    except (OSError, ValueError):
        state = {}  # unreadable -> treat as fresh: everything unasked, online
    if not isinstance(state, dict):
        state = {}
    state.setdefault("offline_mode", False)
    state.setdefault("consents", {})
    return state


def _save(state: dict) -> None:
    secure_store.write_json(PRIVACY_STATE_PATH, state)


def status(feature_key: str) -> str:
    record = _load()["consents"].get(feature_key)
    if not isinstance(record, dict):
        return UNASKED
    return GRANTED if record.get("granted") else DENIED


def _set(feature_key: str, granted: bool) -> None:
    with _lock:
        state = _load()
        state["consents"][feature_key] = {
            "granted": granted,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        _save(state)


def grant(feature_key: str) -> None:
    _set(feature_key, True)


def deny(feature_key: str) -> None:
    _set(feature_key, False)


def all_consents() -> dict[str, dict]:
    """feature key -> {"granted": bool, "at": iso timestamp}, for the
    privacy dashboard and data export."""
    return dict(_load()["consents"])


def offline_mode() -> bool:
    return bool(_load()["offline_mode"])


def set_offline_mode(enabled: bool) -> None:
    with _lock:
        state = _load()
        state["offline_mode"] = enabled
        _save(state)
