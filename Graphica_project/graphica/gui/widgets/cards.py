"""統計のカードと、開閉できる節の見出し。"""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QToolButton, QVBoxLayout

from graphica.gui import theme


class StatCard(QFrame):
    """小さな見出しと、太字の値。"""

    def __init__(self, label, value="-", parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 7)
        layout.setSpacing(0)
        self.label = QLabel(label, self)
        self.label.setObjectName("stat_card_label")
        self.value_label = QLabel(value, self)
        self.value_label.setObjectName("stat_card_value")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)
        layout.addWidget(self.value_label)

    def set_value(self, text):
        self.value_label.setText(text)

    def value(self):
        return self.value_label.text()


class SectionHeader(QToolButton):
    """開閉できる節の見出し。右端に、閉じていても分かるよう今の状態の要約(「オフ」「なし」など)を出す。"""

    STATE_TEXT_MARGIN = 2

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("section_header")
        self.setText(title)
        self.setCheckable(True)
        self.setChecked(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # 既定は文字の幅だけになり、罫線や要約が見出しの文字の所までしか届かない
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._state_text = ""

    def set_state_text(self, text):
        if text != self._state_text:
            self._state_text = text
            self.update()

    def state_text(self):
        return self._state_text

    def paintEvent(self, event):
        super().paintEvent(event)
        # 開いているときは中身が見えるので出さない(見本も閉じた節だけ)
        if not self._state_text or (self.isCheckable() and self.isChecked()):
            return
        painter = QPainter(self)
        font = painter.font()
        font.setBold(False)
        font.setPointSizeF(max(1.0, font.pointSizeF() - 1))
        painter.setFont(font)
        painter.setPen(QColor(theme.current_tokens()["text_muted"]))
        rect = QRect(self.rect()).adjusted(0, 0, -self.STATE_TEXT_MARGIN, 0)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), self._state_text)
        painter.end()
