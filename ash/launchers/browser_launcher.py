"""Opens a URL, optionally pinned to a specific Chrome/Edge profile so
Google's account picker never shows. Phase 3: browser discovery only
via common install paths, profile_directory passed straight through
from registry config. Phase 8 adds real profile-name discovery/picking
via browser_profiles.py -- this launcher's shape doesn't need to change
for that, only what populates `profile_directory` does.
"""
import os
import subprocess
from typing import Any, Mapping

from ash.launchers.base import Launcher

_CHROME_CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]
_EDGE_CANDIDATES = [
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser(browser: str) -> str | None:
    candidates = {"chrome": _CHROME_CANDIDATES, "edge": _EDGE_CANDIDATES}.get(browser, [])
    for candidate in candidates:
        path = os.path.expandvars(candidate)
        if os.path.exists(path):
            return path
    return None


class BrowserLauncher(Launcher):
    def can_handle(self, launch: Mapping[str, Any]) -> bool:
        return launch.get("type") == "browser_open"

    def launch(self, launch: Mapping[str, Any]) -> None:
        url = launch["url"]
        browser_path = _find_browser(launch.get("browser", "default"))

        if not browser_path:
            os.startfile(url)  # system default browser, no profile pinning available
            return

        args = [browser_path]
        profile_directory = launch.get("profile_directory")
        if profile_directory:
            args.append(f"--profile-directory={profile_directory}")
        args.append(url)
        subprocess.Popen(args)
