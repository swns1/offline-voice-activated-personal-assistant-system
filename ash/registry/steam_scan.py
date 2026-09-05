"""Scans installed Steam games via libraryfolders.vdf + appmanifest_*.acf
so games don't need to be hand-added to registry.yaml. Degrades to an
empty result (never raises) if Steam isn't installed -- most machines
running Ash won't have it.
"""
import winreg
from pathlib import Path

import vdf

_SKIP_NAME_SUBSTRINGS = (
    "steamworks common redistributables",
    "steam linux runtime",
    "proton ",
)


def find_steam_path() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            path, _ = winreg.QueryValueEx(key, "SteamPath")
    except OSError:
        return None
    return Path(path)


def scan_steam_library(steam_path: Path | None = None) -> list[dict]:
    if steam_path is None:
        steam_path = find_steam_path()
    if steam_path is None or not steam_path.exists():
        return []

    entries = []
    for library in _library_paths(steam_path):
        steamapps = library / "steamapps"
        if not steamapps.exists():
            continue
        for manifest_path in steamapps.glob("appmanifest_*.acf"):
            entry = _parse_manifest(manifest_path)
            if entry is not None:
                entries.append(entry)
    return entries


def _library_paths(steam_path: Path) -> list[Path]:
    libraryfolders_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    data = _load_vdf(libraryfolders_vdf)
    if data is None:
        return [steam_path]

    folders = data.get("libraryfolders", {})
    paths = [Path(entry["path"]) for entry in folders.values() if "path" in entry]
    return paths or [steam_path]


def _parse_manifest(manifest_path: Path) -> dict | None:
    data = _load_vdf(manifest_path)
    if data is None:
        return None

    state = data.get("AppState", {})
    appid = state.get("appid")
    name = state.get("name")
    if not appid or not name:
        return None
    if any(pattern in name.lower() for pattern in _SKIP_NAME_SUBSTRINGS):
        return None

    return {
        "id": f"steam_{appid}",
        "names": [name.lower()],
        "launch": {
            "type": "uri",
            "protocol": "steam",
            "uri_template": "steam://rungameid/{appid}",
            "appid": appid,
        },
        "source": "steam",
    }


def _load_vdf(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return vdf.load(f)
    except (OSError, SyntaxError):
        return None
