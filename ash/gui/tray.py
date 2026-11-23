"""The tray icon while the window is running (replaces the pystray icon
used in voice-only mode): its colour shows what Ash is doing, and its
menu shows the window, switches the microphone, or quits."""
import os

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ash.core import STATUS, STATUS_LISTENING, STATUS_MIC_OFF, STATUS_NO_MIC, STATUS_TRANSCRIBING, Event
from ash.gui.icon import BLUE, GREEN, GREY, make_icon
from ash.utils.paths import LOG_DIR

_COLOURS = {STATUS_LISTENING: GREEN, STATUS_TRANSCRIBING: GREEN, STATUS_MIC_OFF: GREY, STATUS_NO_MIC: GREY}
_TIPS = {STATUS_LISTENING: "Ash: listening", STATUS_MIC_OFF: "Ash: microphone off",
         STATUS_NO_MIC: "Ash: voice unavailable"}


class AshTray(QSystemTrayIcon):
    def __init__(self, window, bridge):
        super().__init__(make_icon())
        self._window = window
        self._colour = BLUE
        self.setToolTip("Ash")

        menu = QMenu()
        show = QAction("Show Ash", menu)
        show.triggered.connect(self.show_window)
        self.mic = QAction("Microphone on", menu)
        self.mic.setCheckable(True)
        self.mic.setChecked(True)
        self.mic.setEnabled(False)
        logs = QAction("Open logs folder", menu)
        logs.triggered.connect(lambda: os.startfile(LOG_DIR))
        quit_action = QAction("Quit Ash", menu)
        quit_action.triggered.connect(window.quit_requested.emit)
        for action in (show, self.mic, logs):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._menu = menu  # keep a reference: Qt doesn't own it
        self.setContextMenu(menu)

        self.activated.connect(self._activated)
        bridge.event.connect(self.on_event)

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def on_event(self, event: Event) -> None:
        if event.kind != STATUS:
            return
        colour = _COLOURS.get(event.text, BLUE)
        if colour != self._colour:
            self._colour = colour
            self.setIcon(make_icon(colour))
        self.setToolTip(_TIPS.get(event.text, "Ash"))
