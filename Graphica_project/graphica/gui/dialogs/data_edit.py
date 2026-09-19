# gui/dialogs/data_edit.py
"""
データの編集・列操作のダイアログ。

gui/dialogs.py(5,560行・47ダイアログ)を機能群ごとに分割したもの
(改善ボード B-2)。呼び出し側は従来どおり `from gui.dialogs import X` で
参照できる(gui/dialogs/__init__.py が再エクスポートしている)。
"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from graphica.gui.theme import apply_form_spacing




#==============================================================================
# カスタムダイアログクラス (5)
#==============================================================================
class ColumnCalculatorDialog(QDialog):
    """
    データエディタの「列の計算」機能で使用するダイアログクラスです。
    出力先（新規または既存）の列名と、safe_eval_column_formula() で実行する
    計算式をユーザーに入力させます。
    """
    
    def __init__(self, column_names, parent=None):
        """
        ダイアログのUIコンポーネントを初期化します。
        
        Args:
            column_names (list[str]): 
                現在の DataFrame に存在する列名のリスト。コンボボックスの選択肢として使用されます。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("列の計算")
        
        self.column_names = column_names
        
        # --- UIコンポーネントの作成 ---
        
        self.output_col_label = QLabel("出力先の列 (既存または新規)")
        
        # --- 出力先コンボボックス ---
        self.output_col_combo = QComboBox()
        self.output_col_combo.addItems(self.column_names) # 既存の列を選択肢に追加
        # ★ setEditable(True) が重要
        # これにより、ユーザーは既存の列を選択するだけでなく、
        # テキストボックスのように新しい列名を自由に入力できます。
        self.output_col_combo.setEditable(True) 
        
        self.formula_label = QLabel("計算式 (例: A + B * 2)")

        # --- 計算式入力欄 ---
        self.formula_edit = QLineEdit()
        # ★ (入力例をプレースホルダーとして表示)
        self.formula_edit.setPlaceholderText("例: (A + B) / 2 や log(C)")

        # --- ヘルプテキスト ---
        help_text = QLabel("列名はそのまま使えます (例: `A`)。\n数値や `log(A)`, `sin(A)` なども利用可能です。")
        help_text.setStyleSheet("font-size: 9pt; color: gray;") # 少し小さく灰色で表示

        # --- プリセット (よく使う計算をボタン一つで挿入) ---
        preset_group = QGroupBox("プリセット (対象列を選んでボタンを押すと計算式が自動入力されます)")
        preset_layout = QVBoxLayout()

        preset_source_row = QHBoxLayout()
        preset_source_row.addWidget(QLabel("対象列"))
        self.preset_source_combo = QComboBox()
        self.preset_source_combo.addItems(self.column_names)
        preset_source_row.addWidget(self.preset_source_combo)
        preset_source_row.addWidget(QLabel("移動平均の窓幅"))
        self.preset_window_spinbox = QSpinBox()
        self.preset_window_spinbox.setRange(2, 100000)
        self.preset_window_spinbox.setValue(5)
        preset_source_row.addWidget(self.preset_window_spinbox)
        preset_layout.addLayout(preset_source_row)

        preset_button_row = QHBoxLayout()
        moving_avg_button = QPushButton("移動平均")
        moving_avg_button.clicked.connect(self._apply_preset_moving_average)
        diff_button = QPushButton("微分(差分)")
        diff_button.clicked.connect(self._apply_preset_diff)
        normalize_button = QPushButton("正規化")
        normalize_button.clicked.connect(self._apply_preset_normalize)
        cumsum_button = QPushButton("累積和")
        cumsum_button.clicked.connect(self._apply_preset_cumsum)
        for btn in (moving_avg_button, diff_button, normalize_button, cumsum_button):
            preset_button_row.addWidget(btn)
        preset_layout.addLayout(preset_button_row)

        preset_group.setLayout(preset_layout)

        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # --- レイアウト ---
        # (このダイアログは QFormLayout ではなく QVBoxLayout (垂直) を使用)
        layout = QVBoxLayout(self)
        layout.addWidget(self.output_col_label)
        layout.addWidget(self.output_col_combo)
        layout.addWidget(self.formula_label)
        layout.addWidget(self.formula_edit)
        layout.addWidget(help_text)
        layout.addWidget(preset_group)
        layout.addWidget(button_box)

    def _apply_preset_moving_average(self):
        """「移動平均」プリセットボタン: 選択列に rolling().mean() の式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        window = self.preset_window_spinbox.value()
        self.formula_edit.setText(f"{col}.rolling({window}).mean()")
        self.output_col_combo.setCurrentText(f"{col}_moving_avg{window}")

    def _apply_preset_diff(self):
        """「微分(差分)」プリセットボタン: 選択列に diff() の式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        self.formula_edit.setText(f"{col}.diff()")
        self.output_col_combo.setCurrentText(f"{col}_diff")

    def _apply_preset_normalize(self):
        """「正規化」プリセットボタン: 選択列を平均0・標準偏差1に正規化する式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        self.formula_edit.setText(f"({col} - {col}.mean()) / {col}.std()")
        self.output_col_combo.setCurrentText(f"{col}_normalized")

    def _apply_preset_cumsum(self):
        """「累積和」プリセットボタン: 選択列に cumsum() の式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        self.formula_edit.setText(f"{col}.cumsum()")
        self.output_col_combo.setCurrentText(f"{col}_cumsum")

    def get_formula(self):
        """
        ダイアログで入力された「出力先列名」と「計算式」をタプルで返します。
        
        Returns:
            tuple (str, str): (出力先列名, 計算式)
        """
        # QComboBox が setEditable(True) の場合、
        # currentText() は、選択されたアイテムまたは入力されたテキストを返します。
        output_column_name = self.output_col_combo.currentText()
        formula_string = self.formula_edit.text()
        
        return output_column_name, formula_string




