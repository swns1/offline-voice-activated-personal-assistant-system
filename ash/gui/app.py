"""run_gui(): Ash with its desktop window.

Qt owns the main thread (as it must). Ash itself starts on a
background thread -- the app list, the command worker, then the speech
models, which take a few seconds -- so the window opens straight away
and typing works as soon as the command worker is up, even before the
microphone is ready (or if it never is).
"""
import ctypes
import logging
import os
import threading
from concurrent.futures import Future

from PySide6.QtWidgets import QApplication, QMessageBox

from ash.config import Config
from ash.core import STATUS_DOWNLOADING, STATUS_NO_MIC
from ash.gui.bridge import CoreBridge
from ash.gui.icon import make_icon
from ash.gui.tray import AshTray
from ash.gui.window import MainWindow

STYLE = """
QWidget { font-family: "Segoe UI"; font-size: 10pt; }
QLabel#status { padding: 6px 8px; border-radius: 6px;
                background: rgba(37, 99, 235, 0.14); border: 1px solid rgba(37, 99, 235, 0.45); }
QTextBrowser { padding: 6px; }
QPushButton { padding: 5px 12px; }
QPushButton#danger { color: #dc2626; }
QGroupBox { font-weight: 600; margin-top: 18px; padding: 4px 6px 6px 6px;
            border: 1px solid palette(mid); border-radius: 6px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px; }
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QTableWidget { font-weight: normal; }
"""

def run_gui(config: Config, log: logging.Logger, *, minimized: bool = False) -> None:
    try:
        # Its own taskbar entry and icon, rather than Python's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Ash.Assistant")
    except (AttributeError, OSError):
        pass
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Ash")
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)  # closing the window hides it to the tray
    app.setStyleSheet(STYLE)

    bridge = CoreBridge()
    window = MainWindow(bridge, config)
    tray = AshTray(window, bridge)
    tray.show()
    _connect_mic_switches(bridge, window, tray)

    told_about_tray = []

    def hidden_to_tray():
        if not told_about_tray:
            told_about_tray.append(True)
            tray.showMessage("Ash is still running",
                             "Say the wake word, or click this icon to open Ash. "
                             "To quit, right-click it and choose Quit Ash.", make_icon(), 6000)
    window.hidden_to_tray.connect(hidden_to_tray)

    def quit_ash():
        log.info("Quit from the window")
        window.quitting = True
        tray.hide()
        app.quit()
    window.quit_requested.connect(quit_ash)

    bridge.voice_failed.connect(window.chat.note)

    def ask(text: str, answer: Future) -> None:
        if not window.isVisible():
            window.show()
        reply = QMessageBox.question(window, "Ash", text)
        answer.set_result(reply == QMessageBox.StandardButton.Yes)
    bridge.ask.connect(ask)

    if minimized:
        hidden_to_tray()
    else:
        window.show()

    threading.Thread(target=_start_ash, args=(bridge, config, log), name="ash-startup", daemon=True).start()
    app.exec()

    core = bridge.core
    if core is not None:
        core.stop(timeout=2)
        core.tts.stop()
    log.info("Ash stopped")
    # The microphone thread is usually blocked mid-read and the TTS
    # thread is a daemon; exit without waiting on either (as the
    # voice-only tray's Quit does).
    os._exit(0)


def _start_ash(bridge: CoreBridge, config: Config, log: logging.Logger) -> None:
    # Imported here: ash.main imports this module's package lazily, and
    # pulls in the audio stack.
    from ash.main import OFFLINE_DOWNLOAD_MESSAGE, start_assistant
    from ash.privacy.egress import OfflineModeError
    from ash.voice import VoiceLoop

    try:
        core = start_assistant(config, log, on_event=bridge.event.emit)
    except Exception:
        log.exception("Ash failed to start")
        bridge.voice_failed.emit("Ash couldn't start. The details are in the log file (tray menu > Open logs folder).")
        return
    bridge.core_ready.emit(core)

    def without_voice(message: str) -> None:
        bridge.voice_failed.emit(message)
        core.set_status(STATUS_NO_MIC)
        core.ask_startup_questions()  # still asked once; answered with the buttons

    if not _ensure_models(bridge, core, config, log, without_voice):
        return
    try:
        voice = VoiceLoop.load(core, config, log)
    except OfflineModeError:
        log.error(OFFLINE_DOWNLOAD_MESSAGE)
        without_voice(OFFLINE_DOWNLOAD_MESSAGE)
        return
    except Exception:
        log.exception("Voice failed to start")
        without_voice("Voice couldn't start (is a microphone connected?). Typing still works. "
                      "The details are in the log file.")
        return

    bridge.voice_ready.emit(voice)
    try:
        voice.run()
    except Exception:
        log.exception("The microphone loop stopped")
        bridge.voice_failed.emit("The microphone stopped working. Typing still works; restart Ash to try again.")
        core.set_status(STATUS_NO_MIC)


def _ensure_models(bridge: CoreBridge, core, config: Config, log: logging.Logger, without_voice) -> bool:
    """First run: ask before downloading the speech models, then download
    the wake-word model here (VoiceLoop.load downloads the speech model).
    False if voice can't start."""
    from ash import setup_models
    from ash.privacy.egress import NetworkBlocked

    keyword = config.wake_word.keyword
    if setup_models.custom_wake_word_missing(keyword):
        without_voice(f"The custom wake-word model {keyword!r} wasn't found. "
                      "Check wake_word.keyword in config.yaml. Typing still works.")
        return False
    piper_voice = config.voice.piper_voice if config.voice.engine == "piper" else None
    missing = setup_models.missing_downloads(keyword, piper_voice=piper_voice)
    if not missing:
        return True

    answer: Future = Future()
    bridge.ask.emit(setup_models.download_question(missing), answer)
    if not answer.result():
        log.info("Model download declined")
        without_voice("Voice is off until Ash's speech models are downloaded; you'll be asked again "
                      "next time Ash starts. Typing works now.")
        return False

    core.set_status(STATUS_DOWNLOADING)
    try:
        if setup_models.wake_word_model_missing(keyword):
            setup_models.download_wake_word_model(keyword)
        if piper_voice and setup_models.piper_installed() and setup_models.piper_voice_missing(piper_voice):
            setup_models.download_piper_voice(piper_voice)
            bridge.voice_failed.emit("The new voice is downloaded; it's used from the next time Ash starts.")
    except NetworkBlocked:
        return True  # offline mode: VoiceLoop.load reports it, with how to fix it
    except Exception:
        log.exception("Wake-word model download failed")
        without_voice("Downloading the wake-word model failed (are you online?). "
                      "Typing still works; restart Ash to try again.")
        return False
    return True


def _connect_mic_switches(bridge: CoreBridge, window: MainWindow, tray: AshTray) -> None:
    """The chat tab's and the tray menu's microphone switches, kept in step."""
    chat_switch, tray_switch = window.chat.mic, tray.mic

    def voice_ready(voice):
        chat_switch.setEnabled(True)
        tray_switch.setEnabled(True)

    def set_mic(on: bool):
        for switch in (chat_switch, tray_switch):
            if switch.isChecked() != on:
                switch.blockSignals(True)
                switch.setChecked(on)
                switch.blockSignals(False)
        chat_switch.setText("Microphone on" if on else "Microphone off")
        tray_switch.setText("Microphone on" if on else "Microphone off")
        if bridge.voice is not None:
            bridge.voice.set_mic_enabled(on)

    bridge.voice_ready.connect(voice_ready)
    chat_switch.toggled.connect(set_mic)
    tray_switch.toggled.connect(set_mic)
