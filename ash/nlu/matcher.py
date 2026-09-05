"""Resolves a spoken target to a registry entry: exact/alias match first,
then a rapidfuzz fallback for loose phrasing (e.g. "open my elden ring
game" against a registered "elden ring" alias). A further fallback
against the full Start Menu index arrives in Phase 6, slotting into
this same function without changing its callers.
"""
from dataclasses import dataclass

from rapidfuzz import fuzz, process, utils

from ash.registry.schema import AppEntry, Registry

FUZZY_SCORE_CUTOFF = 80.0


@dataclass
class MatchResult:
    entry: AppEntry
    score: float


def match_app(target: str, registry: Registry) -> MatchResult | None:
    normalized = target.strip().lower()
    if not normalized:
        return None

    for entry in registry.apps:
        for name in entry.names:
            if name.lower() == normalized:
                return MatchResult(entry=entry, score=100.0)

    name_to_entry = {name: entry for entry in registry.apps for name in entry.names}
    if not name_to_entry:
        return None

    best = process.extractOne(
        normalized, name_to_entry.keys(), scorer=fuzz.WRatio,
        processor=utils.default_process, score_cutoff=FUZZY_SCORE_CUTOFF,
    )
    if best is None:
        return None

    matched_name, score, _ = best
    return MatchResult(entry=name_to_entry[matched_name], score=score)
