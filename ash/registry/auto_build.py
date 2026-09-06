"""Builds and writes config/registry.auto.yaml from the Start Menu +
Steam scanners. Shared by scripts/build_registry_auto.py (manual,
standalone) and ash/main.py (automatic, at every startup -- see
RegistryConfig.auto_rescan_on_startup in ash/config.py) and
ash/actions/open_app.py (one-off retry when a spoken app isn't found,
in case it was installed after Ash last started).
"""
import yaml

from ash.registry.start_menu_scan import scan_start_menu
from ash.registry.steam_scan import scan_steam_library
from ash.utils.paths import REGISTRY_AUTO_PATH


def build_registry_auto() -> list[dict]:
    steam_entries = scan_steam_library()
    start_menu_entries = scan_start_menu()

    # A game found by both scanners gets the Steam URI (handles overlay/
    # DRM/workshop correctly, unlike a raw .lnk exe launch) -- drop the
    # Start Menu duplicate.
    steam_names = {name for entry in steam_entries for name in entry["names"]}
    deduped_start_menu = [
        entry for entry in start_menu_entries
        if not any(name in steam_names for name in entry["names"])
    ]

    return steam_entries + deduped_start_menu


def refresh_registry_auto() -> int:
    """Rescans and overwrites registry.auto.yaml. Returns the entry count."""
    apps = build_registry_auto()
    with open(REGISTRY_AUTO_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump({"apps": apps}, f, sort_keys=False, allow_unicode=True)
    return len(apps)
