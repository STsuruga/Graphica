# gui/color_picker_widget.py
"""
データセットの色選択欄(項目65)用の複合ウィジェット。

スウォッチボタン(クリックでQColorDialog/最近使った色パレットを展開)と、
選択中の色をカラーコード(#RRGGBB)で直接確認・編集できるテキスト欄を
組み合わせ、色を「見て」「数値でも」扱えるようにする。
"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit

from core.i18n import tr
from gui.color_history import get_color_with_history

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

    def _update_swatch(self):
        # ★ 項目H-2-6(H-0調査で判明): 以前はborder色をrgba(128,128,128,110)で
        #   ハードコードしており、gui/theme.pyのトークンと無関係な固定グレーだった
        #   (ライト/ダーク双方で同じ見た目になり、他のUI要素との統一感が無かった)。
        #   現在テーマのborder_strongトークンを参照するよう変更。
        from gui import theme
        border_color = theme.current_tokens()["border_strong"]
        self.swatch_button.setStyleSheet(
            f"background-color: {self._color.name()};"
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
        color = get_color_with_history(self._settings, self, initial=self._color)
        if not color.isValid():
            return
        if color.name() == self._color.name():
            return
        self.set_color(color)
        self.colorChanged.emit(self._color.name())

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
