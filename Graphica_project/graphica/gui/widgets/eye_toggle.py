"""目のアイコンで表示/非表示を切り替えるチェックボックス(四角い印は描かない)。"""
import os

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox

from graphica.gui import theme
from graphica.gui.icon_utils import ICONS_DIR, load_svg_icon
from graphica.gui.resources import resource_path

EYE_TOGGLE_SIZE = 28
EYE_ICON_SIZE = 16
_icon_cache = {}


def _eye_icon(visible, color):
    key = (visible, color)
    if key not in _icon_cache:
        name = "eye" if visible else "eye-off"
        _icon_cache[key] = load_svg_icon(resource_path(os.path.join(ICONS_DIR, f"{name}.svg")),
                                         color=color, size=EYE_ICON_SIZE)
    return _icon_cache[key]


class EyeToggle(QCheckBox):
    """QCheckBox のまま(束ねの stateChanged・isChecked をそのまま使う)。色とアイコンは描くたびに状態から決める。

    復元はシグナルを止めて setChecked するので、toggled でアイコンを替える作りだと古い絵が残る。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(EYE_TOGGLE_SIZE, EYE_TOGGLE_SIZE)

    def sizeHint(self):
        return QSize(EYE_TOGGLE_SIZE, EYE_TOGGLE_SIZE)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        tokens = theme.current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.underMouse() and self.isEnabled():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens["surface_2"]))
            painter.drawRoundedRect(QRectF(self.rect()), theme.RADIUS_MD, theme.RADIUS_MD)
        color = tokens["text_secondary"] if self.isChecked() else tokens["text_muted"]
        icon = _eye_icon(self.isChecked(), color)
        mode = icon.Mode.Normal if self.isEnabled() else icon.Mode.Disabled
        offset = (EYE_TOGGLE_SIZE - EYE_ICON_SIZE) // 2
        icon.paint(painter, offset, offset, EYE_ICON_SIZE, EYE_ICON_SIZE, Qt.AlignmentFlag.AlignCenter, mode)
        painter.end()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()
