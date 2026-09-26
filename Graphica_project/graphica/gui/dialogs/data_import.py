"""データの取り込みのダイアログ。呼び出し側は `from graphica.gui.dialogs import X` で参照する。"""

import logging
import re
import pandas as pd
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from PySide6.QtCore import Qt
from graphica.gui import notify
from graphica.gui.theme import apply_form_spacing

logger = logging.getLogger(__name__)


def _mixes_text_and_other_values(column):
    """文字だけの列はカテゴリとして描けるが、文字と数値・空欄が混ざると描けない。"""
    if column.dtype != object:
        return False
    has_text = has_other = False
    for value in column:
        if isinstance(value, str):
            has_text = True
        else:
            has_other = True
        if has_text and has_other:
            return True
    return False


class ColumnPreviewDialog(QDialog):
    """読み込む前に内容を見せて X/Y の列を選ばせる(列の多いファイルで意図しない列が選ばれないように)。

    Excel はシートとヘッダー行、CSV は文字コード・区切り文字・ヘッダー行・固定長を変えられ、変えるたびにファイルから読み直す。
    """

    # 表示名 -> read_csv の sep。「空白」は空白の連続を区切りとする正規表現なので python エンジンで読む
    _DELIMITER_CHOICES = {
        "カンマ (,)": ",",
        "タブ": "\t",
        "セミコロン (;)": ";",
        "空白": r"\s+",
    }
    _DELIMITER_CUSTOM_LABEL = "その他..."

    _ENCODING_CHOICES = {
        "UTF-8": "utf-8",
        "UTF-8 (BOM付き)": "utf-8-sig",
        "Shift_JIS": "cp932",
        "Latin-1": "latin-1",
        "UTF-16": "utf-16",
    }
    _AUTO_LABEL = "自動判定"

    def __init__(self, df, file_name, parent=None, file_path=None):
        """df は先頭のシート・1行目をヘッダーとして読んだもの。file_path は設定を変えたときの読み直しに使う。"""
        super().__init__(parent)
        self.setWindowTitle(f"列の選択: {file_name}")
        self.resize(600, 480)

        self.file_path = file_path
        self.current_df = df
        from graphica.gui.workers import is_delimited_text_file, is_excel_file
        self.is_excel = is_excel_file(file_path)
        # 組み込みの CSV の読み込みを通ったファイルだけ(プラグインで読んだ形式や貼り付けは対象外)。.txt も CSV と同じ
        self.is_csv = not self.is_excel and is_delimited_text_file(file_path)
        # {列名: "数値" / "文字列" / "日付"}
        self.type_overrides = {}
        self._numeric_table_note = ""

        self.sheet_names = []
        if self.is_excel:
            try:
                from graphica.gui.workers import excel_engine_for
                self.sheet_names = pd.ExcelFile(file_path, engine=excel_engine_for(file_path)).sheet_names
            except Exception as e:
                logger.warning("Excelのシート一覧取得に失敗しました: %s", e)

        self._detected_encoding = None
        self._detected_delimiter = None
        if self.is_csv:
            from graphica.gui.workers import detect_csv_encoding, detect_csv_delimiter
            try:
                self._detected_encoding = detect_csv_encoding(file_path)
            except Exception as e:
                logger.warning("CSVの文字コード自動判定に失敗しました: %s", e)
                self._detected_encoding = 'utf-8-sig'
            try:
                self._detected_delimiter = detect_csv_delimiter(file_path, self._detected_encoding)
            except Exception as e:
                logger.warning("CSVの区切り文字自動判定に失敗しました: %s", e)
                self._detected_delimiter = ','

        layout = QVBoxLayout(self)

        if self.is_excel:
            excel_form = QFormLayout()
            if self.sheet_names:
                self.sheet_combo = QComboBox()
                self.sheet_combo.addItems(self.sheet_names)
                self.sheet_combo.currentIndexChanged.connect(self._on_sheet_or_header_changed)
                excel_form.addRow("シート", self.sheet_combo)
            else:
                self.sheet_combo = None

            self.header_row_spinbox = QSpinBox()
            self.header_row_spinbox.setRange(1, 100)
            self.header_row_spinbox.setValue(1)
            self.header_row_spinbox.setToolTip("列名として使う行を指定します(データの上に説明行がある場合など)")
            self.header_row_spinbox.valueChanged.connect(self._on_sheet_or_header_changed)
            excel_form.addRow("ヘッダー行", self.header_row_spinbox)

            # usecols は "A,C:E" のような Excel の列表記をそのまま受け付ける
            self.usecols_edit = QLineEdit()
            self.usecols_edit.setPlaceholderText("例: A,C:E (空欄で全列)")
            self.usecols_edit.setToolTip("読み込む列をExcelの列表記で指定します(空欄なら全列を読み込みます)")
            self.usecols_edit.editingFinished.connect(self._on_sheet_or_header_changed)
            excel_form.addRow("使用する列 (usecols)", self.usecols_edit)

            self.nrows_spinbox = QSpinBox()
            self.nrows_spinbox.setRange(0, 10_000_000)
            self.nrows_spinbox.setValue(0)
            self.nrows_spinbox.setSpecialValueText("全行")
            self.nrows_spinbox.setToolTip("ヘッダー行より下で読み込む最大行数(0で全行)")
            self.nrows_spinbox.valueChanged.connect(self._on_sheet_or_header_changed)
            excel_form.addRow("読み込む最大行数", self.nrows_spinbox)

            layout.addLayout(excel_form)

            self.check_types_button = QPushButton("列の型を確認...")
            self.check_types_button.clicked.connect(self._on_check_column_types)
            layout.addWidget(self.check_types_button)
        else:
            self.sheet_combo = None
            self.header_row_spinbox = None
            self.usecols_edit = None
            self.nrows_spinbox = None

        if self.is_csv:
            csv_form = QFormLayout()

            self.encoding_combo = QComboBox()
            self.encoding_combo.addItems([self._AUTO_LABEL] + list(self._ENCODING_CHOICES.keys()))
            self.encoding_combo.setToolTip(
                "文字化けする場合は手動で選択してください(自動判定は"
                f"「{self._detected_encoding}」と判定しました)"
            )
            csv_form.addRow("文字コード", self.encoding_combo)

            self.delimiter_combo = QComboBox()
            self.delimiter_combo.addItems(
                [self._AUTO_LABEL] + list(self._DELIMITER_CHOICES.keys()) + [self._DELIMITER_CUSTOM_LABEL]
            )
            self.delimiter_combo.setToolTip(
                f"自動判定は「{self._describe_delimiter(self._detected_delimiter)}」と判定しました"
            )
            csv_form.addRow("区切り文字", self.delimiter_combo)

            self.custom_delimiter_label = QLabel("区切り文字(直接入力)")
            self.custom_delimiter_edit = QLineEdit()
            self.custom_delimiter_edit.setPlaceholderText("区切り文字を入力(例: |)")
            csv_form.addRow(self.custom_delimiter_label, self.custom_delimiter_edit)
            self.custom_delimiter_label.setVisible(False)
            self.custom_delimiter_edit.setVisible(False)

            self.csv_header_row_spinbox = QSpinBox()
            self.csv_header_row_spinbox.setRange(1, 100)
            self.csv_header_row_spinbox.setValue(1)
            self.csv_header_row_spinbox.setToolTip(
                "列名として使う行を指定します(装置が出力する説明文などの前文がある場合は、"
                "その行数分だけ後ろにずらしてください)"
            )
            csv_form.addRow("ヘッダー行", self.csv_header_row_spinbox)

            self.fixed_width_checkbox = QCheckBox("固定長フォーマットとして読み込む")
            self.fixed_width_checkbox.setToolTip("区切り文字を使わず、列の文字位置で区切られたデータの場合に選択します")
            csv_form.addRow(self.fixed_width_checkbox)

            self.fixed_width_label = QLabel("列幅 (固定長)")
            self.fixed_width_edit = QLineEdit()
            self.fixed_width_edit.setPlaceholderText("カンマ区切りで指定(空欄なら自動推測)")
            csv_form.addRow(self.fixed_width_label, self.fixed_width_edit)
            self.fixed_width_label.setVisible(False)
            self.fixed_width_edit.setVisible(False)

            self.csv_nrows_spinbox = QSpinBox()
            self.csv_nrows_spinbox.setRange(0, 10_000_000)
            self.csv_nrows_spinbox.setValue(0)
            self.csv_nrows_spinbox.setSpecialValueText("全行")
            self.csv_nrows_spinbox.setToolTip("ヘッダー行より下で読み込む最大行数(0で全行)")
            csv_form.addRow("読み込む最大行数", self.csv_nrows_spinbox)

            layout.addLayout(csv_form)

            self.check_types_button = QPushButton("列の型を確認...")
            self.check_types_button.clicked.connect(self._on_check_column_types)
            layout.addWidget(self.check_types_button)

            self.encoding_combo.currentIndexChanged.connect(self._reload_csv_preview)
            self.delimiter_combo.currentIndexChanged.connect(self._on_delimiter_combo_changed)
            self.custom_delimiter_edit.editingFinished.connect(self._reload_csv_preview)
            self.csv_header_row_spinbox.valueChanged.connect(self._reload_csv_preview)
            self.fixed_width_checkbox.toggled.connect(self._on_fixed_width_toggled)
            self.fixed_width_edit.editingFinished.connect(self._reload_csv_preview)
            self.csv_nrows_spinbox.valueChanged.connect(self._reload_csv_preview)
        else:
            self.encoding_combo = None
            self.delimiter_combo = None
            self.custom_delimiter_edit = None
            self.csv_header_row_spinbox = None
            self.fixed_width_checkbox = None
            self.fixed_width_edit = None
            self.csv_nrows_spinbox = None

        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        form = QFormLayout()
        self.x_col_combo = QComboBox()
        self.y_col_combo = QComboBox()
        form.addRow("X軸の列", self.x_col_combo)
        form.addRow("Y軸の列", self.y_col_combo)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

        if self.is_csv:
            # 最初に読んだ df はカンマ区切りなので、区切りが違うと1列に潰れている。判定した設定で読み直す
            self._reload_csv_preview()
        else:
            self._rebuild_preview_table()

    @staticmethod
    def _describe_delimiter(delimiter):
        labels = {',': 'カンマ', '\t': 'タブ', ';': 'セミコロン', r'\s+': '空白'}
        return labels.get(delimiter, repr(delimiter))

    def _resolve_csv_encoding(self):
        text = self.encoding_combo.currentText()
        if text == self._AUTO_LABEL:
            return self._detected_encoding or 'utf-8-sig'
        return self._ENCODING_CHOICES.get(text, 'utf-8-sig')

    def _resolve_csv_delimiter(self):
        text = self.delimiter_combo.currentText()
        if text == self._AUTO_LABEL:
            return self._detected_delimiter or ','
        if text == self._DELIMITER_CUSTOM_LABEL:
            return self.custom_delimiter_edit.text() or ','
        return self._DELIMITER_CHOICES.get(text, ',')

    def _csv_settings_are_automatic(self):
        """区切り・ヘッダー行・固定長を利用者が指定していない(指定したらその通りに読む)。"""
        return (self.delimiter_combo.currentText() == self._AUTO_LABEL
                and self.csv_header_row_spinbox.value() == 1
                and not self.fixed_width_checkbox.isChecked())

    def _on_delimiter_combo_changed(self, _index=None):
        is_custom = self.delimiter_combo.currentText() == self._DELIMITER_CUSTOM_LABEL
        self.custom_delimiter_label.setVisible(is_custom)
        self.custom_delimiter_edit.setVisible(is_custom)
        self._reload_csv_preview()

    def _on_fixed_width_toggled(self, checked):
        self.delimiter_combo.setEnabled(not checked)
        self.custom_delimiter_edit.setEnabled(not checked)
        self.fixed_width_label.setVisible(checked)
        self.fixed_width_edit.setVisible(checked)
        self._reload_csv_preview()

    def _reload_csv_preview(self, *_args):
        """CSV の設定が変わったら読み直す。区切りが正規表現のことがあるので python エンジンで読む。"""
        from graphica.gui.workers import has_numeric_column, read_numeric_table

        encoding = self._resolve_csv_encoding()
        header_row = self.csv_header_row_spinbox.value() - 1  # 画面は1始まり
        nrows = self.csv_nrows_spinbox.value() or None
        new_df, error = None, None
        try:
            if self.fixed_width_checkbox.isChecked():
                widths_text = self.fixed_width_edit.text().strip()
                read_kwargs = {'header': header_row, 'encoding': encoding, 'nrows': nrows}
                if widths_text:
                    read_kwargs['widths'] = [int(w.strip()) for w in widths_text.split(',') if w.strip()]
                new_df = pd.read_fwf(self.file_path, **read_kwargs)
            else:
                from graphica.gui.workers import pandas_separator
                delimiter = self._resolve_csv_delimiter()
                # 推測が「空白」なら、最初の読み込みと同じく空白の連続を1つの区切りとみなす
                sep, _engine = pandas_separator(delimiter) if delimiter == ' ' else (delimiter, 'python')
                new_df = pd.read_csv(
                    self.file_path, sep=sep, header=header_row,
                    encoding=encoding, engine='python', nrows=nrows
                )
        except Exception as e:
            error = e

        self._numeric_table_note = ""
        # 設定を変えていないのに読めない・数値の列が無いときは、測定条件などの行に挟まれた数値の表を探す
        if self._csv_settings_are_automatic() and (error is not None or not has_numeric_column(new_df)):
            try:
                found = read_numeric_table(self.file_path, encoding)
            except (OSError, ValueError):  # 文字コードの誤りと pandas の ParserError は ValueError
                logger.exception("数値の表を探せませんでした")
                found = None
            if found is not None:
                table_df, table = found
                new_df, error = (table_df.head(nrows) if nrows else table_df), None
                self._numeric_table_note = (
                    f"前後の説明の行を除き、{table.first_line + 1}〜{table.stop_line} 行目の数値の表を読み込みました。"
                )

        if error is not None:
            logger.error("CSV のプレビューを読み込めませんでした", exc_info=error)
            notify.warning(
                self, "読み込みエラー",
                f"指定した条件(文字コード/区切り文字/ヘッダー行/固定長)では読み込めませんでした:\n{error}"
            )
            return
        self.current_df = new_df
        self._apply_type_overrides()
        self._rebuild_preview_table()

    def _on_sheet_or_header_changed(self):
        """シート・ヘッダー行・使う列・最大行数が変わったら読み直す。"""
        sheet_name = self.sheet_combo.currentText() if self.sheet_combo else 0
        header_row = self.header_row_spinbox.value() - 1  # 画面は1始まり
        usecols = self.usecols_edit.text().strip() or None if self.usecols_edit else None
        nrows = (self.nrows_spinbox.value() or None) if self.nrows_spinbox else None
        try:
            from graphica.gui.workers import excel_engine_for
            new_df = pd.read_excel(
                self.file_path, sheet_name=sheet_name, header=header_row,
                usecols=usecols, nrows=nrows, engine=excel_engine_for(self.file_path)
            )
        except Exception as e:
            logger.exception("Excel のプレビューを読み込めませんでした")
            notify.warning(
                self, "読み込みエラー",
                f"指定した条件(シート/ヘッダー行/使用する列/最大行数)では読み込めませんでした:\n{e}"
            )
            return
        self.current_df = new_df
        self._apply_type_overrides()
        self._rebuild_preview_table()

    def _on_check_column_types(self):
        dialog = ColumnTypeDialog(self.current_df, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.type_overrides = dialog.get_overrides()
            self._apply_type_overrides()
            self._rebuild_preview_table()

    def _apply_type_overrides(self):
        """列の型の上書きを current_df に当てる。読み直した後も、同じ名前の列があれば当て直す。"""
        for col_name, override in self.type_overrides.items():
            if col_name not in self.current_df.columns:
                continue
            try:
                if override == "数値":
                    self.current_df[col_name] = pd.to_numeric(self.current_df[col_name], errors='coerce')
                elif override == "文字列":
                    self.current_df[col_name] = self.current_df[col_name].astype(str)
                elif override == "日付":
                    self.current_df[col_name] = pd.to_datetime(self.current_df[col_name], errors='coerce')
            except Exception as e:
                logger.warning("列「%s」の型変換(%s)に失敗しました: %s", col_name, override, e)

    def _rebuild_preview_table(self):
        df = self.current_df
        columns = [str(c) for c in df.columns]

        self.info_label.setText(
            f"{len(df)}行 × {len(columns)}列 が見つかりました。"
            "プレビューを確認し、X軸・Y軸に使う列を選択してください。"
            + (f"\n{self._numeric_table_note}" if self._numeric_table_note else "")
        )

        preview_row_count = min(len(df), 20)
        self.table.clear()
        self.table.setRowCount(preview_row_count)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        for r in range(preview_row_count):
            for c in range(len(columns)):
                value = df.iloc[r, c]
                text = "" if pd.isna(value) else str(value)
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

        # できるだけ前の選択を残し、無ければ先頭の2列
        prev_x = self.x_col_combo.currentText()
        prev_y = self.y_col_combo.currentText()
        self.x_col_combo.blockSignals(True)
        self.y_col_combo.blockSignals(True)
        self.x_col_combo.clear()
        self.y_col_combo.clear()
        self.x_col_combo.addItems(columns)
        self.y_col_combo.addItems(columns)
        if prev_x in columns:
            self.x_col_combo.setCurrentText(prev_x)
        elif len(columns) >= 1:
            self.x_col_combo.setCurrentIndex(0)
        if prev_y in columns:
            self.y_col_combo.setCurrentText(prev_y)
        elif len(columns) >= 2:
            self.y_col_combo.setCurrentIndex(1)
        self.x_col_combo.blockSignals(False)
        self.y_col_combo.blockSignals(False)

    def accept(self):
        # 文字と数値(や空欄)が混ざった Y の列は、描画の途中で matplotlib が例外を出す。その前に理由を伝える
        _x_col, y_col = self.get_selected_columns()
        if y_col in self.current_df.columns and _mixes_text_and_other_values(self.current_df[y_col]):
            notify.warning(
                self, "Y軸の列を確認してください",
                f"Y軸の列「{y_col}」には、文字と数値(または空欄)が混ざっているため、このままでは描画できません。\n\n"
                "「列の型を確認...」で数値に変換するか、ヘッダー行や別の列を選び直してください。"
            )
            return
        super().accept()

    def get_selected_columns(self):
        """(X の列名, Y の列名)"""
        return self.x_col_combo.currentText(), self.y_col_combo.currentText()

    def get_dataframe(self):
        """いま見せている DataFrame(シートなどを変えていればそれを反映したもの)。"""
        return self.current_df


class ColumnTypeDialog(QDialog):
    """自動判定した列の型を見せ、「数値」「文字列」「日付」に直せるようにする(日付が数値として読まれることがある)。"""

    OVERRIDE_CHOICES = ["自動 (変換しない)", "数値", "文字列", "日付"]

    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列の型を確認")
        self.resize(480, 400)

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "各列について、現在検出されている型を表示しています。"
            "日付が数値として読み込まれている場合など、意図と異なる場合は"
            "「上書き後の型」で変換方法を選択してください。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["列名", "検出された型", "上書き後の型"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setRowCount(len(df.columns))

        self._override_combos = {}
        for row, col_name in enumerate(df.columns):
            self.table.setItem(row, 0, QTableWidgetItem(str(col_name)))

            detected_item = QTableWidgetItem(str(df[col_name].dtype))
            detected_item.setFlags(detected_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, detected_item)

            combo = QComboBox()
            combo.addItems(self.OVERRIDE_CHOICES)
            self.table.setCellWidget(row, 2, combo)
            self._override_combos[str(col_name)] = combo

        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_overrides(self):
        """「自動」以外にした列だけの {列名: "数値" / "文字列" / "日付"}。"""
        overrides = {}
        for col_name, combo in self._override_combos.items():
            text = combo.currentText()
            if text != "自動 (変換しない)":
                overrides[col_name] = text
        return overrides


class ExcelMultiSheetDialog(QDialog):
    """取り込むシートを選ぶ。複数選ぶとシートごとに別のデータセットになる。"""

    def __init__(self, sheet_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("シートの選択")
        self.resize(320, 380)

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "読み込むシートを選択してください(複数選択可)。\n"
            "2つ以上選択すると、シートごとに別々のデータセットとして追加されます。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.sheet_list = QListWidget()
        self.sheet_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for i, name in enumerate(sheet_names):
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if i == 0 else Qt.CheckState.Unchecked)
            self.sheet_list.addItem(item)
        layout.addWidget(self.sheet_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_selected_sheets(self):
        """チェックしたシート名(シートの順)。"""
        result = []
        for i in range(self.sheet_list.count()):
            item = self.sheet_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result


class FolderImportDialog(QDialog):
    """フォルダ一括取り込みの対象の一覧と、ファイル名から条件を取り出す正規表現。読み込みはドラッグ&ドロップと同じ待ち行列。"""

    def __init__(self, folder_path, file_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フォルダから一括インポート")
        self.resize(480, 340)

        layout = QVBoxLayout(self)
        folder_label = QLabel(f"フォルダ: {folder_path}")
        folder_label.setWordWrap(True)
        layout.addWidget(folder_label)
        layout.addWidget(QLabel(f"対象ファイル: {len(file_names)}件"))

        self.file_list = QListWidget()
        self.file_list.addItems(file_names)
        self.file_list.setMaximumHeight(130)
        layout.addWidget(self.file_list)

        layout.addWidget(QLabel(
            "ファイル名から抽出する正規表現(任意、名前付きグループが新しい列になります):"
        ))
        self.regex_edit = QLineEdit()
        self.regex_edit.setPlaceholderText(r"例: (?P<temp>\d+)C_(?P<run>\d+)\.csv")
        layout.addWidget(self.regex_edit)

        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("font-size: 9pt; color: gray;")
        layout.addWidget(self.preview_label)

        self._first_file_name = file_names[0] if file_names else ""
        self.regex_edit.textChanged.connect(self._update_preview)
        self._update_preview()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _update_preview(self):
        """先頭のファイル名で取り出した結果をその場で見せる。"""
        pattern = self.regex_edit.text().strip()
        if not pattern:
            self.preview_label.setText("(正規表現が未入力のため、列は追加されません)")
            return
        try:
            match = re.search(pattern, self._first_file_name)
        except re.error as e:
            self.preview_label.setText(f"正規表現エラー: {e}")
            return
        if match is None:
            self.preview_label.setText(f"「{self._first_file_name}」にマッチしません")
            return
        groups = match.groupdict()
        if not groups:
            self.preview_label.setText("名前付きグループ (?P<name>...) がありません(列は追加されません)")
            return
        preview = ", ".join(f"{k}={v}" for k, v in groups.items())
        self.preview_label.setText(f"「{self._first_file_name}」からの抽出例: {preview}")

    def get_regex_pattern(self):
        """正規表現。空なら None。"""
        pattern = self.regex_edit.text().strip()
        return pattern if pattern else None


class NewDatasetDialog(QDialog):
    """名前・列名・行数だけで空のデータセットを作る(作った後はデータエディタで打ち込む)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from graphica.core.i18n import tr

        self.setWindowTitle(tr("新規データセットを作成"))
        self.resize(360, 180)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(tr("新規データセット"))
        layout.addRow(tr("データセット名"), self.name_edit)

        self.columns_edit = QLineEdit("X, Y")
        self.columns_edit.setToolTip(tr("カンマ区切りで列名を入力してください(例: X, Y, 誤差)"))
        layout.addRow(tr("列名 (カンマ区切り)"), self.columns_edit)

        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setRange(0, 10000)
        self.rows_spinbox.setValue(5)
        layout.addRow(tr("初期の空行数"), self.rows_spinbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        apply_form_spacing(self)

    def _on_accept(self):
        from graphica.core.i18n import tr
        if not self.get_dataset_name():
            notify.warning(self, tr("新規データセットを作成"), tr("データセット名を入力してください。"))
            return
        if not self.get_column_names():
            notify.warning(self, tr("新規データセットを作成"), tr("列名を1つ以上入力してください。"))
            return
        self.accept()

    def get_dataset_name(self):
        return self.name_edit.text().strip()

    def get_column_names(self):
        """カンマ区切りを列名のリストにする(重複と空は除く)。"""
        raw = self.columns_edit.text()
        names = [c.strip() for c in raw.split(',') if c.strip()]
        unique_names = []
        for name in names:
            if name not in unique_names:
                unique_names.append(name)
        return unique_names

    def get_row_count(self):
        return self.rows_spinbox.value()
