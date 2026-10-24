"""左端のアイコンの帯。押すと左パネルのページを替える。下にはダークモードと設定。"""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QButtonGroup, QToolButton, QVBoxLayout, QWidget

from graphica.gui import motion, theme
from graphica.gui.shell.icons import checkable_icon, themed_icon

RAIL_WIDTH = 56
RAIL_BUTTON_SIZE = 38


def _rail_button(icon_name, tooltip, checkable):
    button = QToolButton()
    button.setObjectName("rail_button")
    button.setToolTip(tooltip)
    button.setCheckable(checkable)
    button.setFixedSize(RAIL_BUTTON_SIZE, RAIL_BUTTON_SIZE)
    button.setIconSize(QSize(20, 20))
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setProperty("iconName", icon_name)
    return button


# 左の帯の選んだ四角の動き: 全体の長さ(ms)、進む側の辺がその何割で着くか、後ろの辺がどれだけ遅れて動き出すか
RAIL_SLIDE_MS = 340
RAIL_LEAD_SHARE = 0.5
RAIL_TRAIL_DELAY = 0.4


def _ease_out(t):
    return 1 - (1 - t) ** 3


class ActivityRail(QWidget):
    page_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("activity_rail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(RAIL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._page_buttons = {}
        self._top_count = 0
        layout.addStretch(1)
        # 選んだ四角が動いている間の位置(止まっていれば選んだボタンの位置に描く)と、四角が今いるボタン。
        # ボタンを押すと、こちらが呼ばれる前に QButtonGroup がもう選び替えているので、選び替えからは動き出せない
        self._sliding = None
        self._plate_button = None

    def add_page(self, key, icon_name, tooltip):
        """上の並びにページのボタンを足す。最初のものを選んだ状態にする。"""
        button = _rail_button(icon_name, tooltip, checkable=True)
        button.setIcon(checkable_icon(icon_name))
        button.clicked.connect(lambda _checked=False, k=key: self.select_page(k))
        self._group.addButton(button)
        self.layout().insertWidget(self._top_count, button, 0, Qt.AlignmentFlag.AlignHCenter)
        self._top_count += 1
        self._page_buttons[key] = button
        if len(self._page_buttons) == 1:
            button.setChecked(True)
            self._plate_button = button
        return button

    def add_bottom_button(self, icon_name, tooltip, slot):
        button = _rail_button(icon_name, tooltip, checkable=False)
        button.setIcon(themed_icon(icon_name, size=20))
        button.clicked.connect(slot)
        self.layout().addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        return button

    def page_button(self, key):
        return self._page_buttons.get(key)

    def current_page(self):
        for key, button in self._page_buttons.items():
            if button.isChecked():
                return key
        return None

    def select_page(self, key):
        button = self._page_buttons[key]
        button.setChecked(True)
        start = self._plate_rect() if button is not self._plate_button else None
        self._plate_button = button
        # ページの切り替え(重い)を先に済ませ、描けてから四角を動かす
        self.page_requested.emit(key)
        if start is not None:
            self._slide_plate(start, self._plate_rect())
        self.update()

    def _plate_rect(self):
        button = self._plate_button
        if button is None or not button.isVisible():
            return None
        return QRectF(button.geometry())

    def _slide_plate(self, start, end):
        """先に進む側の辺を先に、後ろの辺を遅れて動かす(四角が伸びてから縮み、にゅるっと移る)。"""
        if start is None or end is None or start == end or not motion.is_enabled() or not self.isVisible():
            self._sliding = None
            return
        downward = end.top() > start.top()
        self._sliding = QRectF(start)

        def step(progress):
            lead = _ease_out(min(1.0, progress / RAIL_LEAD_SHARE))
            trail = _ease_out(max(0.0, (progress - RAIL_TRAIL_DELAY) / (1.0 - RAIL_TRAIL_DELAY)))
            top_t, bottom_t = (trail, lead) if downward else (lead, trail)
            top = start.top() + (end.top() - start.top()) * top_t
            bottom = start.bottom() + (end.bottom() - start.bottom()) * bottom_t
            self._sliding = QRectF(start.left(), top, start.width(), bottom - top)
            self.update()

        def finish():
            self._sliding = None
            self.update()

        motion.animate_value(self, "_motion_plate", 0.0, 1.0, step, finish, RAIL_SLIDE_MS, after_paint=True)

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self._sliding if self._sliding is not None else self._plate_rect()
        if rect is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.current_tokens()["accent"]))
        painter.drawRoundedRect(rect, theme.RADIUS_LG, theme.RADIUS_LG)
        painter.end()

    def refresh_icons(self):
        for button in self.findChildren(QToolButton, "rail_button"):
            name = button.property("iconName")
            if not name:
                continue
            button.setIcon(checkable_icon(name) if button.isCheckable() else themed_icon(name, size=20))
