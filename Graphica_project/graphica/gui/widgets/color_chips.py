"""色のチップの列(今の配色パレットの色をすぐ選べるように、色欄の横に並べる)。"""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

from graphica.gui import theme


class ColorChip(QAbstractButton):
    """角丸の色の見本。選んでいる色は、面の色のすき間の外に強調の色の輪を付ける。"""

    def __init__(self, color, size=20, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self._size = size
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.color.name().upper())
        self.setFixedSize(size + 8, size + 8)

    def sizeHint(self):
        return QSize(self._size + 8, self._size + 8)

    def paintEvent(self, event):
        tokens = theme.current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inner = QRectF(4, 4, self._size, self._size)
        if self.isChecked():
            ring = QPen(QColor(tokens["accent"]))
            ring.setWidthF(2.0)
            painter.setPen(ring)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(inner.adjusted(-3, -3, 3, 3), theme.RADIUS_LG, theme.RADIUS_LG)
        edge = QColor(tokens["text_primary"])
        edge.setAlphaF(0.12)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(self.color)
        painter.drawRoundedRect(inner, theme.RADIUS_MD, theme.RADIUS_MD)
        painter.end()


class ColorChipRow(QWidget):
    """色のチップを並べる。押すと colorPicked(#RRGGBB) を出す(どれを選んでいるかは set_current_color で合わせる)。

    幅が足りないときは入るだけ並べ、残りは隠す(最小幅を 0 にして、フォームの行が折り返されないように)。
    """

    colorPicked = Signal(str)

    def __init__(self, colors=(), chip_size=20, parent=None):
        super().__init__(parent)
        self._chip_size = chip_size
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.chips = []
        self.set_colors(colors)

    def set_colors(self, colors):
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.chips = []
        for color in colors:
            chip = ColorChip(color, self._chip_size, self)
            chip.clicked.connect(lambda _checked=False, c=chip: self._on_chip_clicked(c))
            layout.addWidget(chip)
            self.chips.append(chip)
        layout.addStretch(1)
        self._fit_chips()

    def minimumSizeHint(self):
        return QSize(0, self._chip_size + 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_chips()

    def _fit_chips(self):
        cell = self._chip_size + 8
        fits = max(0, self.width() // cell)
        for index, chip in enumerate(self.chips):
            chip.setVisible(index < fits)

    def colors(self):
        return [chip.color.name().upper() for chip in self.chips]

    def set_current_color(self, color):
        target = QColor(color).name().upper() if color else None
        for chip in self.chips:
            chip.setChecked(chip.color.name().upper() == target)

    def _on_chip_clicked(self, chip):
        self.set_current_color(chip.color.name())
        self.colorPicked.emit(chip.color.name().upper())
