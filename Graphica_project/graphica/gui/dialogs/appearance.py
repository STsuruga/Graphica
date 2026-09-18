# gui/dialogs/appearance.py
"""
見た目・注釈のダイアログ。

gui/dialogs.py(5,560行・47ダイアログ)を機能群ごとに分割したもの
(改善ボード B-2)。呼び出し側は従来どおり `from gui.dialogs import X` で
参照できる(gui/dialogs/__init__.py が再エクスポートしている)。
"""

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
from gui import icon_utils
from gui.theme import apply_form_spacing
from gui.mathtext_preview import FitWidthPixmapLabel
from core.i18n import tr
from core.color_palettes import BUILTIN_PALETTES
from core.named_colors import (
    NamedColorError,
    add_named_color,
    load_named_colors,
    move_named_color,
    remove_named_color,
    save_named_colors,
    update_named_color,
)




#==============================================================================
# カスタムダイアログクラス: タイトル/軸ラベルの編集(項目H-2-4追加分)
#==============================================================================
class LabelEditDialog(QDialog):
    """
    タイトル/X軸ラベル/Y軸ラベルを編集するためのポップアップダイアログ。

    以前はプロパティパネルのQLineEdit直下に小さな「Aa」ボタンを置き、押すと
    文字装飾(太字/イタリック/上付き/下付き)とギリシャ文字/記号パレットを
    ネストしたQMenuとして開いていたが、実機フィードバック(レイアウト画像の
    提示)を受けて、独立したポップアップウィンドウ形式に変更した。装飾ボタンを
    ネストしたメニューの中に隠さず、テキスト入力欄のすぐ下に横一列で常に
    見えるようにし、データセット操作ボタン列と同じ意匠
    (`QPushButton[iconOnly="true"]`)の正方形アイコンボタンにしている。

    書式適用のロジック(選択範囲をmathtextで包む/カーソル位置に記号を挿入する)
    自体は、以前 gui/mixins/settings_mixin.py 側にあった
    `_apply_label_mathtext_format`/`_on_label_symbol_clicked` と同じ考え方を、
    このダイアログの内部QLineEdit(`self.text_edit`)に対して直接行う形に
    移植している(ダイアログが受け持つのは自分自身が持つ1つの入力欄だけなので、
    以前のfield_keyディクショナリ経由の間接参照は不要になった)。
    """

    def __init__(self, initial_text, window_title, symbol_palette, parent=None):
        """
        Args:
            initial_text (str): 編集対象のQLineEditが現在持っているテキスト。
            window_title (str): ダイアログのタイトルバーに出す文字列
                (例: 「タイトルを編集」)。
            symbol_palette (list[tuple[str, str]]): (表示グリフ, mathtextマクロ名)
                のペアのリスト。呼び出し側(gui/main_window.py)の
                LABEL_SYMBOL_PALETTEをそのまま渡す想定(dialogs.py は
                main_window.py を逆import できないため、呼び出し側から渡す)。
            parent (QWidget, optional): 親ウィジェット。
        """
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

        # ★ 実機フィードバック: 「ボタンを押してmathtext形式で書かれたラベルが
        #   出力されるんじゃなくて実際にボールドとかイタリックとかが適用
        #   されてるテキストが見れるようにしたい」。text_edit自体はQLineEdit
        #   なので部分的なリッチテキスト表示はできない(生のmathtext構文の
        #   ままにせざるを得ない)。代わりに、実際の描画結果をレンダリングする
        #   プレビュー欄をtext_editの下に常設し、太字/イタリック等を適用する
        #   たびに実際に適用された見た目を確認できるようにする(タイトル/
        #   軸ラベル欄本体のプレビュー、gui/mathtext_preview.pyを流用)。
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
            # ★ 実機フィードバック(バグ報告、下記参照): この装飾ボタンが
            #   フォーカスを奪わないようにするための本質的な修正。
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button_row.addWidget(button)
            return button

        bold_button = _make_icon_button("bold", "太字")
        italic_button = _make_icon_button("italic", "イタリック")
        superscript_button = _make_icon_button("superscript", "上付き文字")
        subscript_button = _make_icon_button("subscript", "下付き文字")

        # ★ 実機フィードバック(バグ報告): 「文字選択してハイライトされてから
        #   ボタン押しても文字を選択してって出る」。
        #   当初は「QPushButton.clickedはマウスの押下→解放が完了した後に発火
        #   するため、pressed(押下の瞬間)で選択範囲を保存しておけば間に合う」
        #   という仮説で対処したが、実際にQTest.mouseClick()で実クリックを
        #   再現したところ、pressedが発火する時点で既にtext_edit.
        #   hasSelectedText()がFalseになっており、直っていなかったことが判明。
        #   真因は「clickedが遅い」ことではなく、QAbstractButton系ウィジェットの
        #   既定フォーカスポリシー(StrongFocus)により、Qtがマウス押下イベントを
        #   ボタンへ配送する"前"にフォーカスをボタン側へ移してしまい、その
        #   フォーカスアウトでQLineEdit側の選択状態が失われてしまうこと
        #   (この経路はボタン自身のpressed/clickedシグナルより早く走るため、
        #   pressedで捕捉しても既に手遅れ)。
        #   本質的な修正は、これらの装飾ボタンにフォーカスを一切渡さないこと
        #   (上の_make_icon_button内でsetFocusPolicy(Qt.NoFocus)を設定)。
        #   これによりボタンをクリックしてもtext_edit側のフォーカス・選択状態が
        #   維持されたまま保たれる。pressedでの事前捕捉ロジック自体は無害かつ
        #   (フォーカスが移らない環境が万一あった場合の)保険として残す。
        self._pending_selection = None  # (start, selected_text) または選択なしならNone
        self._pending_cursor = 0

        for button in (bold_button, italic_button, superscript_button, subscript_button):
            button.pressed.connect(self._capture_pending_selection)

        # ★ 実機フィードバック(バグ報告): 「mathtextを複数適用しようとすると
        #   (例: イタリック+ボールド、上付き+ボールド)バグる」。
        #   kind引数の意味とバグの詳細は_apply_wrap()のdocstring参照。
        bold_button.clicked.connect(lambda: self._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}"))
        italic_button.clicked.connect(lambda: self._apply_wrap("italic", lambda s: f"\\mathit{{{s}}}"))
        superscript_button.clicked.connect(lambda: self._apply_wrap("super", lambda s: f"{{}}^{{{s}}}"))
        subscript_button.clicked.connect(lambda: self._apply_wrap("sub", lambda s: f"{{}}_{{{s}}}"))

        # ★ 項目81(mathtext拡充)のギリシャ文字/記号パレットは、以前と同じく
        #   小さなグリッドパネルをQMenuに埋め込む形のポップオーバーとして残す
        #   (32個の記号を常時ボタン表示すると場所を取りすぎるため、ここだけは
        #   ドロップダウン形式が妥当と判断した)。
        symbol_button = QToolButton()
        symbol_button.setText("Ω")
        symbol_button.setToolTip("ギリシャ文字・数学記号を挿入")
        symbol_button.setProperty("iconOnly", True)
        symbol_button.setFixedSize(28, 28)
        symbol_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # QToolButtonは既定でNoFocus(QPushButtonと異なりStrongFocusではない)
        # だが、上の装飾ボタンと同じ理由により明示的に指定しておく。
        symbol_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # ★ 上と同じ理由(ポップアップを開く動作自体でQLineEditの選択範囲が
        #   失われうる)で、メニューが開く前のpressedで選択範囲を確定させる。
        symbol_button.pressed.connect(self._capture_pending_selection)

        symbol_menu = QMenu(symbol_button)
        symbol_panel = QWidget()
        symbol_grid = QGridLayout(symbol_panel)
        symbol_grid.setContentsMargins(6, 6, 6, 6)
        symbol_grid.setSpacing(2)
        # ★ 実機フィードバック: 「ここの文字をもう少し大きくしてほしい」。
        #   既定のUIフォントサイズのままだとグリフが小さく判読しづらいため、
        #   このパレット内のボタンだけ明示的に大きくする。
        symbol_font = QFont(self.font())
        symbol_font.setPointSize(symbol_font.pointSize() + 4)
        for index, (glyph, macro) in enumerate(symbol_palette):
            item_button = QToolButton()
            item_button.setText(glyph)
            item_button.setFont(symbol_font)
            # macro=Noneは「mathtextマクロを持たない生の文字」を表す
            # (例: マイナス記号U+2212)。ツールチップもそれに合わせて分岐する。
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
        """
        text_editの現在の内容を実際にレンダリングし、preview_labelへ反映する。
        タイトル/軸ラベル欄本体のライブプレビュー(gui/mixins/settings_mixin.py
        の_refresh_label_preview)と同じ考え方・同じレンダラ(gui/
        mathtext_preview.py)を、このダイアログ内のtext_edit用に流用している。
        """
        from gui import theme
        from gui.mathtext_preview import render_mathtext_to_pixmap

        tokens = theme.current_tokens()
        text = self.text_edit.text()
        color = tokens["text_primary"] if text else tokens["text_muted"]
        pixmap = render_mathtext_to_pixmap(text if text else " ", color=color, fontsize=15)
        # ★ 実機フィードバック: 「ここの文字サイズを枠内に収まるようにして」。
        #   set_natural_pixmap()がpreview_label自身の実際の幅に合わせて
        #   自動的に縮小する(FitWidthPixmapLabel、gui/mathtext_preview.py参照)。
        self.preview_label.set_natural_pixmap(pixmap)

    def _capture_pending_selection(self):
        """
        装飾/記号ボタンが「押された瞬間」(pressed)に呼ばれ、その時点の
        text_editの選択範囲を_pending_selectionへ保存しておく。ボタンの
        clicked(マウス押下→解放が完了した後に発火)まで待つと、その間に
        フォーカスがボタン側へ移り、QLineEditの選択範囲が失われてしまう
        環境があるため(実機で報告されたバグ)、フォーカスがまだtext_editに
        残っているpressedの時点で確定させる。
        """
        if self.text_edit.hasSelectedText():
            self._pending_selection = (
                self.text_edit.selectionStart(), self.text_edit.selectedText()
            )
        else:
            self._pending_selection = None
        self._pending_cursor = self.text_edit.cursorPosition()

    # 既に$...$で囲まれた1個のmathtext断片全体(ちょうど直前の装飾操作の結果)が
    # 選択されているかどうかを判定するための正規表現群。_apply_wrap()参照。
    _MATH_SPAN_RE = re.compile(r'^\$(.*)\$$', re.DOTALL)
    _MATHBF_RE = re.compile(r'^\\mathbf\{(.*)\}$', re.DOTALL)
    _MATHIT_RE = re.compile(r'^\\mathit\{(.*)\}$', re.DOTALL)
    _BOLDSYMBOL_RE = re.compile(r'^\\boldsymbol\{(.*)\}$', re.DOTALL)
    _SUPER_RE = re.compile(r'^\{\}\^\{(.*)\}$', re.DOTALL)
    _SUB_RE = re.compile(r'^\{\}_\{(.*)\}$', re.DOTALL)

    def _apply_wrap(self, kind, wrap_fn):
        """
        太字/イタリック/上付き/下付きボタン共通の処理。pressed時点で確定させた
        _pending_selection(選択範囲が失われる前に保存したもの、__init__の
        _capture_pending_selection参照)を使い、選択されていた文字列を
        wrap_fn()が返すmathtextの中身(前後の$は含まない)で置き換え、
        改めて$...$で囲む。

        Args:
            kind (str): "bold"/"italic"/"super"/"sub"のいずれか。
                "bold"/"italic"の組み合わせ検出にのみ使う。
            wrap_fn (callable): 中身の文字列を受け取り、装飾後の中身
                (前後の$は含まない断片、例: "\\mathbf{...}")を返す関数。

        ★ 実機フィードバック(バグ報告): 「mathtextを複数適用しようとすると
        (例: イタリック+ボールド、上付き+ボールド)バグる」。
        このダイアログは各装飾操作の後、置き換えた範囲を丸ごと選択状態にする
        (末尾のsetSelection参照)ため、続けて別の装飾ボタンを押すと、選択
        文字列は既に"$\\mathbf{wavelength}$"のような、前後を$で囲まれた
        1個のmathtext断片になっている。これに気づかず単純にwrap_fn()の結果を
        新しい$...$でさらに包んでいたため、"$\\mathit{$\\mathbf{wavelength}$}$"
        のように$が入れ子になった不正なmathtext構文になっていた。
        対策として、選択文字列が既に$...$で囲まれた単一の断片であれば、まず
        中身(内側の$無し部分)だけを取り出してから改めて$...$で囲み直す。

        さらに、太字(\\mathbf)とイタリック(\\mathit)は共にmatplotlib
        mathtextの「フォントクラス」指定であり、$\\mathit{\\mathbf{x}}$の
        ように入れ子にしても内側の指定で上書きされるだけで実際には合成
        されない(実機検証済み)。太字とイタリックを組み合わせようとしている
        場合(既存の中身が\\mathbf{...}でこれからイタリックを適用する、また
        はその逆)は、代わりに太字とイタリックを同時に表現できる
        \\boldsymbol{...}に置き換える。

        ★ 実機フィードバック(バグ報告): 「文字スタイルが異常な重ねがけ出来る」。
        装飾ボタンは各操作後、置き換えた範囲全体を選択状態に戻すため
        (末尾のsetSelection参照)、同じボタンを連打すると
        \\mathbf{\\mathbf{\\mathbf{x}}}のように無意味な入れ子が際限なく
        積み重なっていた。同じ種類の装飾が既に外側にかかっている場合は、
        再度押すとトグルオフ(その装飾だけを剥がす)するようにする。
        剥がした結果が装飾を一切含まない生のテキストに戻る場合は、
        $...$自体も外す(mathtext内の裸の文字はデフォルトで斜体表示される
        ため、$で囲んだままだと「無装飾のはずが斜体に見える」という別の
        見た目のズレを生むため)。異なる種類の装飾同士(太字+イタリック→
        \\boldsymbol、太字+上付き/下付きの入れ子等)は従来通り重ねがけできる。
        """
        if not self._pending_selection:
            # ★ 実機フィードバック: 「文字選択されてないときにポップアップ
            #   ウィンドウ出るけどウィンドウ出さないで、ただ変更を適用しない
            #   だけでいい」。案内ダイアログは出さず、単に何もしない。
            return
        start, selected = self._pending_selection
        span_match = self._MATH_SPAN_RE.match(selected)
        inner = span_match.group(1) if span_match else selected

        combined = None
        if kind == "bold":
            m = self._BOLDSYMBOL_RE.match(inner)
            if m:
                combined = f"\\mathit{{{m.group(1)}}}"  # 太字だけトグルオフ、イタリックは残す
            else:
                m = self._MATHIT_RE.match(inner)
                if m:
                    combined = f"\\boldsymbol{{{m.group(1)}}}"
                else:
                    m = self._MATHBF_RE.match(inner)
                    if m:
                        combined = m.group(1)  # 太字のみ → トグルオフ
        elif kind == "italic":
            m = self._BOLDSYMBOL_RE.match(inner)
            if m:
                combined = f"\\mathbf{{{m.group(1)}}}"  # イタリックだけトグルオフ、太字は残す
            else:
                m = self._MATHBF_RE.match(inner)
                if m:
                    combined = f"\\boldsymbol{{{m.group(1)}}}"
                else:
                    m = self._MATHIT_RE.match(inner)
                    if m:
                        combined = m.group(1)  # イタリックのみ → トグルオフ
        elif kind == "super":
            m = self._SUPER_RE.match(inner)
            if m:
                combined = m.group(1)  # 上付きをトグルオフ
        elif kind == "sub":
            m = self._SUB_RE.match(inner)
            if m:
                combined = m.group(1)  # 下付きをトグルオフ

        new_inner = combined if combined is not None else wrap_fn(inner)
        if re.search(r'[\\^_{}]', new_inner):
            replacement = f"${new_inner}$"
        else:
            # 装飾を全てトグルオフし尽くして生のテキストに戻った場合は、
            # $...$自体も外して元の見た目(斜体化されない通常表示)に戻す。
            replacement = new_inner
        text = self.text_edit.text()
        self.text_edit.setText(text[:start] + replacement + text[start + len(selected):])
        self.text_edit.setSelection(start, len(replacement))

    def _insert_symbol(self, glyph, macro):
        """
        ギリシャ文字/記号パレットの1項目が選ばれたときの処理。装飾ボタンと
        異なり、選択文字列を装飾するのではなく新しい断片を挿入するものなので、
        pressed時点の選択範囲(_pending_selection)があればそれを置き換え、
        無ければpressed時点のカーソル位置(_pending_cursor)に挿入する。

        macroがNone(例: マイナス記号)の場合は、mathtextマクロを持たない
        生の文字そのものなので$...$では包まず、glyphをそのまま挿入する
        (mathtext内の裸の文字はデフォルトで斜体表示されてしまうため)。
        """
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
    """
    「自動配色」ボタンで使うカラーサイクル(パレット)を、ユーザーが複数
    定義・保存・切り替えできるようにするダイアログ。
    「Matplotlib既定」と、組み込みの論文向けパレット(項目141、C-804、
    core/color_palettes.BUILTIN_PALETTES)は常に選べる読み取り専用として扱う。
    """

    DEFAULT_PALETTE_NAME = "Matplotlib既定"

    def __init__(self, palettes: dict, active_name: str, parent=None):
        """
        Args:
            palettes (dict[str, list[str]]): パレット名 -> 16進カラーコードのリスト。
            active_name (str): 現在アクティブなパレット名 (初期選択に使う)。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("配色パレットの管理")
        self.resize(420, 440)

        # 呼び出し側の辞書を直接変更しない (Cancel時に元の状態を保つため)
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

        # ★ 組み込みパレット(Okabe-Ito 等)も初期選択の対象にする。以前は
        #   利用者が作ったパレットだけを見ていたため、組み込みパレットを有効に
        #   してから開き直すと表示が「Matplotlib既定」に戻っていた(実際の配色は
        #   組み込みパレットのまま)。そのまま OK を押すと既定に上書きされていた。
        if active_name in self.palettes or active_name in BUILTIN_PALETTES:
            self.palette_combo.setCurrentText(active_name)
        else:
            self.palette_combo.setCurrentText(self.DEFAULT_PALETTE_NAME)
        self._refresh_color_list()
        self._update_button_states()

    def _is_default_selected(self):
        return self._is_readonly_palette(self.palette_combo.currentText())

    def _is_readonly_palette(self, name):
        """「Matplotlib既定」または組み込みパレット(BUILTIN_PALETTES)かどうか。
        いずれもユーザーによる編集(名前変更・削除・色の追加/削除)の対象外。"""
        return name == self.DEFAULT_PALETTE_NAME or name in BUILTIN_PALETTES

    def _update_button_states(self):
        # 既定パレットは読み取り専用 (名前変更・削除・色の追加/削除は不可)
        editable = not self._is_default_selected()
        self.rename_palette_button.setEnabled(editable)
        self.delete_palette_button.setEnabled(editable)
        self.add_color_button.setEnabled(editable)
        self.remove_color_button.setEnabled(editable)

    def _refresh_color_list(self):
        # ★ 項目H-2-6(実機での目視確認で発覚): 以前はQListWidgetItem.
        #   setBackground()/setForeground()で行全体を色のパレットで塗り、
        #   明るさに応じて文字色を白/黒に切り替えることで常に読めるように
        #   していた。ところがQSSで::item(padding指定のみ)に何かひとつでも
        #   プロパティを当てると、Qtはそのサブコントロールを「スタイル
        #   シートでカスタム描画されるもの」とみなし、setBackground()/
        #   setForeground()で設定したBackgroundRole/ForegroundRoleを描画時に
        #   無視するようになる(本コードベースで既に複数回踏んでいる既知の
        #   Qt/QSSの癖、QTabBar::close-buttonのアイコン消失やチェックボックスの
        #   チェックマーク消失と同じ原因)。結果として実機では常にリストの
        #   地の色(surfaceトークン)がそのまま描画され、明るい色(例: 青・緑)は
        #   白文字と、暗い背景では逆に暗い色(黒文字)の行が、それぞれ
        #   ほぼ同化して読めなくなっていた。
        #   対策として、行の描画をQSSに委ねず、setItemWidget()で小さな
        #   スウォッチ(色見本)+通常のテーマ文字色のテキストラベルという
        #   専用ウィジェットに置き換えた(ColorPickerWidgetのスウォッチと
        #   同じ意匠)。テキストが常にテーマの通常文字色で描画されるため、
        #   スウォッチの色がどんな明るさでも可読性が保たれる。
        self.color_list.clear()
        name = self.palette_combo.currentText()
        if name == self.DEFAULT_PALETTE_NAME:
            colors = list(mpl.rcParams['axes.prop_cycle'].by_key()['color'])
        elif name in BUILTIN_PALETTES:
            colors = BUILTIN_PALETTES[name]
        else:
            colors = self.palettes.get(name, [])
        from gui import theme
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
        self.palette_combo.removeItem(self.palette_combo.currentIndex())  # 既定パレットに自動的に切り替わる

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
        """
        (パレット辞書, アクティブにするパレット名) のタプルを返す。
        QSettingsへの実際の保存は呼び出し側が行う。
        """
        return self.palettes, self.palette_combo.currentText()




def _named_color_icon(color_name, size=16):
    """リスト行の先頭に出す色見本(色欄のポップアップと同じ見た目に揃える)。"""
    from gui.color_picker_widget import _color_icon
    return _color_icon(color_name, size=size)




class NamedColorManagerDialog(QDialog):
    """
    「よく使う色」を名前付きで登録・管理するダイアログ。

    ★ ColorPaletteDialog(配色パレット)とは目的が違う。あちらは「系列に順番に
    割り当てるための色のサイクル」で、こちらは「1つの名前に1つの色」。
    同じ物質・同じ試料を、別のプロジェクトや別の図でも同じ色で描くための登録簿
    (詳細は core/named_colors.py の docstring)。

    編集結果は OK を待たずその場で QSettings へ保存する。ここでの操作は
    「登録簿を育てる」行為であって、プロットの見た目を変えるものではないため、
    Cancel で巻き戻せる必要が薄い(パレット管理側は「どのパレットをアクティブに
    するか」という選択を伴うため OK/Cancel を持つ、という違い)。
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

    # --- 表示 ---

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
        """
        名前と色をまとめて聞く小さなダイアログ。色は QColorDialog を使う
        (このアプリの他の色選択と同じ入口に揃えるため)。
        戻り値は (name, color) か、キャンセル時は None。
        """
        chosen = QColorDialog.getColor(QColor(color), self, tr("色を選択"))
        if not chosen.isValid():
            return None
        text, ok = QInputDialog.getText(
            self, title, tr("登録名"), text=name)
        if not ok:
            return None
        return text, chosen.name()

    # --- 操作 ---

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




