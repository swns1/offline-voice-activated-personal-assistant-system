"""Generic launcher for any registered protocol URI (steam://, a future
epic/battlenet/etc entry, ...). os.startfile is the same mechanism
Windows uses when a registered protocol link is clicked -- no console
flash, no shell-quoting concerns. Adding a new launcher-gated ecosystem
later is a new registry entry with this launch type, not new code here.
"""
import os
from collections.abc import Mapping
from typing import Any

from ash.launchers.base import Launcher

_NON_PARAM_KEYS = ("type", "protocol", "uri_template")


class UriLauncher(Launcher):
    def can_handle(self, launch: Mapping[str, Any]) -> bool:
        return launch.get("type") == "uri"

    def launch(self, launch: Mapping[str, Any]) -> None:
        params = {k: v for k, v in launch.items() if k not in _NON_PARAM_KEYS}
        uri = launch["uri_template"].format(**params)
        os.startfile(uri)
