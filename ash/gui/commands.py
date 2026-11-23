"""'What can I say' tab, generated from the skill catalog
(ash/skills/catalog.py) -- so it's never out of date. Double-click an
example to put it in the chat box."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ash.skills import registry as skills

_EXAMPLE_ROLE = Qt.ItemDataRole.UserRole


class CommandsTab(QWidget):
    try_example = Signal(str)

    def __init__(self):
        super().__init__()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search commands, e.g. “timer” or “privacy”")
        self.filter.textChanged.connect(self.apply_filter)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._double_clicked)

        bold = QFont()
        bold.setBold(True)
        italic = QFont()
        italic.setItalic(True)
        for category, members in skills.categories().items():
            top = QTreeWidgetItem([category])
            top.setFont(0, bold)
            for skill in members:
                child = QTreeWidgetItem([skill.description])
                child.setData(0, _EXAMPLE_ROLE, skill.examples[0] if skill.examples else None)
                for example in skill.examples:
                    leaf = QTreeWidgetItem([f"“{example}”"])
                    leaf.setFont(0, italic)
                    leaf.setData(0, _EXAMPLE_ROLE, example)
                    child.addChild(leaf)
                top.addChild(child)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()

        hint = QLabel("Say the wake word first, or type it in Chat. Double-click an example to try it.")
        hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.filter)
        layout.addWidget(self.tree, 1)

    def apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            category_matches = needle in top.text(0).lower()
            any_shown = False
            for j in range(top.childCount()):
                child = top.child(j)
                words = [child.text(0)] + [child.child(k).text(0) for k in range(child.childCount())]
                shown = not needle or category_matches or any(needle in w.lower() for w in words)
                child.setHidden(not shown)
                any_shown |= shown
            top.setHidden(not any_shown)

    def _double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        example = item.data(0, _EXAMPLE_ROLE)
        if example:
            self.try_example.emit(example)
