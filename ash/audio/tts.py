"""Text-to-speech via a single dedicated worker thread.

Two voice engines, chosen by `voice.engine` in config.yaml:

- "windows" (default): the built-in Windows (SAPI) voice via pyttsx3.
- "piper": a neural voice (Piper, https://github.com/OHF-Voice/piper1-gpl),
  run on this PC with onnxruntime. Much more natural. An optional
  install (`pip install piper-tts`), because Piper is GPL-licensed and
  Ash is MIT; see README "A more natural voice". The voice model is
  downloaded once (ash/setup_models.py). If Piper or the voice is
  missing, or fails to load, Ash falls back to the Windows voice and
  says so in the log.

All speech goes through one thread: SAPI is COM, which isn't safely
reentrant across arbitrary threads, and one queue keeps replies in
order whichever engine speaks them.

stop_speaking() (from any thread) clears the queue and interrupts what
is playing; is_speaking() lets ContinuousListener detect barge-in (the
user talking over a response) -- see ash/audio/recorder.py.
"""
import logging
import queue
import threading
from pathlib import Path

import pythoncom
import pyttsx3

_SHUTDOWN = object()
log = logging.getLogger("ash")


class SapiEngine:
    """The Windows voice. Must be created on the thread that uses it."""

    name = "windows"

    def __init__(self, rate: int = 180, voice_id: str | None = None):
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        if voice_id:
            self._engine.setProperty("voice", voice_id)

    def speak(self, text: str) -> None:
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        # Cross-thread engine.stop() interrupts SAPI immediately.
        self._engine.stop()


class PiperEngine:
    """A Piper neural voice, played through the default speakers. Speaks
    sentence by sentence: the first sentence plays while the rest are
    still being generated, and stop() takes effect between sentences
    and mid-sentence alike."""

    name = "piper"

    def __init__(self, model_path: Path):
        from piper import PiperVoice  # optional dependency

        self._voice = PiperVoice.load(model_path)
        self._stopped = threading.Event()
        # The first synthesis is slow (~1.5 s: onnxruntime warming up), so
        # do it now, silently, rather than on your first reply (~0.1 s after).
        for _ in self._voice.synthesize("Ready."):
            pass

    def speak(self, text: str) -> None:
        import sounddevice as sd

        self._stopped.clear()
        # synthesize() makes one sentence per step, so the next sentence
        # is generated while this one plays (sd.play doesn't block).
        for chunk in self._voice.synthesize(text):
            sd.wait()
            if self._stopped.is_set():
                return
            sd.play(chunk.audio_int16_array, chunk.sample_rate)
        sd.wait()

    def stop(self) -> None:
        import sounddevice as sd

        self._stopped.set()
        sd.stop()


def make_engine(engine: str = "windows", piper_model: Path | None = None, rate: int = 180,
                voice_id: str | None = None):
    """The configured engine, or the Windows voice if Piper can't start."""
    if engine == "piper":
        try:
            if piper_model is None or not piper_model.exists():
                raise FileNotFoundError(f"Piper voice not downloaded: {piper_model}")
            return PiperEngine(piper_model)
        except Exception:
            log.warning("Piper voice unavailable, using the Windows voice instead", exc_info=True)
    return SapiEngine(rate, voice_id)


class TtsWorker:
    def __init__(self, rate: int = 180, voice_id: str | None = None, *, engine: str = "windows",
                 piper_model: Path | None = None):
        self._rate = rate
        self._voice_id = voice_id
        self._engine_name = engine
        self._piper_model = piper_model
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._engine = None  # set once _run()'s thread constructs it
        # Set/cleared only by _run()'s own thread; read (lock-free, safe
        # for a plain bool flip) from the mic thread for barge-in
        # detection -- see ContinuousListener._wait_for_wake().
        self._speaking = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def say(self, text: str) -> None:
        self._queue.put(text)

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    @property
    def engine_name(self) -> str | None:
        """"windows" or "piper" once started (after any fallback)."""
        return getattr(self._engine, "name", None)

    def stop_speaking(self) -> None:
        """Clears anything queued but not yet spoken and interrupts
        whatever is currently playing. Safe to call even if nothing is
        speaking."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        if self._engine is not None:
            self._engine.stop()

    def stop(self) -> None:
        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout=5)

    def _run(self) -> None:
        pythoncom.CoInitialize()
        try:
            self._engine = make_engine(self._engine_name, self._piper_model, self._rate, self._voice_id)
            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    break
                self._speaking.set()
                try:
                    self._engine.speak(item)
                except Exception:
                    log.exception("Speaking failed")
                finally:
                    self._speaking.clear()
        finally:
            pythoncom.CoUninitialize()
