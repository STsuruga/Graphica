"""左端の帯の ⚙ で開くポップアップ: テーマカラー(プリセット・カスタム・既定に戻す)と、環境設定への入口。

色を選ぶとすぐ app.set_theme_color() で全部のタブに当てる。読みにくい色は theme_color.derive_accent() が
明るさを動かして使うので、ライト・ダークで実際に使う色と、調整したかどうかを並べて見せる。
"""
from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QColorDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout)

from graphica.core.i18n import tr
from graphica.gui import motion
from graphica.gui import theme
from graphica.gui.builders.common import _svg_icon
from graphica.gui.theme_color import DEFAULT_THEME_COLOR, THEME_COLOR_PRESETS, derive_accent, normalize_hex

POPOVER_WIDTH = 318
SWATCH_SIZE = 34


def theme_color_preview(color):
    """(ライトで使う色, ダークで使う色, 調整の説明 or "")。"""
    light = derive_accent(color, theme.LIGHT_TOKENS["surface"], dark=False)
    dark = derive_accent(color, theme.DARK_TOKENS["surface"], dark=True)
    notes = []
    if light["adjusted"]:
        notes.append(tr("ライトでは白い背景で見えるよう濃く"))
    if dark["adjusted"]:
        notes.append(tr("ダークでは暗い背景で見えるよう明るく"))
    note = tr("、").join(notes) + tr("しています(読みやすさの自動調整)。") if notes else ""
    return light["accent"], dark["accent"], note


class _Swatch(QAbstractButton):
    """角丸の色の見本と、下に名前。選んでいる色は輪で囲む。"""

    def __init__(self, name, color, parent=None):
        super().__init__(parent)
        self.color = normalize_hex(color)
        self.name = name
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{name} {self.color}")
        self.setFixedSize(QSize(62, SWATCH_SIZE + 26))

    def paintEvent(self, event):
        tokens = theme.current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        left = (self.width() - SWATCH_SIZE) / 2
        rect = QRectF(left, 4, SWATCH_SIZE, SWATCH_SIZE)
        if self.isChecked():
            painter.setPen(QPen(QColor(tokens["text_primary"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 11, 11)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(rect, 9, 9)
        painter.setPen(QColor(tokens["text_secondary"]))
        font = painter.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() - 1))
        painter.setFont(font)
        painter.drawText(QRectF(0, SWATCH_SIZE + 8, self.width(), 18),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), self.name)
        painter.end()


