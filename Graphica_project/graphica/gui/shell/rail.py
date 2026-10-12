"""左端のアイコンの帯。押すと左パネルのページを替える。下にはダークモードと設定。"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QToolButton, QVBoxLayout, QWidget

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
        if not button.isChecked():
            button.setChecked(True)
        self.page_requested.emit(key)

    def refresh_icons(self):
        for button in self.findChildren(QToolButton, "rail_button"):
            name = button.property("iconName")
            if not name:
                continue
            button.setIcon(checkable_icon(name) if button.isCheckable() else themed_icon(name, size=20))
