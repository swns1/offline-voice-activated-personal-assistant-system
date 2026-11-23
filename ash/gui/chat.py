"""Chat tab: type to Ash, see everything said either way, and answer
yes/no questions with buttons.

The conversation is shown, never saved: closing Ash clears it (it's
not in the data inventory because it's never written to disk).
"""
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ash.core import (
    BUTTON,
    HEARD,
    QUESTION,
    QUESTION_CLOSED,
    SAID,
    STATUS,
    STATUS_LISTENING,
    STATUS_LOADING,
    STATUS_MIC_OFF,
    STATUS_NO_MIC,
    STATUS_READY,
    STATUS_TRANSCRIBING,
    TYPED,
    VOICE,
    Event,
)

# (light theme, dark theme): readable on either, as Windows' dark mode
# carries over to the window.
_YOU = ("#1d4ed8", "#60a5fa")
_ASH = ("#047857", "#34d399")


def status_text(state: str, wake_phrase: str) -> str:
    return {
        STATUS_LOADING: "Starting up…",
        STATUS_READY: f"Listening for “{wake_phrase}”. You can also type below.",
        STATUS_LISTENING: "Listening…",
        STATUS_TRANSCRIBING: "Working it out…",
        STATUS_MIC_OFF: "Microphone off. Typing still works.",
        STATUS_NO_MIC: "Voice isn't available. Typing still works.",
    }.get(state, state)


class ChatTab(QWidget):
    mic_toggled = Signal(bool)

    def __init__(self, bridge, wake_phrase: str):
        super().__init__()
        self._bridge = bridge
        self._wake_phrase = wake_phrase
        self._question = None

        self.status = QLabel(status_text(STATUS_LOADING, wake_phrase))
        self.status.setObjectName("status")

        self.log = QTextBrowser()
        self.log.setOpenLinks(False)
        self.log.setPlaceholderText("What you say or type, and Ash's replies, appear here. Nothing here is saved.")

        self.choices = QWidget()
        self._choices_layout = QHBoxLayout(self.choices)
        self._choices_layout.setContentsMargins(0, 0, 0, 0)
        self.choices.hide()

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command, e.g. “what's 15% of 80” or “add milk to my shopping list”")
        self.input.returnPressed.connect(self.send)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        self.set_ready(False)

        self.speak = QCheckBox("Speak replies")
        self.speak.setChecked(True)
        self.speak.toggled.connect(self._set_speak)
        self.mic = QCheckBox("Microphone on")
        self.mic.setChecked(True)
        self.mic.setEnabled(False)  # until the speech models have loaded
        self.mic.toggled.connect(self.mic_toggled.emit)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        options = QHBoxLayout()
        options.addWidget(self.speak)
        options.addWidget(self.mic)
        options.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.log, 1)
        layout.addWidget(self.choices)
        layout.addLayout(input_row)
        layout.addLayout(options)

    # --- input ----------------------------------------------------------------------------

    def set_ready(self, ready: bool) -> None:
        self.input.setEnabled(ready)
        self.send_button.setEnabled(ready)
        if ready:
            self.input.setFocus()

    def send(self) -> None:
        text = self.input.text().strip()
        if not text or self._bridge.core is None:
            return
        self.input.clear()
        self._bridge.core.submit(text, TYPED)

    def prefill(self, text: str) -> None:
        self.input.setText(text)
        self.input.setFocus()

    def _answer(self, choice: str) -> None:
        if self._bridge.core is None or self._question is None:
            return
        self._bridge.core.submit(choice, TYPED, answering=self._question.id)

    def _set_speak(self, on: bool) -> None:
        if self._bridge.core is not None:
            self._bridge.core.tts.speak = on

    # --- events ---------------------------------------------------------------------------

    def on_event(self, event: Event) -> None:
        if event.kind == HEARD:
            marker = " 🎤" if event.source == VOICE else ""
            self._append("You" + marker, event.text, _YOU)
        elif event.kind == SAID:
            self._append("Ash", event.text, _ASH)
        elif event.kind == QUESTION:
            # Questions from the privacy dashboard's buttons open as a
            # dialog there instead (see ash/gui/window.py).
            if event.question.source != BUTTON:
                self._show_choices(event.question)
        elif event.kind == QUESTION_CLOSED:
            self._show_choices(None)
        elif event.kind == STATUS:
            self.status.setText(status_text(event.text, self._wake_phrase))

    def note(self, text: str) -> None:
        """A message from Ash itself, not a reply (e.g. voice couldn't start)."""
        self.log.append(f'<p style="margin:4px 0; color:#6b7280"><i>{html.escape(text)}</i></p>')

    def _append(self, who: str, text: str, colours: tuple[str, str]) -> None:
        dark = self.palette().color(QPalette.ColorRole.Base).lightness() < 128
        colour = colours[1] if dark else colours[0]
        self.log.append(f'<p style="margin:4px 0"><b style="color:{colour}">{html.escape(who)}:</b> '
                        f'{html.escape(text)}</p>')
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _show_choices(self, question) -> None:
        self._question = question
        while self._choices_layout.count():
            widget = self._choices_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if question is None or not question.choices:
            self.choices.hide()
            return
        for choice in question.choices:
            button = QPushButton(choice)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, c=choice: self._answer(c))
            self._choices_layout.addWidget(button)
        self._choices_layout.addStretch(1)
        self.choices.show()
