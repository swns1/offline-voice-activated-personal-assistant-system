"""Scans Windows Start Menu shortcuts to auto-populate the app registry,
so ordinary installed apps don't need to be hand-added to registry.yaml.
A shortcut's real target can only be read via the shell COM interface
(pywin32, already a dependency) -- there's no way to parse a .lnk file's
target directly that's simpler or more reliable than this.
"""
import os
from collections.abc import Callable
from pathlib import Path

import pythoncom
import win32com.client

from ash.registry._slugify import slugify

_DEFAULT_SEARCH_DIRS = [
    Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
    Path(os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")),
]

# Shortcut display names that are never something you'd say "open X" for.
_SKIP_NAME_SUBSTRINGS = (
    "uninstall", "readme", "help", "documentation", "license", "changelog",
    "website", "web site",
)


def _default_shell_factory():
    return win32com.client.Dispatch("WScript.Shell")


def scan_start_menu(
    search_dirs: list[Path] | None = None,
    shell_factory: Callable[[], object] | None = None,
) -> list[dict]:
    """Returns AppEntry-shaped dicts for resolvable, non-junk .lnk targets,
    deduped by resolved target path (per-user and all-users Start Menu
    trees often contain the same app twice)."""
    if search_dirs is None:
        search_dirs = _DEFAULT_SEARCH_DIRS
    if shell_factory is None:
        shell_factory = _default_shell_factory

    pythoncom.CoInitialize()
    try:
        shell = shell_factory()
        entries: dict[str, dict] = {}
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for lnk_path in search_dir.rglob("*.lnk"):
                entry = _resolve_shortcut(shell, lnk_path)
                if entry is None:
                    continue
                target = entry["launch"]["target"]
                if target in entries:
                    existing_names = entries[target]["names"]
                    for name in entry["names"]:
                        if name not in existing_names:
                            existing_names.append(name)
                else:
                    entries[target] = entry
        return list(entries.values())
    finally:
        pythoncom.CoUninitialize()


def _resolve_shortcut(shell, lnk_path: Path) -> dict | None:
    display_name = lnk_path.stem
    lowered = display_name.lower()
    if any(pattern in lowered for pattern in _SKIP_NAME_SUBSTRINGS):
        return None

    try:
        shortcut = shell.CreateShortcut(str(lnk_path))
        target = shortcut.Targetpath
        args = shortcut.Arguments
    except Exception:
        return None

    if not target or not target.lower().endswith(".exe") or not os.path.exists(target):
        return None

    launch = {"type": "exe", "target": target}
    if args:
        launch["args"] = args.split()

    return {
        "id": slugify(display_name),
        "names": [lowered],
        "launch": launch,
        "source": "start_menu",
    }
