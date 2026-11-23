"""Privacy tab: your rights under RA 10173, as buttons.

- Offline mode switch, and an allow/don't-allow switch per online
  feature, each saying what it sends and to whom (Sec. 11, 12).
  Withdrawing is one click with no questions; allowing shows the same
  explanation Ash would speak first.
- What Ash stores, why, for how long, and whether it's encrypted
  (Sec. 16(a), (c)).
- The network log: every time Ash went online, to where, sending what
  kind of data (never the data itself).
- Export, delete my voiceprint, delete all my data (Sec. 16(e), 18):
  these run the same commands you'd say, so they ask the same
  questions; the window shows those as a dialog.
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ash.core import BUTTON
from ash.privacy import consent, dashboard
from ash.privacy.egress import FEATURES
from ash.privacy.permission import consent_question
from ash.skills import registry as skills

PRIVACY_DOC = Path(__file__).resolve().parents[2] / "docs" / "PRIVACY.md"


def _command(intent: str) -> str:
    """What the button says on your behalf: the skill's own example."""
    return skills.get(intent).examples[0]


def _size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / 1024 ** 2:.1f} MB"


def _when(at: str) -> str:
    try:
        return datetime.fromisoformat(at).strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return str(at)


def _table(headers: list[str], wrap_column: int) -> QTableWidget:
    """A read-only table whose `wrap_column` takes the spare width and
    wraps its text; the others fit their contents. Its height follows
    its rows (the tab itself scrolls)."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setWordWrap(True)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = table.horizontalHeader()
    for column in range(len(headers)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(wrap_column, QHeaderView.ResizeMode.Stretch)
    # Wrapped rows get taller or shorter as the window is resized.
    header.sectionResized.connect(lambda *args: _fit(table))
    return table


def _fit(table: QTableWidget, max_rows: int = 12) -> None:
    """Size a table to its rows, up to max_rows (then it scrolls)."""
    table.resizeRowsToContents()
    rows = min(table.rowCount(), max_rows)
    height = table.horizontalHeader().height() + 2 * table.frameWidth()
    height += sum(table.rowHeight(r) for r in range(rows)) if rows else 28
    table.setFixedHeight(height)


def _cell(text: str, tooltip: str = "") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if tooltip:
        item.setToolTip(tooltip)
    return item


class PrivacyTab(QWidget):
    def __init__(self, bridge, config):
        super().__init__()
        self._bridge = bridge
        self._config = config
        self._updating = False  # filling in switches, not you clicking them

        self.offline = QCheckBox("Offline mode: nothing leaves this PC")
        self.offline.toggled.connect(self._offline_toggled)
        offline_note = QLabel("Features that need the internet say so instead of going online. "
                              "Everything else (apps, timers, notes, maths, the local AI) keeps working.")
        offline_note.setWordWrap(True)

        self.features = _table(["Allowed", "Feature", "Sends", "To"], wrap_column=2)
        self.stored = _table(["Data", "Stored now", "Encrypted", "Kept"], wrap_column=3)
        self.network_summary = QLabel()
        self.network_summary.setWordWrap(True)
        self.network = _table(["When", "Feature", "Website", "What kind of data"], wrap_column=3)

        export = QPushButton("Export my data…")
        export.setToolTip("Saves a readable copy of your data to your Documents folder.")
        export.clicked.connect(lambda: self._run_command("privacy_export"))
        delete_voice = QPushButton("Delete my voiceprint…")
        delete_voice.clicked.connect(lambda: self._run_command("privacy_delete_voiceprint"))
        delete_all = QPushButton("Delete all my data…")
        delete_all.setObjectName("danger")
        delete_all.clicked.connect(lambda: self._run_command("privacy_delete_all"))
        how = QPushButton("How Ash handles your data")
        how.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(PRIVACY_DOC))))
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.result = QLabel()
        self.result.setWordWrap(True)

        actions = QHBoxLayout()
        for button in (export, delete_voice, delete_all):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(how)
        actions.addWidget(refresh)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(self.offline)
        layout.addWidget(offline_note)
        layout.addWidget(self._group("Online features", self.features,
                                     "Each one asks before its first use. Unticking stops it straight away."))
        layout.addWidget(self._group("What Ash stores on this PC", self.stored,
                                     "Encrypted files can only be read by your Windows account."))
        network_box = self._group("Network activity (last 30 days)", self.network,
                                  "Where Ash went and what kind of data it sent, never the data itself.")
        network_box.layout().insertWidget(1, self.network_summary)
        layout.addWidget(network_box)
        layout.addWidget(QLabel("<b>Your data</b>"))
        layout.addLayout(actions)
        layout.addWidget(self.result)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    @staticmethod
    def _group(title: str, table: QTableWidget, note: str) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        label = QLabel(note)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(table)
        return box

    # --- showing --------------------------------------------------------------------------

    def refresh(self) -> None:
        self._bridge.run(lambda: dashboard.snapshot(self._config), self.show_snapshot)

    def show_snapshot(self, snap: dashboard.Snapshot) -> None:
        self._updating = True
        try:
            self.offline.setChecked(snap.offline_mode)

            self.features.setRowCount(len(snap.features))
            for row, f in enumerate(snap.features):
                switch = QCheckBox()
                switch.setChecked(f.status == consent.GRANTED)
                if f.by_setup:
                    switch.setEnabled(False)
                    switch.setToolTip(f.fixed_reason)
                else:
                    switch.setToolTip("Not asked yet" if f.status == consent.UNASKED else "")
                    switch.toggled.connect(lambda on, key=f.key: self._feature_toggled(key, on))
                holder = QWidget()
                holder_layout = QHBoxLayout(holder)
                holder_layout.setContentsMargins(6, 0, 6, 0)
                holder_layout.addWidget(switch)
                self.features.setCellWidget(row, 0, holder)
                name = f.name[0].upper() + f.name[1:]
                self.features.setItem(row, 1, _cell(name, f"Used to {f.purpose}."))
                self.features.setItem(row, 2, _cell(f.sends))
                self.features.setItem(row, 3, _cell(f.service, f.websites))

            self.stored.setRowCount(len(snap.stored))
            for row, s in enumerate(snap.stored):
                name = s.name[0].upper() + s.name[1:] + (" (sensitive)" if s.sensitive else "")
                self.stored.setItem(row, 0, _cell(name, f"Why: {s.purpose}."))
                self.stored.setItem(row, 1, _cell(f"Yes, {_size(s.size_bytes)}" if s.stored else "No"))
                self.stored.setItem(row, 2, _cell("Yes" if s.encrypted else "No"))
                self.stored.setItem(row, 3, _cell(s.kept))

            self.network_summary.setText(snap.summary)
            self.network.setRowCount(len(snap.network))
            for row, entry in enumerate(snap.network):
                self.network.setItem(row, 0, _cell(_when(entry.get("at"))))
                self.network.setItem(row, 1, _cell(entry.get("name") or entry.get("feature", "")))
                self.network.setItem(row, 2, _cell(f"{entry.get('domain', '')} ({entry.get('service', '')})"))
                self.network.setItem(row, 3, _cell(entry.get("sends", "")))
            for table in (self.features, self.stored, self.network):
                _fit(table)
        finally:
            self._updating = False

    # --- changing -------------------------------------------------------------------------

    def _offline_toggled(self, on: bool) -> None:
        if self._updating:
            return
        self._bridge.run(lambda: consent.set_offline_mode(on), lambda _: self.refresh())

    def _feature_toggled(self, key: str, on: bool) -> None:
        if self._updating:
            return
        if on:
            feature = FEATURES[key]
            answer = QMessageBox.question(self, "Allow this feature?", consent_question(feature))
            if answer != QMessageBox.StandardButton.Yes:
                self.refresh()  # put the switch back
                return
        self._bridge.run(lambda: dashboard.set_allowed(key, on), lambda _: self.refresh())

    def _run_command(self, intent: str) -> None:
        self.result.setText("")
        self._bridge.submit(_command(intent), BUTTON, lambda question: self.refresh())

    def show_reply(self, text: str) -> None:
        """What Ash said after one of this tab's buttons (set by the window)."""
        self.result.setText(text)
