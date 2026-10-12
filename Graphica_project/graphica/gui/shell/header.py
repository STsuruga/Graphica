"""上部バー: ≡(メニュー)・ロゴ・プロジェクトのタブ・コマンドを検索・モードの切り替え・元に戻す/やり直す・保存・
クイックアクセス・エクスポート。高さ 48px の1段。見本は docs/dev/mockups/gui_redesign/。

押したときの行き先(表示中のタブ)は MainAppWindow がつなぐ。ここは部品と並びだけを持つ。
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget, QToolButton,
                               QWidget)

from graphica.core.i18n import tr
from graphica.gui import ui_mode
from graphica.gui.shell.icons import themed_icon
from graphica.gui.widgets import SegmentedControl

HEADER_HEIGHT = 48
SEARCH_WIDTH = 300
COMMAND_PALETTE_SHORTCUT_TEXT = "Ctrl+Shift+P"


def _header_button(name, tooltip):
    button = QToolButton()
    button.setObjectName("header_button")
    button.setToolTip(tooltip)
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(30, 30)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setProperty("iconName", name)
    button.setIcon(themed_icon(name))
    return button


def _separator():
    line = QFrame()
    line.setObjectName("header_separator")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedSize(1, 20)
    return line


class AppHeader(QWidget):
    def __init__(self, tab_bar, app_icon_path, parent=None):
        super().__init__(parent)
        self.setObjectName("app_header")
        # 上の帯の色を QSS で塗るため(素の QWidget は背景を描かない)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 12, 0)
        layout.setSpacing(6)

        self.menu_button = _header_button("menu-2", tr("メニュー"))
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # ▼の印を出さない(≡ だけ)
        self.menu_button.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        layout.addWidget(self.menu_button)

        self.logo = QLabel()
        self.logo.setObjectName("header_logo")
        self.logo.setPixmap(QIcon(app_icon_path).pixmap(22, 22))
        layout.addWidget(self.logo)
        self.title_label = QLabel("Graphica")
        self.title_label.setObjectName("header_title")
        layout.addWidget(self.title_label)
        layout.addSpacing(8)

        self.tab_bar = tab_bar
        layout.addWidget(tab_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        self.add_tab_button = _header_button("plus", tr("新しいプロジェクトタブを開く"))
        self.add_tab_button.setObjectName("add_tab_button")
        layout.addWidget(self.add_tab_button)

        layout.addStretch(1)
        self.search_button = self._make_search_button()
        layout.addWidget(self.search_button)
        layout.addStretch(1)

        self.mode_switch = SegmentedControl()
        self.mode_switch.setObjectName("mode_switch")
        for mode in ui_mode.MODES:
            self.mode_switch.addItem(ui_mode.mode_label(mode), mode)
        self.mode_switch.setFixedWidth(190)
        layout.addWidget(self.mode_switch)
        layout.addWidget(_separator())

        self.undo_button = _header_button("arrow-back-up", tr("元に戻す"))
        self.redo_button = _header_button("arrow-forward-up", tr("やり直し"))
        self.save_button = _header_button("device-floppy", tr("上書き保存"))
        for button in (self.undo_button, self.redo_button, self.save_button):
            layout.addWidget(button)

        # 表示中のタブのクイックアクセス(ピン留め)。タブごとのツールバーを重ねて、前のタブのものだけを見せる
        self.quick_access_stack = QStackedWidget()
        self.quick_access_stack.setObjectName("quick_access_slot")
        self.quick_access_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.quick_access_stack)

        self.export_button = QPushButton(tr("エクスポート"))
        self.export_button.setObjectName("header_export_button")
        self.export_button.setProperty("primaryButton", True)
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.export_button.setIconSize(QSize(16, 16))
        self.export_button.setIcon(themed_icon("download", size=16, token="on_accent"))
        layout.addWidget(self.export_button)

    def _make_search_button(self):
        button = QPushButton()
        button.setObjectName("command_search")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(SEARCH_WIDTH, 30)
        inner = QHBoxLayout(button)
        inner.setContentsMargins(10, 0, 8, 0)
        inner.setSpacing(6)
        self.search_icon = QLabel()
        self.search_icon.setPixmap(themed_icon("search", size=15, token="text_muted").pixmap(15, 15))
        text = QLabel(tr("コマンドを検索"))
        text.setObjectName("command_search_text")
        shortcut = QLabel(COMMAND_PALETTE_SHORTCUT_TEXT)
        shortcut.setObjectName("kbd_hint")
        for label in (self.search_icon, text, shortcut):
            # ボタンの子のラベルが押下を取らないように(ボタン全体で押せる)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        inner.addWidget(self.search_icon)
        inner.addWidget(text)
        inner.addStretch(1)
        inner.addWidget(shortcut)
        return button

    def set_mode(self, mode):
        blocked = self.mode_switch.blockSignals(True)
        self.mode_switch.setCurrentIndex(self.mode_switch.findData(mode))
        self.mode_switch.blockSignals(blocked)

    def refresh_icons(self):
        for button in self.findChildren(QToolButton, "header_button") + [self.add_tab_button]:
            name = button.property("iconName")
            if name:
                button.setIcon(themed_icon(name))
        self.search_icon.setPixmap(themed_icon("search", size=15, token="text_muted").pixmap(15, 15))
        self.export_button.setIcon(themed_icon("download", size=16, token="on_accent"))
