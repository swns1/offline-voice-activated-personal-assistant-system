"""The microphone side of Ash: wake word -> record until silence ->
speech-to-text -> AssistantCore, then any follow-up question by voice.

Used the same way with or without the desktop window. Commands are
handed to AssistantCore (ash/core.py) rather than dispatched here, so
the window can answer the same follow-up questions with a click; this
loop notices and stops listening for an answer that's no longer needed.
"""
import logging

from ash.audio.recorder import ContinuousListener
from ash.audio.stt import SpeechToText
from ash.audio.wake_word import WakeWordDetector
from ash.config import Config
from ash.core import STATUS_LISTENING, STATUS_MIC_OFF, STATUS_READY, STATUS_TRANSCRIBING, VOICE, AssistantCore
from ash.security import voice_gate

FOLLOWUP_SECONDS = 6.0
VOICE_MISMATCH_REPLY = "That didn't sound like you, so I'm not doing that."

_LISTENER_STATES = {"listening": STATUS_LISTENING, "idle": STATUS_READY, "mic_off": STATUS_MIC_OFF}


class VoiceLoop:
    def __init__(self, core: AssistantCore, listener: ContinuousListener, stt, config: Config,
                 log: logging.Logger, *, wake_detector=None, verify=voice_gate.verify,
                 followup_seconds: float = FOLLOWUP_SECONDS):
        self.core = core
        self.listener = listener
        self.stt = stt
        self.config = config
        self.log = log
        self._wake_detector = wake_detector
        self._verify = verify
        self._followup_seconds = followup_seconds

    @classmethod
    def load(cls, core: AssistantCore, config: Config, log: logging.Logger) -> "VoiceLoop":
        """Loads the speech models (a few seconds). Raises
        ash.privacy.egress.OfflineModeError if the speech-recognition
        model still has to be downloaded and offline mode is on."""
        stt = SpeechToText()
        wake_detector = WakeWordDetector(keyword=config.wake_word.keyword, threshold=config.wake_word.threshold)
        tts = core.tts
        listener = ContinuousListener(
            wake_detector,
            input_device=config.audio.input_device,
            silence_ms=config.audio.silence_ms,
            max_record_seconds=config.audio.max_record_seconds,
            is_speaking=tts.is_speaking if config.audio.barge_in_enabled else None,
            on_barge_in=tts.stop_speaking if config.audio.barge_in_enabled else None,
            is_talking=tts.is_speaking,
        )
        return cls(core, listener, stt, config, log, wake_detector=wake_detector)

    # --- microphone switch (any thread) -------------------------------------------------

    def set_mic_enabled(self, enabled: bool) -> None:
        self.listener.set_mic_enabled(enabled)
        self.log.info("Microphone %s", "on" if enabled else "off")

    @property
    def mic_enabled(self) -> bool:
        return self.listener.mic_enabled

    # --- the loop -------------------------------------------------------------------------

    def run(self, *, greet: bool = True) -> None:
        """Blocks until the listener stops (it doesn't, normally: Ctrl+C
        in a terminal, Quit in the window or tray)."""
        try:
            # Privacy questions for online features you haven't answered
            # yet (all of them on first run) -- asked once, here, rather
            # than in the middle of the first command that needs one.
            if self.core.ask_startup_questions().result() is not None:
                with self.listener.open_stream():  # only open the mic if there's something to ask
                    self._follow_up()

            if greet:
                self.core.tts.say("Ash is listening.")
            self.core.set_status(STATUS_READY)
            for utterance in self.listener.listen(on_state_change=self._on_listener_state):
                self.core.set_status(STATUS_TRANSCRIBING)
                text = self.stt.transcribe(utterance)
                before = self.core.question
                question = self.core.submit(text, VOICE).result()
                # Only listen for an answer to a question this command
                # asked -- not one still open from something typed earlier.
                if question is not None and question is not before:
                    self._follow_up()
                self.core.set_status(STATUS_READY)
        finally:
            if self._wake_detector is not None:
                self._wake_detector.delete()

    def _on_listener_state(self, state: str) -> None:
        self.core.set_status(_LISTENER_STATES.get(state, state))

    def _follow_up(self) -> None:
        """Listen for answers while a question is open. A question
        answered in the window meanwhile is noticed (its id changes), so
        this either stops or moves on to the next question."""
        while (question := self.core.question) is not None:
            audio = self.listener.listen_for_followup(
                timeout_seconds=self._followup_seconds, on_state_change=self._on_listener_state)
            current = self.core.question
            if current is None or current.id != question.id:
                continue  # answered by a click or typing while we listened
            if audio is None:
                self.core.time_out(question.id).result()
                return
            self.core.set_status(STATUS_TRANSCRIBING)
            answer = self.stt.transcribe(audio)
            if question.requires_voice_match and not self._verify(audio, self.config, self.log):
                self.log.warning("Voice gate blocked a confirmation answer")
                self.core.cancel(question.id, VOICE_MISMATCH_REPLY).result()
                return
            self.core.submit(answer, VOICE, answering=question.id).result()
