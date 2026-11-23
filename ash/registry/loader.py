"""Loads registry.yaml and merges in registry.auto.yaml (Start Menu /
Steam scan results, see scripts/build_registry_auto.py) when present.
Manual entries always win on collision, by id or by any shared voice
name -- a hand-authored entry (e.g. the Steam client itself, launched
via a URI rather than its .lnk) must not be shadowed by an auto-scanned
duplicate.
"""
from pathlib import Path

import yaml

from ash.registry.schema import AppEntry, Registry
from ash.utils.paths import REGISTRY_AUTO_PATH, REGISTRY_MANUAL_PATH


def load_registry(
    manual_path: Path = REGISTRY_MANUAL_PATH,
    auto_path: Path = REGISTRY_AUTO_PATH,
) -> Registry:
    manual_data = _read_yaml(manual_path)
    registry = Registry.model_validate(manual_data)

    auto_data = _read_yaml(auto_path)
    auto_apps = [AppEntry.model_validate(app) for app in auto_data.get("apps", [])]
    registry.apps.extend(_without_manual_overlaps(auto_apps, registry.apps))

    return registry


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {"apps": [], "intents": {}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _without_manual_overlaps(auto_apps: list[AppEntry], manual_apps: list[AppEntry]) -> list[AppEntry]:
    manual_ids = {entry.id for entry in manual_apps}
    manual_names = {name.lower() for entry in manual_apps for name in entry.names}
    return [
        entry for entry in auto_apps
        if entry.id not in manual_ids
        and not any(name.lower() in manual_names for name in entry.names)
    ]