#==============================================================================
# カスタムダイアログクラス (2)
#==============================================================================
class CalcHelpDialog(QDialog):
    """
    データエディタの「列計算」機能のリファレンスを表示するヘルプダイアログクラスです。
    core/safe_eval.py の safe_eval_column_formula() で使用できる構文について説明します。
    """
    
    def __init__(self, parent=None):
        """
        ダイアログの初期化を行います。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("列計算機能 リファレンス")
        self.resize(600, 700) # ウィンドウサイズを指定

        # メインレイアウト (垂直)
        layout = QVBoxLayout(self)
        
        # HTML表示用のテキストブラウザ
        text_browser = QTextBrowser()
        text_browser.setReadOnly(True)
        # ★ HTML内のリンクをクリックしたときに外部ブラウザで開くように設定
        text_browser.setOpenExternalLinks(True) 
        
        # --- リファレンスの内容をHTMLで定義 ---
        help_html = r"""
        <h1>列計算機能 リファレンス</h1>
        <p>
            計算式を使って、列データをまとめて計算します。
            「出力先の列」に指定した列に、計算式の結果が一度に適用されます（Excelのオートフィルのように、全行に適用されます）。
        </p>
        
        <hr>
        
        <h2>1. 基本的な算術演算子 🧮</h2>
        <p>列名（例: <code>A</code>, <code>B</code>）や数値をそのまま使えます。</p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row"><th>計算式 (入力例)</th><th>実行内容</th></tr>
            <tr><td><code>A + B</code></td><td>A列とB列の各行を足し算します。</td></tr>
            <tr><td><code>A * 100</code></td><td>A列の全データを100倍します。</td></tr>
            <tr><td><code>(A + B) / 2</code></td><td>A列とB列の平均値を計算します。</td></tr>
            <tr><td><code>A ** 2</code></td><td>A列の値を2乗します。</td></tr>
            <tr><td><code>A % 5</code></td><td>A列の値を5で割った余りを計算します。</td></tr>
        </table>
        
        <hr>
        
        <h2>2. 一般的な数学関数 📈</h2>
        <p>
            以下の関数が利用可能です。
        </p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row"><th>関数 (入力例)</th><th>意味</th></tr>
            <tr><td><code>sqrt(A)</code></td><td>Aの平方根 (&radic;A)</td></tr>
            <tr><td><code>log(A)</code></td><td>Aの自然対数 (ln A)</td></tr>
            <tr><td><code>log10(A)</code></td><td>Aの常用対数 (log₁₀ A)</td></tr>
            <tr><td><code>exp(A)</code></td><td>Aの指数関数 (e<sup>A</sup>)</td></tr>
            <tr><td><code>abs(A)</code></td><td>Aの絶対値</td></tr>
            <tr><td><code>sin(A)</code></td><td>Aのサイン (ラジアン)</td></tr>
            <tr><td><code>cos(A)</code></td><td>Aのコサイン (ラジアン)</td></tr>
            <tr><td><code>tan(A)</code></td><td>Aのタンジェント (ラジアン)</td></tr>
        </table>

        <hr>
        
        <h2>3. 比較・論理演算子 🔍</h2>
        <p>
            条件に合うかどうかを <code>True</code> / <code>False</code> で返す新しい列を作成できます。
            複数の条件を組み合わせる場合は <code>and</code>, <code>or</code>, <code>not</code> を使います。
        </p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row"><th>計算式 (入力例)</th><th>実行内容</th></tr>
            <tr><td><code>A > 10</code></td><td>A列の値が10より大きい行はTrueになります。</td></tr>
            <tr><td><code>A == B</code></td><td>A列とB列の値が等しい行はTrueになります。</td></tr>
            <tr><td><code>A > 5 and B < 3</code></td><td>Aが5より大きく、<b>かつ</b> Bが3未満の行だけTrueになります。</td></tr>
            <tr><td><code>A < 0 or A > 10</code></td><td>Aが0未満、<b>または</b> Aが10より大きい行がTrueになります。</td></tr>
            <tr><td><code>not (A > 5)</code></td><td>Aが5より大きい、という条件を否定します (A <= 5 と同じ)。</td></tr>
        </table>
        """
        self._text_browser = text_browser
        self.refresh_theme()
        text_browser.setHtml(help_html)
        # --- HTML定義ここまで ---

        layout.addWidget(text_browser)

        # 閉じるボタン
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def refresh_theme(self):
        """表見出し行の色を現在のテーマトークンに合わせて再適用する
        (詳しい経緯はHelpDialog.refresh_theme参照、同じバグ・同じ対処)。"""
        from graphica.gui import theme
        _tokens = theme.current_tokens()
        self._text_browser.document().setDefaultStyleSheet(
            f"tr.header-row {{ background-color: {_tokens['surface_2']}; "
            f"color: {_tokens['text_primary']}; }}"
        )




#==============================================================================
# カスタムダイアログクラス: 列の分割・結合・数値抽出 (項目C-205)
#==============================================================================
class ColumnStringOpsDialog(QDialog):
    """
    データエディタの「文字列操作...」機能で使用するダイアログ(項目C-205:
    列の分割・結合・文字列操作)。「列の分割」「列の結合」「数値抽出」の
    3モードをコンボボックスで切り替え、モードごとの入力欄をQStackedWidgetで
    表示する(gui/dialogs.pyのResampleDatasetDialogと同じパターン)。
    実際の分割/結合/抽出処理は呼び出し側(gui/data_editor.pyのDataEditorDialog)
    が行う。このダイアログは設定値の入力・受け渡しのみを担う。
    """

    MODE_SPLIT = "列の分割"
    MODE_MERGE = "列の結合"
    MODE_EXTRACT_NUMERIC = "数値抽出"
    MODES = [MODE_SPLIT, MODE_MERGE, MODE_EXTRACT_NUMERIC]

    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文字列操作")
        self.resize(420, 400)
        self.column_names = column_names

        layout = QVBoxLayout(self)

        mode_form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        mode_form.addRow("操作", self.mode_combo)
        layout.addLayout(mode_form)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # --- 列の分割: 1列を区切り文字で複数列に分ける ---
        split_page = QWidget()
        split_form = QFormLayout(split_page)
        self.split_source_combo = QComboBox()
        self.split_source_combo.addItems(column_names)
        split_form.addRow("対象列", self.split_source_combo)
        self.split_delimiter_edit = QLineEdit()
        self.split_delimiter_edit.setPlaceholderText("例: , や _ (空白なら半角スペース)")
        split_form.addRow("区切り文字", self.split_delimiter_edit)
        self.split_prefix_edit = QLineEdit()
        self.split_prefix_edit.setPlaceholderText("例: part (空欄なら対象列名を使用)")
        split_form.addRow("出力列名の接頭辞", self.split_prefix_edit)
        self.stack.addWidget(split_page)

        # --- 列の結合: 複数列を区切り文字でつなげて1列にする ---
        merge_page = QWidget()
        merge_layout = QVBoxLayout(merge_page)
        merge_layout.addWidget(QLabel("結合する列を2つ以上選択してください:"))
        self.merge_column_list = QListWidget()
        for name in column_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.merge_column_list.addItem(item)
        merge_layout.addWidget(self.merge_column_list)
        merge_form = QFormLayout()
        self.merge_separator_edit = QLineEdit()
        self.merge_separator_edit.setPlaceholderText("例: _ (空欄可)")
        merge_form.addRow("区切り文字", self.merge_separator_edit)
        self.merge_output_edit = QLineEdit()
        merge_form.addRow("出力列名", self.merge_output_edit)
        merge_layout.addLayout(merge_form)
        self.stack.addWidget(merge_page)

        # --- 数値抽出: 正規表現で文字列から数値部分を取り出す ---
        extract_page = QWidget()
        extract_form = QFormLayout(extract_page)
        self.extract_source_combo = QComboBox()
        self.extract_source_combo.addItems(column_names)
        extract_form.addRow("対象列", self.extract_source_combo)
        self.extract_pattern_edit = QLineEdit(r'[-+]?\d*\.?\d+')
        extract_form.addRow("正規表現", self.extract_pattern_edit)
        extract_help = QLabel('既定は数値(整数/小数、符号付き)を抽出します。例: "400nm" → 400')
        extract_help.setWordWrap(True)
        extract_help.setStyleSheet("font-size: 9pt; color: gray;")
        extract_form.addRow(extract_help)
        self.extract_output_edit = QLineEdit()
        extract_form.addRow("出力列名", self.extract_output_edit)
        self.stack.addWidget(extract_page)

        self.mode_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_mode(self):
        return self.mode_combo.currentText()

    def get_split_settings(self):
        """Returns: (対象列名, 区切り文字, 出力列名の接頭辞)"""
        return (
            self.split_source_combo.currentText(),
            self.split_delimiter_edit.text(),
            self.split_prefix_edit.text().strip(),
        )

    def get_merge_settings(self):
        """Returns: (選択された列名のリスト, 区切り文字, 出力列名)"""
        selected = []
        for i in range(self.merge_column_list.count()):
            item = self.merge_column_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected, self.merge_separator_edit.text(), self.merge_output_edit.text().strip()

    def get_extract_settings(self):
        """Returns: (対象列名, 正規表現パターン, 出力列名)"""
        return (
            self.extract_source_combo.currentText(),
            self.extract_pattern_edit.text(),
            self.extract_output_edit.text().strip(),
        )




#==============================================================================
# カスタムダイアログクラス: 検索/置換 (項目C-208)
#==============================================================================
class FindReplaceDialog(QDialog):
    """
    データエディタの「検索/置換...」機能で使用する非モーダルダイアログ
    (項目C-208: テーブルの検索・置換・行ジャンプ)。「次を検索」でテーブル上の
    次の一致セルへ移動し、「すべて置換」で一致する全セルの値を置換する。

    実際の検索/置換ロジックは呼び出し側(gui/data_editor.pyのDataEditorDialog、
    _on_find_next/_on_replace_all)が持ち、このダイアログは入力欄・ボタン・
    状態表示ラベルだけを提供する薄いUI。データエディタ側のテーブルを見ながら
    次々に検索できるよう非モーダル(exec()ではなくshow())で使うことを想定する。
    """

    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("検索/置換")
        # 常にデータエディタの上に浮かぶツールウィンドウにする(非モーダルのため、
        # 裏に隠れて操作できなくなるのを防ぐ)。
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(340, 200)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.search_edit = QLineEdit()
        form.addRow("検索文字列", self.search_edit)
        self.replace_edit = QLineEdit()
        form.addRow("置換後の文字列", self.replace_edit)
        self.column_combo = QComboBox()
        self.column_combo.addItem("(すべての列)")
        self.column_combo.addItems(column_names)
        form.addRow("対象列", self.column_combo)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        self.find_next_button = QPushButton("次を検索")
        self.replace_all_button = QPushButton("すべて置換")
        button_row.addWidget(self.find_next_button)
        button_row.addWidget(self.replace_all_button)
        button_row.addStretch()
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        apply_form_spacing(self)

    def get_search_text(self):
        return self.search_edit.text()

    def get_replace_text(self):
        return self.replace_edit.text()

    def get_target_column(self):
        """選択中の対象列名、「(すべての列)」ならNoneを返す"""
        text = self.column_combo.currentText()
        return None if text == "(すべての列)" else text

    def set_status(self, text):
        self.status_label.setText(text)




#==============================================================================
# カスタムダイアログクラス: 行フィルタ(項目C-204)
#==============================================================================
class RowFilterDialog(QDialog):
    """
    条件式(例: "y > 0.5")を満たさない行をマスク(項目36、非破壊)する
    ダイアログ。ColumnCalculatorDialogと同じ`core/safe_eval.py`の
    safe_eval_column_formula()をそのまま使う(列名を裸の識別子として
    参照する、比較/論理演算子が使える、という同じ規約)。
    """

    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("行フィルタ")
        self.resize(440, 240)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("条件式を満たさない行をマスク(除外)します(非破壊、いつでも解除できます)。"))

        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("例: y > 0.5 や (x > 0) and (y < 100)")
        layout.addWidget(self.formula_edit)

        help_text = QLabel(
            "列名はそのまま使えます(例: y)。比較演算子(>, <, ==, != 等)や\n"
            "and / or / not が使えます(core/safe_eval.pyの安全な数式評価器)。"
        )
        help_text.setStyleSheet("font-size: 9pt; color: gray;")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        if column_names:
            columns_label = QLabel("利用可能な列: " + ", ".join(str(c) for c in column_names))
            columns_label.setWordWrap(True)
            columns_label.setStyleSheet("font-size: 9pt; color: gray;")
            layout.addWidget(columns_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_formula(self):
        return self.formula_edit.text().strip()




#==============================================================================
# カスタムダイアログクラス: 列の表示/非表示 (項目C-207)
#==============================================================================
class ColumnVisibilityDialog(QDialog):
    """
    データエディタの「列の表示/非表示...」機能で使用するダイアログ(項目C-207)。
    チェックを外した列は、テーブル上でのみ非表示になる(dataset.df自体は
    変更しない、ソート状態と同じ「ビュー専用」の状態)。
    """

    def __init__(self, column_names, hidden_columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列の表示/非表示")
        self.resize(280, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("表示する列にチェックを入れてください:"))

        self.column_list = QListWidget()
        for name in column_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = Qt.CheckState.Unchecked if name in hidden_columns else Qt.CheckState.Checked
            item.setCheckState(state)
            self.column_list.addItem(item)
        layout.addWidget(self.column_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_hidden_columns(self):
        """チェックが外された(非表示にする)列名のリストを返す"""
        hidden = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.CheckState.Unchecked:
                hidden.append(item.text())
        return hidden




#==============================================================================
# カスタムダイアログクラス: 重複X値の検出(項目C-203)
#==============================================================================
class DuplicateXDialog(QDialog):
    """
    同じX値を持つ行の処理方法(平均化/除去)を選ばせるダイアログ。
    「平均化」は新しいデータセットを作る(_on_cumulative_integral_dataset等と
    同じ「カレント1件から新しいデータセットを1つ作る」パターン)、「除去」は
    先頭以外をマスク(項目36、非破壊)する。ResampleDatasetDialogと同じく
    モードごとの入力欄をQStackedWidgetで切り替える。
    """

    MODE_AVERAGE = "平均化(新しいデータセットを作成)"
    MODE_REMOVE = "除去(先頭以外をマスク)"
    MODES = [MODE_AVERAGE, MODE_REMOVE]

    def __init__(self, name, n_duplicate_rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("重複X値の検出")
        self.resize(420, 240)
        self._name = name

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))
        layout.addWidget(QLabel(f"重複するX値を持つ行: {n_duplicate_rows}件"))

        form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        form.addRow("処理方法", self.mode_combo)
        layout.addLayout(form)

        self.stack = QStackedWidget()

        average_page = QWidget()
        average_form = QFormLayout(average_page)
        self.output_name_edit = QLineEdit(f"{name}_averaged")
        average_form.addRow("出力データセット名", self.output_name_edit)
        self.stack.addWidget(average_page)

        remove_page = QWidget()
        remove_form = QFormLayout(remove_page)
        remove_note = QLabel("同じX値のうち最初に出現した行だけを残し、残りをマスク(除外)します。")
        remove_note.setWordWrap(True)
        remove_form.addRow(remove_note)
        self.stack.addWidget(remove_page)

        layout.addWidget(self.stack)
        self.mode_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (str, str): (処理方法("average"|"remove"), 出力データセット名
                ("remove"モードでは無視される))
        """
        mode = "average" if self.mode_combo.currentText() == self.MODE_AVERAGE else "remove"
        return mode, self.output_name_edit.text().strip()




