"""グラフのカードのレイアウトのボタンで開くポップアップ: 行数・列数・軸の共有・自由配置(グラフ全体の設定)。

欄そのものは axis_panel.rebuild_label_tab が作る(app.figure_layout_panel)。ここはそれを入れて出すだけ。
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from graphica.core.i18n import tr
from graphica.gui import motion
from graphica.gui.builders.common import _svg_icon

POPOVER_WIDTH = 300


class LayoutPopover(QFrame):
    def __init__(self, app, panel, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        # 窓の四隅は透かし、中の枠を角丸にする
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(POPOVER_WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("settings_popover")
        outer.addWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel(tr("グラフ全体のレイアウト"))
        title.setObjectName("settings_popover_title")
        self.close_button = QToolButton()
        self.close_button.setObjectName("card_button")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.hide)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.close_button)
        layout.addLayout(title_row)
        layout.addWidget(panel)
        self.panel = panel

    def open_below(self, anchor):
        """anchor(カードのボタン)の下、右端をそろえて開く。"""
        self.close_button.setIcon(_svg_icon("x", size=14))
        self.adjustSize()
        bottom_right = anchor.mapToGlobal(QPoint(anchor.width(), anchor.height() + 6))
        self.move(bottom_right.x() - self.width(), bottom_right.y())
        self.show()
        motion.fade_in_window(self)


def toggle_layout_popover(app, anchor):
    popover = app.layout_popover
    if popover.isVisible():
        popover.hide()
    else:
        popover.open_below(anchor)
