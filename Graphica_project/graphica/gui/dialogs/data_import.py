# gui/dialogs/data_import.py
"""
データの取り込みのダイアログ。

gui/dialogs.py(5,560行・47ダイアログ)を機能群ごとに分割したもの
(改善ボード B-2)。呼び出し側は従来どおり `from gui.dialogs import X` で
参照できる(gui/dialogs/__init__.py が再エクスポートしている)。
"""

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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from PySide6.QtCore import Qt
from graphica.gui.theme import apply_form_spacing

logger = logging.getLogger(__name__)




#==============================================================================
# カスタムダイアログクラス (7)
#==============================================================================
class ColumnPreviewDialog(QDialog):
    """
    データファイル (CSV/Excel) 読み込み時に、内容をプレビュー表示しつつ
    X軸・Y軸に使う列をユーザーに選択させるダイアログ。

    これまでは常に先頭2列を自動でX/Y軸に割り当てていたが、
    列数の多いファイルでは意図しない列が選ばれることがあるため、
    読み込み前に確認・選択できるようにする。

    Excelファイルの場合は、シートの切り替えとヘッダー行の指定にも対応する
    (どちらも変更するとファイルからその場で再読み込みしてプレビューを更新する)。

    CSVファイルの場合は、文字コード・区切り文字の自動判定+手動上書き、
    ヘッダー行の指定(装置が出力する説明文などの前文をスキップする用途を兼ねる)、
    固定長フォーマットとしての読み込みに対応する(項目C-101、インポートウィザード強化)。
    実測データはこの手の「綺麗でないCSV」であることが多いため、Excel同様
    その場で再読み込みしてプレビューを更新する。
    """

    # 区切り文字コンボの表示名 -> 実際の区切り文字(pandas read_csv の sep に渡す値)。
    # 「空白」は空白1文字以上の連続を区切りとみなすため正規表現になる
    # (engine='python' が必要、_reload_csv_preview 側で常にpythonエンジンを使う)。
    _DELIMITER_CHOICES = {
        "カンマ (,)": ",",
        "タブ": "\t",
        "セミコロン (;)": ";",
        "空白": r"\s+",
    }
    _DELIMITER_CUSTOM_LABEL = "その他..."

    # エンコーディングコンボの表示名 -> Python/pandasのエンコーディング名。
    _ENCODING_CHOICES = {
        "UTF-8": "utf-8",
        "UTF-8 (BOM付き)": "utf-8-sig",
        "Shift_JIS": "cp932",
        "Latin-1": "latin-1",
        "UTF-16": "utf-16",
    }
    _AUTO_LABEL = "自動判定"

    def __init__(self, df, file_name, parent=None, file_path=None):
        """
        Args:
            df (pandas.DataFrame): 読み込んだファイルのデータ (プレビュー表示用、
                先頭シート・1行目ヘッダーで読み込んだ初期状態)。
            file_name (str): 表示用のファイル名。
            parent (QWidget, optional): 親ウィジェット。
            file_path (str, optional): 実ファイルパス。Excel/CSVファイルの場合、
                シート切り替え・ヘッダー行変更・文字コード/区切り文字の上書き時の
                再読み込みに使う。
        """
        super().__init__(parent)
        self.setWindowTitle(f"列の選択: {file_name}")
        self.resize(600, 480)

        self.file_path = file_path
        self.current_df = df
        from graphica.gui.workers import is_delimited_text_file, is_excel_file
        self.is_excel = is_excel_file(file_path)
        # ビルトインのCSV読み込み(gui/workers.pyのread_data_file)経由のファイルのみ
        # 対象(プラグインインポーターが読み込んだ他形式やクリップボード貼り付けは
        # file_path=Noneまたは非csv拡張子のため、以下の追加コントロールは表示しない)。
        # .txt も CSV と同じ区切り文字付きテキストとして扱う(v1.4.2)。
        self.is_csv = not self.is_excel and is_delimited_text_file(file_path)
        # 「列の型を確認...」で設定された、列ごとの型上書き ({列名: "数値"/"文字列"/"日付"})
        self.type_overrides = {}

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

        # --- Excel専用: シート選択・ヘッダー行指定 ---
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

            # 使用する列 (pandasのusecolsは "A,C:E" のようなExcel列表記の文字列を
            # そのまま受け付けるため、パース処理を自前で書く必要がない)
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

        # --- CSV専用: 文字コード・区切り文字・ヘッダー行・固定長(項目C-101) ---
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

            layout.addLayout(csv_form)

            self.encoding_combo.currentIndexChanged.connect(self._reload_csv_preview)
            self.delimiter_combo.currentIndexChanged.connect(self._on_delimiter_combo_changed)
            self.custom_delimiter_edit.editingFinished.connect(self._reload_csv_preview)
            self.csv_header_row_spinbox.valueChanged.connect(self._reload_csv_preview)
            self.fixed_width_checkbox.toggled.connect(self._on_fixed_width_toggled)
            self.fixed_width_edit.editingFinished.connect(self._reload_csv_preview)
        else:
            self.encoding_combo = None
            self.delimiter_combo = None
            self.custom_delimiter_edit = None
            self.csv_header_row_spinbox = None
            self.fixed_width_checkbox = None
            self.fixed_width_edit = None

        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        # --- プレビューテーブル (先頭最大20行、読み取り専用) ---
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # --- X/Y列選択 ---
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
            # 自動判定したエンコーディング/区切り文字で初回プレビューを作る
            # (workers.load_data_file_task が既定のカンマ区切りで読んだ初期dfは、
            # 実際の区切り文字がカンマでない場合1列に崩れていることがあるため)。
            self._reload_csv_preview()
        else:
            self._rebuild_preview_table()

    @staticmethod
    def _describe_delimiter(delimiter):
        """区切り文字を人間が読める短いラベルにする(ツールチップ表示用)"""
        labels = {',': 'カンマ', '\t': 'タブ', ';': 'セミコロン', r'\s+': '空白'}
        return labels.get(delimiter, repr(delimiter))

    def _resolve_csv_encoding(self):
        """エンコーディングコンボの選択値を、pandasに渡すエンコーディング名に変換する"""
        text = self.encoding_combo.currentText()
        if text == self._AUTO_LABEL:
            return self._detected_encoding or 'utf-8-sig'
        return self._ENCODING_CHOICES.get(text, 'utf-8-sig')

    def _resolve_csv_delimiter(self):
        """区切り文字コンボの選択値を、pandasのsepに渡す実際の区切り文字に変換する"""
        text = self.delimiter_combo.currentText()
        if text == self._AUTO_LABEL:
            return self._detected_delimiter or ','
        if text == self._DELIMITER_CUSTOM_LABEL:
            return self.custom_delimiter_edit.text() or ','
        return self._DELIMITER_CHOICES.get(text, ',')

    def _on_delimiter_combo_changed(self, _index=None):
        """区切り文字コンボの選択に応じて「その他」用のカスタム入力欄の表示を切り替える"""
        is_custom = self.delimiter_combo.currentText() == self._DELIMITER_CUSTOM_LABEL
        self.custom_delimiter_label.setVisible(is_custom)
        self.custom_delimiter_edit.setVisible(is_custom)
        self._reload_csv_preview()

    def _on_fixed_width_toggled(self, checked):
        """固定長チェックボックスに応じて、区切り文字系コントロールと列幅入力の有効/表示を切り替える"""
        self.delimiter_combo.setEnabled(not checked)
        self.custom_delimiter_edit.setEnabled(not checked)
        self.fixed_width_label.setVisible(checked)
        self.fixed_width_edit.setVisible(checked)
        self._reload_csv_preview()

    def _reload_csv_preview(self, *_args):
        """
        CSV(項目C-101)の文字コード・区切り文字・ヘッダー行・固定長設定のいずれかが
        変更されたときに呼ばれる。指定された条件でファイルから再読み込みし、
        プレビュー全体を更新する(_on_sheet_or_header_changedのCSV版)。
        区切り文字に「空白」等の正規表現が来ることがあるため、常にPythonエンジンで読む。
        """
        encoding = self._resolve_csv_encoding()
        header_row = self.csv_header_row_spinbox.value() - 1  # UIは1始まり、pandasは0始まり
        try:
            if self.fixed_width_checkbox.isChecked():
                widths_text = self.fixed_width_edit.text().strip()
                read_kwargs = {'header': header_row, 'encoding': encoding}
                if widths_text:
                    read_kwargs['widths'] = [int(w.strip()) for w in widths_text.split(',') if w.strip()]
                new_df = pd.read_fwf(self.file_path, **read_kwargs)
            else:
                from graphica.gui.workers import pandas_separator
                delimiter = self._resolve_csv_delimiter()
                # 推測結果が「空白」のとき、初回読み込み(read_data_file)と同じく
                # 空白の連続を1つの区切りとみなす。
                sep, _engine = pandas_separator(delimiter) if delimiter == ' ' else (delimiter, 'python')
                new_df = pd.read_csv(
                    self.file_path, sep=sep, header=header_row,
                    encoding=encoding, engine='python'
                )
        except Exception as e:
            logger.exception("CSV のプレビューを読み込めませんでした")
            QMessageBox.warning(
                self, "読み込みエラー",
                f"指定した条件(文字コード/区切り文字/ヘッダー行/固定長)では読み込めませんでした:\n{e}"
            )
            return
        self.current_df = new_df
        self._apply_type_overrides()
        self._rebuild_preview_table()

    def _on_sheet_or_header_changed(self):
        """
        シート選択、ヘッダー行、使用する列(usecols)、最大行数(nrows) のいずれかが
        変更されたときに呼ばれる。指定された条件でファイルから再読み込みし、
        プレビュー全体を更新する。
        """
        sheet_name = self.sheet_combo.currentText() if self.sheet_combo else 0
        header_row = self.header_row_spinbox.value() - 1  # UIは1始まり、pandasは0始まり
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
            QMessageBox.warning(
                self, "読み込みエラー",
                f"指定した条件(シート/ヘッダー行/使用する列/最大行数)では読み込めませんでした:\n{e}"
            )
            return
        self.current_df = new_df
        self._apply_type_overrides()
        self._rebuild_preview_table()

    def _on_check_column_types(self):
        """「列の型を確認...」ボタンの処理。ColumnTypeDialogを表示し、上書き設定を反映する"""
        dialog = ColumnTypeDialog(self.current_df, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.type_overrides = dialog.get_overrides()
            self._apply_type_overrides()
            self._rebuild_preview_table()

    def _apply_type_overrides(self):
        """
        self.type_overrides に設定されている列の型上書きを self.current_df に適用する。
        シート/ヘッダー行等の変更で current_df が新しく読み直された場合も、
        同じ列名がまだ存在すれば上書き設定を再適用する(呼び出し元で毎回呼ばれる)。
        """
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
        """現在の self.current_df の内容で、情報ラベル・プレビュー表・X/Y列コンボを再構築する"""
        df = self.current_df
        columns = [str(c) for c in df.columns]

        self.info_label.setText(
            f"{len(df)}行 × {len(columns)}列 が見つかりました。"
            "プレビューを確認し、X軸・Y軸に使う列を選択してください。"
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

        # X/Y列の選択肢を更新 (できる限り元の選択を維持し、無ければ先頭2列にフォールバック)
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

    def get_selected_columns(self):
        """
        選択された (X軸の列名, Y軸の列名) をタプルで返す。

        Returns:
            tuple (str, str): (x_col_name, y_col_name)
        """
        return self.x_col_combo.currentText(), self.y_col_combo.currentText()

    def get_dataframe(self):
        """
        現在プレビュー表示しているDataFrameを返す。
        Excelでシート/ヘッダー行を変更した場合は、その内容を反映したものになる。
        """
        return self.current_df




#==============================================================================
# カスタムダイアログクラス: Excel列の型自動判定確認
#==============================================================================
class ColumnTypeDialog(QDialog):
    """
    読み込んだ表の各列について、pandasが自動判定した型を一覧表示し、
    必要であれば「数値」「文字列」「日付」に強制変換できるようにするダイアログ。
    日付列が数値(Excelのシリアル値)として誤認識される、といったケースへの対策として、
    読み込み前にユーザー自身が気づいて修正できるようにする。
    """

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
        """
        「自動」以外が選択された列だけを対象に、{列名: 上書き後の型} の辞書を返す。
        上書き後の型は "数値" / "文字列" / "日付" のいずれか。
        """
        overrides = {}
        for col_name, combo in self._override_combos.items():
            text = combo.currentText()
            if text != "自動 (変換しない)":
                overrides[col_name] = text
        return overrides




#==============================================================================
# カスタムダイアログクラス: Excel複数シートの一括インポート
#==============================================================================
class ExcelMultiSheetDialog(QDialog):
    """
    複数シートを持つExcelファイルを読み込む際に、どのシートを
    データセットとして取り込むかチェックボックスで選択させるダイアログ。
    2つ以上チェックした場合は、シートごとに別々のデータセットとして追加される
    (シートごとにX/Y列の選択プレビューが続けて表示される)。
    """

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
        """チェックされたシート名のリストを、シート一覧に現れる順序で返す"""
        result = []
        for i in range(self.sheet_list.count()):
            item = self.sheet_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result




#==============================================================================
# カスタムダイアログクラス: フォルダから一括インポート(項目C-104)
#==============================================================================
class FolderImportDialog(QDialog):
    """
    フォルダ一括インポートの対象ファイル一覧を表示し、任意でファイル名から
    測定条件(温度・濃度等)を抜き出す正規表現を入力させるダイアログ。
    実際の読み込み自体は既存のドラッグ&ドロップ一括取込み機構
    (gui/main_window.pyの_queue_data_files)をそのまま再利用するため、
    このダイアログはファイルパスの収集と正規表現の入力だけを担当する。
    """

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
        """正規表現入力欄の変更のたびに、先頭ファイル名での抽出結果をライブプレビューする"""
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
        """Returns: str | None (未入力ならNone)"""
        pattern = self.regex_edit.text().strip()
        return pattern if pattern else None




#==============================================================================
# カスタムダイアログクラス: 新規データセットを作成 (項目63)
#==============================================================================
class NewDatasetDialog(QDialog):
    """
    ファイル読み込みを介さず、名前・列名・初期行数だけを指定して空のデータセットを
    作成するためのダイアログ(項目63)。作成後はデータエディタが自動的に開き、
    そこでセルに直接データを打ち込んでいく運用を想定している。
    """

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
            QMessageBox.warning(self, tr("新規データセットを作成"), tr("データセット名を入力してください。"))
            return
        if not self.get_column_names():
            QMessageBox.warning(self, tr("新規データセットを作成"), tr("列名を1つ以上入力してください。"))
            return
        self.accept()

    def get_dataset_name(self):
        return self.name_edit.text().strip()

    def get_column_names(self):
        """カンマ区切りの入力を列名のリストに変換する(重複・空文字は除く)"""
        raw = self.columns_edit.text()
        names = [c.strip() for c in raw.split(',') if c.strip()]
        unique_names = []
        for name in names:
            if name not in unique_names:
                unique_names.append(name)
        return unique_names

    def get_row_count(self):
        return self.rows_spinbox.value()
