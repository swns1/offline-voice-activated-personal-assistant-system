"""The scripts' audio helpers live in ash/audio/clips.py; re-exported
here so `from clips import ...` keeps working in scripts/."""
from ash.audio.clips import SAMPLE_RATE, read_wav, record_command, synthesize, write_wav  # noqa: F401
