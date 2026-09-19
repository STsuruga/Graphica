import os
import logging
import re
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                               QTableWidget, QTableWidgetItem, QMenuBar,
                               QInputDialog, QMessageBox, QFileDialog, QDialogButtonBox)
from PySide6.QtGui import QUndoStack, QKeySequence, QColor
from PySide6.QtCore import Signal, Qt

logger = logging.getLogger(__name__)

from graphica.core.commands import (EditCellCommand, AddRowCommand, DeleteRowsCommand,
                           AddColumnCommand, DeleteColumnCommand, SetMaskedRowsCommand,
                           RenameColumnCommand)
from graphica.core.safe_eval import safe_eval_column_formula
from graphica.gui.dialogs import (ColumnCalculatorDialog, ReplicateErrorDialog, ColumnStringOpsDialog,
                         ColumnVisibilityDialog, FindReplaceDialog)
from graphica.gui import icon_utils
from graphica.gui import theme


def _masked_row_background():
    """マスク済み行の背景色を、現在のテーマトークンから解決する。"""
    return QColor(theme.current_tokens()["surface_2"])


def _nan_cell_background():
    """欠損値のセルの背景。マスクした行(行全体の印)とは別の色にする。"""
    return QColor(theme.current_tokens()["warning_soft"])


class DataEditorDialog(QDialog):
    """dataset.df の表示と編集。編集は Undo できる(列の計算など一部を除く)。"""
    
    # データが変わったことを PlotterApp に知らせる
    dataChanged = Signal()

    # 選んだ行の df.index ラベル(空なら選択なし)。グラフ側で強調するため
    rowsHighlighted = Signal(list)
    
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        # 独立したウィンドウにして、タスクバーや Alt+Tab から呼び戻せるようにする。親は残すので本体と一緒に閉じる
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle(f"データエディタ: {dataset.name}")
        self.resize(800, 600)
        
        self.dataset = dataset
        
        # 並べ替えは表示用のコピーに対して行い、dataset.df は変えない
        self.view_df = self.dataset.df.copy()
        self.sort_state = (None, True)  # (並べ替え中の列名, 昇順か)

        # 隠した列の名前(表示だけで dataset.df は変えない)
        self._hidden_columns = set()

        # 開いたままにして、「次を検索」を前回の続きから探す
        self._find_replace_dialog = None
        self._last_search_query = None
        self._last_search_index = -1

        self.undo_stack = QUndoStack(self)
        # コマンドは GUI を知らないので、表の描き直しと通知はここでする
        self.undo_stack.indexChanged.connect(self._on_undo_stack_changed)

        self.table_widget = QTableWidget()
        self.table_widget.setSortingEnabled(False)  # 並べ替えは view_df で自前で行う
        self.table_widget.horizontalHeader().setSectionsClickable(True)
        self.table_widget.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table_widget.horizontalHeader().sectionDoubleClicked.connect(self._on_header_double_clicked)
        # 列の並べ替えも見た目だけ(dataset.df の列順は変えない)
        self.table_widget.horizontalHeader().setSectionsMovable(True)
        self.table_widget.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._populate_table()
        
        button_layout = QHBoxLayout()
        self.add_row_button = QPushButton("行を追加")
        self.delete_row_button = QPushButton("選択行を削除")
        self.mask_rows_button = QPushButton("選択行を除外/解除")
        self.add_col_button = QPushButton("列を追加")
        self.delete_col_button = QPushButton("選択列を削除")
        self.calc_button = QPushButton("列の計算...")
        self.replicate_error_button = QPushButton("誤差の自動計算...")
        self.string_ops_button = QPushButton("文字列操作...")
        self.column_visibility_button = QPushButton("列の表示/非表示...")
        self.find_replace_button = QPushButton("検索/置換...")
        self.jump_to_row_button = QPushButton("行へ移動...")
        self.save_csv_button = QPushButton("CSVとして保存...")

        _button_icons = (
            (self.add_row_button, "row-insert-bottom"),
            (self.delete_row_button, "row-remove"),
            (self.mask_rows_button, "eye-off"),
            (self.add_col_button, "column-insert-right"),
            (self.delete_col_button, "column-remove"),
            (self.calc_button, "calculator"),
            (self.replicate_error_button, "math-function"),
            (self.string_ops_button, "typography"),
            (self.column_visibility_button, "eye"),
            (self.find_replace_button, "search"),
            (self.jump_to_row_button, "arrow-right"),
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
            # フォーカスが残ると :focus の枠が次の操作まで出たままになる
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        button_layout.addWidget(self.add_row_button)
        button_layout.addWidget(self.delete_row_button)
        button_layout.addWidget(self.mask_rows_button)
        button_layout.addStretch()
        button_layout.addWidget(self.add_col_button)
        button_layout.addWidget(self.delete_col_button)
        button_layout.addStretch()
        button_layout.addWidget(self.calc_button)
        button_layout.addWidget(self.replicate_error_button)
        button_layout.addWidget(self.string_ops_button)
        button_layout.addStretch()
        button_layout.addWidget(self.column_visibility_button)
        button_layout.addWidget(self.find_replace_button)
        button_layout.addWidget(self.jump_to_row_button)
        button_layout.addStretch()
        button_layout.addWidget(self.save_csv_button)


        main_layout = QVBoxLayout(self)
        
        menu_bar = QMenuBar(self)
        edit_menu = menu_bar.addMenu("編集")
        
        undo_action = self.undo_stack.createUndoAction(self, "元に戻す")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        
        redo_action = self.undo_stack.createRedoAction(self, "やり直し")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)
        
        main_layout.setMenuBar(menu_bar)


        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.table_widget)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        self.table_widget.cellChanged.connect(self._on_cell_changed)
        
        self.add_row_button.clicked.connect(self._on_add_row)
        self.delete_row_button.clicked.connect(self._on_delete_rows)
        self.mask_rows_button.clicked.connect(self._on_toggle_mask_rows)
        self.add_col_button.clicked.connect(self._on_add_column)
        self.delete_col_button.clicked.connect(self._on_delete_column)
        self.calc_button.clicked.connect(self._on_calculate_column)
        self.replicate_error_button.clicked.connect(self._on_calculate_replicate_error)
        self.string_ops_button.clicked.connect(self._on_column_string_ops)
        self.column_visibility_button.clicked.connect(self._on_toggle_column_visibility)
        self.find_replace_button.clicked.connect(self._on_open_find_replace)
        self.jump_to_row_button.clicked.connect(self._on_jump_to_row)
        self.save_csv_button.clicked.connect(self._on_save_as_csv)

    def _populate_table(self):
        """view_df を表に入れる。NaN / NaT は空欄で出す。"""
        df = self.view_df
        
        # 入れている間に cellChanged が出ないように
        self.table_widget.blockSignals(True) 
        
        self.table_widget.setRowCount(len(df))
        self.table_widget.setColumnCount(len(df.columns))
        self.table_widget.setHorizontalHeaderLabels(df.columns)
        
        # 行の見出しは df.index のラベル(並べ替えてもどの行か分かる)
        self.table_widget.setVerticalHeaderLabels([str(i) for i in df.index])

        for i in range(len(df)):
            is_masked = df.index[i] in self.dataset.masked_row_indices
            for j in range(len(df.columns)):
                value = df.iloc[i, j]

                is_nan = pd.isna(value)
                item_text = "" if is_nan else str(value)

                item = QTableWidgetItem(item_text)
                if is_masked:
                    item.setBackground(_masked_row_background())
                    item.setToolTip("この行はフィット/プロットから除外されています")
                elif is_nan:
                    # マスクした行は行全体に色が付いているので重ねない
                    item.setBackground(_nan_cell_background())
                    item.setToolTip("欠損値(NaN)です")
                self.table_widget.setItem(i, j, item)
        
        self.table_widget.resizeColumnsToContents()

        # 表を作り直すたびに隠す列を当て直す(並べ替え・列の追加・Undo の後も消えないように)
        for col_idx, col_name in enumerate(df.columns):
            self.table_widget.setColumnHidden(col_idx, col_name in self._hidden_columns)

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

        self.table_widget.blockSignals(False)

    def _on_header_clicked(self, logical_index):
        """その列で並べ替える(同じ列なら昇順と降順を入れ替える)。表示だけで、データと Undo には影響しない。"""
        col_name = self.view_df.columns[logical_index]
        current_col, current_ascending = self.sort_state
        ascending = (not current_ascending) if current_col == col_name else True

        try:
            # 安定な並べ替え(同じ値の行の順を保つ)
            self.view_df = self.view_df.sort_values(by=col_name, ascending=ascending, kind='mergesort')
        except TypeError:
            # 型の混ざった列は並べ替えられないことがある
            QMessageBox.warning(self, "ソートエラー", f"列 '{col_name}' はソートできませんでした。")
            return

        self.sort_state = (col_name, ascending)
        self._populate_table()

    def _on_header_double_clicked(self, logical_index):
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
        """選んだ行の dataset.df の index ラベル。view_df は並べ替えてあるので view_df.index を通す。"""
        rows = sorted({index.row() for index in self.table_widget.selectionModel().selectedRows()})
        return [self.view_df.index[r] for r in rows if r < len(self.view_df.index)]

    def _on_table_selection_changed(self):
        self.rowsHighlighted.emit(self.get_selected_master_indices())

    def select_row_by_master_index(self, master_index):
        """グラフの点から表の行を選ぶ(逆向きの強調)。通知が往復しないよう itemSelectionChanged を止める。"""
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
        self.rowsHighlighted.emit([])
        super().closeEvent(event)

    def _on_cell_changed(self, row, column):
        try:
            # row は表示上の行番号なので、view_df.index で df のラベルにする
            original_index = self.view_df.index[row]
            col_name = self.view_df.columns[column]
            
            old_value = self.dataset.df.loc[original_index, col_name]
            
            new_value_str = self.table_widget.item(row, column).text()
            
            new_value = None
            
            if new_value_str == "":
                new_value = np.nan
            else:
                original_dtype = self.dataset.df[col_name].dtype
                
                try:
                    # bool 列は np.bool_("False") が True になるので自前で読む
                    if np.issubdtype(original_dtype, np.bool_):
                        normalized = new_value_str.strip().lower()
                        if normalized in ("true", "1", "yes"):
                            new_value = True
                        elif normalized in ("false", "0", "no"):
                            new_value = False
                        else:
                            raise ValueError(f"'{new_value_str}' を真偽値として解釈できません")
                    else:
                        new_value = np.dtype(original_dtype).type(new_value_str)
                except (ValueError, TypeError):
                    # 数値と bool の列は NaN にする(文字列のまま入れると列全体が object 型になる)
                    if np.issubdtype(original_dtype, np.number) or np.issubdtype(original_dtype, np.bool_):
                        new_value = np.nan
                    else:
                        new_value = new_value_str
            
            # NaN 同士は != で比べられない
            is_nan_old = pd.isna(old_value)
            is_nan_new = pd.isna(new_value)
            
            if (is_nan_old and not is_nan_new) or \
               (not is_nan_old and is_nan_new) or \
               (not is_nan_old and not is_nan_new and old_value != new_value):
                
                command = EditCellCommand(self.dataset, original_index, col_name, old_value, new_value)
                self.undo_stack.push(command)
            
            else:
                # 変わっていなくても表示を整える("1.0" を "1.0" に編集したときなど)
                self.table_widget.blockSignals(True)
                item_text = "" if is_nan_old else str(old_value)
                self.table_widget.item(row, column).setText(item_text)
                self.table_widget.blockSignals(False)

        except Exception:
            logger.exception("セル編集コマンド作成エラー")
            # 元の値を表示し直す。シグナルは必ず戻す(止めたままだと以後の編集が無視される)。
            self.table_widget.blockSignals(True)
            try:
                original_index = self.view_df.index[row]
                col_name = self.view_df.columns[column]
                original_value = self.dataset.df.loc[original_index, col_name]
                item_text = "" if pd.isna(original_value) else str(original_value)
                self.table_widget.item(row, column).setText(item_text)
            except Exception:
                logger.exception("セルの表示を元の値に戻せませんでした")
            finally:
                self.table_widget.blockSignals(False)

    def _reset_view(self):
        """view_df を dataset.df から取り直し、並べ替えを戻して描き直す。"""
        self.view_df = self.dataset.df.copy()
        self.sort_state = (None, True)
        self._populate_table()

    def _on_undo_stack_changed(self, index):
        self._reset_view()
        self.dataChanged.emit()

    def _on_add_row(self):
        command = AddRowCommand(self.dataset)
        self.undo_stack.push(command)

    def _on_delete_rows(self):
        selected_items = self.table_widget.selectedItems()
        if not selected_items: return
            
        view_rows = sorted(list(set(item.row() for item in selected_items)))
        
        try:
            original_indices_attempt = [self.view_df.index[row] for row in view_rows]
        except IndexError:
             QMessageBox.warning(self, "削除エラー", "行インデックスの取得に失敗しました。")
             return

        # view_df と dataset.df の index がずれていた場合に備える
        valid_indices_to_delete = [
            idx for idx in original_indices_attempt 
            if idx in self.dataset.df.index
        ]
        
        if not valid_indices_to_delete:
            QMessageBox.warning(self, "削除エラー", "削除対象のデータがマスターに見つかりませんでした。")
            return 

        # Undo のため、消す前に写しを取る
        deleted_data = self.dataset.df.loc[valid_indices_to_delete].copy()
        
        command = DeleteRowsCommand(self.dataset, valid_indices_to_delete, deleted_data)
        self.undo_stack.push(command)

    def _on_toggle_mask_rows(self):
        """選んだ行のマスクを反転する(行は消さない。Undo できる)。"""
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
        col_name, ok = QInputDialog.getText(self, "列の追加", "新しい列名を入力してください:")
        
        if ok and col_name:
            if col_name in self.dataset.df.columns:
                QMessageBox.warning(self, "エラー", f"列名 '{col_name}' は既に存在します。")
                return
            
            command = AddColumnCommand(self.dataset, col_name)
            self.undo_stack.push(command)

    def _on_delete_column(self):
        current_col_index = self.table_widget.currentColumn()
        if current_col_index == -1:
            QMessageBox.warning(self,"エラー", "削除する列が選択されていません。")
            return
            
        col_name = self.view_df.columns[current_col_index]
        
        # 描画に使っている列は消させない
        if (col_name == self.dataset.x_col_name or 
            col_name == self.dataset.y_col_name):
            
            QMessageBox.warning(self, "削除不可", 
                                f"列 '{col_name}' は現在プロットに使用されているため削除できません。")
            return

        deleted_column_data = self.dataset.df[col_name].copy()
        
        command = DeleteColumnCommand(self.dataset, col_name, deleted_column_data)
        self.undo_stack.push(command)


    def _on_calculate_column(self):
        """列の計算。Undo できない。"""

        dialog = ColumnCalculatorDialog(self.dataset.df.columns.tolist(), self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            output_col, formula = dialog.get_formula()

            if not output_col or not formula:
                QMessageBox.warning(self, "入力エラー", "出力列または計算式が空です。")
                return

            try:
                self.dataset.df[output_col] = safe_eval_column_formula(self.dataset.df, formula)
                self.dataset.invalidate_visible_df_cache()

                logger.info("計算完了: %s = %s", output_col, formula)
                
                self._reset_view()
                
                self.dataChanged.emit() 
                
            except Exception as e:
                logger.exception("計算エラー")
                QMessageBox.critical(self, "計算エラー", 
                                     f"計算式の実行に失敗しました:\n\n{e}\n\n"
                                     "列名 (A, B など) や関数 (log(A) など) が正しいか確認してください。")
    
    def _on_calculate_replicate_error(self):
        """反復測定の列から行ごとの平均と誤差(SD / SEM / 95%CI)を2つの列として足す。Undo できない。"""
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
            values = self.dataset.df[selected_cols].apply(pd.to_numeric, errors='coerce')
            mean = values.mean(axis=1)
            std = values.std(axis=1, ddof=1)
            n = values.notna().sum(axis=1)

            if stat_type == "SD":
                error = std
            elif stat_type == "SEM":
                error = std / np.sqrt(n)
            else:  # 95%CI は t 分布で(反復が少ないと正規近似より正確)
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

            self._reset_view()
            self.dataChanged.emit()

        except Exception as e:
            logger.exception("誤差自動計算エラー")
            QMessageBox.critical(self, "計算エラー", f"誤差の計算に失敗しました:\n{e}")

    def _on_column_string_ops(self):
        """列の分割・結合・数値の抽出。結果は新しい列に入れる(既存の列は上書きしない)。Undo できない。"""
        dialog = ColumnStringOpsDialog(self.dataset.df.columns.tolist(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        mode = dialog.get_mode()

        if mode == ColumnStringOpsDialog.MODE_SPLIT:
            source_col, delimiter, prefix = dialog.get_split_settings()
            if not delimiter:
                QMessageBox.warning(self, "入力エラー", "区切り文字が空です。")
                return
            prefix = prefix or source_col
            try:
                split_result = self.dataset.df[source_col].astype(str).str.split(delimiter, expand=True)
            except Exception as e:
                logger.exception("列の分割エラー")
                QMessageBox.critical(self, "列の分割エラー", f"分割に失敗しました:\n{e}")
                return
            new_names = []
            for i in range(split_result.shape[1]):
                name = f"{prefix}_{i + 1}"
                while name in self.dataset.df.columns or name in new_names:
                    name = f"{name}_2"
                new_names.append(name)
            for name, col_idx in zip(new_names, split_result.columns):
                self.dataset.df[name] = split_result[col_idx]
            self.dataset.invalidate_visible_df_cache()
            logger.info("列の分割完了: %s -> %s (区切り文字: %r)", source_col, new_names, delimiter)

        elif mode == ColumnStringOpsDialog.MODE_MERGE:
            selected_cols, separator, output_col = dialog.get_merge_settings()
            if len(selected_cols) < 2:
                QMessageBox.warning(self, "入力エラー", "結合する列を2つ以上選択してください。")
                return
            if not output_col:
                QMessageBox.warning(self, "入力エラー", "出力列名が空です。")
                return
            if output_col in self.dataset.df.columns:
                QMessageBox.warning(self, "入力エラー", f"列名 '{output_col}' は既に存在します。")
                return
            try:
                merged = self.dataset.df[selected_cols[0]].astype(str)
                for col in selected_cols[1:]:
                    merged = merged + separator + self.dataset.df[col].astype(str)
            except Exception as e:
                logger.exception("列の結合エラー")
                QMessageBox.critical(self, "列の結合エラー", f"結合に失敗しました:\n{e}")
                return
            self.dataset.df[output_col] = merged
            self.dataset.invalidate_visible_df_cache()
            logger.info("列の結合完了: %s -> %s (区切り文字: %r)", selected_cols, output_col, separator)

        else:
            source_col, pattern, output_col = dialog.get_extract_settings()
            if not pattern:
                QMessageBox.warning(self, "入力エラー", "正規表現が空です。")
                return
            if not output_col:
                QMessageBox.warning(self, "入力エラー", "出力列名が空です。")
                return
            if output_col in self.dataset.df.columns:
                QMessageBox.warning(self, "入力エラー", f"列名 '{output_col}' は既に存在します。")
                return
            try:
                extracted = self.dataset.df[source_col].astype(str).str.extract(f"({pattern})", expand=False)
                values = pd.to_numeric(extracted, errors='coerce')
            except Exception as e:
                logger.exception("数値抽出エラー")
                QMessageBox.critical(self, "数値抽出エラー", f"正規表現が不正です:\n{e}")
                return
            self.dataset.df[output_col] = values
            self.dataset.invalidate_visible_df_cache()
            logger.info("数値抽出完了: %s -> %s (パターン: %r)", source_col, output_col, pattern)

        self._reset_view()
        self.dataChanged.emit()

    def _on_toggle_column_visibility(self):
        """チェックを外した列を隠す(表示だけ)。"""
        dialog = ColumnVisibilityDialog(self.view_df.columns.tolist(), self._hidden_columns, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._hidden_columns = set(dialog.get_hidden_columns())
        for col_idx, col_name in enumerate(self.view_df.columns):
            self.table_widget.setColumnHidden(col_idx, col_name in self._hidden_columns)

    def _on_open_find_replace(self):
        """開いていれば前面に出すだけ。"""
        if self._find_replace_dialog is None:
            self._find_replace_dialog = FindReplaceDialog(self.dataset.df.columns.tolist(), self)
            self._find_replace_dialog.find_next_button.clicked.connect(self._on_find_next)
            self._find_replace_dialog.replace_all_button.clicked.connect(self._on_replace_all)
        self._find_replace_dialog.show()
        self._find_replace_dialog.raise_()
        self._find_replace_dialog.activateWindow()

    def _on_find_next(self):
        """前回見つけた位置の次から、行優先で大文字小文字を区別せず部分一致で探す。検索語が変われば最初から。"""
        dialog = self._find_replace_dialog
        query = dialog.get_search_text()
        if not query:
            dialog.set_status("検索文字列を入力してください")
            return

        target_col = dialog.get_target_column()
        df = self.view_df
        columns = [target_col] if target_col else list(df.columns)
        if not columns or len(df) == 0:
            dialog.set_status("検索対象のデータがありません")
            return

        if self._last_search_query != query:
            self._last_search_index = -1
            self._last_search_query = query

        cells = [(r, c) for r in range(len(df)) for c in columns]
        total = len(cells)
        for offset in range(1, total + 1):
            idx = (self._last_search_index + offset) % total
            row, col_name = cells[idx]
            value = df.iloc[row][col_name]
            if pd.isna(value):
                continue
            if query.lower() in str(value).lower():
                col_index = df.columns.get_loc(col_name)
                self.table_widget.setCurrentCell(row, col_index)
                item = self.table_widget.item(row, col_index)
                if item is not None:
                    self.table_widget.scrollToItem(item)
                self._last_search_index = idx
                dialog.set_status(f"見つかりました(表示上の{row + 1}行目、列「{col_name}」)")
                return

        dialog.set_status("見つかりませんでした")

    def _on_replace_all(self):
        """一致する全セルを置き換え、1つの Undo にまとめる。

        置き換えた値は文字列なので、対象は文字列の列だけ(数値などの列は丸ごと object 型になってしまう)。
        """
        dialog = self._find_replace_dialog
        query = dialog.get_search_text()
        replacement = dialog.get_replace_text()
        if not query:
            dialog.set_status("検索文字列を入力してください")
            return

        target_col = dialog.get_target_column()
        all_columns = [target_col] if target_col else list(self.dataset.df.columns)
        columns = [c for c in all_columns if self.dataset.df[c].dtype == object]
        skipped_non_string = len(all_columns) - len(columns)

        matches = []  # (行ラベル, 列名, 旧値, 新値)
        for col_name in columns:
            for row_label, value in self.dataset.df[col_name].items():
                if pd.isna(value):
                    continue
                text = str(value)
                new_text = re.sub(re.escape(query), replacement, text, flags=re.IGNORECASE)
                if new_text != text:
                    matches.append((row_label, col_name, value, new_text))

        if not matches:
            note = "(数値/真偽値/日付列は置換対象外です)" if skipped_non_string else ""
            dialog.set_status(f"置換対象が見つかりませんでした{note}")
            return

        self.undo_stack.beginMacro(f"検索/置換 ({len(matches)}件)")
        for row_label, col_name, old_value, new_value in matches:
            self.undo_stack.push(EditCellCommand(self.dataset, row_label, col_name, old_value, new_value))
        self.undo_stack.endMacro()

        note = "(数値/真偽値/日付列は置換対象外です)" if skipped_non_string else ""
        dialog.set_status(f"{len(matches)}件を置換しました{note}")

    def _on_jump_to_row(self):
        """表示上の行番号(1始まり)の行を選んで見せる。"""
        if len(self.view_df) == 0:
            QMessageBox.information(self, "行へ移動", "テーブルにデータがありません。")
            return
        row_number, ok = QInputDialog.getInt(
            self, "行へ移動", f"移動先の行番号 (1〜{len(self.view_df)}):",
            1, 1, len(self.view_df)
        )
        if not ok:
            return
        row_index = row_number - 1
        self.table_widget.setCurrentCell(row_index, 0)
        item = self.table_widget.item(row_index, 0)
        if item is not None:
            self.table_widget.scrollToItem(item)

    def _on_save_as_csv(self):
        base_name = os.path.splitext(self.dataset.name)[0]
        base_name = base_name.split(' (')[0] 
        suggested_name = f"{base_name}_edited.csv"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "CSVとして保存", 
            suggested_name, 
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return

        try:
            # utf-8-sig でないと Excel で開いたとき日本語が化ける
            self.dataset.df.to_csv(file_path, index=False, encoding='utf-8-sig')
            
            QMessageBox.information(self, "保存完了", f"データをCSVファイルとして保存しました:\n{file_path}")
            
        except Exception as e:
            logger.exception("CSV保存エラー")
            QMessageBox.warning(self, "保存エラー", f"CSVファイルの保存中にエラーが発生しました:\n{e}")
