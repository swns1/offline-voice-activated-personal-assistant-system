"""Resolves a spoken profile name ("Work", "Personal") to the internal
folder name Chrome/Edge's --profile-directory flag actually expects
("Profile 1", "Profile 2", ...). That mapping lives in each browser's
own Local State file, an undocumented Chromium-internal JSON format --
treated as unreliable/best-effort, never crashing Ash if it's missing
or its shape changes.
"""
import json
import os
from pathlib import Path

from rapidfuzz import fuzz, process, utils

_LOCAL_STATE_PATHS = {
    "chrome": r"%LocalAppData%\Google\Chrome\User Data\Local State",
    "edge": r"%LocalAppData%\Microsoft\Edge\User Data\Local State",
}

FUZZY_SCORE_CUTOFF = 80.0


def list_profiles(browser: str) -> dict[str, str]:
    """Returns {display_name.lower(): internal_directory_key}, e.g.
    {"work": "Profile 1"}. Empty dict if the browser or its Local State
    file can't be found or parsed."""
    template = _LOCAL_STATE_PATHS.get(browser)
    if template is None:
        return {}

    path = Path(os.path.expandvars(template))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data["profile"]["info_cache"]
        return {
            info["name"].lower(): directory_key
            for directory_key, info in info_cache.items()
            if "name" in info
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def resolve_profile(browser: str, spoken_name: str) -> str | None:
    """Spoken display name -> internal directory key, exact then fuzzy."""
    profiles = list_profiles(browser)
    if not profiles:
        return None

    normalized = spoken_name.strip().lower()
    if normalized in profiles:
        return profiles[normalized]

    best = process.extractOne(
        normalized, profiles.keys(), scorer=fuzz.WRatio,
        processor=utils.default_process, score_cutoff=FUZZY_SCORE_CUTOFF,
    )
    if best is None:
        return None

    matched_name, _score, _ = best
    return profiles[matched_name]
