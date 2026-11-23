"""AssistantCore: the one place commands run, whoever sends them.

Commands now arrive from three places at once: the microphone, the
chat box in the desktop window, and the window's buttons (privacy
dashboard, Yes/No answers). Dispatch, the shared "it/that" context
(ash/nlu/context.py) and Ash's encrypted data files were all written
for one caller at a time, so instead of making each of them
thread-safe, every command -- and every read or write of your data
the window makes -- runs on this one worker thread, in the order it
arrived. Callers get a Future back and never block each other.

A follow-up question ("Are you sure?", "Which app?") stays open here,
not in whichever input asked it, so it can be answered from any of
them: say "yes", type "yes", or click Yes. The next command from
anywhere answers the open question, exactly as the next thing you say
does in voice-only mode.

Everything Ash says, hears and asks is published as an Event to
subscribers (the window, or the console printer in voice-only mode),
so handlers stay unchanged: they still just call tts.say().

Qt-free on purpose, so it's tested without a window and voice-only
mode doesn't need PySide6 installed.
"""
import logging
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable

from ash.actions.dispatcher import dispatch
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.privacy.permission import startup_questions
from ash.privacy.redact import said
from ash.registry.schema import Registry

# Where a command came from.
VOICE = "voice"
TYPED = "typed"
# A button in the window (privacy dashboard, settings) that runs a
# command for you. Its questions are shown as a dialog, not in the chat.
BUTTON = "button"
# Ash itself: the startup privacy questions.
SYSTEM = "system"

# Event kinds.
SAID = "said"              # Ash said `text`
HEARD = "heard"            # a command or answer `text` arrived from `source`
QUESTION = "question"      # a follow-up question is open (see Question)
QUESTION_CLOSED = "question_closed"
STATUS = "status"          # `text` is one of the STATUS_* states below

STATUS_LOADING = "loading"          # starting up
STATUS_READY = "ready"              # waiting for the wake word (or typing)
STATUS_LISTENING = "listening"      # recording what you say
STATUS_TRANSCRIBING = "transcribing"
STATUS_MIC_OFF = "mic_off"          # microphone switched off from the window/tray
STATUS_NO_MIC = "no_mic"            # voice couldn't start; typing still works

FAILED_REPLY = "Sorry, something went wrong with that."


@dataclass(frozen=True)
class Question:
    id: int                   # increments with every question, so a late answer to an old one is ignored
    text: str | None          # None: a conversation turn (the reply just said is the prompt)
    choices: tuple[str, ...]  # buttons to show, e.g. ("Yes", "No")
    source: str               # where the command that led to it came from
    requires_voice_match: bool


@dataclass(frozen=True)
class Event:
    kind: str
    text: str = ""
    source: str = ""
    question: Question | None = None


class ReplyTts:
    """Wraps the real TtsWorker: say() still speaks, and also publishes
    what was said, so the window shows every reply -- including ones
    from timers and reminders, which speak from their own threads.
    With `speak` off (a setting in the window), replies are only shown.
    Everything else (is_speaking, stop_speaking, ...) passes through."""

    def __init__(self, inner, publish: Callable[[Event], None]):
        self._inner = inner
        self._publish = publish
        self.speak = True

    def say(self, text: str) -> None:
        self._publish(Event(SAID, text=text))
        if self.speak:
            self._inner.say(text)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


_STOP = object()


