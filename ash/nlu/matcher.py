"""Resolves a spoken target to a registry entry: exact/alias match first,
then a rapidfuzz fallback for loose phrasing (e.g. "open my elden ring
game" against a registered "elden ring" alias).

A fuzzy score alone isn't enough to accept a match. WRatio scores any
single shared word highly when the two strings differ in length -- "turn
it down a bit" scores 85.5 against "Python 3.13 Module Docs (64-bit)"
purely on "bit", well over the cutoff. So a fuzzy candidate must also
cover enough of what was actually said: the share of the target's
meaningful words (filler like "my"/"the"/"app" ignored) that appear,
allowing for small transcription slips, in the app's name.

- An explicit "open X" needs at least half of X's words covered -- you
  asked to open something, so loose phrasing gets some benefit of the
  doubt ("open my elden ring game" -> elden, ring: both covered).
- A guessed open (no verb recognized; the whole utterance became the
  target) needs every meaningful word covered -- you never said "open",
  so a sentence that merely shares a word with some app's name must not
  launch it.
"""
from dataclasses import dataclass

from rapidfuzz import fuzz, process, utils

from ash.registry.schema import AppEntry, Registry

FUZZY_SCORE_CUTOFF = 80.0

# Minimum share of the target's meaningful words that must appear in the
# matched name.
EXPLICIT_MIN_COVERAGE = 0.5
GUESSED_MIN_COVERAGE = 1.0

# Two words count as the same if they're this similar (fuzz.ratio) --
# tolerates small speech-to-text slips ("spotfy" ~ "spotify").
_WORD_SIMILARITY = 80.0

# Words that say nothing about *which* app is meant.
_FILLER_WORDS = frozenset({
    "a", "an", "the", "my", "me", "it", "this", "that", "please", "up",
    "for", "to", "on", "of", "and", "some", "app", "application",
    "program", "game",
})

# How many fuzzy candidates to look past the top one for, before giving
# up -- the best-scoring name can fail coverage while a slightly lower
# one passes.
_CANDIDATE_POOL = 10


@dataclass
class MatchResult:
    entry: AppEntry
    score: float


def word_coverage(target: str, name: str) -> float:
    """Share (0..1) of the target's meaningful words found in `name`."""
    words = utils.default_process(target).split()
    meaningful = [w for w in words if w not in _FILLER_WORDS] or words
    if not meaningful:
        return 0.0
    name_words = utils.default_process(name).split()
    hits = sum(
        1 for w in meaningful
        if any(fuzz.ratio(w, n) >= _WORD_SIMILARITY for n in name_words)
    )
    return hits / len(meaningful)


def match_app(target: str, registry: Registry, *, guessed: bool = False) -> MatchResult | None:
    normalized = target.strip().lower()
    if not normalized:
        return None

    for entry in registry.apps:
        for name in entry.names:
            if name.lower() == normalized:
                return MatchResult(entry=entry, score=100.0)

    candidates = _fuzzy_candidates(normalized, registry, guessed=guessed, limit=1)
    return candidates[0] if candidates else None


def match_candidates(target: str, registry: Registry, limit: int = 3, *, guessed: bool = False) -> list[MatchResult]:
    """Like match_app, but returns up to `limit` candidates above the
    fuzzy cutoff instead of just the best one -- lets a caller detect
    genuine ambiguity (multiple close-scoring apps) instead of silently
    picking whichever scored highest."""
    normalized = target.strip().lower()
    if not normalized:
        return []
    return _fuzzy_candidates(normalized, registry, guessed=guessed, limit=limit)


def _fuzzy_candidates(normalized: str, registry: Registry, *, guessed: bool, limit: int) -> list[MatchResult]:
    name_to_entry = {name: entry for entry in registry.apps for name in entry.names}
    if not name_to_entry:
        return []

    min_coverage = GUESSED_MIN_COVERAGE if guessed else EXPLICIT_MIN_COVERAGE
    results = process.extract(
        normalized, name_to_entry.keys(), scorer=fuzz.WRatio,
        processor=utils.default_process, score_cutoff=FUZZY_SCORE_CUTOFF,
        limit=max(limit, _CANDIDATE_POOL),
    )

    candidates: list[MatchResult] = []
    seen_ids: set[str] = set()
    for matched_name, score, _ in results:
        entry = name_to_entry[matched_name]
        if entry.id in seen_ids:
            continue  # a second alias of an app already in the list
        if word_coverage(normalized, matched_name) < min_coverage:
            continue  # high score from a word or two in common, not a real match
        seen_ids.add(entry.id)
        candidates.append(MatchResult(entry=entry, score=score))
        if len(candidates) == limit:
            break
    return candidates
