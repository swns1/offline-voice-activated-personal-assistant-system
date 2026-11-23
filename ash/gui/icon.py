"""Ash's icon, drawn in code (no image files to ship): a filled circle
whose colour shows the state -- blue waiting for the wake word, green
listening, grey with the microphone off."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

BLUE = "#2563eb"
GREEN = "#16a34a"
GREY = "#6b7280"


def make_icon(colour: str = BLUE, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    margin = size * 0.06
    painter.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", int(size * 0.42))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size * 0.97), Qt.AlignmentFlag.AlignCenter, "A")
    painter.end()
    return QIcon(pixmap)
