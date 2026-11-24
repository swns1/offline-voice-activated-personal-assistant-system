"""The desktop window (ash/gui/), headless: Qt's offscreen platform, a
real AssistantCore and the real dispatcher, with speech faked."""
import logging
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ash.config import Config, load_config  # noqa: E402
from ash.core import BUTTON, STATUS, STATUS_LISTENING, STATUS_MIC_OFF, AssistantCore, Event  # noqa: E402
from ash.gui.bridge import CoreBridge  # noqa: E402
from ash.gui.tray import AshTray  # noqa: E402
from ash.gui.window import MainWindow  # noqa: E402
from ash.privacy import consent, inventory  # noqa: E402
from ash.privacy.egress import FEATURES  # noqa: E402
from ash.registry.schema import Registry  # noqa: E402
from ash.skills import registry as skills  # noqa: E402
from ash.utils.paths import CONFIG_PATH  # noqa: E402

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def is_speaking(self):
        return False

    def stop_speaking(self):
        pass


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the window")


@pytest.fixture
def ash(qapp, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    config = Config()
    bridge = CoreBridge()
    window = MainWindow(bridge, config, config_path=config_path)
    core = AssistantCore(Registry(), FakeTts(), log, config)
    core.subscribe(bridge.event.emit)
    core.start()
    bridge.core_ready.emit(core)
    wait_until(lambda: bridge.core is core)
    window.config_path = config_path
    yield window
    core.stop()
    window.quitting = True
    window.close()


def _chat_text(window) -> str:
    return window.chat.log.toPlainText()


# --- chat -------------------------------------------------------------------------------

def test_typing_a_command_shows_it_and_the_reply(ash):
    ash.chat.input.setText("what's 15% of 80")
    ash.chat.send_button.click()

    wait_until(lambda: "Ash: " in _chat_text(ash))
    assert "You: what's 15% of 80" in _chat_text(ash)
    assert "12" in _chat_text(ash)
    assert ash.chat.input.text() == ""


def test_a_risky_command_shows_yes_and_no_buttons(ash):
    ash.chat.input.setText("shut down")
    ash.chat.send()
    wait_until(lambda: ash.chat.choices.isVisibleTo(ash.chat))

    buttons = ash.chat.choices.findChildren(QtWidgets.QPushButton)
    assert [b.text() for b in buttons] == ["Yes", "No"]
    [no] = [b for b in buttons if b.text() == "No"]
    no.click()

    wait_until(lambda: not ash.chat.choices.isVisibleTo(ash.chat))
    wait_until(lambda: "won't shut down" in _chat_text(ash))
    assert ash._bridge.core.question is None


def test_replies_can_be_shown_without_speaking(ash):
    ash.chat.speak.setChecked(False)
    ash.chat.input.setText("what's 2 plus 2")
    ash.chat.send()
    wait_until(lambda: "Ash: " in _chat_text(ash))
    assert ash._bridge.core.tts._inner.said == []


def test_voice_commands_are_marked_with_a_microphone(ash):
    ash._bridge.core.submit("thank you", "voice").result(timeout=5)
    wait_until(lambda: "You 🎤: thank you" in _chat_text(ash))


def test_status_line_follows_the_microphone(ash):
    ash._bridge.event.emit(Event(STATUS, text=STATUS_LISTENING))
    wait_until(lambda: ash.chat.status.text() == "Listening…")
    ash._bridge.event.emit(Event(STATUS, text=STATUS_MIC_OFF))
    wait_until(lambda: "Microphone off" in ash.chat.status.text())


# --- what can I say ----------------------------------------------------------------------

def test_every_visible_command_is_listed(ash):
    tree = ash.commands.tree
    listed = {tree.topLevelItem(i).child(j).text(0)
              for i in range(tree.topLevelItemCount()) for j in range(tree.topLevelItem(i).childCount())}
    assert listed == {skill.description for skill in skills.visible_skills()}


def test_filtering_and_trying_an_example(ash):
    ash.commands.apply_filter("timer")
    tree = ash.commands.tree
    shown = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())
             if not tree.topLevelItem(i).isHidden()]
    assert "Timers and reminders" in shown or any("Timer" in s for s in shown)
    assert "Privacy" not in shown

    ash.tabs.setCurrentWidget(ash.commands)
    ash.commands.try_example.emit("set a timer for 5 minutes")
    assert ash.chat.input.text() == "set a timer for 5 minutes"
    assert ash.tabs.currentWidget() is ash.chat


# --- settings ---------------------------------------------------------------------------

def test_saving_settings_writes_config_yaml_and_applies_them(ash):
    settings = ash.settings
    units = settings.widgets["weather.units"]
    units.setCurrentIndex(units.findData("fahrenheit"))
    settings.widgets["privacy.log_retention_days"].setValue(14)
    assert settings.changes() == {"weather.units": "fahrenheit", "privacy.log_retention_days": 14}

    settings.save()
    wait_until(lambda: settings.message.text().startswith("Saved"))

    assert ash._config.weather.units == "fahrenheit"  # live, no restart
    saved = load_config(ash.config_path)
    assert saved.weather.units == "fahrenheit" and saved.privacy.log_retention_days == 14
    assert settings.changes() == {}


def test_nothing_to_save(ash):
    ash.settings.save()
    assert "Nothing to save" in ash.settings.message.text()


