"""データの編集と列の操作のダイアログ。呼び出し側は `from graphica.gui.dialogs import X` で参照する。"""

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
from graphica.core.safe_eval import column_reference
from graphica.gui.theme import apply_form_spacing


class ColumnCalculatorDialog(QDialog):
    """列の計算の出力先の列と式(式は safe_eval_column_formula で評価する)。"""
    
    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列の計算")
        
        self.column_names = column_names


        self.output_col_label = QLabel("出力先の列 (既存または新規)")
        
        self.output_col_combo = QComboBox()
        self.output_col_combo.addItems(self.column_names)
        # 新しい列名も打ち込めるように
        self.output_col_combo.setEditable(True) 
        
        self.formula_label = QLabel("計算式 (例: A + B * 2)")

        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("例: (A + B) / 2 や log(C)")

        help_text = QLabel("列名はそのまま使えます (例: `A`)。\n数値や `log(A)`, `sin(A)` なども利用可能です。")
        help_text.setStyleSheet("font-size: 9pt; color: gray;")

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

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.output_col_label)
        layout.addWidget(self.output_col_combo)
        layout.addWidget(self.formula_label)
        layout.addWidget(self.formula_edit)
        layout.addWidget(help_text)
        layout.addWidget(preset_group)
        layout.addWidget(button_box)

    def _apply_preset_moving_average(self):
        name = self.preset_source_combo.currentText()
        if not name:
            return
        col = column_reference(name)
        window = self.preset_window_spinbox.value()
        self.formula_edit.setText(f"{col}.rolling({window}).mean()")
        self.output_col_combo.setCurrentText(f"{name}_moving_avg{window}")

    def _apply_preset_diff(self):
        name = self.preset_source_combo.currentText()
        if not name:
            return
        col = column_reference(name)
        self.formula_edit.setText(f"{col}.diff()")
        self.output_col_combo.setCurrentText(f"{name}_diff")

    def _apply_preset_normalize(self):
        """平均0・標準偏差1にする式。"""
        name = self.preset_source_combo.currentText()
        if not name:
            return
        col = column_reference(name)
        self.formula_edit.setText(f"({col} - {col}.mean()) / {col}.std()")
        self.output_col_combo.setCurrentText(f"{name}_normalized")

    def _apply_preset_cumsum(self):
        name = self.preset_source_combo.currentText()
        if not name:
            return
        col = column_reference(name)
        self.formula_edit.setText(f"{col}.cumsum()")
        self.output_col_combo.setCurrentText(f"{name}_cumsum")

    def get_formula(self):
        """(出力先の列名, 式)"""
        output_column_name = self.output_col_combo.currentText()
        formula_string = self.formula_edit.text()
        
        return output_column_name, formula_string


class CalcHelpDialog(QDialog):
    """列の計算で使える書き方のリファレンス。"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列計算機能 リファレンス")
        self.resize(600, 700)

        layout = QVBoxLayout(self)
        
        text_browser = QTextBrowser()
        text_browser.setReadOnly(True)
        text_browser.setOpenExternalLinks(True) 
        
        help_html = r"""
        <h1>列計算機能 リファレンス</h1>
        <p>
            計算式を使って、列データをまとめて計算します。
            「出力先の列」に指定した列に、計算式の結果が一度に適用されます（Excelのオートフィルのように、全行に適用されます）。
        </p>
        
        <hr>
        
        <h2>1. 基本的な算術演算子 🧮</h2>
        <p>列名（例: <code>A</code>, <code>B</code>）や数値をそのまま使えます。空白や記号を含む列名は <code>`強度 (a.u.)`</code> のようにバッククォートで囲みます。</p>
        
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

        layout.addWidget(text_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def refresh_theme(self):
        """開いたままダークモードを切り替えられるので、見出し行の色を今のテーマで当て直す。"""
        from graphica.gui import theme
        _tokens = theme.current_tokens()
        self._text_browser.document().setDefaultStyleSheet(
            f"tr.header-row {{ background-color: {_tokens['surface_2']}; "
            f"color: {_tokens['text_primary']}; }}"
        )


class ColumnStringOpsDialog(QDialog):
    """列の分割・結合・数値の抽出の設定。処理は呼び出し側(DataEditorDialog)が行う。"""

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
        """(対象の列, 区切り文字, 出力の列名の接頭辞)"""
        return (
            self.split_source_combo.currentText(),
            self.split_delimiter_edit.text(),
            self.split_prefix_edit.text().strip(),
        )

    def get_merge_settings(self):
        """(列名のリスト, 区切り文字, 出力の列名)"""
        selected = []
        for i in range(self.merge_column_list.count()):
            item = self.merge_column_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected, self.merge_separator_edit.text(), self.merge_output_edit.text().strip()

    def get_extract_settings(self):
        """(対象の列, 正規表現, 出力の列名)"""
        return (
            self.extract_source_combo.currentText(),
            self.extract_pattern_edit.text(),
            self.extract_output_edit.text().strip(),
        )


class FindReplaceDialog(QDialog):
    """検索と置換。入力欄とボタンだけで、処理は DataEditorDialog が持つ。表を見ながら使うので非モーダル。"""

    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("検索/置換")
        # 非モーダルなので、データエディタの裏に隠れないよう上に浮かせる
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
        """対象の列。「(すべての列)」なら None。"""
        text = self.column_combo.currentText()
        return None if text == "(すべての列)" else text

    def set_status(self, text):
        self.status_label.setText(text)


class RowFilterDialog(QDialog):
    """条件式(例: "y > 0.5")を満たさない行をマスクする。式は列の計算と同じ規則。"""

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
            columns_label = QLabel("利用可能な列: " + ", ".join(column_reference(str(c)) for c in column_names))
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


class ColumnVisibilityDialog(QDialog):
    """チェックを外した列を表で隠す(表示だけで dataset.df は変えない)。"""

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
        """隠す列名のリスト。"""
        hidden = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.CheckState.Unchecked:
                hidden.append(item.text())
        return hidden


class DuplicateXDialog(QDialog):
    """同じ X の行を、平均した新しいデータセットにするか、先頭以外をマスクする。"""

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
        """(方法 "average" | "remove", 出力名("remove" では使わない))"""
        mode = "average" if self.mode_combo.currentText() == self.MODE_AVERAGE else "remove"
        return mode, self.output_name_edit.text().strip()


class ReplicateErrorDialog(QDialog):
    """反復測定の列を選び、行ごとの平均と誤差(SD / SEM / 95%CI)の列を作る。"""

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
        """(列名のリスト, 誤差の種類 'SD' / 'SEM' / '95%CI', 出力の列名のもと)"""
        selected = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        stat_type = self.stat_combo.currentText().split(" ")[0]  # "SD (標準偏差)" -> "SD"
        return selected, stat_type, self.base_name_edit.text().strip()
