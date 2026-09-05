"""Loads registry.yaml. Phase 6 will extend this to also load and merge
registry.auto.yaml (Start Menu / Steam scan results), manual entries
taking precedence on id collision — kept out for now since that file
doesn't exist yet.
"""
from pathlib import Path

import yaml

from ash.registry.schema import Registry
from ash.utils.paths import REGISTRY_MANUAL_PATH


def load_registry(manual_path: Path = REGISTRY_MANUAL_PATH) -> Registry:
    data: dict = {"apps": [], "intents": {}}
    if manual_path.exists():
        with open(manual_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        data.update(loaded)
    return Registry.model_validate(data)