# --- privacy dashboard -----------------------------------------------------------------------

def test_privacy_tab_lists_features_data_and_activity(ash):
    from ash.privacy import network_log
    network_log.record("web_search", "web search", "DuckDuckGo", "api.duckduckgo.com", "the words you search for")

    ash.tabs.setCurrentWidget(ash.privacy)
    wait_until(lambda: ash.privacy.network.rowCount() == 1)

    assert ash.privacy.features.rowCount() == len(FEATURES)
    assert ash.privacy.stored.rowCount() == len(inventory.INVENTORY)
    assert ash.privacy.network.item(0, 2).text() == "api.duckduckgo.com (DuckDuckGo)"
    assert "1 time to DuckDuckGo" in ash.privacy.network_summary.text()


def test_offline_switch_and_withdrawing_a_feature(ash):
    ash.tabs.setCurrentWidget(ash.privacy)
    wait_until(lambda: ash.privacy.features.rowCount() == len(FEATURES))

    ash.privacy.offline.setChecked(True)
    wait_until(lambda: consent.offline_mode())

    row = list(FEATURES).index("web_search")
    switch = ash.privacy.features.cellWidget(row, 0).findChild(QtWidgets.QCheckBox)
    assert switch.isChecked()
    switch.setChecked(False)  # withdrawing asks nothing
    wait_until(lambda: consent.status("web_search") == consent.DENIED)


def test_allowing_a_feature_explains_it_first(ash, monkeypatch):
    consent.deny("web_search")
    asked = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or QtWidgets.QMessageBox.StandardButton.No)
    ash.tabs.setCurrentWidget(ash.privacy)
    row = list(FEATURES).index("web_search")
    wait_until(lambda: ash.privacy.features.cellWidget(row, 0) is not None
               and not ash.privacy.features.cellWidget(row, 0).findChild(QtWidgets.QCheckBox).isChecked())

    ash.privacy.features.cellWidget(row, 0).findChild(QtWidgets.QCheckBox).setChecked(True)

    assert "DuckDuckGo" in asked[0]
    assert consent.status("web_search") == consent.DENIED  # you said No


def test_delete_all_asks_in_a_dialog_and_no_keeps_everything(ash):
    from ash.actions import notes
    ash._bridge.core.submit("add milk to my shopping list").result(timeout=5)
    ash.tabs.setCurrentWidget(ash.privacy)

    [button] = [b for b in ash.privacy.findChildren(QtWidgets.QPushButton) if b.text() == "Delete all my data…"]
    button.click()
    wait_until(lambda: ash._dialog is not None)
    question = ash._dialog_question
    assert question.source == BUTTON and "Are you sure?" in question.text
    assert not ash.chat.choices.isVisibleTo(ash.chat)  # in the dialog, not the chat

    ash._dialog_answered(question, "No")
    wait_until(lambda: ash._bridge.core.question is None)
    wait_until(lambda: ash.privacy.result.text() != "")
    assert notes.NOTES_PATH.exists()


def test_a_dialog_closes_if_the_question_is_answered_by_voice(ash):
    ash.tabs.setCurrentWidget(ash.privacy)
    [button] = [b for b in ash.privacy.findChildren(QtWidgets.QPushButton) if b.text() == "Delete all my data…"]
    button.click()
    wait_until(lambda: ash._dialog is not None)

    ash._bridge.core.submit("no", "voice").result(timeout=5)
    wait_until(lambda: ash._dialog is None)


# --- window and tray ------------------------------------------------------------------------

def test_closing_the_window_hides_it_to_the_tray(ash):
    hidden = []
    ash.hidden_to_tray.connect(lambda: hidden.append(True))
    ash.show()
    ash.close()
    assert hidden == [True] and not ash.isVisible()


def test_tray_icon_shows_the_microphone_state(ash):
    tray = AshTray(ash, ash._bridge)
    ash._bridge.event.emit(Event(STATUS, text=STATUS_MIC_OFF))
    wait_until(lambda: tray.toolTip() == "Ash: microphone off")


# --- first run --------------------------------------------------------------------------

class _StatusCore:
    def __init__(self):
        self.statuses = []

    def set_status(self, state):
        self.statuses.append(state)


@pytest.mark.parametrize("allow", [False, True])
def test_first_run_asks_before_downloading_the_speech_models(qapp, monkeypatch, allow):
    from ash import setup_models
    from ash.core import STATUS_DOWNLOADING
    from ash.gui.app import _ensure_models

    monkeypatch.setattr(setup_models, "missing_downloads",
                        lambda keyword, whisper_size="small", piper_voice=None: ["the wake-word model"])
    monkeypatch.setattr(setup_models, "wake_word_model_missing", lambda keyword: True)
    downloads = []
    monkeypatch.setattr(setup_models, "download_wake_word_model", downloads.append)
    bridge = CoreBridge()
    asked = []
    bridge.ask.connect(lambda text, answer: (asked.append(text), answer.set_result(allow)))
    core, problems = _StatusCore(), []

    assert _ensure_models(bridge, core, Config(), log, problems.append) is allow

    assert "Download now?" in asked[0]
    if allow:
        assert downloads == ["hey_jarvis"] and core.statuses == [STATUS_DOWNLOADING] and problems == []
    else:
        assert downloads == [] and "Typing works now" in problems[0]