class _ColorChip(QLabel):
    """小さな色の四角(プレビュー用)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)

    def set_color(self, color):
        self.setStyleSheet(f"background: {color}; border-radius: 4px;")


class SettingsPopover(QFrame):
    def __init__(self, app, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._app = app
        # 窓の四隅は透かし、中の枠を角丸にする(窓のままだと角が四角く残る)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(POPOVER_WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("settings_popover")
        outer.addWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(0)

        title_row = QHBoxLayout()
        title = QLabel(tr("テーマカラー"))
        title.setObjectName("settings_popover_title")
        self.close_button = QToolButton()
        self.close_button.setObjectName("card_button")
        self.close_button.setIcon(_svg_icon("x", size=14))
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.close)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.close_button)
        layout.addLayout(title_row)
        subtitle = QLabel(tr("ボタン・選択・枠などに使う色です。グラフの線の色は変わりません。"))
        subtitle.setObjectName("settings_popover_sub")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.swatches = []
        for index, (name, color) in enumerate(THEME_COLOR_PRESETS):
            swatch = _Swatch(tr(name), color)
            swatch.clicked.connect(lambda _checked=False, c=swatch.color: self.choose(c))
            grid.addWidget(swatch, index // 4, index % 4, Qt.AlignmentFlag.AlignHCenter)
            self.swatches.append(swatch)
        layout.addLayout(grid)

        custom_box = QFrame()
        custom_box.setObjectName("settings_popover_row")
        custom_row = QHBoxLayout(custom_box)
        custom_row.setContentsMargins(0, 12, 0, 0)
        custom_row.setSpacing(8)
        self.custom_button = QPushButton()
        self.custom_button.setObjectName("settings_custom_color")
        self.custom_button.setFixedSize(34, 30)
        self.custom_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_button.clicked.connect(self._on_custom)
        custom_text = QVBoxLayout()
        custom_text.setSpacing(0)
        custom_title = QLabel(tr("カスタム"))
        custom_title.setObjectName("settings_popover_strong")
        custom_sub = QLabel(tr("好きな色を選ぶ"))
        custom_sub.setObjectName("settings_popover_sub")
        custom_text.addWidget(custom_title)
        custom_text.addWidget(custom_sub)
        self.hex_label = QLabel()
        self.hex_label.setObjectName("settings_popover_mono")
        custom_row.addWidget(self.custom_button)
        custom_row.addLayout(custom_text)
        custom_row.addStretch(1)
        custom_row.addWidget(self.hex_label)
        layout.addSpacing(12)
        layout.addWidget(custom_box)

        preview = QGridLayout()
        preview.setContentsMargins(0, 10, 0, 0)
        preview.setHorizontalSpacing(10)
        preview.setVerticalSpacing(6)
        self.light_chip, self.dark_chip = _ColorChip(), _ColorChip()
        self.light_hex, self.dark_hex = QLabel(), QLabel()
        for row, (text, chip, hex_label) in enumerate(((tr("ライトで使う色"), self.light_chip, self.light_hex),
                                                       (tr("ダークで使う色"), self.dark_chip, self.dark_hex))):
            label = QLabel(text)
            label.setObjectName("settings_popover_label")
            hex_label.setObjectName("settings_popover_mono")
            value = QHBoxLayout()
            value.setSpacing(6)
            value.addWidget(chip)
            value.addWidget(hex_label)
            value.addStretch(1)
            preview.addWidget(label, row, 0)
            preview.addLayout(value, row, 1)
        layout.addLayout(preview)

        self.note_label = QLabel()
        self.note_label.setObjectName("settings_popover_note")
        self.note_label.setWordWrap(True)
        layout.addSpacing(10)
        layout.addWidget(self.note_label)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 12, 0, 0)
        buttons.setSpacing(8)
        self.reset_button = QPushButton(tr("既定に戻す(アイコンの色)"))
        self.reset_button.clicked.connect(lambda: self.choose(DEFAULT_THEME_COLOR))
        self.preferences_button = QPushButton(tr("環境設定..."))
        self.preferences_button.clicked.connect(self._on_preferences)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.preferences_button)
        layout.addLayout(buttons)
        self.refresh()

    def current_color(self):
        return normalize_hex(theme.current_theme_color())

    def choose(self, color):
        self._app.set_theme_color(color)
        self.refresh()

    def refresh(self):
        color = self.current_color()
        for swatch in self.swatches:
            swatch.setChecked(swatch.color == color)
            swatch.update()
        self.custom_button.setStyleSheet(
            f"background: {color}; border: 1px solid {theme.current_tokens()['border_strong']}; border-radius: 7px;")
        self.hex_label.setText(color)
        light, dark, note = theme_color_preview(color)
        self.light_chip.set_color(light)
        self.dark_chip.set_color(dark)
        self.light_hex.setText(light)
        self.dark_hex.setText(dark)
        self.note_label.setText(note)
        self.note_label.setVisible(bool(note))
        self.close_button.setIcon(_svg_icon("x", size=14))
        self.adjustSize()

    def _on_custom(self):
        # 色の画面を開くとポップアップは閉じる(フォーカスが外れる)ので、選び終えてから当てる
        self.hide()
        chosen = QColorDialog.getColor(QColor(self.current_color()), self._app, tr("テーマカラー"))
        if chosen.isValid():
            self._app.set_theme_color(chosen.name())

    def _on_preferences(self):
        self.hide()
        self._app._on_show_preferences()

    def open_beside(self, anchor):
        """anchor(帯の ⚙)の右、下端をそろえて開く。"""
        self.refresh()
        bottom_right = anchor.mapToGlobal(QPoint(anchor.width() + 8, anchor.height()))
        self.move(bottom_right.x(), bottom_right.y() - self.sizeHint().height())
        self.show()
        motion.fade_in_window(self)


def toggle_settings_popover(app, anchor):
    popover = getattr(app, 'settings_popover', None)
    if popover is None:
        popover = app.settings_popover = SettingsPopover(app, app)
    if popover.isVisible():
        popover.hide()
    else:
        popover.open_beside(anchor)

