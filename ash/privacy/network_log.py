"""A record of every time Ash sent anything off this PC: when, which
feature, to which website, and what kind of data -- never the content
itself (the log says "the words you search for", not the words).
Stored encrypted in %LOCALAPPDATA%\\Ash\\network_log.json and pruned to
the last RETENTION_DAYS days.

This is what lets you check, rather than take on trust, that Ash only
goes online when and how it says (RA 10173 Sec. 11: transparency).
"""
import threading
from collections import Counter
from datetime import datetime, timedelta

from ash.privacy import secure_store
from ash.utils.paths import NETWORK_LOG_PATH

RETENTION_DAYS = 30

_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        entries = secure_store.read_json(NETWORK_LOG_PATH, default=[])
    except (OSError, ValueError):
        return []
    return entries if isinstance(entries, list) else []


def record(feature: str, name: str, service: str, domain: str, sends: str, now: datetime | None = None) -> None:
    """`feature` is the key (e.g. "web_search"), `name` how it's spoken ("web search")."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=RETENTION_DAYS)
    with _lock:
        entries = [e for e in _load() if _parse(e.get("at")) >= cutoff]
        entries.append({
            "at": now.isoformat(timespec="seconds"),
            "feature": feature,
            "name": name,
            "service": service,
            "domain": domain,
            "sends": sends,
        })
        try:
            secure_store.write_json(NETWORK_LOG_PATH, entries)
        except OSError:
            pass  # best-effort, like the rest of Ash's persistence


def entries(since: datetime | None = None) -> list[dict]:
    if since is None:
        return _load()
    return [e for e in _load() if _parse(e.get("at")) >= since]


def summary(days: int = 7, now: datetime | None = None) -> str:
    """A spoken summary, e.g. "In the last 7 days, I went online 12
    times: 10 times to DuckDuckGo for web search, and 2 times to
    Spotify for Spotify." """
    now = now or datetime.now()
    recent = entries(since=now - timedelta(days=days))
    if not recent:
        return f"I haven't sent anything off this PC in the last {days} days."
    counts = Counter((e.get("service", "?"), e.get("name") or e.get("feature", "?")) for e in recent)
    parts = [f"{n} time{'' if n == 1 else 's'} to {service} for {name}"
             for (service, name), n in counts.most_common()]
    total = len(recent)
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f", and {parts[-1]}"
    return (f"In the last {days} days, I went online {total} time{'' if total == 1 else 's'}: "
            f"{listed}.")


def _parse(value) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min
