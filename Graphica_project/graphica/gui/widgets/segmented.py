"""セグメント(横に並んだ排他のボタン)と、今のコンボを値の持ち主にしたままの同期。"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton

from graphica.gui import motion, theme

# matplotlib の線の種類と、それを描く Qt のペン
LINE_STYLE_PENS = {
    "-": Qt.PenStyle.SolidLine,
    "solid": Qt.PenStyle.SolidLine,
    "--": Qt.PenStyle.DashLine,
    "dashed": Qt.PenStyle.DashLine,
    ":": Qt.PenStyle.DotLine,
    "dotted": Qt.PenStyle.DotLine,
    "-.": Qt.PenStyle.DashDotLine,
    "dashdot": Qt.PenStyle.DashDotLine,
}


SEGMENT_HEIGHT = 28
# 溝の内側の余白と、板どうしの間。板の角丸は QSS の border-radius(溝の丸み 14 から余白を引いた値)
SEGMENT_TRACK_PADDING = 2
SEGMENT_RADIUS = 11
SEGMENT_SHADOW_ALPHA = 36


class _LineSegmentButton(QToolButton):
    """文字の代わりに線の見本を描く。色は描くたびにトークンから取るので、テーマを替えても描き直すだけでよい。"""

    def __init__(self, pen_style, parent=None):
        super().__init__(parent)
        self._pen_style = pen_style

    def sizeHint(self):
        return QSize(40, 24)

    def minimumSizeHint(self):
        # 線の見本は縮めても見分けられるので、狭い欄(グリッドの行)では詰める
        return QSize(28, 20)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = theme.current_tokens()
        if not self.isEnabled():
            color = tokens["text_muted"]
        else:
            color = tokens["accent_fg"] if self.isChecked() else tokens["text_secondary"]
        pen = QPen(QColor(color))
        pen.setWidthF(2.0)
        pen.setStyle(self._pen_style)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        y = self.height() / 2
        half = min(15.0, self.width() / 2 - 5)
        center = self.width() / 2
        painter.drawLine(QPointF(center - half, y), QPointF(center + half, y))
        painter.end()


class _FillSegmentButton(QToolButton):
    """マーカーの塗りの見本(塗った丸か白抜きの丸)。小さいと見分けにくいので、文字より少し大きく描く。"""

    DIAMETER = 13.0

    def __init__(self, filled, parent=None):
        super().__init__(parent)
        self._filled = filled

    def sizeHint(self):
        return QSize(40, 24)

    def paintEvent(self, event):
        super().paintEvent(event)
        tokens = theme.current_tokens()
        if not self.isEnabled():
            color = QColor(tokens["text_muted"])
        else:
            color = QColor(tokens["accent_fg"] if self.isChecked() else tokens["text_secondary"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(color)
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(color if self._filled else Qt.BrushStyle.NoBrush)
        radius = self.DIAMETER / 2 - (0 if self._filled else 0.8)
        painter.drawEllipse(QPointF(self.width() / 2, self.height() / 2), radius, radius)
        painter.end()


class SegmentedControl(QFrame):
    """QComboBox と同じ呼び方(currentIndex・itemData・findData・setCurrentIndex)ができる排他のボタンの列。"""

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented_control")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # 溝と板の色は QSS。板の位置(segmentPosition)は QSS の見分けに残しておく
        self.setFixedHeight(SEGMENT_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SEGMENT_TRACK_PADDING, SEGMENT_TRACK_PADDING,
                                  SEGMENT_TRACK_PADDING, SEGMENT_TRACK_PADDING)
        layout.setSpacing(SEGMENT_TRACK_PADDING)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.setCurrentIndex)
        self._items = []  # (text, data)
        self._current = -1
        # 板が滑っている途中の位置(止まっているときは選んだボタンの位置に描く)
        self._sliding_plate = None

    def _add_button(self, button, text, data, tooltip):
        button.setObjectName("segment")
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            button.setToolTip(tooltip)
        index = len(self._items)
        self._items.append((text, data))
        self._group.addButton(button, index)
        self.layout().addWidget(button)
        self._refresh_positions()
        if self._current < 0:
            # QComboBox と同じく、最初の項目を足した時点でそれを選ぶ
            self.setCurrentIndex(0)
        return index

    def _refresh_positions(self):
        buttons = self._group.buttons()
        for index, button in enumerate(buttons):
            if len(buttons) == 1:
                position = "only"
            elif index == 0:
                position = "first"
            elif index == len(buttons) - 1:
                position = "last"
            else:
                position = "middle"
            if button.property("segmentPosition") != position:
                button.setProperty("segmentPosition", position)
                button.style().unpolish(button)
                button.style().polish(button)

    def addItem(self, text, data=None, tooltip=""):
        button = QToolButton(self)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return self._add_button(button, text, data, tooltip)

    def addIconItem(self, icon, data=None, tooltip=""):
        button = QToolButton(self)
        button.setIcon(icon)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        return self._add_button(button, "", data, tooltip)

    def addLineStyleItem(self, line_style, data=None, tooltip=""):
        """線の見本のボタン。line_style は matplotlib の書き方('-'・'--'・':'・'-.' など)。"""
        button = _LineSegmentButton(LINE_STYLE_PENS[line_style], self)
        return self._add_button(button, "", line_style if data is None else data, tooltip)

    def addMarkerFillItem(self, filled, data=None, tooltip=""):
        """マーカーの塗りの見本のボタン(filled=True で塗った丸、False で白抜きの丸)。"""
        return self._add_button(_FillSegmentButton(filled, self), "", data, tooltip)

    def setItemEnabled(self, index, enabled):
        """コンボの項目を選べなくしたとき(model().item(i).setEnabled)と同じく、そのボタンだけ押せなくする。"""
        button = self._group.button(index)
        if button is not None:
            button.setEnabled(enabled)

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
        start = self._plate_rect()
        self._current = index
        if index >= 0:
            self._group.button(index).setChecked(True)
        else:
            # 何も選ばない(コンボに見本に無い値が入っているとき)。排他を一時外さないとチェックを外せない
            self._group.setExclusive(False)
            for button in self._group.buttons():
                button.setChecked(False)
            self._group.setExclusive(True)
        end = self._plate_rect()
        if start is not None and end is not None and self.isVisible() and motion.is_enabled():
            # 動きは次の刻みから値を出すので、最初の1枚が行き先に描かれないよう、出発点を先に置く
            self._sliding_plate = start
            motion.animate_value(self, "_motion_plate", start, end, self._move_plate, self._stop_plate, after_paint=True)
        else:
            self._stop_plate()
        self.update()
        self.currentIndexChanged.emit(index)

    def _plate_rect(self):
        button = self._group.button(self._current) if self._current >= 0 else None
        if button is None or not button.isVisible():
            return None
        return QRectF(button.geometry())

    def _move_plate(self, rect):
        self._sliding_plate = rect
        self.update()

    def _stop_plate(self):
        self._sliding_plate = None
        self.update()

    def paintEvent(self, event):
        """溝(QSS)の上に、選んだものの板とその下の薄い影を描く(文字は子のボタンが上に描く)。"""
        super().paintEvent(event)
        rect = self._sliding_plate if self._sliding_plate is not None else self._plate_rect()
        if rect is None:
            return
        tokens = theme.current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isEnabled():
            painter.setBrush(QColor(0, 0, 0, SEGMENT_SHADOW_ALPHA))
            painter.drawRoundedRect(rect.adjusted(0, 0.5, 0, 1.0), SEGMENT_RADIUS, SEGMENT_RADIUS)
        painter.setBrush(QColor(tokens["raised"] if self.isEnabled() else tokens["surface"]))
        painter.drawRoundedRect(rect, SEGMENT_RADIUS, SEGMENT_RADIUS)
        painter.end()

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Up: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Down: 1}.get(event.key())
        if step is None or not self._items:
            super().keyPressEvent(event)
            return
        self.setCurrentIndex(max(0, min(len(self._items) - 1, self._current + step)))


class ComboMirror:
    """今のコンボを値の持ち主にしたまま、見た目の代わり(セグメントなど)と同期する。

    見た目の側で選ぶとコンボの setCurrentIndex を呼ぶ(コンボのシグナルで今までどおり値が反映される)。
    コンボがシグナルを止めて書き換えられる(バインディングの「戻す」)と同期の知らせが来ないので、
    戻したあとに refresh() を呼ぶこと。コンボの値は itemData、無ければ表示の文字で突き合わせる。
    """

    def __init__(self, view, combo):
        self.view = view
        self.combo = combo
        combo.currentIndexChanged.connect(lambda _index: self.refresh())
        view.currentIndexChanged.connect(self._on_view_changed)
        self.refresh()

    def _combo_key(self, index):
        data = self.combo.itemData(index)
        return self.combo.itemText(index) if data is None else data

    def refresh(self):
        index = self.view.findData(self._combo_key(self.combo.currentIndex()))
        blocked = self.view.blockSignals(True)
        self.view.setCurrentIndex(index)
        self.view.blockSignals(blocked)

    def _on_view_changed(self, index):
        key = self.view.itemData(index)
        combo_index = self.combo.findData(key)
        if combo_index < 0 and isinstance(key, str):
            combo_index = self.combo.findText(key)
        if combo_index >= 0 and combo_index != self.combo.currentIndex():
            self.combo.setCurrentIndex(combo_index)
