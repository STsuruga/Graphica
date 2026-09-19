"""見た目と注釈のダイアログ。呼び出し側は `from graphica.gui.dialogs import X` で参照する。"""

import re
import matplotlib as mpl
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont
from graphica.gui import icon_utils
from graphica.gui.theme import apply_form_spacing
from graphica.gui.mathtext_preview import FitWidthPixmapLabel
from graphica.core.i18n import tr
from graphica.core.color_palettes import BUILTIN_PALETTES
from graphica.core.named_colors import (
    NamedColorError,
    add_named_color,
    load_named_colors,
    move_named_color,
    remove_named_color,
    save_named_colors,
    update_named_color,
)


class LabelEditDialog(QDialog):
    """タイトルと軸ラベルの編集。装飾ボタンは選択範囲を mathtext で包み、記号はカーソル位置に入れる。"""

    def __init__(self, initial_text, window_title, symbol_palette, parent=None):
        """symbol_palette は main_window の LABEL_SYMBOL_PALETTE(dialogs は main_window を import できないので渡してもらう)。"""
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        self.text_edit = QLineEdit(initial_text)
        self.text_edit.setMinimumHeight(34)
        larger_font = QFont(self.text_edit.font())
        larger_font.setPointSize(larger_font.pointSize() + 1)
        self.text_edit.setFont(larger_font)
        layout.addWidget(self.text_edit)

        # QLineEdit では装飾を見せられないので、描いた結果を下に出す
        self.preview_label = FitWidthPixmapLabel()
        self.preview_label.setObjectName("mathtext_preview_label")
        self.preview_label.setMinimumHeight(36)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.preview_label)
        self.text_edit.textChanged.connect(self._refresh_preview)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        def _make_icon_button(icon_name, tooltip):
            button = QPushButton()
            button.setIcon(icon_utils.icon(icon_name, size=16))
            button.setToolTip(tooltip)
            button.setProperty("iconOnly", True)
            button.setFixedSize(28, 28)
            # フォーカスを取るとテキスト欄の選択が消える(下の説明)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button_row.addWidget(button)
            return button

        bold_button = _make_icon_button("bold", "太字")
        italic_button = _make_icon_button("italic", "イタリック")
        superscript_button = _make_icon_button("superscript", "上付き文字")
        subscript_button = _make_icon_button("subscript", "下付き文字")

        # ボタンがフォーカスを取ると、pressed が出るより前にテキスト欄の選択が消える。
        # だから装飾ボタンはフォーカスを取らない。pressed で選択を控えるのは、それでも移る環境のための保険
        self._pending_selection = None  # (start, selected_text)、選択が無ければ None
        self._pending_cursor = 0

        for button in (bold_button, italic_button, superscript_button, subscript_button):
            button.pressed.connect(self._capture_pending_selection)

        bold_button.clicked.connect(lambda: self._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}"))
        italic_button.clicked.connect(lambda: self._apply_wrap("italic", lambda s: f"\\mathit{{{s}}}"))
        superscript_button.clicked.connect(lambda: self._apply_wrap("super", lambda s: f"{{}}^{{{s}}}"))
        subscript_button.clicked.connect(lambda: self._apply_wrap("sub", lambda s: f"{{}}_{{{s}}}"))

        # 記号は32個あり、常に並べると場所を取るのでドロップダウンにする
        symbol_button = QToolButton()
        symbol_button.setText("Ω")
        symbol_button.setToolTip("ギリシャ文字・数学記号を挿入")
        symbol_button.setProperty("iconOnly", True)
        symbol_button.setFixedSize(28, 28)
        symbol_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # 既定でも NoFocus だが、装飾ボタンと同じ理由で明示する
        symbol_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # メニューを開く動作でも選択が消えうるので、開く前に控える
        symbol_button.pressed.connect(self._capture_pending_selection)

        symbol_menu = QMenu(symbol_button)
        symbol_panel = QWidget()
        symbol_grid = QGridLayout(symbol_panel)
        symbol_grid.setContentsMargins(6, 6, 6, 6)
        symbol_grid.setSpacing(2)
        # 既定の大きさでは記号が読みにくい
        symbol_font = QFont(self.font())
        symbol_font.setPointSize(symbol_font.pointSize() + 4)
        for index, (glyph, macro) in enumerate(symbol_palette):
            item_button = QToolButton()
            item_button.setText(glyph)
            item_button.setFont(symbol_font)
            # macro=None は mathtext のマクロを持たない文字そのもの(マイナス記号など)
            item_button.setToolTip(f"\\{macro}" if macro else glyph)
            item_button.setFixedSize(30, 30)
            item_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            item_button.clicked.connect(
                lambda checked=False, g=glyph, m=macro, sm=symbol_menu: (self._insert_symbol(g, m), sm.close())
            )
            symbol_grid.addWidget(item_button, index // 4, index % 4)
        symbol_widget_action = QWidgetAction(symbol_button)
        symbol_widget_action.setDefaultWidget(symbol_panel)
        symbol_menu.addAction(symbol_widget_action)
        symbol_button.setMenu(symbol_menu)
        button_row.addWidget(symbol_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._refresh_preview()

    def _refresh_preview(self):
        """テキスト欄の内容を描いてプレビューに出す(タイトル欄のプレビューと同じ描き方)。"""
        from graphica.gui import theme
        from graphica.gui.mathtext_preview import render_mathtext_to_pixmap

        tokens = theme.current_tokens()
        text = self.text_edit.text()
        color = tokens["text_primary"] if text else tokens["text_muted"]
        pixmap = render_mathtext_to_pixmap(text if text else " ", color=color, fontsize=15)
        self.preview_label.set_natural_pixmap(pixmap)

    def _capture_pending_selection(self):
        """ボタンが押された瞬間の選択範囲を控える(clicked まで待つと消えている環境がある)。"""
        if self.text_edit.hasSelectedText():
            self._pending_selection = (
                self.text_edit.selectionStart(), self.text_edit.selectedText()
            )
        else:
            self._pending_selection = None
        self._pending_cursor = self.text_edit.cursorPosition()

    # 選択が $...$ で囲んだ1つの断片か(直前の装飾の結果をさらに装飾するとき)
    _MATH_SPAN_RE = re.compile(r'^\$(.*)\$$', re.DOTALL)
    _MATHBF_RE = re.compile(r'^\\mathbf\{(.*)\}$', re.DOTALL)
    _MATHIT_RE = re.compile(r'^\\mathit\{(.*)\}$', re.DOTALL)
    _BOLDSYMBOL_RE = re.compile(r'^\\boldsymbol\{(.*)\}$', re.DOTALL)
    _SUPER_RE = re.compile(r'^\{\}\^\{(.*)\}$', re.DOTALL)
    _SUB_RE = re.compile(r'^\{\}_\{(.*)\}$', re.DOTALL)

    def _apply_wrap(self, kind, wrap_fn):
        """選択範囲を wrap_fn の中身で包み、$...$ で囲む。kind は "bold" / "italic" / "super" / "sub"。

        選択が既に $...$ の断片なら、中身を取り出してから包み直す($ が入れ子になると壊れた構文になる)。
        \\mathbf と \\mathit は入れ子にしても合成されないので、両方なら \\boldsymbol にする。
        同じ装飾がもう外側にかかっていれば外す(連打で入れ子が積み重ならないように)。
        装飾が無くなれば $ も外す(mathtext の中の裸の文字は斜体になる)。
        """
        if not self._pending_selection:
            # 選択が無ければ何もしない(案内は出さない)
            return
        start, selected = self._pending_selection
        span_match = self._MATH_SPAN_RE.match(selected)
        inner = span_match.group(1) if span_match else selected

        combined = None
        if kind == "bold":
            m = self._BOLDSYMBOL_RE.match(inner)
            if m:
                combined = f"\\mathit{{{m.group(1)}}}"  # 太字だけ外し、イタリックは残す
            else:
                m = self._MATHIT_RE.match(inner)
                if m:
                    combined = f"\\boldsymbol{{{m.group(1)}}}"
                else:
                    m = self._MATHBF_RE.match(inner)
                    if m:
                        combined = m.group(1)
        elif kind == "italic":
            m = self._BOLDSYMBOL_RE.match(inner)
            if m:
                combined = f"\\mathbf{{{m.group(1)}}}"  # イタリックだけ外し、太字は残す
            else:
                m = self._MATHBF_RE.match(inner)
                if m:
                    combined = f"\\boldsymbol{{{m.group(1)}}}"
                else:
                    m = self._MATHIT_RE.match(inner)
                    if m:
                        combined = m.group(1)
        elif kind == "super":
            m = self._SUPER_RE.match(inner)
            if m:
                combined = m.group(1)
        elif kind == "sub":
            m = self._SUB_RE.match(inner)
            if m:
                combined = m.group(1)

        new_inner = combined if combined is not None else wrap_fn(inner)
        if re.search(r'[\\^_{}]', new_inner):
            replacement = f"${new_inner}$"
        else:
            replacement = new_inner
        text = self.text_edit.text()
        self.text_edit.setText(text[:start] + replacement + text[start + len(selected):])
        self.text_edit.setSelection(start, len(replacement))

    def _insert_symbol(self, glyph, macro):
        """記号を選択範囲に置き換えるか、カーソル位置に入れる。macro が None なら $ で包まない(包むと斜体になる)。"""
        text = self.text_edit.text()
        if self._pending_selection:
            start, selected = self._pending_selection
            end = start + len(selected)
        else:
            start = end = self._pending_cursor
        replacement = glyph if macro is None else f"$\\{macro}$"
        self.text_edit.setText(text[:start] + replacement + text[end:])
        self.text_edit.setCursorPosition(start + len(replacement))

    def get_text(self):
        return self.text_edit.text()


class ColorPaletteDialog(QDialog):
    """「自動配色」のパレットを作り、選ぶ。「Matplotlib既定」と組み込みのパレットは読み取り専用。"""

    DEFAULT_PALETTE_NAME = "Matplotlib既定"

    def __init__(self, palettes: dict, active_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配色パレットの管理")
        self.resize(420, 440)

        # キャンセルしたとき元に戻せるよう、呼び出し側の辞書は変えない
        self.palettes = {name: list(colors) for name, colors in palettes.items()}

        layout = QVBoxLayout(self)

        combo_layout = QHBoxLayout()
        combo_layout.addWidget(QLabel("パレット"))
        self.palette_combo = QComboBox()
        self.palette_combo.addItem(self.DEFAULT_PALETTE_NAME)
        self.palette_combo.addItems(sorted(BUILTIN_PALETTES.keys()))
        self.palette_combo.addItems(sorted(self.palettes.keys()))
        combo_layout.addWidget(self.palette_combo, stretch=1)
        layout.addLayout(combo_layout)

        palette_button_layout = QHBoxLayout()
        self.new_palette_button = QPushButton("新規パレット...")
        self.rename_palette_button = QPushButton("名前を変更...")
        self.delete_palette_button = QPushButton("削除")
        palette_button_layout.addWidget(self.new_palette_button)
        palette_button_layout.addWidget(self.rename_palette_button)
        palette_button_layout.addWidget(self.delete_palette_button)
        layout.addLayout(palette_button_layout)

        self.color_list = QListWidget()
        layout.addWidget(self.color_list)

        color_button_layout = QHBoxLayout()
        self.add_color_button = QPushButton("色を追加...")
        self.remove_color_button = QPushButton("選択した色を削除")
        color_button_layout.addWidget(self.add_color_button)
        color_button_layout.addWidget(self.remove_color_button)
        color_button_layout.addStretch()
        layout.addLayout(color_button_layout)

        info_label = QLabel("「OK」を押すと、選択中のパレットが以後「自動配色」ボタンで使われます。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.palette_combo.currentTextChanged.connect(self._on_palette_selected)
        self.new_palette_button.clicked.connect(self._on_new_palette)
        self.rename_palette_button.clicked.connect(self._on_rename_palette)
        self.delete_palette_button.clicked.connect(self._on_delete_palette)
        self.add_color_button.clicked.connect(self._on_add_color)
        self.remove_color_button.clicked.connect(self._on_remove_color)

        # 組み込みのパレットも初期の選択にする(でないと既定の表示のまま OK を押して上書きしてしまう)
        if active_name in self.palettes or active_name in BUILTIN_PALETTES:
            self.palette_combo.setCurrentText(active_name)
        else:
            self.palette_combo.setCurrentText(self.DEFAULT_PALETTE_NAME)
        self._refresh_color_list()
        self._update_button_states()

    def _is_default_selected(self):
        return self._is_readonly_palette(self.palette_combo.currentText())

    def _is_readonly_palette(self, name):
        """「Matplotlib既定」か組み込みのパレット(どちらも編集できない)。"""
        return name == self.DEFAULT_PALETTE_NAME or name in BUILTIN_PALETTES

    def _update_button_states(self):
        editable = not self._is_default_selected()
        self.rename_palette_button.setEnabled(editable)
        self.delete_palette_button.setEnabled(editable)
        self.add_color_button.setEnabled(editable)
        self.remove_color_button.setEnabled(editable)

    def _refresh_color_list(self):
        # 行は QSS に任せず色見本+テーマの文字色のラベルにする。QSS で ::item に何か当てると、
        # setBackground / setForeground が無視され、明るい色や暗い色の行が読めなくなる
        self.color_list.clear()
        name = self.palette_combo.currentText()
        if name == self.DEFAULT_PALETTE_NAME:
            colors = list(mpl.rcParams['axes.prop_cycle'].by_key()['color'])
        elif name in BUILTIN_PALETTES:
            colors = BUILTIN_PALETTES[name]
        else:
            colors = self.palettes.get(name, [])
        from graphica.gui import theme
        border_color = theme.current_tokens()["border_strong"]
        for color_hex in colors:
            item = QListWidgetItem()
            self.color_list.addItem(item)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 2, 6, 2)
            row_layout.setSpacing(8)

            swatch = QLabel()
            swatch.setFixedSize(20, 20)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; border: 1px solid {border_color}; "
                f"border-radius: 4px;"
            )
            row_layout.addWidget(swatch)
            row_layout.addWidget(QLabel(color_hex), 1)

            item.setSizeHint(row_widget.sizeHint())
            self.color_list.setItemWidget(item, row_widget)

    def _on_palette_selected(self, _name):
        self._refresh_color_list()
        self._update_button_states()

    def _on_new_palette(self):
        name, ok = QInputDialog.getText(self, "新規パレット", "パレット名")
        if not ok or not name:
            return
        if self._is_readonly_palette(name) or name in self.palettes:
            QMessageBox.warning(self, "エラー", f"パレット名 '{name}' は既に使われています。")
            return
        self.palettes[name] = []
        self.palette_combo.addItem(name)
        self.palette_combo.setCurrentText(name)

    def _on_rename_palette(self):
        old_name = self.palette_combo.currentText()
        if self._is_readonly_palette(old_name):
            return
        new_name, ok = QInputDialog.getText(self, "名前を変更", "新しいパレット名", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return
        if self._is_readonly_palette(new_name) or new_name in self.palettes:
            QMessageBox.warning(self, "エラー", f"パレット名 '{new_name}' は既に使われています。")
            return
        self.palettes[new_name] = self.palettes.pop(old_name)
        self.palette_combo.setItemText(self.palette_combo.currentIndex(), new_name)

    def _on_delete_palette(self):
        name = self.palette_combo.currentText()
        if self._is_readonly_palette(name):
            return
        reply = QMessageBox.question(
            self, "パレットを削除", f"パレット '{name}' を削除しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del self.palettes[name]
        self.palette_combo.removeItem(self.palette_combo.currentIndex())

    def _on_add_color(self):
        name = self.palette_combo.currentText()
        if self._is_readonly_palette(name):
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        self.palettes.setdefault(name, []).append(color.name())
        self._refresh_color_list()

    def _on_remove_color(self):
        name = self.palette_combo.currentText()
        if self._is_readonly_palette(name):
            return
        row = self.color_list.currentRow()
        if row < 0:
            return
        del self.palettes[name][row]
        self._refresh_color_list()

    def get_result(self):
        """(パレットの辞書, 選んだパレット名)。QSettings への保存は呼び出し側。"""
        return self.palettes, self.palette_combo.currentText()


def _named_color_icon(color_name, size=16):
    """リスト行の先頭に出す色見本(色欄のポップアップと同じ見た目に揃える)。"""
    from graphica.gui.color_picker_widget import _color_icon
    return _color_icon(color_name, size=size)


class NamedColorManagerDialog(QDialog):
    """名前を付けて登録した色(core/named_colors.py)の管理。配色パレット(色の並び)とは別物。

    登録簿を育てる操作で、プロットの見た目は変えないので、OK を待たずにその場で保存する。
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("色名の管理"))
        self.resize(420, 400)
        self._settings = settings
        self.entries = load_named_colors(settings)

        layout = QVBoxLayout(self)

        description = QLabel(tr(
            "よく使う色に名前を付けて登録します。データセットの色欄で"
            "スウォッチを押すと、ここに登録した色を名前から選べます。"))
        description.setWordWrap(True)
        layout.addWidget(description)

        self.color_list = QListWidget()
        self.color_list.setIconSize(QSize(16, 16))
        self.color_list.itemDoubleClicked.connect(lambda _item: self._on_edit())
        layout.addWidget(self.color_list, stretch=1)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton(tr("追加..."))
        self.edit_button = QPushButton(tr("編集..."))
        self.delete_button = QPushButton(tr("削除"))
        self.up_button = QPushButton(tr("上へ"))
        self.down_button = QPushButton(tr("下へ"))
        for button in (self.add_button, self.edit_button, self.delete_button):
            button_layout.addWidget(button)
        button_layout.addStretch()
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        layout.addLayout(button_layout)

        order_note = QLabel(tr("並び順は、色欄のポップアップにそのまま反映されます。"))
        order_note.setWordWrap(True)
        layout.addWidget(order_note)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.add_button.clicked.connect(self._on_add)
        self.edit_button.clicked.connect(self._on_edit)
        self.delete_button.clicked.connect(self._on_delete)
        self.up_button.clicked.connect(lambda: self._on_move(-1))
        self.down_button.clicked.connect(lambda: self._on_move(1))

        self._reload_list()


    def _reload_list(self, select_index=None):
        self.color_list.clear()
        for entry in self.entries:
            item = QListWidgetItem(f'{entry["name"]}    {entry["color"]}')
            item.setIcon(_named_color_icon(entry["color"]))
            self.color_list.addItem(item)
        if select_index is not None and 0 <= select_index < self.color_list.count():
            self.color_list.setCurrentRow(select_index)

    def _commit(self, entries, select_index=None):
        self.entries = entries
        save_named_colors(self._settings, self.entries)
        self._reload_list(select_index)

    def _current_index(self):
        return self.color_list.currentRow()

    def _ask_name_and_color(self, title, name="", color="#1f77b4"):
        """名前と色を尋ねる。(name, color) かキャンセルなら None。"""
        chosen = QColorDialog.getColor(QColor(color), self, tr("色を選択"))
        if not chosen.isValid():
            return None
        text, ok = QInputDialog.getText(
            self, title, tr("登録名"), text=name)
        if not ok:
            return None
        return text, chosen.name()


    def _on_add(self):
        result = self._ask_name_and_color(tr("色を登録"))
        if result is None:
            return
        name, color = result
        try:
            entries = add_named_color(self.entries, name, color)
        except NamedColorError as e:
            QMessageBox.warning(self, tr("色を登録"), str(e))
            return
        self._commit(entries, len(entries) - 1)

    def _on_edit(self):
        index = self._current_index()
        if index < 0:
            QMessageBox.information(self, tr("色名の管理"), tr("編集する登録を選んでください。"))
            return
        current = self.entries[index]
        result = self._ask_name_and_color(
            tr("登録を編集"), current["name"], current["color"])
        if result is None:
            return
        name, color = result
        try:
            entries = update_named_color(self.entries, index, name, color)
        except NamedColorError as e:
            QMessageBox.warning(self, tr("登録を編集"), str(e))
            return
        self._commit(entries, index)

    def _on_delete(self):
        index = self._current_index()
        if index < 0:
            QMessageBox.information(self, tr("色名の管理"), tr("削除する登録を選んでください。"))
            return
        try:
            entries = remove_named_color(self.entries, index)
        except NamedColorError as e:
            QMessageBox.warning(self, tr("色名の管理"), str(e))
            return
        self._commit(entries, min(index, len(entries) - 1))

    def _on_move(self, offset):
        index = self._current_index()
        if index < 0:
            return
        try:
            entries = move_named_color(self.entries, index, offset)
        except NamedColorError:
            return
        new_index = max(0, min(index + offset, len(entries) - 1))
        self._commit(entries, new_index)


class NamedColorPickerDialog(QDialog):
    """登録した色を名前で絞り込んで選ぶ(色欄のポップアップは先頭 POPUP_LIMIT 件しか並べない)。編集はしない。"""

    def __init__(self, settings, parent=None, title=None):
        super().__init__(parent)
        self.setWindowTitle(title or tr("登録色を選択"))
        self.resize(380, 420)
        self.entries = load_named_colors(settings)
        self._selected = None

        layout = QVBoxLayout(self)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("名前または色コードで絞り込み"))
        self.filter_edit.setClearButtonEnabled(True)
        layout.addWidget(self.filter_edit)

        self.color_list = QListWidget()
        self.color_list.setIconSize(QSize(16, 16))
        layout.addWidget(self.color_list, stretch=1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                      QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.filter_edit.textChanged.connect(self._reload_list)
        self.color_list.itemDoubleClicked.connect(lambda _item: self.accept())

        self._reload_list()

    def _reload_list(self, _text=None):
        """名前と色コードの両方で絞り込む。"""
        needle = self.filter_edit.text().strip().lower()
        self.color_list.clear()
        for entry in self.entries:
            if needle and needle not in entry["name"].lower()                     and needle not in entry["color"].lower():
                continue
            item = QListWidgetItem(f'{entry["name"]}    {entry["color"]}')
            item.setIcon(_named_color_icon(entry["color"]))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.color_list.addItem(item)
        if self.color_list.count():
            self.color_list.setCurrentRow(0)

    def accept(self):
        item = self.color_list.currentItem()
        self._selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        super().accept()

    def selected_entry(self):
        """選んだ登録({'name', 'color'})。キャンセルか未選択なら None。"""
        return self._selected


class LegendOrderDialog(QDialog):
    """凡例の並びを、描画順とは別にドラッグで決める。"""

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle("凡例の順序")
        self.resize(320, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("ドラッグして凡例の表示順序を変更できます:"))

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_widget.addItems(labels)
        layout.addWidget(self.list_widget)

        reset_button = QPushButton("描画順にリセット")
        reset_button.clicked.connect(self._on_reset)
        layout.addWidget(reset_button)
        self._original_labels = list(labels)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_reset(self):
        self.list_widget.clear()

    def get_order(self):
        """今の並び。「描画順にリセット」なら空のリスト(描画順に従う)。"""
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]


class ArrowAnnotationDialog(QDialog):
    """矢印の注釈のラベル、形('single' / 'double' / 'bracket')、曲がり具合。"""

    STYLE_SINGLE = "通常(片矢印)"
    STYLE_DOUBLE = "両矢印"
    STYLE_BRACKET = "ブラケット(有意差表示等)"
    STYLES = [STYLE_SINGLE, STYLE_DOUBLE, STYLE_BRACKET]
    _STYLE_KEY_BY_LABEL = {STYLE_SINGLE: "single", STYLE_DOUBLE: "double", STYLE_BRACKET: "bracket"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("矢印注釈の追加")
        self.resize(360, 200)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("ラベル(空欄可):"))
        self.text_edit = QLineEdit()
        layout.addWidget(self.text_edit)

        form = QFormLayout()
        self.style_combo = QComboBox()
        self.style_combo.addItems(self.STYLES)
        form.addRow("矢印の形状", self.style_combo)

        self.curvature_spinbox = QDoubleSpinBox()
        self.curvature_spinbox.setRange(-1.0, 1.0)
        self.curvature_spinbox.setSingleStep(0.05)
        self.curvature_spinbox.setDecimals(2)
        self.curvature_spinbox.setValue(0.0)
        self.curvature_spinbox.setToolTip(
            "0で直線。正/負で曲がる向きが変わります(matplotlibのarc3 rad相当)。"
        )
        form.addRow("曲率", self.curvature_spinbox)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """(ラベル, 形, 曲がり具合)"""
        style_text = self.style_combo.currentText()
        style = self._STYLE_KEY_BY_LABEL[style_text]
        return self.text_edit.text().strip(), style, self.curvature_spinbox.value()


class InsetDialog(QDialog):
    """拡大図の位置(角と大きさ)と、拡大する X の範囲。"""

    CORNERS = ["右上", "左上", "右下", "左下"]

    def __init__(self, x_min, x_max, default_zoom_min, default_zoom_max, parent=None):
        super().__init__(parent)
        self.setWindowTitle("インセット(拡大図)を追加")
        self.resize(380, 260)

        layout = QVBoxLayout(self)
        info_label = QLabel(
            f"データのX範囲: {x_min:.4g} 〜 {x_max:.4g}\n"
            "拡大表示したいX範囲と、インセットを表示する位置を選んでください。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()
        self.zoom_min_spinbox = QDoubleSpinBox()
        self.zoom_min_spinbox.setRange(-1e12, 1e12)
        self.zoom_min_spinbox.setDecimals(4)
        self.zoom_min_spinbox.setValue(default_zoom_min)
        form.addRow("拡大範囲(最小)", self.zoom_min_spinbox)

        self.zoom_max_spinbox = QDoubleSpinBox()
        self.zoom_max_spinbox.setRange(-1e12, 1e12)
        self.zoom_max_spinbox.setDecimals(4)
        self.zoom_max_spinbox.setValue(default_zoom_max)
        form.addRow("拡大範囲(最大)", self.zoom_max_spinbox)

        self.corner_combo = QComboBox()
        self.corner_combo.addItems(self.CORNERS)
        form.addRow("表示位置", self.corner_combo)

        self.size_spinbox = QDoubleSpinBox()
        self.size_spinbox.setRange(0.15, 0.6)
        self.size_spinbox.setSingleStep(0.05)
        self.size_spinbox.setValue(0.35)
        form.addRow("大きさ(軸に対する比率)", self.size_spinbox)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """{'corner', 'size', 'zoom_x_range'(昇順)}"""
        lo = self.zoom_min_spinbox.value()
        hi = self.zoom_max_spinbox.value()
        return {
            'corner': self.corner_combo.currentText(),
            'size': self.size_spinbox.value(),
            'zoom_x_range': (min(lo, hi), max(lo, hi)),
        }
