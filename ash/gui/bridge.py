"""Carries things from Ash's background threads to the window.

Qt widgets may only be touched on the main (GUI) thread, but Ash's
events come from the command worker, the microphone loop and timer
threads. Emitting a Qt signal from any thread is safe: the connected
slot runs later on the GUI thread (a queued connection).

run() is how the window reads or changes your data: the work runs on
AssistantCore's worker thread (the only thread that touches Ash's data
files, so nothing races a command that's running), and the result
comes back to `on_done` on the GUI thread.
"""
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from PySide6.QtCore import QObject, Signal


class CoreBridge(QObject):
    event = Signal(object)          # an ash.core.Event
    core_ready = Signal(object)     # the AssistantCore, once it's running
    voice_ready = Signal(object)    # the VoiceLoop, once the speech models are loaded
    voice_failed = Signal(str)      # why voice couldn't start (typing still works)
    # A yes/no question from a background thread: (text, Future). The
    # window shows it and sets the Future's result to True/False.
    ask = Signal(str, object)
    _done = Signal(object, object)  # (callback, Future), see run()

    def __init__(self):
        super().__init__()
        self.core = None
        self.voice = None
        self._done.connect(self._finish)
        self.core_ready.connect(self._set_core)
        self.voice_ready.connect(self._set_voice)

    def _set_core(self, core) -> None:
        self.core = core

    def _set_voice(self, voice) -> None:
        self.voice = voice

    def run(self, fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
            on_error: Callable[[BaseException], None] | None = None) -> None:
        """Run fn on the command worker; call on_done(result) (or
        on_error(exception)) back on the GUI thread."""
        if self.core is None:
            return
        future = self.core.call(fn)
        future.add_done_callback(lambda f: self._done.emit((on_done, on_error), f))

    def submit(self, text: str, source: str, on_done: Callable[[Any], None] | None = None) -> None:
        """Run a command as if you'd said it (so it asks the same
        questions and gives the same reply); on_done(open question or
        None) is called on the GUI thread once it has finished."""
        if self.core is None:
            return
        future = self.core.submit(text, source)
        future.add_done_callback(lambda f: self._done.emit((on_done, None), f))

    def _finish(self, callbacks, future: Future) -> None:
        on_done, on_error = callbacks
        error = future.exception()
        if error is not None:
            if on_error is not None:
                on_error(error)
            elif self.core is not None:
                self.core.log.error("Window task failed", exc_info=error)
            return
        if on_done is not None:
            on_done(future.result())
