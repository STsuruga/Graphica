# gui/mixins/dataset_mixin.py
"""
データセット (Dataset) の追加/削除/複製、プロパティ編集、フォルダ分け、
曲線フィット・ピーク検出、データエディタ連携をまとめた Mixin。

データセットリスト (self.ui.dataset_list_widget) は QTreeWidget であり、
データセットは「葉 (leaf)」、フォルダは「内部ノード」として表現される。
葉アイテムの Qt.ItemDataRole.UserRole には対応する Dataset オブジェクトそのものを、
フォルダには None を格納することで区別する (main_window.py の
_add_dataset_list_item / _add_dataset_folder_item 参照)。

「現在選択中の1件」や「選択中の全件」を取得する際は、行番号 (currentRow等) では
なく、main_window.py 側の _get_current_dataset() / _get_selected_datasets() を
経由する。これによりフォルダのネストがあっても正しくデータセットだけを扱える。
"""
import copy
import logging
import matplotlib as mpl
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox, QColorDialog, QFileDialog, QInputDialog, QMenu

from core.analysis import calculate_curve_fit, calculate_peaks
from core.commands import SetDatasetPropertiesCommand, ReorderDatasetsCommand
from core.dataset import Dataset
from gui.data_editor import DataEditorDialog
from gui.dialogs import PeakSettingsDialog, FitDialog, ResultDialog

logger = logging.getLogger(__name__)

# エラーバー用の誤差列コンボボックスで「誤差列を使わない」ことを表す選択肢
NO_ERROR_COLUMN_LABEL = "(なし)"


