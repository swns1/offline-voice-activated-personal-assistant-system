r"""Standalone health check: loads every engine Ash needs (wake word,
speech recognition, voice output, encryption, the window) without
speaking, opening the microphone or downloading anything, plus the
checks the "run diagnostics" voice command speaks.

Run: .venv\Scripts\python.exe scripts\selftest.py
(The same as `python -m ash --selftest`, or `Ash.exe --selftest` for
the packaged app.)
"""
import sys

from ash.config import load_config
from ash.selftest import report, run_selftest

if __name__ == "__main__":
    text, passed = report(run_selftest(load_config()))
    print(text)
    sys.exit(0 if passed else 1)