class AssistantCore:
    def __init__(self, registry: Registry, tts, log: logging.Logger, config: Config, *,
                 dispatch_fn=dispatch):
        self.registry = registry
        self.log = log
        self.config = config
        self.tts = ReplyTts(tts, self.publish)
        self._dispatch = dispatch_fn
        self._jobs: "queue.Queue[Any]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="ash-core", daemon=True)
        self._subscribers: list[Callable[[Event], None]] = []
        # Written only by the worker thread; read from anywhere (a plain
        # reference swap, so no lock needed to read a consistent value).
        self._pending: HandlerResult | None = None
        self._question: Question | None = None
        self._next_id = 1

    # --- lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._jobs.put(_STOP)
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is _STOP:
                return
            fn, future = job
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn())
            except BaseException as exc:  # a job failing must not stop the worker
                future.set_exception(exc)

    # --- events ----------------------------------------------------------------------

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._subscribers.append(fn)

    def publish(self, event: Event) -> None:
        for fn in list(self._subscribers):
            try:
                fn(event)
            except Exception:
                self.log.exception("Event subscriber failed")

    def set_status(self, state: str) -> None:
        self.publish(Event(STATUS, text=state))

    # --- public API (any thread) ---------------------------------------------------------

    @property
    def question(self) -> Question | None:
        """The open follow-up question, if any."""
        return self._question

    def call(self, fn: Callable[[], Any]) -> Future:
        """Run fn on the worker thread, after anything already queued."""
        future: Future = Future()
        self._jobs.put((fn, future))
        return future

    def submit(self, text: str, source: str = TYPED, *, answering: int | None = None) -> Future:
        """Run a command, or answer the open question. `answering` is the
        id of the question a voice follow-up was recorded for: if that
        question was meanwhile answered in the window, the late answer is
        dropped instead of being run as a new command. The Future's
        result is the question left open afterwards (or None)."""
        return self.call(lambda: self._handle(text, source, answering))

    def ask_startup_questions(self) -> Future:
        """The once-only privacy questions for online features you
        haven't answered yet (see ash/privacy/permission.py)."""
        return self.call(lambda: self._settle(startup_questions(self.config, self.tts, self.log), SYSTEM))

    def time_out(self, question_id: int) -> Future:
        """No answer came in time: say the question's timeout reply."""
        def run():
            if self._question is not None and self._question.id == question_id:
                reply = self._pending.timeout_reply
                self._close_question()
                self.tts.say(reply)
            return self._question
        return self.call(run)

    def cancel(self, question_id: int, reply: str) -> Future:
        """Drop the open question without running its answer (e.g. the
        voice check failed), saying `reply`."""
        def run():
            if self._question is not None and self._question.id == question_id:
                self._close_question()
                self.tts.say(reply)
            return self._question
        return self.call(run)

    # --- worker thread only ------------------------------------------------------------

    def _handle(self, text: str, source: str, answering: int | None) -> Question | None:
        if answering is not None and (self._question is None or self._question.id != answering):
            self.log.info("Dropped a late answer: that question was already answered")
            return self._question
        text = text.strip()
        if not text:
            return self._question

        self.publish(Event(HEARD, text=text, source=source))
        pending = self._pending
        if pending is not None:
            self.log.info("Follow-up (%s): %s", source, said(text))
            question_source = self._question.source
            self._close_question()
            run = lambda: pending.resume(text)  # noqa: E731
        else:
            self.log.info("%s: %s", "Transcript" if source == VOICE else "Typed command", said(text))
            question_source = source
            run = lambda: self._dispatch(text, self.registry, self.tts, self.log, self.config)  # noqa: E731

        try:
            result = run()
        except Exception:
            # One failing command must never take the assistant down: say
            # so, keep the details in the log, keep going.
            self.log.exception("Command failed")
            self.tts.say(FAILED_REPLY)
            return None
        return self._settle(result, question_source)

    def _settle(self, result: HandlerResult | None, source: str) -> Question | None:
        if result is None or result.done:
            return None
        if result.question:
            self.tts.say(result.question)
        self._pending = result
        self._question = Question(
            id=self._next_id, text=result.question, choices=result.choices,
            source=source, requires_voice_match=result.requires_voice_match,
        )
        self._next_id += 1
        self.publish(Event(QUESTION, text=result.question or "", source=source, question=self._question))
        return self._question

    def _close_question(self) -> None:
        self._pending = None
        self._question = None
        self.publish(Event(QUESTION_CLOSED))
