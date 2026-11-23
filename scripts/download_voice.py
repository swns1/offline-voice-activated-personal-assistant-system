r"""One-time download of a Piper voice, for voice.engine: piper (the
desktop window offers the same download when Ash starts). Blocked in
offline mode and recorded in Ash's network log, like Ash's other model
downloads. Needs `pip install piper-tts` to be used.

Run: .venv\Scripts\python.exe scripts\download_voice.py [voice]
Defaults to the voice set in config.yaml (voice.piper_voice).
"""
import sys

from ash.config import load_config
from ash.setup_models import PIPER_VOICES, download_piper_voice, piper_installed, piper_voice_path

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else load_config().voice.piper_voice
    if name in PIPER_VOICES:
        description, size, licence = PIPER_VOICES[name]
        print(f"Downloading {name}: {description}, about {size} MB, voice licence: {licence}")
    else:
        print(f"Downloading {name}")
    download_piper_voice(name)
    print(f"Saved to {piper_voice_path(name)}")
    if not piper_installed():
        print("To use it: pip install piper-tts, then set voice.engine: piper in config.yaml (or in Settings).")