#==============================================================================
# カスタムダイアログクラス (8)
#==============================================================================
class NamedColorPickerDialog(QDialog):
    """
    登録済みの色を、名前で絞り込みながら選ぶダイアログ。

    色欄のポップアップメニューには先頭 POPUP_LIMIT 件しか並べない(登録は
    際限なく増やせるので、全件並べるとメニューが縦に伸び続ける)。溢れたぶんは
    ここから選ぶ。編集はしない — 追加/削除/並べ替えは NamedColorManagerDialog の
    担当で、こちらは「選ぶ」だけに徹する。
    """

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
        """絞り込みを反映して一覧を作り直す。名前と色コードの両方を対象にする。"""
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
        # 絞り込みで0件になっている状態のOKは、選択が無いので何も返さず閉じる
        self._selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        super().accept()

    def selected_entry(self):
        """選ばれた登録({'name','color'})。キャンセル/未選択なら None。"""
        return self._selected




#==============================================================================
# カスタムダイアログクラス: 凡例の表示順序
#==============================================================================
class LegendOrderDialog(QDialog):
    """
    凡例の表示順序を、データセットの描画順とは独立にドラッグで並べ替えるためのダイアログ。
    QListWidget の InternalMove ドラッグ&ドロップをそのまま順序編集に使う。
    """

    def __init__(self, labels, parent=None):
        """
        Args:
            labels (list[str]): 現在の軸の凡例ラベル(既存の並び順、または
                以前保存した並び順)を並べたリスト。
            parent (QWidget, optional): 親ウィジェット。
        """
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
        """凡例をカスタム順ではなく、常にデータセットの描画順で表示するようにリセットする"""
        self.list_widget.clear()

    def get_order(self):
        """
        現在のリスト順を返す。「描画順にリセット」が押された場合は空リスト
        (=カスタム順を使わず、常に描画順に従う)を返す。
        """
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]




