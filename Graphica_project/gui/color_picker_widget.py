# gui/color_picker_widget.py
"""
データセットの色選択欄(項目65)用の複合ウィジェット。

スウォッチボタン(クリックでQColorDialog/最近使った色パレットを展開)と、
選択中の色をカラーコード(#RRGGBB)で直接確認・編集できるテキスト欄を
組み合わせ、色を「見て」「数値でも」扱えるようにする。
"""
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QLineEdit,
                               QInputDialog, QMenu, QMessageBox)

from core.i18n import tr
from core.named_colors import (
    NamedColorError, add_named_color, load_named_colors, save_named_colors,
)
from gui.color_history import get_color_with_history

# ポップアップに並べる色見本の一辺(px)
_SWATCH_ICON_SIZE = 14

DEFAULT_COLOR = "#1f77b4"


class ColorPickerWidget(QWidget):
    """
    スウォッチ(パレット展開ボタン) + カラーコード入力欄の複合ウィジェット。

    colorChanged(str) は、ユーザー操作(スウォッチでの選択 or カラーコード欄への
    直接入力)によって色が実際に変わったときのみ発火する。set_color() による
    プログラム的な表示更新(データセット切り替え時など)では発火しない。
    """
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
        """現在の色を QColor で返す。"""
        return QColor(self._color)

    def color_name(self):
        """現在の色を #RRGGBB 形式の文字列で返す。"""
        return self._color.name()

    def set_color(self, color):
        """
        表示のみを更新する(colorChangedは発火しない)。
        データセット選択の切り替え時など、外部の状態にUIを合わせる用途。
        """
        new_color = QColor(color)
        if not new_color.isValid():
            return
        self._color = new_color
        self._update_swatch()
        self.hex_edit.blockSignals(True)
        self.hex_edit.setText(self._color.name())
        self.hex_edit.blockSignals(False)

    def blockSignals(self, block):
        # dataset_mixin.py 側の「シグナルを一時ブロックしてUIへ値をロードする」既存パターン
        # (self.ui.xxx.blockSignals(True/False)) と同じ流儀で使えるよう、内部の
        # 子ウィジェットにも伝播させる。
        self.swatch_button.blockSignals(block)
        self.hex_edit.blockSignals(block)
        return super().blockSignals(block)

    def _update_swatch(self, preview_color=None):
        # ★ 項目H-2-6(H-0調査で判明): 以前はborder色をrgba(128,128,128,110)で
        #   ハードコードしており、gui/theme.pyのトークンと無関係な固定グレーだった
        #   (ライト/ダーク双方で同じ見た目になり、他のUI要素との統一感が無かった)。
        #   現在テーマのborder_strongトークンを参照するよう変更。
        # preview_color: カラーコード欄への入力中(未確定)のライブプレビュー用。
        #   Noneなら確定済みの self._color を使う(通常の再描画)。
        from gui import theme
        border_color = theme.current_tokens()["border_strong"]
        color_name = (preview_color or self._color).name()
        self.swatch_button.setStyleSheet(
            f"background-color: {color_name};"
            f"border: 1px solid {border_color};"
            f"border-radius: 4px;"
        )

    def refresh_theme(self):
        """
        ダークモード切り替え時に呼ばれ、スウォッチの枠線色を現在のテーマに
        合わせて再描画する(スウォッチの背景色自体はユーザーが選んだデータ色
        なのでテーマとは無関係、枠線色だけがテーマ依存)。
        """
        self._update_swatch()

    def _on_swatch_clicked(self):
        """
        スウォッチを押したときのポップアップ。

        以前は直接 QColorDialog を開いていたが、「よく使う色を名前付きで登録して
        おき、複数の種類のデータで同じ物質に同じ色を使いたい」という要望を受けて、
        登録済みの色(core/named_colors.py)を先に見せるメニューにした。
        従来どおりの自由な色選択は「その他の色...」から辿れる
        (ツールチップが元から「クリックしてパレットを開く」なので、挙動としても
        こちらの方が素直)。
        """
        menu = QMenu(self)
        entries = load_named_colors(self._settings)

        for entry in entries:
            action = menu.addAction(_color_icon(entry["color"]),
                                    f'{entry["name"]}	{entry["color"]}')
            action.setData(entry["color"])
            action.triggered.connect(
                lambda checked=False, c=entry["color"]: self._apply_color_name(c))
        if entries:
            menu.addSeparator()

        register_action = menu.addAction(tr("この色を登録..."))
        register_action.triggered.connect(self._on_register_current_color)
        manage_action = menu.addAction(tr("色名の管理..."))
        manage_action.triggered.connect(self._on_manage_named_colors)
        menu.addSeparator()
        other_action = menu.addAction(tr("その他の色..."))
        other_action.triggered.connect(self._on_pick_other_color)

        # サブメニューは無いが、ローカル変数 menu が exec() の間ずっと生きている
        # ことに依存する点は、データセットの右クリックメニューと同じ。
        menu.exec(self.swatch_button.mapToGlobal(
            self.swatch_button.rect().bottomLeft()))

    def _apply_color_name(self, color_name):
        """登録済みの色を選んだときの反映(値が変わったときだけ通知する)。"""
        candidate = QColor(color_name)
        if not candidate.isValid() or candidate.name() == self._color.name():
            return
        self.set_color(candidate)
        self.colorChanged.emit(self._color.name())

    def _on_pick_other_color(self):
        """従来どおりの QColorDialog(最近使った色の履歴つき)。"""
        color = get_color_with_history(self._settings, self, initial=self._color)
        if not color.isValid():
            return
        if color.name() == self._color.name():
            return
        self.set_color(color)
        self.colorChanged.emit(self._color.name())

    def _on_register_current_color(self):
        """いま選んでいる色に名前を付けて登録する。"""
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
        """
        色名の管理ダイアログを開く。
        ★ gui/dialogs.py はこのモジュールを取り込む側なので、循環importを避ける
        ため関数内で遅延importする。
        """
        from gui.dialogs import NamedColorManagerDialog
        dialog = NamedColorManagerDialog(self._settings, self)
        dialog.exec()

    def _on_hex_text_changed(self, text):
        """
        カラーコード欄をキー入力するたびに呼ばれ、まだ確定(editingFinished)
        していなくても、有効な色になった時点でスウォッチにライブプレビュー
        表示する。確定処理(Dataset側への反映・Undoコマンド発行・colorChanged
        発火)は_on_hex_edited側のみが行う — キー入力のたびにUndo履歴を
        積んでしまわないよう、ここではあくまで見た目の先行表示に留める。
        """
        candidate = QColor(text.strip())
        if candidate.isValid():
            self._update_swatch(preview_color=candidate)
        else:
            # 入力途中で無効な状態(未入力・不完全な桁数など)は確定色の表示に戻す
            self._update_swatch()

    def _on_hex_edited(self):
        text = self.hex_edit.text().strip()
        candidate = QColor(text)
        if not candidate.isValid():
            # 無効な入力(例: 未入力・誤字)は現在の色の表記に戻す
            self.hex_edit.setText(self._color.name())
            return
        if candidate.name() == self._color.name():
            return
        self.set_color(candidate)
        self.colorChanged.emit(self._color.name())


def _color_icon(color_name, size=_SWATCH_ICON_SIZE):
    """
    メニュー項目の先頭に出す色見本。枠線を1px描くのは、白や淡い色が
    メニューの背景に溶けて「何も無い」ように見えるのを防ぐため。
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    from gui import theme
    painter.setPen(QPen(QColor(theme.current_tokens()["border_strong"]), 1))
    painter.setBrush(QColor(color_name))
    painter.drawRoundedRect(0, 0, size - 1, size - 1, 3, 3)
    painter.end()
    return QIcon(pixmap)
