"""Text-to-speech via a single dedicated worker thread.

pyttsx3 wraps SAPI5 over COM, which is not safely reentrant across
arbitrary threads. Centralizing all speech through one thread with its
own CoInitialize() call avoids the intermittent, hard-to-reproduce
failures that come from calling pyttsx3 from whichever thread happens
to trigger a response.

Cross-thread engine.stop() (called from the main thread while this
worker's thread is blocked inside engine.runAndWait()) is confirmed to
interrupt speech immediately rather than needing to run on the TTS
thread itself.
"""
import queue
import threading

import pythoncom
import pyttsx3

_SHUTDOWN = object()


class TtsWorker:
    def __init__(self, rate: int = 180, voice_id: str | None = None):
        self._rate = rate
        self._voice_id = voice_id
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._engine = None  # set once _run()'s thread constructs it

    def start(self) -> None:
        self._thread.start()

    def say(self, text: str) -> None:
        self._queue.put(text)

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
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            if self._voice_id:
                engine.setProperty("voice", self._voice_id)
            self._engine = engine

            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    break
                engine.say(item)
                engine.runAndWait()
        finally:
            pythoncom.CoUninitialize()
