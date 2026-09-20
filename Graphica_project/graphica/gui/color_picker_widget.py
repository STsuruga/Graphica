"""データセットの色の欄: 色見本のボタン(クリックで色を選ぶ)と、#RRGGBB の入力欄。"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QLineEdit,
                               QInputDialog, QMenu, QMessageBox)

from graphica.core.i18n import tr
from graphica.core.named_colors import (
    POPUP_LIMIT, NamedColorError, add_named_color, load_named_colors,
    save_named_colors,
)
from graphica.gui.color_history import get_color_with_history

_SWATCH_ICON_SIZE = 14

DEFAULT_COLOR = "#1f77b4"


class ColorPickerWidget(QWidget):
    """colorChanged(str) は利用者の操作で色が変わったときだけ出る(set_color() では出ない)。"""
    colorChanged = Signal(str)

    def __init__(self, settings, parent=None, initial_color=DEFAULT_COLOR):
        super().__init__(parent)
        self._settings = settings
        self._color = QColor(initial_color)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.swatch_button = QPushButton(self)
        self.swatch_button.setFixedSize(30, 24)
        self.swatch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch_button.setToolTip(tr("クリックしてパレットを開く"))
        self.swatch_button.clicked.connect(self._on_swatch_clicked)

        self.hex_edit = QLineEdit(self)
        self.hex_edit.setPlaceholderText("#RRGGBB")
        self.hex_edit.setMaxLength(7)
        self.hex_edit.editingFinished.connect(self._on_hex_edited)
        self.hex_edit.textChanged.connect(self._on_hex_text_changed)

        layout.addWidget(self.swatch_button)
        layout.addWidget(self.hex_edit, 1)

        self._update_swatch()
        self.hex_edit.setText(self._color.name())

    def color(self):
        return QColor(self._color)

    def color_name(self):
        return self._color.name()

    def set_color(self, color):
        """表示だけ変える(colorChanged は出ない)。"""
        new_color = QColor(color)
        if not new_color.isValid():
            return
        self._color = new_color
        self._update_swatch()
        self.hex_edit.blockSignals(True)
        self.hex_edit.setText(self._color.name())
        self.hex_edit.blockSignals(False)

    def blockSignals(self, block):
        # ほかの欄と同じく blockSignals で値を入れられるよう、中の部品にも伝える
        self.swatch_button.blockSignals(block)
        self.hex_edit.blockSignals(block)
        return super().blockSignals(block)

    def _update_swatch(self, preview_color=None):
        # preview_color は入力中(未確定)の色。None なら確定した self._color
        from graphica.gui import theme
        border_color = theme.current_tokens()["border_strong"]
        color_name = (preview_color or self._color).name()
        self.swatch_button.setStyleSheet(
            f"background-color: {color_name};"
            f"border: 1px solid {border_color};"
            f"border-radius: 4px;"
        )

    def refresh_theme(self):
        """ダークモードの切り替えで枠の色を当て直す(塗りはデータの色なのでテーマと関係ない)。"""
        self._update_swatch()

    def _on_swatch_clicked(self):
        """登録した色(core/named_colors.py)を先に並べ、自由な色選びは「その他の色...」から。"""
        menu = QMenu(self)
        entries = load_named_colors(self._settings)

        # 登録は際限なく増えるので、並べるのは先頭 POPUP_LIMIT 件まで。残りは検索できる一覧から選ぶ
        for entry in entries[:POPUP_LIMIT]:
            action = menu.addAction(_color_icon(entry["color"]),
                                    f'{entry["name"]}	{entry["color"]}')
            action.setData(entry["color"])
            action.triggered.connect(
                lambda checked=False, c=entry["color"]: self._apply_color_name(c))
        if len(entries) > POPUP_LIMIT:
            more_action = menu.addAction(
                tr("すべての登録色... (%d件)") % len(entries))
            more_action.triggered.connect(self._on_choose_from_all_named_colors)
        if entries:
            menu.addSeparator()

        register_action = menu.addAction(tr("この色を登録..."))
        register_action.triggered.connect(self._on_register_current_color)
        manage_action = menu.addAction(tr("色名の管理..."))
        manage_action.triggered.connect(self._on_manage_named_colors)
        menu.addSeparator()
        other_action = menu.addAction(tr("その他の色..."))
        other_action.triggered.connect(self._on_pick_other_color)

        # menu が exec() の間生きていることに頼っている(データセットの右クリックメニューと同じ)
        menu.exec(self.swatch_button.mapToGlobal(
            self.swatch_button.rect().bottomLeft()))

    def _apply_color_name(self, color_name):
        """値が変わったときだけ知らせる。"""
        candidate = QColor(color_name)
        if not candidate.isValid() or candidate.name() == self._color.name():
            return
        self.set_color(candidate)
        self.colorChanged.emit(self._color.name())

    def _on_choose_from_all_named_colors(self):
        from graphica.gui.dialogs import NamedColorPickerDialog
        dialog = NamedColorPickerDialog(self._settings, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        entry = dialog.selected_entry()
        if entry:
            self._apply_color_name(entry["color"])

    def _on_pick_other_color(self):
        color = get_color_with_history(self._settings, self, initial=self._color)
        if not color.isValid():
            return
        if color.name() == self._color.name():
            return
        self.set_color(color)
        self.colorChanged.emit(self._color.name())

    def _on_register_current_color(self):
        name, ok = QInputDialog.getText(
            self, tr("色を登録"),
            tr("この色の登録名 (%s)") % self._color.name())
        if not ok:
            return
        entries = load_named_colors(self._settings)
        try:
            entries = add_named_color(entries, name, self._color.name())
        except NamedColorError as e:
            QMessageBox.warning(self, tr("色を登録"), str(e))
            return
        save_named_colors(self._settings, entries)

    def _on_manage_named_colors(self):
        """dialogs がこのモジュールを import しているので、ここで遅れて import する。"""
        from graphica.gui.dialogs import NamedColorManagerDialog
        dialog = NamedColorManagerDialog(self._settings, self)
        dialog.exec()

    def _on_hex_text_changed(self, text):
        """入力中でも有効な色になったら色見本に先に出す。確定(反映・Undo・colorChanged)は _on_hex_edited だけ(打つたびに Undo を積まないように)。"""
        candidate = QColor(text.strip())
        if candidate.isValid():
            self._update_swatch(preview_color=candidate)
        else:
            self._update_swatch()

    def _on_hex_edited(self):
        text = self.hex_edit.text().strip()
        candidate = QColor(text)
        if not candidate.isValid():
            # 無効な入力なら今の色の表記に戻す
            self.hex_edit.setText(self._color.name())
            return
        if candidate.name() == self._color.name():
            return
        self.set_color(candidate)
        self.colorChanged.emit(self._color.name())


def _color_icon(color_name, size=_SWATCH_ICON_SIZE):
    """メニューの色見本。白や淡い色が背景に溶けないよう1pxの枠を描く。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    from graphica.gui import theme
    painter.setPen(QPen(QColor(theme.current_tokens()["border_strong"]), 1))
    painter.setBrush(QColor(color_name))
    painter.drawRoundedRect(0, 0, size - 1, size - 1, 3, 3)
    painter.end()
    return QIcon(pixmap)
