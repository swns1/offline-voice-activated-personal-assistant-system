"""Syncs the Windows Registry Run key to match config.yaml's
`autostart` setting, without starting Ash itself. main() already does
this on every startup -- this script is for checking/applying it
without launching the full assistant.

Run: .venv\\Scripts\\python.exe scripts\\apply_autostart.py
"""
from ash.config import load_config
from ash.utils.autostart import is_autostart_enabled, sync_autostart

if __name__ == "__main__":
    config = load_config()
    sync_autostart(config.autostart)
    state = "enabled" if is_autostart_enabled() else "disabled"
    print(f"Autostart is now {state} (config.yaml: autostart: {str(config.autostart).lower()})")
