"""Launches plain .exe / .lnk targets (registry `launch.type: exe`)."""
import os
import subprocess
from collections.abc import Mapping
from typing import Any

from ash.launchers.base import Launcher


class ExeLauncher(Launcher):
    def can_handle(self, launch: Mapping[str, Any]) -> bool:
        return launch.get("type") == "exe"

    def launch(self, launch: Mapping[str, Any]) -> None:
        target = os.path.expandvars(launch["target"])
        args = launch.get("args", [])
        subprocess.Popen([target, *args])
