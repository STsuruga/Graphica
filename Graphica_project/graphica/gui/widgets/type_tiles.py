"""グラフの種類のタイル(線・点・線+点・棒)。シンプル表示のプロパティで「種別」のコンボの代わりに出す。"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from graphica.gui import theme

GLYPHS = ("line", "scatter", "line_scatter", "bar")


def draw_glyph(painter, glyph, rect, color):
    """種類の小さな絵。rect の中に収める。"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    # 右下がりから持ち上がる、測定データらしい形
    points = [QPointF(x + w * fx, y + h * fy) for fx, fy in
              ((0.05, 0.85), (0.3, 0.45), (0.55, 0.6), (0.8, 0.2), (0.95, 0.3))]
    if glyph in ("line", "line_scatter"):
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)
    if glyph in ("scatter", "line_scatter"):
        painter.setBrush(color)
        radius = 1.9 if glyph == "line_scatter" else 2.2
        for point in points:
            painter.drawEllipse(point, radius, radius)
    if glyph == "bar":
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        bar_w = w * 0.16
        for fx, fh in ((0.12, 0.45), (0.42, 0.85), (0.72, 0.6)):
            painter.drawRoundedRect(QRectF(x + w * fx, y + h * (1 - fh), bar_w, h * fh), 1, 1)
    painter.restore()


class _TypeTile(QToolButton):
    def __init__(self, glyph, text, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self.setObjectName("type_tile")
        self.setText(text)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(48)
        # 文字は下に寄せ、上の空きに絵を描く
        self.setStyleSheet("padding-top: 22px;")

    def sizeHint(self):
        return QSize(56, 48)

    def paintEvent(self, event):
        super().paintEvent(event)
        tokens = theme.current_tokens()
        color = QColor(tokens["accent_fg"] if self.isChecked() else tokens["text_secondary"])
        painter = QPainter(self)
        size = 20
        draw_glyph(painter, self._glyph, QRectF((self.width() - size) / 2, 5, size, 16), color)
        painter.end()


class TypeTileGroup(QWidget):
    """QComboBox と同じ呼び方ができるタイルの列(ComboMirror で今の「種別」のコンボと同期させる)。"""

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.setCurrentIndex)
        self._items = []
        self._current = -1

    def addTile(self, glyph, text, data):
        if glyph not in GLYPHS:
            raise ValueError(f"知らない絵: {glyph}")
        tile = _TypeTile(glyph, text, self)
        index = len(self._items)
        self._items.append((text, data))
        self._group.addButton(tile, index)
        self.layout().addWidget(tile)
        if self._current < 0:
            self.setCurrentIndex(0)
        return index

    def count(self):
        return len(self._items)

    def itemText(self, index):
        return self._items[index][0] if 0 <= index < len(self._items) else ""

    def itemData(self, index):
        return self._items[index][1] if 0 <= index < len(self._items) else None

    def findData(self, data):
        for index, (_, item_data) in enumerate(self._items):
            if item_data == data:
                return index
        return -1

    def currentIndex(self):
        return self._current

    def currentData(self):
        return self.itemData(self._current)

    def setCurrentIndex(self, index):
        if index < -1 or index >= len(self._items) or index == self._current:
            return
        self._current = index
        if index >= 0:
            self._group.button(index).setChecked(True)
        else:
            # 4つに無い種類(面・ステップ・プラグインの種類など)のときは、どれも選ばない
            self._group.setExclusive(False)
            for button in self._group.buttons():
                button.setChecked(False)
            self._group.setExclusive(True)
        self.currentIndexChanged.emit(index)