#==============================================================================
# カスタムダイアログクラス: 矢印注釈の追加(項目C-703)
#==============================================================================
class ArrowAnnotationDialog(QDialog):
    """
    矢印注釈の追加(gui/mixins/annotation_mixin.pyのドラッグ操作から呼ばれる)。
    ラベルテキストに加え、矢印の形状(通常/両矢印/ブラケット)と曲率を選べる
    (項目C-703: 矢印のバリエーション拡張)。既定は形状'single'・曲率0.0で、
    追加前の唯一の挙動(直線の片矢印、QInputDialog.getTextでラベルだけ聞く形)
    と同じ結果になる。
    """

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
        """
        Returns:
            tuple (str, str, float): (ラベルテキスト, 矢印の形状
                ("single"|"double"|"bracket")、曲率)
        """
        style_text = self.style_combo.currentText()
        style = self._STYLE_KEY_BY_LABEL[style_text]
        return self.text_edit.text().strip(), style, self.curvature_spinbox.value()




#==============================================================================
# カスタムダイアログクラス: インセット(拡大図、項目138、C-711)
#==============================================================================
class InsetDialog(QDialog):
    """
    インセット(拡大図)+拡大範囲の指示線の設定ダイアログ。
    #37自由配置のドラッグ基盤の流用は見送り(既存5モードのマウス排他機構に
    7つ目を組み込むリスクに見合わないと判断)、コーナー位置+サイズの
    プリセット選択で位置を決める簡略版。拡大するX範囲は数値で直接指定する。
    """

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
        """
        Returns:
            dict: {'corner': str, 'size': float, 'zoom_x_range': (float, float)}
                (zoom_x_rangeは常に昇順(min, max)で返す)
        """
        lo = self.zoom_min_spinbox.value()
        hi = self.zoom_max_spinbox.value()
        return {
            'corner': self.corner_combo.currentText(),
            'size': self.size_spinbox.value(),
            'zoom_x_range': (min(lo, hi), max(lo, hi)),
        }