class DatasetMixin:
    def _on_add_dataset(self):
        """「データセット追加」ボタンからの読み込み（Excel対応版）"""
        # ★ .xls と .xlsx をフィルターに追加
        file_path, _ = QFileDialog.getOpenFileName(
            self, "データファイルを選択", "", "Data Files (*.csv *.txt *.xls *.xlsx);;All Files (*)"
        )
        if file_path:
            # 古い読み込み処理は捨てて、一番下にある load_data メソッドに処理を任せる
            self.load_data(file_path)

    def _on_new_folder(self):
        """
        「新しいフォルダ」ボタンが押されたときの処理。
        現在選択されているアイテムがフォルダなら、その子フォルダとして作成する
        (ネスト構造を作れる)。それ以外は最上位に作成する。
        """
        name, ok = QInputDialog.getText(self, "新しいフォルダ", "フォルダ名:", text="新しいフォルダ")
        if not ok or not name:
            return

        current_item = self.ui.dataset_list_widget.currentItem()
        parent_item = None
        if current_item is not None and current_item.data(0, Qt.ItemDataRole.UserRole) is None:
            parent_item = current_item # 選択中がフォルダなら、その子として作成

        self._add_dataset_folder_item(name, parent_item)

    def _on_dataset_tree_context_menu(self, pos):
        """データセットツリーを右クリックしたときのコンテキストメニュー"""
        menu = QMenu(self)
        new_folder_action = menu.addAction("新しいフォルダ")
        new_folder_action.triggered.connect(self._on_new_folder)

        if self.ui.dataset_list_widget.selectedItems():
            menu.addSeparator()
            remove_action = menu.addAction("削除")
            remove_action.triggered.connect(self._on_remove_dataset)

        menu.exec(self.ui.dataset_list_widget.viewport().mapToGlobal(pos))

    def _top_level_selected_items(self, items):
        """
        選択されたアイテムのうち、他の選択アイテムの子孫であるものを除いた
        「実質的に一番上位にある」アイテムだけを返す。
        (フォルダとその中のデータセットが同時に選択されている場合に、
         フォルダの削除だけで子も一緒に消えるようにするため)
        """
        item_set = {id(it) for it in items}
        result = []
        for item in items:
            ancestor = item.parent()
            nested_under_selected = False
            while ancestor is not None:
                if id(ancestor) in item_set:
                    nested_under_selected = True
                    break
                ancestor = ancestor.parent()
            if not nested_under_selected:
                result.append(item)
        return result

    def _on_remove_dataset(self):
        """
        「データセット削除」ボタンが押されたときの処理。
        選択中の(複数可)データセット・フォルダをリストとUIから削除する。
        フォルダを削除すると、その中のデータセットもまとめて削除される。
        """
        selected_items = self.ui.dataset_list_widget.selectedItems()
        if not selected_items:
            return # 何も選択されていない

        # フォルダの中身も含め、削除対象のデータセットをすべて収集する
        datasets_to_remove = []

        def collect(item):
            dataset = item.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                datasets_to_remove.append(dataset)
            else:
                for i in range(item.childCount()):
                    collect(item.child(i))

        for item in selected_items:
            collect(item)

        # 【★ 重要 ★】
        # これからUIツリーを操作する。操作中に currentItemChanged が
        # 意図せず発行されるのを防ぐため、シグナルを一時的にブロックする。
        self.ui.dataset_list_widget.blockSignals(True)

        # project.datasets から削除 (インデックスがずれないよう降順で処理)
        rows_to_remove = sorted(
            {row for ds in datasets_to_remove if (row := self._find_dataset_row(ds)) != -1},
            reverse=True
        )
        for row in rows_to_remove:
            del self.project.datasets[row]

        # UIツリーから、選択された最上位アイテムだけを削除する
        # (子アイテムも同時に選択されていても、親を消せば一緒に消えるため二重削除は避ける)
        for item in self._top_level_selected_items(selected_items):
            parent = item.parent()
            if parent is not None:
                parent.removeChild(item)
            else:
                idx = self.ui.dataset_list_widget.indexOfTopLevelItem(item)
                if idx != -1:
                    self.ui.dataset_list_widget.takeTopLevelItem(idx)

        self.ui.dataset_list_widget.blockSignals(False)

        # UIの状態を更新 (プロパティ欄などを無効化)
        self._update_ui_state()

        # グラフを再描画
        self._update_plot()

    def _find_dataset_row(self, dataset):
        """
        project.datasets の中で、指定した Dataset インスタンスが何行目にあるかを返す。
        (Dataset は dataclass で値ベースの __eq__ を持ち、フィールドに DataFrame を
         含むため `list.index()` は使えない (DataFrame の真偽値判定でエラーになる)。
         そのため `is` によるオブジェクト同一性で検索する。)
        """
        for i, ds in enumerate(self.project.datasets):
            if ds is dataset:
                return i
        return -1

    def _on_dataset_rows_moved(self, source_parent, source_start, source_end, dest_parent, dest_row):
        """
        dataset_list_widget (ツリー) 内でドラッグ&ドロップによる移動が行われた後に
        呼ばれるスロット (ツリーの内部モデルの rowsMoved シグナルに接続)。

        project.datasets の順序がそのままプロットの描画順(=重なり順。後から描画された
        ものが手前に表示される)を決めているため、ツリーの表示順 (先行順に辿った
        データセットの並び) に合わせて project.datasets を並べ替える。

        - 同じ親 (フォルダ) 内での並べ替えの場合のみ、Undo/Redo 可能な
          ReorderDatasetsCommand として発行する。
        - フォルダをまたぐ移動 (フォルダ構造そのものの変更) は、データセットの
          追加/削除/複製と同様、現状 Undo 非対応の単純な操作として扱う
          (フォルダ構造ごとのUndoは対象外)。
        """
        reordered = [item.data(0, Qt.ItemDataRole.UserRole) for item in self._flatten_dataset_tree()]

        if len(reordered) != len(self.project.datasets):
            logger.warning(
                "データセットの並べ替え同期に失敗しました (表示数 %d, 実際 %d)。",
                len(reordered), len(self.project.datasets)
            )
            return

        old_order = list(self.project.datasets)
        # Dataset は値ベースの __eq__ (DataFrameを含む) を持つため、順序の比較は
        # `==` ではなくオブジェクト同一性 (id) のリストで行う。
        if [id(d) for d in reordered] == [id(d) for d in old_order]:
            return # 実質的な順序変化なし (誤検知の rowsMoved など)

        if source_parent == dest_parent:
            # 同じ親内での純粋な並べ替え -> Undo/Redo可能に
            command = ReorderDatasetsCommand(
                self.project, old_order, reordered,
                on_applied=self._on_dataset_order_applied,
                description="データセットの並べ替え"
            )
            self.undo_stack.push(command)
        else:
            # フォルダをまたぐ移動 -> 直接反映 (Undo非対応)
            self.project.datasets = reordered
            self._update_plot()

    def _on_dataset_order_applied(self):
        """
        ReorderDatasetsCommand の redo/undo 後に呼ばれるコールバック。
        ドラッグ&ドロップ操作自身の呼び出しスタックの中で dataset_list_widget を
        直接いじると再入 (Qt内部のドロップ処理と衝突) の恐れがあるため、
        ウィジェットの同期とプロット再描画は次のイベントループに遅延させる。
        """
        QTimer.singleShot(0, self._sync_dataset_list_and_replot)

    def _sync_dataset_list_and_replot(self):
        self._sync_dataset_list_widget_order()
        self._update_plot()

    def _refresh_after_dataset_property_change(self, dataset):
        """
        Undo/Redo でデータセットのプロパティが変更された後の共通後処理。
        - 変更されたデータセットがリストに表示されている名前と食い違っていれば同期
        - 変更されたデータセットが現在選択中なら、プロパティパネルにも反映
        - グラフを再描画
        """
        item = self._get_dataset_tree_item(dataset)
        if item is not None:
            if item.text(0) != dataset.name:
                item.setText(0, dataset.name)
            if item is self.ui.dataset_list_widget.currentItem():
                self._update_ui_state()
        self._update_plot()

    def _push_dataset_property_command(self, dataset, old_values: dict, new_values: dict, description: str):
        """
        Dataset のプロパティ変更を Undo/Redo 可能なコマンドとして発行する共通ヘルパー。
        old_values と new_values が同じ (実質的に変更なし) 場合は何もしない。
        """
        if old_values == new_values:
            return
        command = SetDatasetPropertiesCommand(
            dataset, old_values, new_values,
            on_applied=lambda: self._refresh_after_dataset_property_change(dataset),
            description=description
        )
        self.undo_stack.push(command)

    def _on_subplot_target_changed(self, index):
        """
        データセットの「描画先プロット」コンボボックスが変更されたときに呼び出されます。

        Args:
            index (int): 新しく選択された描画先の軸インデックス。
        """
        dataset = self._get_current_dataset()
        if dataset is None or index == -1:
            return
        if dataset.subplot_target == index:
            return

        # Dataset オブジェクトが持つ描画先インデックスを更新
        # (データが移動するため、外観のみの更新ではなく _update_plot による全体再描画が必要。
        #  これは _refresh_after_dataset_property_change 内で行われる)
        self._push_dataset_property_command(
            dataset,
            {'subplot_target': dataset.subplot_target},
            {'subplot_target': index},
            description="描画先プロットの変更"
        )

    def _on_dataset_selected(self, current_item, previous_item):
        """
        UIのデータセットリスト (dataset_list_widget) で選択されている項目が
        変更されたときに呼び出されるスロット。

        Args:
            current_item (QTreeWidgetItem): 新しく選択されたアイテム。
            previous_item (QTreeWidgetItem): 以前選択されていたアイテム。
        """
        # 選択状態が変わったので、UI全体の状態を更新するヘルパーメソッドを呼ぶ
        # (_update_ui_state が、選択されたデータセットのプロパティをUIにロードする)
        self._update_ui_state()

    def _on_legend_name_changed(self):
        """
        「凡例名」テキストボックス (legend_name_edit) の編集が完了したときに
        呼び出されるスロット (editingFinished シグナル)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        new_name = self.ui.legend_name_edit.text()

        # Dataset オブジェクトの name 属性を更新 (Undo/Redo可能にする)
        # リスト表示の同期とプロット再描画は _refresh_after_dataset_property_change が行う
        self._push_dataset_property_command(
            dataset,
            {'name': dataset.name},
            {'name': new_name},
            description="凡例名の変更"
        )

    def _on_property_changed(self):
        """
        データセットのプロパティ (プロットタイプ、線種、マーカー、平滑化など) の
        UIコントロールが変更されたときに呼び出されるスロット。
        6つの異なるUIコントロールがすべてこのスロットに接続されているため、
        self.sender() でどのウィジェットが変更されたかを特定し、
        「そのプロパティだけ」を選択中の(複数可)全データセットに一括適用する。
        (仮に全プロパティを常に一括適用してしまうと、複数選択時に選択されている
        データセット同士でプロパティ値が異なる場合、触っていないプロパティまで
        1つの値に揃えられてしまうため)
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        marker_text = self.ui.marker_combo.currentText()
        # ウィジェット -> (属性名, 現在のUI値) の対応表
        field_by_widget = {
            self.ui.plot_type_combo: ('plot_type', self.ui.plot_type_combo.currentText()),
            self.ui.linestyle_combo: ('linestyle', self.ui.linestyle_combo.currentText()),
            self.ui.linewidth_spinbox: ('linewidth', self.ui.linewidth_spinbox.value()),
            # ★ UIで "None" が選択されたら、属性には None を設定
            self.ui.marker_combo: ('marker', None if marker_text == 'None' else marker_text),
            self.ui.markersize_spinbox: ('markersize', self.ui.markersize_spinbox.value()),
            self.ui.smoothing_checkbox: ('smoothing', self.ui.smoothing_checkbox.isChecked()),
            self.alpha_spinbox: ('alpha', self.alpha_spinbox.value()),
        }

        changed = field_by_widget.get(self.sender())
        if changed is None:
            return # 想定外の呼び出し元 (通常は発生しない)
        attr_name, new_value = changed

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"プロパティの一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset, {attr_name: getattr(dataset, attr_name)}, {attr_name: new_value},
                description="プロパティ変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_change_dataset_color(self):
        """
        データセットの色選択ボタン (color_button) がクリックされたときの処理。
        QColorDialog を表示し、選択された色を Dataset に適用します。
        複数のデータセットが選択されている場合は、全てに同じ色を適用し、
        1回のUndo/Redoでまとめて元に戻せるようにする。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        # 1. 色選択ダイアログを表示
        color = QColorDialog.getColor() # QColor オブジェクトが返る

        # 2. 有効な色が選択されたか確認 (Cancel されなかったか)
        if not color.isValid():
            return
        new_color = color.name()

        # 3. Undo/Redo可能なコマンドとして発行
        #    複数選択時は beginMacro/endMacro で1つの操作としてまとめる
        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"データセットの色を一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset,
                {'color': dataset.color},
                {'color': new_color},
                description="データセットの色変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_auto_assign_colors(self):
        """
        「自動配色」ボタンが押されたときの処理。
        選択中の(複数可)データセットに、matplotlibの既定カラーサイクル
        (tab10など、rcParamsで設定されているもの) を順番に自動で割り当てる。
        手動で1つずつ色を選ぶ手間を省くための一括操作。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        color_cycle = mpl.rcParams['axes.prop_cycle'].by_key()['color']

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"配色の自動割り当て ({len(selected_datasets)}件)")
        for i, dataset in enumerate(selected_datasets):
            new_color = color_cycle[i % len(color_cycle)]
            self._push_dataset_property_command(
                dataset,
                {'color': dataset.color},
                {'color': new_color},
                description="配色の自動割り当て"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _update_ui_state(self):
        """
        アプリケーションの現在の状態 (主にデータセットの選択状態) に基づいて、
        UIの有効/無効、表示/非表示、および内容を更新する。
        _on_dataset_selected や _on_remove_dataset などから呼び出される。
        """

        # 1. サブプロット関連のコンボボックス（選択肢）を更新
        self._update_subplot_combos()

        # 2. データセットリストの選択状態を取得
        # ★ フォルダも選択可能なため、「何か選択されているか」(フォルダ含む。主に
        #   削除ボタン用) と「データセットが選択されているか」(色変更等、
        #   データセット固有の操作用) を分けて扱う。
        current_dataset = self._get_current_dataset()
        selected_datasets = self._get_selected_datasets()
        has_any_selection = bool(self.ui.dataset_list_widget.selectedItems())
        has_dataset_selection = bool(selected_datasets)

        # 3. 選択状態に基づいて、UIの有効/無効を一括設定

        # 「データセットプロパティ」ドックウィジェット (中身の GroupBox)
        self.ui.properties_groupbox.setEnabled(has_dataset_selection)

        # データセットリストタブのボタン
        self.ui.remove_dataset_button.setEnabled(has_any_selection) # フォルダの削除も許可
        self.duplicate_dataset_button.setEnabled(has_dataset_selection)
        self.view_edit_data_button.setEnabled(has_dataset_selection)
        self.auto_color_button.setEnabled(has_dataset_selection)

        # (フィット/ピークボタン)
        self.fit_curve_button.setEnabled(has_dataset_selection)
        self.find_peaks_button.setEnabled(has_dataset_selection)

        # プロパティタブ内のコンボボックス (setEnabled(has_dataset_selection) に含まれるが明示)
        self.subplot_target_combo.setEnabled(has_dataset_selection)
        self.use_secondary_y_checkbox.setEnabled(has_dataset_selection)
        self.x_col_combo.setEnabled(has_dataset_selection)
        self.y_col_combo.setEnabled(has_dataset_selection)
        self.x_err_col_combo.setEnabled(has_dataset_selection)
        self.y_err_col_combo.setEnabled(has_dataset_selection)

        # 4. 【選択中】の場合: 選択された Dataset の内容をUIにロード
        #    (current_dataset は「カレント」アイテムがフォルダの場合や、
        #     何も選択されていない場合は None になる)
        if current_dataset is not None:
            dataset = current_dataset

            # 4b. ★★★ シグナルを一時的にブロック ★★★
            # (これからコードでUIの値をセットするため、シグナルが発火するのを防ぐ)
            self.ui.legend_name_edit.blockSignals(True)
            self.ui.plot_type_combo.blockSignals(True)
            self.ui.color_button.blockSignals(True)
            self.ui.linestyle_combo.blockSignals(True)
            self.ui.linewidth_spinbox.blockSignals(True)
            self.ui.marker_combo.blockSignals(True)
            self.ui.markersize_spinbox.blockSignals(True)
            self.ui.smoothing_checkbox.blockSignals(True)
            self.alpha_spinbox.blockSignals(True)
            self.use_secondary_y_checkbox.blockSignals(True)
            self.subplot_target_combo.blockSignals(True)

            # 4c. Dataset オブジェクトの値をUIにロード
            self.ui.legend_name_edit.setText(dataset.name)
            self.ui.plot_type_combo.setCurrentText(dataset.plot_type)
            self.ui.linestyle_combo.setCurrentText(dataset.linestyle)
            self.ui.linewidth_spinbox.setValue(dataset.linewidth)
            self.ui.marker_combo.setCurrentText(dataset.marker if dataset.marker is not None else 'None')
            self.ui.markersize_spinbox.setValue(dataset.markersize)
            self.ui.smoothing_checkbox.setChecked(dataset.smoothing)
            self.alpha_spinbox.setValue(dataset.alpha)
            self.use_secondary_y_checkbox.setChecked(dataset.use_secondary_y)
            self.subplot_target_combo.setCurrentIndex(dataset.subplot_target)

            # 4d. ★★★ シグナルを解除 ★★★
            self.ui.legend_name_edit.blockSignals(False)
            self.ui.plot_type_combo.blockSignals(False)
            self.ui.color_button.blockSignals(False)
            self.ui.linestyle_combo.blockSignals(False)
            self.ui.linewidth_spinbox.blockSignals(False)
            self.ui.marker_combo.blockSignals(False)
            self.ui.markersize_spinbox.blockSignals(False)
            self.ui.smoothing_checkbox.blockSignals(False)
            self.alpha_spinbox.blockSignals(False)
            self.use_secondary_y_checkbox.blockSignals(False)
            self.subplot_target_combo.blockSignals(False)

            # 4e. X/Y軸コンボボックスの更新処理 (シグナルブロックを含む)
            self.x_col_combo.blockSignals(True)
            self.y_col_combo.blockSignals(True)

            all_columns = dataset.df.columns.tolist()
            self.x_col_combo.clear()
            self.y_col_combo.clear()
            self.x_col_combo.addItems(all_columns)
            self.y_col_combo.addItems(all_columns)

            # 現在の列名を選択状態にする
            self.x_col_combo.setCurrentText(dataset.x_col_name)
            self.y_col_combo.setCurrentText(dataset.y_col_name)

            self.x_col_combo.blockSignals(False)
            self.y_col_combo.blockSignals(False)

            # 4e-2. エラーバー用の誤差列コンボボックス ("(なし)" を先頭に追加)
            self.x_err_col_combo.blockSignals(True)
            self.y_err_col_combo.blockSignals(True)

            self.x_err_col_combo.clear()
            self.y_err_col_combo.clear()
            self.x_err_col_combo.addItems([NO_ERROR_COLUMN_LABEL] + all_columns)
            self.y_err_col_combo.addItems([NO_ERROR_COLUMN_LABEL] + all_columns)
            self.x_err_col_combo.setCurrentText(dataset.x_err_col_name or NO_ERROR_COLUMN_LABEL)
            self.y_err_col_combo.setCurrentText(dataset.y_err_col_name or NO_ERROR_COLUMN_LABEL)

            self.x_err_col_combo.blockSignals(False)
            self.y_err_col_combo.blockSignals(False)

            # 4f. フィット情報UIの更新
            if dataset.fit_info:
                self.fit_info_label.setVisible(True)
                self.fit_info_textedit.setVisible(True)
                self.fit_info_textedit.setText(dataset.fit_info)
            else:
                self.fit_info_label.setVisible(False)
                self.fit_info_textedit.setVisible(False)
                self.fit_info_textedit.clear()

        # 5. 【非選択中 (またはフォルダ選択中)】の場合: UIをクリア
        else:
            self.x_col_combo.clear()
            self.y_col_combo.clear()
            self.x_err_col_combo.clear()
            self.y_err_col_combo.clear()

            self.fit_info_label.setVisible(False)
            self.fit_info_textedit.setVisible(False)
            self.fit_info_textedit.clear()

    def _on_duplicate_dataset(self):
        """
        「プロット複製」ボタンが押されたときの処理。選択中の(複数可)データセットを複製する。
        複製先は元のデータセットと同じフォルダ (兄弟) にする。
        """
        selected_items = [
            item for item in self.ui.dataset_list_widget.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole) is not None
        ]
        if not selected_items:
            return

        self.ui.dataset_list_widget.blockSignals(True)
        new_items = []
        for item in selected_items:
            original_dataset = item.data(0, Qt.ItemDataRole.UserRole)

            # ★★★ deepcopy が重要 ★★★
            # Dataset オブジェクト (特に中の DataFrame df) を完全に複製する
            new_dataset = copy.deepcopy(original_dataset)

            # 新しい名前を付ける (例: "data.csv (copy)")
            new_dataset.name = f"{original_dataset.name} (copy)"

            # リストとUIに追加 (元のデータセットと同じ親フォルダに)
            self.project.datasets.append(new_dataset)
            new_item = self._add_dataset_list_item(new_dataset, item.parent())
            new_items.append(new_item)

        # 複製されたアイテムをまとめて選択状態にする
        self.ui.dataset_list_widget.clearSelection()
        for item in new_items:
            item.setSelected(True)
        self.ui.dataset_list_widget.setCurrentItem(new_items[-1])
        self.ui.dataset_list_widget.blockSignals(False)

        # UIの状態とグラフを更新
        self._update_ui_state()
        self._update_plot()

    def _on_show_data_editor(self):
        """「データ表示/編集」ボタンが押されたときの処理。DataEditorDialog を表示する"""
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        # 1. もし古いダイアログが画面に残っていれば、閉じて削除する
        #    (これにより、常に選択中のデータセットに対応したエディタが表示される)
        if self.data_editor_dialog:
            self.data_editor_dialog.close() # ウィンドウを閉じる
            # self.data_editor_dialog.deleteLater() # より安全な削除方法 (任意)
            del self.data_editor_dialog
            self.data_editor_dialog = None # 参照をクリア

        # 2. 新しい DataEditorDialog を作成し、インスタンス変数に保持する
        self.data_editor_dialog = DataEditorDialog(dataset, self)

        # 3. ダイアログの dataChanged シグナルを、メインウィンドウの
        #    _on_data_structure_changed スロットに接続する。
        #    (エディタでの変更を検知するため)
        self.data_editor_dialog.dataChanged.connect(self._on_data_structure_changed)

        # 4. exec() (モーダル) の代わりに show() (非モーダル) で表示する
        #    (エディタを開いたままメインウィンドウを操作できるようにするため)
        self.data_editor_dialog.show()

    def _on_plot_column_changed(self):
        """
        「X軸の列」または「Y軸の列」コンボボックスが変更されたときに呼び出される。
        Dataset オブジェクトの x_col_name / y_col_name を更新し、プロットを再描画する。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        # 新しい列名を取得
        new_x_col = self.x_col_combo.currentText()
        new_y_col = self.y_col_combo.currentText()

        # 実際に変更がある列だけを old/new_values に含める
        # (コンボボックスが空の場合もあるため、空でないかチェック)
        old_values, new_values = {}, {}
        if new_x_col and new_x_col in dataset.df.columns and new_x_col != dataset.x_col_name:
            old_values['x_col_name'] = dataset.x_col_name
            new_values['x_col_name'] = new_x_col
        if new_y_col and new_y_col in dataset.df.columns and new_y_col != dataset.y_col_name:
            old_values['y_col_name'] = dataset.y_col_name
            new_values['y_col_name'] = new_y_col

        # Undo/Redo可能なコマンドとして発行 (X/Yが同時に変わった場合は1つの操作としてまとめる)
        self._push_dataset_property_command(dataset, old_values, new_values, description="プロット列の変更")

    def _on_error_column_changed(self):
        """
        「X誤差列」または「Y誤差列」コンボボックスが変更されたときに呼び出される。
        Dataset オブジェクトの x_err_col_name / y_err_col_name を更新し、
        エラーバー付きでプロットを再描画する。"(なし)" が選択された場合は
        None (エラーバー非表示) を設定する。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        new_x_err = self.x_err_col_combo.currentText()
        new_y_err = self.y_err_col_combo.currentText()
        new_x_err_col = None if (not new_x_err or new_x_err == NO_ERROR_COLUMN_LABEL) else new_x_err
        new_y_err_col = None if (not new_y_err or new_y_err == NO_ERROR_COLUMN_LABEL) else new_y_err

        old_values, new_values = {}, {}
        if new_x_err_col != dataset.x_err_col_name:
            old_values['x_err_col_name'] = dataset.x_err_col_name
            new_values['x_err_col_name'] = new_x_err_col
        if new_y_err_col != dataset.y_err_col_name:
            old_values['y_err_col_name'] = dataset.y_err_col_name
            new_values['y_err_col_name'] = new_y_err_col

        self._push_dataset_property_command(dataset, old_values, new_values, description="誤差列(エラーバー)の変更")

    def _on_data_structure_changed(self):
        """
        DataEditorDialog から dataChanged シグナルを受け取ったときに呼び出されるスロット。
        データの構造 (値/列/行) が変更された可能性があるため、UIとプロットを更新する。
        """
        if self._get_current_dataset() is None:
            return # (通常はエディタが開いている＝選択中のはずだが念のため)

        # ★ UIの状態(主にX/Y列コンボボックス)を最新のDataFrame情報で更新
        self._update_ui_state()
        # ★ プロットを最新のデータで更新
        self._update_plot()

    def _on_fit_curve(self):
        """「曲線フィット」ボタンが押されたときの処理"""
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return
        x_data, y_data = original_dataset.x_data, original_dataset.y_data

        # ダイアログからフィットの種類を取得
        fit_type = FitDialog.get_fit_type(self)
        if fit_type is None:
            return

        try:
            # ★ 計算はすべて分離したモジュールに丸投げ
            popt, params_info, x_fit, y_fit = calculate_curve_fit(x_data, y_data, fit_type)
        except Exception as e:
            QMessageBox.warning(self, "フィットエラー", f"フィッティングに失敗しました:\n{e}")
            return

        # 結果文字列の作成
        result_text = f"[{fit_type}] のフィッティング結果:\n"
        for param_name, param_value in zip(params_info, popt):
            result_text += f"  {param_name} = {param_value: .4e}\n"

        # UI/Modelへの反映 (Datasetの追加。元のデータセットと同じフォルダに追加する)
        fit_df = pd.DataFrame({'x_fit': x_fit, 'y_fit': y_fit})
        fit_dataset = Dataset(
            name=f"Fit ({original_dataset.name})",
            df=fit_df,
            x_col_name='x_fit', y_col_name='y_fit',
            color=original_dataset.color, linestyle='--', marker='None',
            linewidth=original_dataset.linewidth,
            use_secondary_y=original_dataset.use_secondary_y,
            subplot_target=original_dataset.subplot_target,
            fit_info=result_text
        )

        self.project.datasets.append(fit_dataset)
        original_item = self._get_dataset_tree_item(original_dataset)
        self._add_dataset_list_item(fit_dataset, original_item.parent() if original_item else None)
        self._update_plot()

        # ★ グラフを見ながら結果を確認できるよう、非モーダル・スクロール可能なダイアログで表示する
        if self.fit_result_dialog is not None:
            self.fit_result_dialog.close()
        fit_csv_data = pd.DataFrame({'パラメータ': params_info, '値': popt})
        self.fit_result_dialog = ResultDialog("フィッティング完了", result_text, self, csv_data=fit_csv_data)
        self.fit_result_dialog.show()

    def _on_secondary_y_changed(self):
        """
        「第2Y軸 (右側) を使用」チェックボックスが変更されたときの処理。
        複数選択時は選択中の全データセットに一括適用する。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        new_value = self.use_secondary_y_checkbox.isChecked()

        # Dataset オブジェクトの use_secondary_y 属性を Undo/Redo可能に更新
        # (軸の割り当てが変わるため、プロット全体の再描画が必要。
        #  これは _refresh_after_dataset_property_change 内で行われる)
        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"第2Y軸使用の一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset,
                {'use_secondary_y': dataset.use_secondary_y},
                {'use_secondary_y': new_value},
                description="第2Y軸使用の変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_find_peaks(self):
        """「ピーク検出」ボタンが押されたときの処理"""
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data, y_data = original_dataset.x_data, original_dataset.y_data

        if len(x_data) < 3:
            QMessageBox.warning(self, "ピーク検出", "データ点数が少なすぎます (最低3点必要)。")
            return

        settings = PeakSettingsDialog.get_peak_settings(self)
        if settings is None:
            return

        peak_type = settings.get("peak_type", "上に凸 (Peaks)")

        try:
            # ★ 計算はモジュールに丸投げ
            peak_x, peak_y = calculate_peaks(x_data, y_data, peak_type, settings)
        except Exception as e:
            QMessageBox.warning(self, "ピーク検出エラー", f"エラーが発生しました:\n{e}")
            return

        if len(peak_x) == 0:
            QMessageBox.information(self, "ピーク検出", f"指定された条件で {peak_type} は見つかりませんでした。")
            return

        # 結果文字列の作成 (X座標順にソート)
        sort_order = np.argsort(peak_x)
        result_text = f"検出された {peak_type} ({len(peak_x)}個):\n  X座標\t\tY座標\n" + "-"*30 + "\n"
        for i in sort_order:
            result_text += f"  {peak_x[i]:.4g}\t\t{peak_y[i]:.4g}\n"

        # UI/Modelへの反映 (元のデータセットと同じフォルダに追加する)
        peak_marker = 'v' if "下に凸" not in peak_type else '^'
        peak_color = 'red' if "下に凸" not in peak_type else 'blue'

        peaks_df = pd.DataFrame({'peak_x': peak_x, 'peak_y': peak_y})
        peak_dataset = Dataset(
            name=f"{peak_type.split(' ')[0]} ({original_dataset.name})",
            df=peaks_df,
            x_col_name='peak_x', y_col_name='peak_y',
            plot_type='Scatter', color=peak_color, linestyle='None',
            marker=peak_marker, markersize=8,
            use_secondary_y=original_dataset.use_secondary_y,
            subplot_target=original_dataset.subplot_target
        )

        self.project.datasets.append(peak_dataset)
        original_item = self._get_dataset_tree_item(original_dataset)
        self._add_dataset_list_item(peak_dataset, original_item.parent() if original_item else None)
        self._update_plot()

        # ★ グラフを見ながら結果を確認できるよう、非モーダル・スクロール可能なダイアログで表示する
        # (検出数が多いと行数が非常に多くなりうるため、スクロールできることが重要)
        if self.peak_result_dialog is not None:
            self.peak_result_dialog.close()
        peak_csv_data = pd.DataFrame({'X座標': peak_x[sort_order], 'Y座標': peak_y[sort_order]})
        self.peak_result_dialog = ResultDialog("ピーク検出完了", result_text, self, csv_data=peak_csv_data)
        self.peak_result_dialog.show()