#==============================================================================
# カスタムダイアログクラス (9)
#==============================================================================
class ReplicateErrorDialog(QDialog):
    """
    同一条件で複数回測定した列 (反復測定列) から、行ごとの平均と誤差
    (標準偏差/標準誤差/95%信頼区間) を自動計算するための列を選ばせるダイアログ。
    データエディタの「誤差の自動計算...」ボタンから使われる。
    """

    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("誤差の自動計算 (反復測定)")
        self.resize(360, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("反復測定として扱う列を2つ以上選んでください:"))

        self.column_list = QListWidget()
        self.column_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for name in column_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.column_list.addItem(item)
        layout.addWidget(self.column_list)

        form = QFormLayout()
        self.stat_combo = QComboBox()
        self.stat_combo.addItems(["SD (標準偏差)", "SEM (標準誤差)", "95%CI (信頼区間)"])
        form.addRow("誤差の種類", self.stat_combo)

        self.base_name_edit = QLineEdit("measurement")
        form.addRow("出力列名 (ベース)", self.base_name_edit)
        layout.addLayout(form)

        info_label = QLabel(
            "「平均」列と「誤差」列の2つが追加されます (例: measurement_mean, measurement_SD)。"
            "NaNを含む行は、その行にある有効な測定値だけで計算します。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (list[str], str, str): (選択された列名のリスト,
                誤差の種類 ('SD'/'SEM'/'95%CI'), 出力列名のベース名)
        """
        selected = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        stat_type = self.stat_combo.currentText().split(" ")[0]  # "SD (標準偏差)" -> "SD"
        return selected, stat_type, self.base_name_edit.text().strip()
