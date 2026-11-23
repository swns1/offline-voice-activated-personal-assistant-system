"""Ash's real startup imports, each in a fresh Python process -- the
only way to catch native-library (DLL) clashes, which depend on what's
already loaded into the process. Unit tests can't see these: by the
time they run, pytest has imported everything in some other order.

The clash this guards against: the winrt packages bundle an older
msvcp140.dll, and if it loads before onnxruntime's, the wake-word
engine fails to start (see ash/__init__.py)."""
import subprocess
import sys

import pytest

# conftest's safety net blocks subprocess.Popen for every test (so no
# test launches a real program); this test needs to start Python itself.
_REAL_POPEN = subprocess.Popen


def _run_python(code: str) -> subprocess.CompletedProcess:
    process = _REAL_POPEN([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True)
    out, err = process.communicate(timeout=120)
    return subprocess.CompletedProcess(process.args, process.returncode, out, err)


@pytest.mark.parametrize("first", [
    "ash.actions.timers",       # imports win11toast -> winrt
    "ash.actions.media",        # imports winrt media controls
    "ash.main",
])
def test_the_wake_word_engine_loads_whatever_is_imported_first(first):
    result = _run_python(f"import {first}; import onnxruntime; import openwakeword; print('ok')")
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("ok")


def test_the_whole_app_imports():
    pytest.importorskip("PySide6")
    result = _run_python("import ash.main, ash.voice, ash.gui.app; print('ok')")
    assert result.returncode == 0, result.stderr[-2000:]
