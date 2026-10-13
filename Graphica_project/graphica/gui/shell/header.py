"""上部バー: ≡(メニュー)・ロゴ・プロジェクトのタブ・コマンドを検索・モードの切り替え・元に戻す/やり直す・保存・
クイックアクセス・エクスポート。高さ 48px の1段。見本は docs/dev/mockups/gui_redesign/。

押したときの行き先(表示中のタブ)は MainAppWindow がつなぐ。ここは部品と並びだけを持つ。
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QWidget

from graphica.core.i18n import tr
from graphica.gui import ui_mode
from graphica.gui.shell.icons import themed_icon
from graphica.gui.shell.rail import RAIL_WIDTH
from graphica.gui.theme import make_toggle_switch

HEADER_HEIGHT = 48
HEADER_BUTTON_SIZE = 30
SEARCH_WIDTH = 300
COMMAND_PALETTE_SHORTCUT_TEXT = "Ctrl+Shift+P"
EXPORT_ICON = "file-export"


class ModeToggle(QWidget):
    """「シンプル (スイッチ) アドバンスド」。どこを押しても切り替わり、今のモードの名前を濃く見せる。

    mode_changed は利用者の操作でだけ出る(set_mode では出ない)。
    """

    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mode_switch")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("シンプル / アドバンスドを切り替える"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        self.lite_label = QLabel(ui_mode.mode_label(ui_mode.LITE))
        self.advanced_label = QLabel(ui_mode.mode_label(ui_mode.ADVANCED))
        self.switch = QCheckBox()
        # 押すのはこの部品全体(スイッチだけが押しを受けると、名前を押しても切り替わらない)
        self.switch.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        make_toggle_switch(self.switch)
        layout.addWidget(self.lite_label)
        layout.addWidget(self.switch)
        layout.addWidget(self.advanced_label)
        self.refresh()

    def mode(self):
        return ui_mode.ADVANCED if self.switch.isChecked() else ui_mode.LITE

    def set_mode(self, mode):
        self.switch.setChecked(mode == ui_mode.ADVANCED)
        self.refresh()

    def toggle(self):
        self.set_mode(ui_mode.LITE if self.mode() == ui_mode.ADVANCED else ui_mode.ADVANCED)
        self.mode_changed.emit(self.mode())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.toggle()
        super().mouseReleaseEvent(event)

    def refresh(self):
        for label, active in ((self.lite_label, self.mode() == ui_mode.LITE),
                              (self.advanced_label, self.mode() == ui_mode.ADVANCED)):
            label.setObjectName("mode_label_active" if active else "mode_label")
            label.style().unpolish(label)
            label.style().polish(label)


def _header_button(name, tooltip):
    button = QToolButton()
    button.setObjectName("header_button")
    button.setToolTip(tooltip)
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(HEADER_BUTTON_SIZE, HEADER_BUTTON_SIZE)
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
        # ≡ を左の帯のアイコンと同じ縦の列に置く(帯の幅の真ん中に ≡ の真ん中)
        layout.setContentsMargins((RAIL_WIDTH - HEADER_BUTTON_SIZE) // 2, 0, 12, 0)
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

        # 検索は右側(モードの切り替えの左)に寄せる。タブが増えても動かない
        layout.addStretch(1)
        self.search_button = self._make_search_button()
        layout.addWidget(self.search_button)
        layout.addSpacing(10)

        self.mode_switch = ModeToggle()
        layout.addWidget(self.mode_switch)
        layout.addWidget(_separator())

        self.undo_button = _header_button("arrow-back-up", tr("元に戻す"))
        self.redo_button = _header_button("arrow-forward-up", tr("やり直し"))
        self.save_button = _header_button("device-floppy", tr("上書き保存"))
        for button in (self.undo_button, self.redo_button, self.save_button):
            layout.addWidget(button)

        # クイックアクセス(ピン留め)は ★ の一覧にまとめる(いくつ増やしても上部バーの幅を取らない)。
        # 中身は開くたびに表示中のタブのピン留めから作る(MainAppWindow)
        self.quick_access_button = _header_button("star", tr("クイックアクセス"))
        self.quick_access_button.setObjectName("header_button")
        self.quick_access_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.quick_access_button.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.quick_access_menu = QMenu(self.quick_access_button)
        self.quick_access_button.setMenu(self.quick_access_menu)
        layout.addWidget(self.quick_access_button)

        # エクスポートはアイコンだけ(名前はツールチップ)。強調の色で塗って、ほかのボタンと見分ける
        self.export_button = QPushButton()
        self.export_button.setObjectName("header_export_button")
        self.export_button.setProperty("primaryButton", True)
        self.export_button.setToolTip(tr("エクスポート"))
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.export_button.setFixedSize(34, 30)
        self.export_button.setIconSize(QSize(17, 17))
        self.export_button.setIcon(themed_icon(EXPORT_ICON, size=17, token="on_accent"))
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
        # 検索欄の高さいっぱいに伸ばさず、文字の高さで真ん中に置く
        inner.addWidget(shortcut, 0, Qt.AlignmentFlag.AlignVCenter)
        return button

    def set_mode(self, mode):
        self.mode_switch.set_mode(mode)

    def refresh_icons(self):
        for button in self.findChildren(QToolButton, "header_button") + [self.add_tab_button]:
            name = button.property("iconName")
            if name:
                button.setIcon(themed_icon(name))
        self.search_icon.setPixmap(themed_icon("search", size=15, token="text_muted").pixmap(15, 15))
        self.export_button.setIcon(themed_icon(EXPORT_ICON, size=17, token="on_accent"))
        self.mode_switch.refresh()
