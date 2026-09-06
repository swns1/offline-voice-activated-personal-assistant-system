"""Rescans the Start Menu and (if installed) the Steam library, writing
the combined results to config/registry.auto.yaml. Ash also does this
automatically at every startup (see RegistryConfig.auto_rescan_on_startup
in ash/config.py) -- this script is for forcing a rescan on demand
without starting the full assistant, e.g. right after installing a new
app/game while Ash is already running (restart Ash afterward to pick it
up, or just ask for it -- see the retry-on-no-match fallback in
ash/actions/open_app.py). Entries in registry.yaml always win over these
on collision; see ash/registry/loader.py.

Run: .venv\\Scripts\\python.exe scripts\\build_registry_auto.py
"""
from ash.registry.auto_build import refresh_registry_auto
from ash.utils.paths import REGISTRY_AUTO_PATH

if __name__ == "__main__":
    count = refresh_registry_auto()
    print(f"Wrote {count} auto-discovered entries to {REGISTRY_AUTO_PATH}")
