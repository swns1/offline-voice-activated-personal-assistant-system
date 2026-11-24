"""A health check of everything Ash needs, without speaking, opening the
microphone or downloading anything: `python -m ash --selftest` (or
`Ash.exe --selftest > selftest.txt` for the packaged app, which has no
console). Each check loads the real engine, so it also catches a broken
build (a missing file or DLL) that unit tests can't see.

Exit code 0 if everything Ash needs to listen works; the optional
extras (local AI, Spotify) are reported but don't fail it.
"""
import tempfile
import time
from pathlib import Path

import numpy as np

from ash.actions.diagnostics import run_diagnostics
from ash.config import Config

Check = tuple[str, bool, str]

# Reported, but not needed for Ash to work.
OPTIONAL = {"Ollama", "Spotify", "Natural voice"}  # the voice falls back to Windows


def _timed(name: str, fn) -> Check:
    start = time.perf_counter()
    try:
        detail = fn()
    except Exception as exc:  # report every failure, keep checking the rest
        return (name, False, f"{type(exc).__name__}: {exc}")
    return (name, True, f"{detail} ({time.perf_counter() - start:.1f} s)")


def _wake_word(config: Config) -> str:
    from ash import setup_models
    from ash.audio.wake_word import FRAME_LENGTH, WakeWordDetector

    if setup_models.wake_word_model_missing(config.wake_word.keyword):
        raise RuntimeError("model not downloaded yet (Ash asks to download it when it starts)")
    detector = WakeWordDetector(config.wake_word.keyword, config.wake_word.threshold)
    detector.process(np.zeros(FRAME_LENGTH, dtype="int16"))
    return f"{config.wake_word.keyword} loaded"


def _speech_recognition(config: Config) -> str:
    from ash import setup_models
    from ash.audio.stt import SAMPLE_RATE, SpeechToText

    if setup_models.whisper_model_missing(config.speech.model):
        raise RuntimeError("model not downloaded yet (Ash asks to download it when it starts)")
    stt = SpeechToText(model_size=config.speech.model, device=config.speech.device)
    stt.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))
    return f"Whisper {config.speech.model} on the {'GPU' if stt.device == 'cuda' else 'CPU'}"


def _piper_voice(config: Config) -> str:
    from ash import setup_models
    from ash.audio.tts import PiperEngine

    name = config.voice.piper_voice
    if not setup_models.piper_installed():
        raise RuntimeError("piper-tts isn't installed (pip install piper-tts); Ash uses the Windows voice")
    if setup_models.piper_voice_missing(name):
        raise RuntimeError(f"voice {name} not downloaded yet (scripts/download_voice.py); Ash uses the Windows voice")
    PiperEngine(setup_models.piper_voice_path(name))  # loads and warms up, silently
    return f"Piper {name}"


def _voice_output() -> str:
    import pythoncom
    import pyttsx3

    pythoncom.CoInitialize()
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        engine.stop()
    finally:
        pythoncom.CoUninitialize()
    return f"{len(voices)} Windows voice{'' if len(voices) == 1 else 's'}"


def _encryption() -> str:
    from ash.privacy import secure_store

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "check.json"
        secure_store.write_json(path, {"check": True})
        if not secure_store.is_encrypted(path) or secure_store.read_json(path, default=None) != {"check": True}:
            raise RuntimeError("round trip failed")
    return "DPAPI round trip"


def _window() -> str:
    import PySide6

    return f"PySide6 {PySide6.__version__}"


def run_selftest(config: Config) -> list[Check]:
    checks = [
        _timed("Wake word", lambda: _wake_word(config)),
        _timed("Speech recognition", lambda: _speech_recognition(config)),
        _timed("Voice output", _voice_output),
        *([_timed("Natural voice", lambda: _piper_voice(config))] if config.voice.engine == "piper" else []),
        _timed("Encryption", _encryption),
        _timed("Desktop window", _window),
    ]
    return checks + run_diagnostics(config)


def report(checks: list[Check]) -> tuple[str, bool]:
    lines = []
    passed = True
    for name, ok, detail in checks:
        optional = name in OPTIONAL
        status = "OK" if ok else ("--" if optional else "FAIL")
        passed &= ok or optional
        lines.append(f"[{status:>4}] {name}: {detail}")
    lines.append("All required checks passed." if passed else "Some required checks failed.")
    return "\n".join(lines), passed
