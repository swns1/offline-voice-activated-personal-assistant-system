"""The main window: Chat, What can I say, Settings, Privacy.

Closing the window hides it to the tray; Ash keeps listening. Quit
from the tray menu (or File > Quit) to stop Ash.
"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from ash.config import Config
from ash.core import BUTTON, HEARD, QUESTION, QUESTION_CLOSED, SAID, Event
from ash.gui.chat import ChatTab
from ash.gui.commands import CommandsTab
from ash.gui.icon import make_icon
from ash.gui.privacy import PrivacyTab
from ash.gui.settings import SettingsTab


def wake_phrase(config: Config) -> str:
    return config.wake_word.keyword.replace("_", " ")


class MainWindow(QMainWindow):
    quit_requested = Signal()
    hidden_to_tray = Signal()

    def __init__(self, bridge, config: Config, config_path=None):
        super().__init__()
        self._bridge = bridge
        self._config = config
        self._dialog: QMessageBox | None = None
        self._dialog_question = None
        # A dashboard/settings button's command is running: its replies go
        # to that tab's message line too, not only the chat.
        self._button_reply_tab = None
        self.quitting = False

        self.setWindowTitle("Ash")
        self.setWindowIcon(make_icon())
        self.resize(780, 680)

        self.chat = ChatTab(bridge, wake_phrase(config))
        self.commands = CommandsTab()
        self.settings = SettingsTab(bridge, config, **({"config_path": config_path} if config_path else {}))
        self.privacy = PrivacyTab(bridge, config)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.chat, "Chat")
        self.tabs.addTab(self.commands, "What can I say")
        self.tabs.addTab(self.settings, "Settings")
        self.tabs.addTab(self.privacy, "Privacy")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.commands.try_example.connect(self._try_example)

        menu = self.menuBar().addMenu("&File")
        hide = QAction("Hide to tray", self)
        hide.triggered.connect(self.hide)
        quit_action = QAction("Quit Ash", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(hide)
        menu.addAction(quit_action)

        bridge.event.connect(self.on_event)
        bridge.core_ready.connect(self._core_ready)

    def _core_ready(self, core) -> None:
        self.chat.set_ready(True)
        self.chat._set_speak(self.chat.speak.isChecked())
        self._tab_changed(self.tabs.currentIndex())

    def _tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.privacy:
            self.privacy.refresh()
        elif widget is self.settings:
            self.settings.refresh_city()

    def _try_example(self, text: str) -> None:
        self.chat.prefill(text)
        self.tabs.setCurrentWidget(self.chat)

    # --- events -------------------------------------------------------------------------

    def on_event(self, event: Event) -> None:
        self.chat.on_event(event)
        if event.kind == HEARD:
            current = self.tabs.currentWidget()
            self._button_reply_tab = current if event.source == BUTTON and hasattr(current, "show_reply") else None
        elif event.kind == SAID and self._button_reply_tab is not None:
            self._button_reply_tab.show_reply(event.text)
        elif event.kind == QUESTION and event.question.source == BUTTON:
            self._ask_in_dialog(event.question)
        elif event.kind == QUESTION_CLOSED:
            self._close_dialog()

    def _ask_in_dialog(self, question) -> None:
        """A question from a button's command (e.g. "Delete all my data"
        -> "This will permanently delete... Are you sure?")."""
        self._close_dialog()
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Ash")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(question.text or "")
        choices = question.choices or ("OK",)
        buttons = {dialog.addButton(choice, QMessageBox.ButtonRole.AcceptRole): choice for choice in choices}
        dialog.buttonClicked.connect(lambda button: self._dialog_answered(question, buttons.get(button)))
        self._dialog, self._dialog_question = dialog, question
        dialog.open()

    def _dialog_answered(self, question, choice: str | None) -> None:
        self._dialog = self._dialog_question = None
        if choice is not None and self._bridge.core is not None:
            self._bridge.core.submit(choice, BUTTON, answering=question.id)

    def _close_dialog(self) -> None:
        """The question was answered another way (by voice, or timed out)."""
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            self._dialog_question = None
            dialog.done(0)

    # --- closing ------------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()
