import os
import logging
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                               QTableWidget, QTableWidgetItem, QMenuBar,
                               QInputDialog, QMessageBox, QFileDialog, QDialogButtonBox)
from PySide6.QtGui import QUndoStack, QKeySequence, QColor
from PySide6.QtCore import Signal, Qt

logger = logging.getLogger(__name__)

# 自分で切り出したモジュールの読み込み
from core.commands import (EditCellCommand, AddRowCommand, DeleteRowsCommand,
                           AddColumnCommand, DeleteColumnCommand, SetMaskedRowsCommand,
                           RenameColumnCommand)
from core.safe_eval import safe_eval_column_formula
from gui.dialogs import ColumnCalculatorDialog, ReplicateErrorDialog
from gui import icon_utils

# 外れ値のマスク機能(項目36): 除外中の行をテーブル上でひと目で分かるように示す背景色
MASKED_ROW_BACKGROUND = QColor(220, 220, 220)

#==============================================================================
# データ構造とMatplotlibキャンバスクラス (2)
#==============================================================================
class DataEditorDialog(QDialog):
    """
    DataFrame (dataset.df) の内容を QTableWidget で表示・編集するための
    ダイアログクラスです。
    
    Undo/Redo 機能 (QUndoStack) を持ち、セル編集、行/列の追加・削除を
    元に戻したり、やり直したりすることができます。
    """
    
    # dataChanged シグナルを定義
    # このダイアログ外 (PlotterApp) に「データが変更された」ことを通知するために使う
    dataChanged = Signal()

    # テーブルで選択されている行が変わったときに発行するシグナル。
    # 引数は dataset.df のインデックスラベルのリスト (空リストなら選択なし)。
    # データ⇔グラフの双方向ハイライト機能で、グラフ側の表示を連動させるために使う。
    rowsHighlighted = Signal(list)
    
    def __init__(self, dataset, parent=None):
        """
        ダイアログの初期化。
        
        Args:
            dataset (Dataset): 編集対象の Dataset オブジェクト。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle(f"データエディタ: {dataset.name}")
        self.resize(800, 600)
        
        # 編集対象の dataset オブジェクトへの参照を保持
        self.dataset = dataset
        
        # ★ view_df: フィルターやソートを適用するための「表示用」DataFrame
        # マスター (dataset.df) のコピー (copy()) を使うことが重要。
        # (元のコードではコピーしていなかったため、ソートなどがマスターに影響する可能性があった)
        self.view_df = self.dataset.df.copy()
        self.sort_state = (None, True) # (現在ソート中の列名, 昇順かどうか)。未ソート時は (None, True)

        # --- ★ Undo/Redo スタックを作成 ---
        self.undo_stack = QUndoStack(self)
        # コマンドが push/undo/redo されるたびに呼ばれる (コマンド自体はGUIを一切知らない)
        self.undo_stack.indexChanged.connect(self._on_undo_stack_changed)

        # --- メインのテーブルウィジェット ---
        self.table_widget = QTableWidget()
        self.table_widget.setSortingEnabled(False) # ★ ソート機能は自前で実装する必要があるため、標準は無効
        self.table_widget.horizontalHeader().setSectionsClickable(True)
        self.table_widget.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        # 列ヘッダーのダブルクリックで列名をリネームできるようにする(項目64)
        self.table_widget.horizontalHeader().sectionDoubleClicked.connect(self._on_header_double_clicked)
        # 選択中の行が変わるたびに、対応するデータ点をグラフ上でハイライトする
        self.table_widget.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._populate_table()
        
        # --- 1. ボタンのレイアウトを作成 (QHBoxLayout: 水平) ---
        button_layout = QHBoxLayout()
        self.add_row_button = QPushButton("行を追加")
        self.delete_row_button = QPushButton("選択行を削除")
        self.mask_rows_button = QPushButton("選択行を除外/解除")
        self.add_col_button = QPushButton("列を追加")
        self.delete_col_button = QPushButton("選択列を削除")
        self.calc_button = QPushButton("列の計算...")
        self.replicate_error_button = QPushButton("誤差の自動計算...")
        self.save_csv_button = QPushButton("CSVとして保存...")

        # メインウィンドウの操作ボタン行(項目70)と統一感を持たせるため、
        # ここもテキスト付きボタンではなくアイコンのみの正方形ボタンにする。
        # ラベルはツールチップに残す。
        _button_icons = (
            (self.add_row_button, "row-insert-bottom"),
            (self.delete_row_button, "row-remove"),
            (self.mask_rows_button, "eye-off"),
            (self.add_col_button, "column-insert-right"),
            (self.delete_col_button, "column-remove"),
            (self.calc_button, "calculator"),
            (self.replicate_error_button, "math-function"),
            (self.save_csv_button, "download"),
        )
        self.mask_rows_button.setToolTip(
            "行を削除せず、フィット/プロットの対象から除外(または解除)します(非破壊的)"
        )
        for button, icon_name in _button_icons:
            if not button.toolTip():
                button.setToolTip(button.text())
            button.setText("")
            button.setIcon(icon_utils.icon(icon_name, size=18))
            button.setProperty("iconOnly", True)
            button.setFixedSize(34, 34)

        button_layout.addWidget(self.add_row_button)
        button_layout.addWidget(self.delete_row_button)
        button_layout.addWidget(self.mask_rows_button)
        button_layout.addStretch() # 伸縮可能なスペース (ボタンを左端に寄せる)
        button_layout.addWidget(self.add_col_button)
        button_layout.addWidget(self.delete_col_button)
        button_layout.addStretch()
        button_layout.addWidget(self.calc_button)
        button_layout.addWidget(self.replicate_error_button)
        button_layout.addStretch()
        button_layout.addWidget(self.save_csv_button)


        # --- 2. メインレイアウト (QVBoxLayout: 垂直) ---
        main_layout = QVBoxLayout(self)
        
        # --- メニューバーの作成 (Undo/Redo のため) ---
        menu_bar = QMenuBar(self)
        edit_menu = menu_bar.addMenu("編集")
        
        # QUndoStack から Undo/Redo の QAction を自動生成
        undo_action = self.undo_stack.createUndoAction(self, "元に戻す")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo) # Ctrl+Z
        
        redo_action = self.undo_stack.createRedoAction(self, "やり直し")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo) # Ctrl+Y (Win) / Cmd+Shift+Z (Mac)
        
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)
        
        # QDialog にも QMenuBar をセットできる (setMenuBar)
        main_layout.setMenuBar(menu_bar)
        
        # (デバッグ用に Undo 履歴を表示するビューを追加することも可能)
        # undo_view = QUndoView(self.undo_stack)
        # main_layout.addWidget(undo_view)
        
        main_layout.addLayout(button_layout) # メニューバーの下にボタンレイアウト
        main_layout.addWidget(self.table_widget) # その下にテーブル
        
        # 閉じるボタン
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        # --- 3. シグナル接続 ---
        # テーブルのセルが編集されたら _on_cell_changed を呼ぶ
        self.table_widget.cellChanged.connect(self._on_cell_changed)
        
        # 各ボタンのクリックシグナルを対応するスロット（メソッド）に接続
        self.add_row_button.clicked.connect(self._on_add_row)
        self.delete_row_button.clicked.connect(self._on_delete_rows)
        self.mask_rows_button.clicked.connect(self._on_toggle_mask_rows)
        self.add_col_button.clicked.connect(self._on_add_column)
        self.delete_col_button.clicked.connect(self._on_delete_column)
        self.calc_button.clicked.connect(self._on_calculate_column)
        self.replicate_error_button.clicked.connect(self._on_calculate_replicate_error)
        self.save_csv_button.clicked.connect(self._on_save_as_csv)

    def _populate_table(self):
        """
        テーブル (QTableWidget) に view_df の内容をセットする。
        NaN/NaT は空文字列として表示する。
        """
        # view_df を使う (ソート/フィルターされた状態を表示するため)
        df = self.view_df
        
        # ★ blockSignals(True):
        # これからUIをプログラムで変更する。
        # この変更によって cellChanged シグナルが発生しないように一時停止する。
        self.table_widget.blockSignals(True) 
        
        self.table_widget.setRowCount(len(df))
        self.table_widget.setColumnCount(len(df.columns))
        self.table_widget.setHorizontalHeaderLabels(df.columns)
        
        # ★ 行ヘッダ (0, 1, 2...) には、マスターdfのインデックス (loc用) を表示
        # これにより、表示がソートされても、どのデータか追跡できる
        self.table_widget.setVerticalHeaderLabels([str(i) for i in df.index])

        for i in range(len(df)):
            # 外れ値のマスク機能(項目36): 除外中の行は背景色を変えてひと目で分かるようにする
            is_masked = df.index[i] in self.dataset.masked_row_indices
            for j in range(len(df.columns)):
                # iloc[i, j] を使って「表示上のi行目」のデータを取得
                value = df.iloc[i, j]

                # ★ pd.isna で NaN (Not a Number) や NaT (Not a Time) をチェック
                item_text = "" if pd.isna(value) else str(value)

                item = QTableWidgetItem(item_text)
                if is_masked:
                    item.setBackground(MASKED_ROW_BACKGROUND)
                    item.setToolTip("この行はフィット/プロットから除外されています")
                self.table_widget.setItem(i, j, item)
        
        self.table_widget.resizeColumnsToContents() # 列幅を自動調整

        # ソート中の列があれば、ヘッダーに矢印アイコンで表示する
        sort_col, sort_ascending = self.sort_state
        header = self.table_widget.horizontalHeader()
        if sort_col is not None and sort_col in df.columns:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(
                df.columns.get_loc(sort_col),
                Qt.SortOrder.AscendingOrder if sort_ascending else Qt.SortOrder.DescendingOrder
            )
        else:
            header.setSortIndicatorShown(False)

        # ★ blockSignals(False): UIの準備が終わったので、シグナルを再開
        self.table_widget.blockSignals(False)

    def _on_header_clicked(self, logical_index):
        """
        テーブルの列ヘッダーがクリックされたときに呼ばれる。
        その列を基準に昇順/降順ソートする (同じ列を再度クリックすると昇順/降順を反転)。
        ソートは表示用の view_df のみに適用され、マスターデータ (dataset.df) や
        Undo/Redoスタックには影響しない (見た目上の並べ替えのため)。
        """
        col_name = self.view_df.columns[logical_index]
        current_col, current_ascending = self.sort_state
        ascending = (not current_ascending) if current_col == col_name else True

        try:
            # kind='mergesort' は安定ソート (同値の行の相対順序を保つ)
            self.view_df = self.view_df.sort_values(by=col_name, ascending=ascending, kind='mergesort')
        except TypeError:
            # 型が混在する列 (数値とNaN以外の文字列が混じる等) はソートできないことがある
            QMessageBox.warning(self, "ソートエラー", f"列 '{col_name}' はソートできませんでした。")
            return

        self.sort_state = (col_name, ascending)
        self._populate_table()

    def _on_header_double_clicked(self, logical_index):
        """
        列ヘッダーをダブルクリックすると、列名を変更できるようにする(項目64)。
        手動データ入力(項目63)で「列1」「列2」のような仮の名前を付けた場合の
        リネームや、既存データの列名修正を想定している。
        """
        old_name = self.view_df.columns[logical_index]
        new_name, ok = QInputDialog.getText(self, "列名の変更", "新しい列名:", text=old_name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if new_name in self.dataset.df.columns:
            QMessageBox.warning(self, "列名の変更", f"列名 '{new_name}' は既に使用されています。")
            return

        command = RenameColumnCommand(self.dataset, old_name, new_name)
        self.undo_stack.push(command)

    def get_selected_master_indices(self):
        """
        現在テーブルで選択されている行に対応する、マスターDataFrame(dataset.df)の
        インデックスラベルのリストを返す。view_df はソート済みの場合があるため、
        表示上の行番号をそのまま使わず view_df.index 経由で変換する。
        """
        rows = sorted({index.row() for index in self.table_widget.selectionModel().selectedRows()})
        return [self.view_df.index[r] for r in rows if r < len(self.view_df.index)]

    def _on_table_selection_changed(self):
        """テーブルの選択行が変わるたびに呼ばれ、グラフ側のハイライトを更新するよう通知する"""
        self.rowsHighlighted.emit(self.get_selected_master_indices())

    def select_row_by_master_index(self, master_index):
        """
        マスターDataFrame(dataset.df)のインデックスラベルを指定して、対応する行を
        テーブル上で選択・スクロール表示する(グラフ上の点クリックからの逆方向ハイライト用)。
        プログラムによる選択のため itemSelectionChanged はブロックし、
        グラフ側への通知が無駄にループしないようにする。
        """
        matches = np.where(self.view_df.index == master_index)[0]
        if len(matches) == 0:
            return
        row = int(matches[0])

        self.table_widget.blockSignals(True)
        self.table_widget.clearSelection()
        self.table_widget.selectRow(row)
        self.table_widget.blockSignals(False)

        item = self.table_widget.item(row, 0)
        if item is not None:
            self.table_widget.scrollToItem(item)

    def closeEvent(self, event):
        """閉じるときはグラフ側のハイライトも消す"""
        self.rowsHighlighted.emit([])
        super().closeEvent(event)

    def _on_cell_changed(self, row, column):
        """
        テーブルのセルがユーザーによって編集されたときに呼び出されるスロット。
        Undo/Redo コマンド (EditCellCommand) を発行します。
        """
        try:
            # 1. 編集されたセルが、マスターDFのどのインデックス/列名に対応するか特定
            
            # `row` は表示上の行番号。`view_df.index[row]` で、
            # マスターDFに対応するインデックス (loc用) を取得。
            original_index = self.view_df.index[row]
            col_name = self.view_df.columns[column]
            
            # 2. 変更「前」の値をマスターDF (dataset.df) から取得
            old_value = self.dataset.df.loc[original_index, col_name]
            
            # 3. 変更「後」の値をテーブル (QTableWidget) から文字列として取得
            new_value_str = self.table_widget.item(row, column).text()
            
            # 4. 変更後の値を適切な型に変換
            new_value = None
            
            if new_value_str == "":
                # 空文字列で上書きされたら np.nan (欠損値) として扱う
                new_value = np.nan
            else:
                # 元の列のデータ型 (dtype) を取得
                original_dtype = self.dataset.df[col_name].dtype
                
                # 型変換を試みる
                try:
                    # np.dtype(original_dtype).type は、
                    # np.float64 や np.int64 などの型コンストラクタを返す
                    new_value = np.dtype(original_dtype).type(new_value_str)
                except (ValueError, TypeError):
                    # 型変換に失敗した場合 (例: 数値列に "abc" と入力)
                    # もし元の型が数値系 (number) なら NaN にする
                    if np.issubdtype(original_dtype, np.number):
                        new_value = np.nan
                    else: 
                        # 文字列型 (object) の場合は、入力された文字列をそのまま使う
                        new_value = new_value_str
            
            # 5. 変更があったかどうかのチェック
            #    (NaN 同士は `old_value != new_value` では比較できないため、
            #     pd.isna で個別にチェックする必要がある)
            is_nan_old = pd.isna(old_value)
            is_nan_new = pd.isna(new_value)
            
            # 変更があった場合:
            if (is_nan_old and not is_nan_new) or \
               (not is_nan_old and is_nan_new) or \
               (not is_nan_old and not is_nan_new and old_value != new_value):
                
                # 6. ★★★ Undo/Redo コマンドを作成し、スタックに push する ★★★
                #    (元のコードにあった self.dataset.df への直接代入は削除)
                command = EditCellCommand(self.dataset, original_index, col_name, old_value, new_value)
                self.undo_stack.push(command)
                # -> push されると、自動的に command.redo() が呼ばれ、
                #    EditCellCommand 側でデータが更新され、dataChanged.emit() される。
            
            else:
                # 変更がなかった場合 (例: "1.0" を "1.0" に編集)
                # 元の値を再表示 (UIの正規化のため)
                self.table_widget.blockSignals(True)
                item_text = "" if is_nan_old else str(old_value)
                self.table_widget.item(row, column).setText(item_text)
                self.table_widget.blockSignals(False)

        except Exception as e:
            # コマンド作成中に予期せぬエラーが発生した場合
            logger.exception("セル編集コマンド作成エラー")
            # エラーが起きたら元の値をテーブルに再表示 (Undoはされない)
            try:
                self.table_widget.blockSignals(True)
                original_index = self.view_df.index[row]
                col_name = self.view_df.columns[column]
                original_value = self.dataset.df.loc[original_index, col_name]
                item_text = "" if pd.isna(original_value) else str(original_value)
                self.table_widget.item(row, column).setText(item_text)
                self.table_widget.blockSignals(False)
            except Exception: 
                pass # 復元も失敗した場合はあきらめる

    def _reset_view(self):
        """
        view_df をマスターから再コピーし、ソート状態をリセットし、
        テーブルUIを再描画する。
        """
        self.view_df = self.dataset.df.copy()
        self.sort_state = (None, True)
        self._populate_table()

    def _on_undo_stack_changed(self, index):
        """
        QUndoStack の push/undo/redo で現在位置が変わるたびに呼ばれるスロット。
        コマンド (core/commands.py) は Dataset だけを更新して GUI を一切知らないため、
        テーブルUIの再描画と外部への通知はここで一元的に行う。
        """
        self._reset_view()
        self.dataChanged.emit()

    def _on_add_row(self):
        """行追加ボタンが押された -> AddRowCommand を発行する"""
        command = AddRowCommand(self.dataset)
        self.undo_stack.push(command)

    def _on_delete_rows(self):
        """行削除ボタンが押された -> DeleteRowsCommand を発行する"""
        
        # 1. テーブル (UI) で選択されているアイテムを取得
        selected_items = self.table_widget.selectedItems()
        if not selected_items: return
            
        # 2. 選択されている「表示上の行番号 (view_rows)」を重複なく取得
        view_rows = sorted(list(set(item.row() for item in selected_items)))
        
        # 3. 「表示上の行番号」を「マスターDFのインデックス (loc用)」に変換
        #    (view_df.index がこのマッピングを持っている)
        try:
            original_indices_attempt = [self.view_df.index[row] for row in view_rows]
        except IndexError:
             QMessageBox.warning(self, "削除エラー", "行インデックスの取得に失敗しました。")
             return

        # 4. ★★★ 安全性チェック ★★★
        # (万が一、view_df と dataset.df のインデックスがズレている場合に備える)
        valid_indices_to_delete = [
            idx for idx in original_indices_attempt 
            if idx in self.dataset.df.index
        ]
        
        if not valid_indices_to_delete:
            QMessageBox.warning(self, "削除エラー", "削除対象のデータがマスターに見つかりませんでした。")
            return 

        # 5. Undo のために、削除するデータを「先に」コピーして保存
        deleted_data = self.dataset.df.loc[valid_indices_to_delete].copy()
        
        # 6. コマンドを発行
        command = DeleteRowsCommand(self.dataset, valid_indices_to_delete, deleted_data)
        self.undo_stack.push(command)

    def _on_toggle_mask_rows(self):
        """
        「選択行を除外/解除」ボタンが押された処理(項目36: 外れ値のマスク機能)。
        選択中の行それぞれについて、フィット/プロットからの除外(マスク)状態を
        反転させる。行そのものは削除しない非破壊的な操作で、Undo/Redo可能。
        """
        selected_items = self.table_widget.selectedItems()
        if not selected_items:
            return

        view_rows = sorted(set(item.row() for item in selected_items))
        try:
            master_indices = [self.view_df.index[row] for row in view_rows]
        except IndexError:
            QMessageBox.warning(self, "操作エラー", "行インデックスの取得に失敗しました。")
            return
        master_indices = [idx for idx in master_indices if idx in self.dataset.df.index]
        if not master_indices:
            return

        old_masked = list(self.dataset.masked_row_indices)
        new_masked = list(old_masked)
        for idx in master_indices:
            if idx in new_masked:
                new_masked.remove(idx)
            else:
                new_masked.append(idx)

        command = SetMaskedRowsCommand(self.dataset, old_masked, new_masked)
        self.undo_stack.push(command)

    def _on_add_column(self):
        """列追加ボタンが押された -> AddColumnCommand を発行する"""
        
        # 1. QInputDialog で新しい列名をユーザーに入力させる
        col_name, ok = QInputDialog.getText(self, "列の追加", "新しい列名を入力してください:")
        
        if ok and col_name: # OKが押され、かつ文字列が空でない
            # 2. 列名の重複チェック
            if col_name in self.dataset.df.columns:
                QMessageBox.warning(self, "エラー", f"列名 '{col_name}' は既に存在します。")
                return
            
            # 3. コマンドを発行
            command = AddColumnCommand(self.dataset, col_name)
            self.undo_stack.push(command)

    def _on_delete_column(self):
        """列削除ボタンが押された -> DeleteColumnCommand を発行する"""
        
        # 1. 現在選択されている列（のインデックス）を取得
        current_col_index = self.table_widget.currentColumn()
        if current_col_index == -1:
            QMessageBox.warning(self,"エラー", "削除する列が選択されていません。")
            return
            
        # 2. 表示上の列インデックスから、列名を取得
        col_name = self.view_df.columns[current_col_index]
        
        # 3. ★ 安全性チェック: プロットに使用中の列は削除させない
        if (col_name == self.dataset.x_col_name or 
            col_name == self.dataset.y_col_name):
            
            QMessageBox.warning(self, "削除不可", 
                                f"列 '{col_name}' は現在プロットに使用されているため削除できません。")
            return

        # 4. Undo のために、削除する列データ (Series) をコピーして保存
        deleted_column_data = self.dataset.df[col_name].copy()
        
        # 5. コマンドを発行
        command = DeleteColumnCommand(self.dataset, col_name, deleted_column_data)
        self.undo_stack.push(command)


    def _on_calculate_column(self):
        """
        列計算ボタンが押された -> ColumnCalculatorDialog を表示し、
        safe_eval_column_formula() で計算式を実行する。

        【★ 指摘 ★】
        この操作は Undo/Redo スタックを経由しないため、「元に戻す」ことができません。
        対応するには CalculateColumnCommand(QUndoCommand) の実装が必要です。
        """

        # 1. 現在の列名を計算ダイアログに渡す
        dialog = ColumnCalculatorDialog(self.dataset.df.columns.tolist(), self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            output_col, formula = dialog.get_formula()

            if not output_col or not formula:
                QMessageBox.warning(self, "入力エラー", "出力列または計算式が空です。")
                return

            try:
                # 2. ★ 列名を変数として計算式を評価 ★
                # log() や sin() などの関数、mean()/rolling().mean() などの
                # 許可されたSeriesメソッドが使える(詳細は core/safe_eval.py)。
                #
                # .dataset.df[output_col] = ... と代入することで、
                # 既存列の上書き、または新規列の作成が自動的に行われます。
                self.dataset.df[output_col] = safe_eval_column_formula(self.dataset.df, formula)
                self.dataset.invalidate_visible_df_cache()

                logger.info("計算完了: %s = %s", output_col, formula)
                
                # 3. テーブルUIを更新
                self._reset_view() # (列が追加された可能性があるので _reset_view)
                
                # 4. メインウィンドウに通知
                self.dataChanged.emit() 
                
            except Exception as e:
                # 計算式の評価に失敗した場合 (例: "A +", 未知の列/関数名)
                logger.exception("計算エラー")
                QMessageBox.critical(self, "計算エラー", 
                                     f"計算式の実行に失敗しました:\n\n{e}\n\n"
                                     "列名 (A, B など) や関数 (log(A) など) が正しいか確認してください。")
    
    def _on_calculate_replicate_error(self):
        """
        「誤差の自動計算...」ボタンが押されたときの処理。
        同一条件で複数回測定した列 (反復測定列) から、行ごとの平均と誤差
        (SD/SEM/95%信頼区間) を計算し、新しい2つの列 (平均・誤差) として追加する。
        計算した誤差列は、プロパティ欄の「誤差(エラーバー)の列」からY誤差列として
        選択すれば、そのままグラフにエラーバー表示できる。

        【★ 指摘 ★】_on_calculate_column と同様、この操作はUndo/Redoスタックを
        経由しないため「元に戻す」ことができない(既知の制限。列計算機能と同じ扱い)。
        """
        dialog = ReplicateErrorDialog(self.dataset.df.columns.tolist(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_cols, stat_type, base_name = dialog.get_settings()
        if len(selected_cols) < 2:
            QMessageBox.warning(self, "入力エラー", "反復測定として扱う列を2つ以上選択してください。")
            return
        if not base_name:
            QMessageBox.warning(self, "入力エラー", "出力列名のベースが空です。")
            return

        error_suffix = {"SD": "SD", "SEM": "SEM", "95%CI": "CI95"}[stat_type]
        mean_col_name = f"{base_name}_mean"
        error_col_name = f"{base_name}_{error_suffix}"

        if mean_col_name in self.dataset.df.columns or error_col_name in self.dataset.df.columns:
            QMessageBox.warning(
                self, "エラー",
                f"列名 '{mean_col_name}' または '{error_col_name}' は既に存在します。"
                "別のベース名を指定してください。"
            )
            return

        try:
            # 選択列を数値として扱い、行ごと(反復測定間)の平均・標準偏差・有効データ数を計算
            values = self.dataset.df[selected_cols].apply(pd.to_numeric, errors='coerce')
            mean = values.mean(axis=1)
            std = values.std(axis=1, ddof=1)  # 標本標準偏差 (不偏推定)
            n = values.notna().sum(axis=1)

            if stat_type == "SD":
                error = std
            elif stat_type == "SEM":
                error = std / np.sqrt(n)
            else:  # 95%CI: t分布の臨界値を使う (反復回数が少ない場合に正規近似より正確)
                dof = (n - 1).clip(lower=1)
                t_crit = pd.Series(scipy_stats.t.ppf(0.975, dof), index=dof.index)
                error = t_crit * std / np.sqrt(n)

            self.dataset.df[mean_col_name] = mean
            self.dataset.df[error_col_name] = error
            self.dataset.invalidate_visible_df_cache()

            logger.info(
                "誤差自動計算完了: %s, %s (元列: %s, 統計量: %s)",
                mean_col_name, error_col_name, selected_cols, stat_type
            )

            self._reset_view() # (列が追加されたので再描画)
            self.dataChanged.emit()

        except Exception as e:
            logger.exception("誤差自動計算エラー")
            QMessageBox.critical(self, "計算エラー", f"誤差の計算に失敗しました:\n{e}")

    def _on_save_as_csv(self):
        """現在のDataFrameをCSVファイルとして保存する"""
        
        # 1. 保存ダイアログのデフォルトファイル名を提案
        # (例: data.csv -> data_edited.csv)
        base_name = os.path.splitext(self.dataset.name)[0]
        # (copy) などが含まれていたらそれも削除
        base_name = base_name.split(' (')[0] 
        suggested_name = f"{base_name}_edited.csv"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "CSVとして保存", 
            suggested_name, 
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return # キャンセルされた

        try:
            # 2. DataFrame を CSV に保存
            # index=False : pandas のインデックス（0, 1, 2...）をファイルに保存しない
            # encoding='utf-8-sig' : Excel で開いたときの文字化け（特に日本語）を防ぐ
            self.dataset.df.to_csv(file_path, index=False, encoding='utf-8-sig')
            
            QMessageBox.information(self, "保存完了", f"データをCSVファイルとして保存しました:\n{file_path}")
            
        except Exception as e:
            logger.exception("CSV保存エラー")
            QMessageBox.warning(self, "保存エラー", f"CSVファイルの保存中にエラーが発生しました:\n{e}")
