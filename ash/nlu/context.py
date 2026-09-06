"""Tracks the most recently opened app, searched query, and Spotify
track, so a bare pronoun ("it", "that", "this") in a follow-up command
resolves to what it obviously refers to -- "open spotify" ... "close
it" -- instead of being passed through literally as a nonsensical
target string. Module-level state, same pattern as
ash/actions/timers.py's _active registry: a single conversation with
one user at a time, no per-session isolation needed.
"""
import re
from dataclasses import dataclass

_PRONOUNS = {"it", "that", "this"}
# Stripped before the pronoun check, so "search that again"/"open it
# please" resolve the same way as the bare pronoun does.
_TRAILING_FILLER_RE = re.compile(r"\s+(again|please)$", re.IGNORECASE)


@dataclass
class _RecentContext:
    last_app: str | None = None
    last_search: str | None = None
    last_spotify_track: str | None = None


_context = _RecentContext()

# Which _RecentContext field a bare pronoun resolves against, per intent.
# Intents not listed here never get their target substituted.
_INTENT_FIELD = {
    "open": "last_app",
    "close_app": "last_app",
    "search": "last_search",
    "spotify_play": "last_spotify_track",
}


def remember_app(name: str) -> None:
    _context.last_app = name


def remember_search(query: str) -> None:
    _context.last_search = query


def remember_spotify_track(name: str) -> None:
    _context.last_spotify_track = name


def resolve_target(intent: str, target: str) -> str:
    normalized = _TRAILING_FILLER_RE.sub("", target.strip().lower())
    if normalized not in _PRONOUNS:
        return target
    field = _INTENT_FIELD.get(intent)
    if field is None:
        return target
    value = getattr(_context, field)
    return value if value else target
