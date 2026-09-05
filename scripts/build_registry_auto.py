"""Scans the Start Menu and (if installed) the Steam library, writing the
combined results to config/registry.auto.yaml. Not run automatically on
every Ash startup -- it's a deliberate, occasional action (re-run after
installing new apps/games). Entries in registry.yaml always win over
these on collision; see ash/registry/loader.py.

Run: .venv\\Scripts\\python.exe scripts\\build_registry_auto.py
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


if __name__ == "__main__":
    apps = build_registry_auto()
    with open(REGISTRY_AUTO_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump({"apps": apps}, f, sort_keys=False, allow_unicode=True)
    print(f"Wrote {len(apps)} auto-discovered entries to {REGISTRY_AUTO_PATH}")
