"""Settings tab: the everyday options from config.yaml, saved back into
config.yaml with its comments kept (ash/config.py save_settings), and
your city, which isn't a config setting: it's personal data, stored
encrypted, so it's set through the same "my city is ..." command you'd
say (and asks the same privacy question first)."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pydantic
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ash.config import Config, save_settings
from ash.core import BUTTON
from ash.privacy.redact import set_log_content
from ash.utils import preferences
from ash.utils.autostart import sync_autostart
from ash.utils.paths import CONFIG_PATH


@dataclass(frozen=True)
class Setting:
    key: str                  # dotted path in config.yaml
    label: str
    kind: str                 # "bool" | "int" | "float" | "text" | "choice"
    minimum: float = 0
    maximum: float = 0
    step: float = 1
    # For "choice": (shown text, value) pairs.
    options: tuple[tuple[str, Any], ...] = ()
    tooltip: str = ""
    restart: bool = False     # only takes effect the next time Ash starts


@dataclass(frozen=True)
class Group:
    title: str
    settings: tuple[Setting, ...] = field(default_factory=tuple)


GROUPS = (
    Group("Listening", (
        Setting("wake_word.threshold", "Wake word threshold", "float", 0.1, 0.95, 0.05,
                tooltip="Lower hears the wake word more easily, but also by mistake more often.",
                restart=True),
        Setting("audio.silence_ms", "Pause that ends a command (ms)", "int", 300, 3000, 100, restart=True),
        Setting("audio.max_record_seconds", "Longest command (seconds)", "float", 2, 30, 1, restart=True),
        Setting("audio.barge_in_enabled", "Talk over Ash to interrupt it", "bool", restart=True,
                tooltip="Turn off if Ash's own voice from your speakers interrupts it."),
    )),
    Group("Answers", (
        Setting("search.enabled", "Web search (DuckDuckGo)", "bool",
                tooltip="“What is…” and “search for…” answers. Asks permission before first use."),
        Setting("ollama.enabled", "Local AI (Ollama)", "choice", options=(
            ("Automatic: when Ollama is running", "auto"), ("On", True), ("Off", False))),
        Setting("ollama.model", "Local AI model", "text"),
        Setting("weather.units", "Temperature", "choice",
                options=(("Celsius", "celsius"), ("Fahrenheit", "fahrenheit"))),
        Setting("calendar.enabled", "Outlook calendar", "bool"),
        Setting("email.enabled", "Outlook email", "bool",
                tooltip="Who your latest emails are from, and sending (always asks first)."),
    )),
    Group("Privacy and safety", (
        Setting("privacy.log_transcripts", "Include what I say in log files", "bool",
                tooltip="Off: logs show which command ran, never what you said."),
        Setting("privacy.log_retention_days", "Delete log files after (days)", "int", 1, 365),
        Setting("security.voice_gate_enabled", "Check it's my voice before risky actions", "bool",
                tooltip="Needs a voiceprint first: scripts/enroll_voice.py."),
        Setting("desktop_control.enabled", "Let Ash click and type on screen", "bool",
                tooltip="Every click or typing action still asks first."),
    )),
    Group("Startup", (
        Setting("autostart", "Start Ash when I sign in to Windows", "bool"),
        Setting("gui.start_minimized", "Start hidden in the system tray", "bool", restart=True),
    )),
)


def current_value(config: Config, key: str) -> Any:
    value: Any = config
    for part in key.split("."):
        value = getattr(value, part)
    return value


def apply_settings(config: Config, changes: dict[str, Any], path: Path = CONFIG_PATH) -> Config:
    """Save `changes` and apply them to the running Ash. Runs on the
    command worker thread (see SettingsTab.save), so a command never
    sees half-applied settings."""
    new = save_settings(changes, path)
    for name in Config.model_fields:
        setattr(config, name, getattr(new, name))
    set_log_content(new.privacy.log_transcripts)
    if "autostart" in changes:
        sync_autostart(new.autostart)
    return new


class SettingsTab(QWidget):
    def __init__(self, bridge, config: Config, config_path: Path = CONFIG_PATH):
        super().__init__()
        self._bridge = bridge
        self._config = config
        self._path = config_path
        self.widgets: dict[str, QWidget] = {}

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.addWidget(self._city_group())
        for group in GROUPS:
            box = QGroupBox(group.title)
            form = QFormLayout(box)
            for setting in group.settings:
                widget = self._make_widget(setting)
                self.widgets[setting.key] = widget
                label = setting.label + (" *" if setting.restart else "")
                if setting.kind == "bool":
                    widget.setText(label)
                    form.addRow(widget)
                else:
                    form.addRow(label, widget)
            body_layout.addWidget(box)
        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)

        self.message = QLabel("* applies the next time Ash starts")
        self.message.setWordWrap(True)
        self.save_button = QPushButton("Save settings")
        self.save_button.clicked.connect(self.save)
        footer = QHBoxLayout()
        footer.addWidget(self.message, 1)
        footer.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(footer)
        self.load()

    # --- your city ------------------------------------------------------------------

    def _city_group(self) -> QGroupBox:
        box = QGroupBox("Your city (for the weather)")
        self.city_label = QLabel("Not set")
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("e.g. Manila")
        self.city_input.returnPressed.connect(self.set_city)
        set_button = QPushButton("Set city")
        set_button.clicked.connect(self.set_city)
        forget_button = QPushButton("Forget city")
        forget_button.clicked.connect(self.forget_city)
        row = QHBoxLayout()
        row.addWidget(self.city_input, 1)
        row.addWidget(set_button)
        row.addWidget(forget_button)
        note = QLabel("Stored encrypted on this PC. Looking a city up sends its name to Open-Meteo, "
                      "so Ash asks first. Your location is never worked out automatically.")
        note.setWordWrap(True)
        layout = QVBoxLayout(box)
        layout.addWidget(self.city_label)
        layout.addLayout(row)
        layout.addWidget(note)
        return box

    def refresh_city(self) -> None:
        def show(place):
            if place:
                where = f"{place['name']}, {place['country']}" if place.get("country") else place["name"]
                self.city_label.setText(f"Current: {where}")
            else:
                self.city_label.setText("Not set")
        self._bridge.run(lambda: preferences.get("city"), show)

    def set_city(self) -> None:
        name = self.city_input.text().strip()
        if name:
            self.city_input.clear()
            self._bridge.submit(f"my city is {name}", BUTTON, lambda question: self.refresh_city())

    def forget_city(self) -> None:
        self._bridge.submit("forget my city", BUTTON, lambda question: self.refresh_city())

    # --- config settings ------------------------------------------------------------------

    def _make_widget(self, setting: Setting) -> QWidget:
        if setting.kind == "bool":
            return QCheckBox()
        if setting.kind == "int":
            widget = QSpinBox()
            widget.setRange(int(setting.minimum), int(setting.maximum))
            widget.setSingleStep(int(setting.step))
        elif setting.kind == "float":
            widget = QDoubleSpinBox()
            widget.setRange(setting.minimum, setting.maximum)
            widget.setSingleStep(setting.step)
            widget.setDecimals(2)
        elif setting.kind == "choice":
            widget = QComboBox()
            for text, value in setting.options:
                widget.addItem(text, value)
        else:
            widget = QLineEdit()
        if setting.tooltip:
            widget.setToolTip(setting.tooltip)
        return widget

    def load(self) -> None:
        """Show the running settings."""
        for group in GROUPS:
            for setting in group.settings:
                self._set_widget(setting, current_value(self._config, setting.key))

    def _set_widget(self, setting: Setting, value: Any) -> None:
        widget = self.widgets[setting.key]
        if setting.kind == "bool":
            widget.setChecked(bool(value))
        elif setting.kind in ("int", "float"):
            widget.setValue(value)
        elif setting.kind == "choice":
            for i in range(widget.count()):
                # `is` for bools: True == 1 but "auto" != True.
                data = widget.itemData(i)
                if data == value and type(data) is type(value):
                    widget.setCurrentIndex(i)
        else:
            widget.setText("" if value is None else str(value))

    def _widget_value(self, setting: Setting) -> Any:
        widget = self.widgets[setting.key]
        if setting.kind == "bool":
            return widget.isChecked()
        if setting.kind in ("int", "float"):
            return widget.value()
        if setting.kind == "choice":
            return widget.currentData()
        return widget.text().strip()

    def changes(self) -> dict[str, Any]:
        changed = {}
        for group in GROUPS:
            for setting in group.settings:
                value = self._widget_value(setting)
                current = current_value(self._config, setting.key)
                if value != current or type(value) is not type(current):
                    changed[setting.key] = value
        return changed

    def save(self) -> None:
        changes = self.changes()
        if not changes:
            self.message.setText("Nothing to save: no settings changed.")
            return
        restart = any(s.restart for g in GROUPS for s in g.settings if s.key in changes)

        def saved(_config):
            self.load()
            self.message.setText("Saved." + (" Some changes apply the next time Ash starts." if restart else ""))

        def failed(error):
            if isinstance(error, pydantic.ValidationError):
                self.message.setText(f"Not saved: {error.errors()[0]['msg']}.")
            else:
                self.message.setText(f"Not saved: {error}")
        self._bridge.run(lambda: apply_settings(self._config, changes, self._path), saved, failed)

    def show_reply(self, text: str) -> None:
        """What Ash said after this tab's city buttons (set by the window)."""
        self.message.setText(text)
