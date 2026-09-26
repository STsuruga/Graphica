"""
データセットの一覧(ツリー)の管理: 追加・削除・複製、フォルダ、表示/非表示、並べ替え。
データセットに対する個々の操作は graphica.gui.datasets の機能ごとのクラスにある。

ツリーの項目の UserRole には、データセットなら Dataset そのもの、フォルダなら None が入る。
選択を読むときは行番号ではなく _get_current_dataset() / _get_selected_datasets() を使う
(フォルダが入れ子になっていてもデータセットだけを扱えるように)。
"""
import copy
import logging
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QMenu)

from graphica.gui import notify
from graphica.core.commands import (SetDatasetPropertiesCommand, ReorderDatasetsCommand)
from graphica.core.dataset import Dataset
from graphica.gui.datasets.order import DatasetOrder
from graphica.gui.workers import BUILTIN_DATA_FILE_EXTENSIONS
from graphica.core.plugin_api import get_registered_importer_extensions
from graphica.gui.data_editor import DataEditorDialog
from graphica.gui.datasets.actions_menu import populate_dataset_actions_menu
from graphica.gui.dialogs import (NewDatasetDialog)
from graphica.gui.dataset_style_icon import (
    make_dataset_style_icon, make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_VISIBILITY_COLUMN,
)

logger = logging.getLogger(__name__)


class DatasetMixin:
    def _on_add_dataset(self):
        # プラグインが登録した拡張子も選べるようにする
        plugin_extensions = get_registered_importer_extensions()
        plugin_pattern = ''.join(f' *{ext}' for ext in plugin_extensions)
        builtin_pattern = ' '.join(f'*{ext}' for ext in BUILTIN_DATA_FILE_EXTENSIONS)
        file_path, _ = notify.get_open_file_name(
            self, "データファイルを選択", "",
            f"Data Files ({builtin_pattern}{plugin_pattern});;All Files (*)"
        )
        if file_path:
            self.load_data(file_path)

    def _on_create_new_dataset(self):
        """名前・列・行数を指定した空のデータセットを作り、そのままデータエディタで手入力させる。"""
        dialog = NewDatasetDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name = dialog.get_dataset_name()
        column_names = dialog.get_column_names()
        row_count = dialog.get_row_count()

        df = pd.DataFrame({col: [np.nan] * row_count for col in column_names})
        x_col_name = column_names[0]
        y_col_name = column_names[1] if len(column_names) > 1 else column_names[0]

        new_dataset = Dataset(name=name, df=df, x_col_name=x_col_name, y_col_name=y_col_name)
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())

        self._on_show_data_editor()

    def _on_dataset_search_changed(self, text):
        """名前に検索文字列を含むデータセットだけを出す。フォルダは中に1つでも当たりがあれば出す。"""
        self.dataset_order.filter_by_name(text)

    def _on_new_folder(self):
        """選択中がフォルダならその中に、そうでなければ一番上に作る。"""
        name, ok = notify.get_text(self, "新しいフォルダ", "フォルダ名:", text="新しいフォルダ")
        if not ok or not name:
            return

        current_item = self.ui.dataset_list_widget.currentItem()
        parent_item = None
        if current_item is not None and current_item.data(0, Qt.ItemDataRole.UserRole) is None:
            parent_item = current_item

        self._add_dataset_folder_item(name, parent_item)

    def _on_rename_dataset_folder(self):
        """
        フォルダの構造は Undo の対象外なので、名前の変更も Undo しない。
        保存時はツリーの表示文字列を読むので、setText だけで保存にも反映される。
        """
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None or current_item.data(0, Qt.ItemDataRole.UserRole) is not None:
            return
        old_name = current_item.text(0)
        new_name, ok = notify.get_text(self, "フォルダ名を変更", "新しいフォルダ名:", text=old_name)
        if not ok or not new_name:
            return
        current_item.setText(0, new_name)

    def _set_folder_datasets_visibility(self, folder_item, visible):
        """フォルダの中(サブフォルダも)のデータセットをまとめて表示/非表示にする(Undo 1回分)。"""
        dataset_items = self._flatten_dataset_tree(folder_item)
        datasets = [item.data(0, Qt.ItemDataRole.UserRole) for item in dataset_items]
        if not datasets:
            return
        is_batch = len(datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"フォルダ内の表示/非表示切替 ({len(datasets)}件)")
        for ds in datasets:
            self._push_dataset_property_command(
                ds, {'visible': ds.visible}, {'visible': visible},
                description="データセットの表示/非表示切替"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _set_all_datasets_visibility(self, visible):
        """フォルダに関係なく、全データセットをまとめて表示/非表示にする(Undo 1回分)。"""
        datasets = list(self.project.datasets)
        if not datasets:
            return
        is_batch = len(datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"全データセットの表示/非表示切替 ({len(datasets)}件)")
        for ds in datasets:
            self._push_dataset_property_command(
                ds, {'visible': ds.visible}, {'visible': visible},
                description="データセットの表示/非表示切替"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_show_all_datasets(self):
        self._set_all_datasets_visibility(True)

    def _on_hide_all_datasets(self):
        self._set_all_datasets_visibility(False)

    def _on_show_all_in_folder(self):
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None:
            return
        self._set_folder_datasets_visibility(current_item, True)

    def _on_hide_all_in_folder(self):
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None:
            return
        self._set_folder_datasets_visibility(current_item, False)

    def _on_dataset_tree_context_menu(self, pos):
        menu = QMenu(self)
        populate_dataset_actions_menu(self, menu)
        menu.exec(self.ui.dataset_list_widget.viewport().mapToGlobal(pos))

    def _top_level_selected_items(self, items):
        """ほかの選択項目の子孫でないものだけを返す(フォルダと中身が両方選ばれていても二重に消さないため)。"""
        return DatasetOrder.top_level_items(items)

    def _on_remove_dataset(self):
        """選択中のデータセットとフォルダ(中身ごと)を Undo できる形で消す。"""
        selected_items = self.ui.dataset_list_widget.selectedItems()
        if not selected_items:
            return

        self._remove_dataset_items_with_undo(self._top_level_selected_items(selected_items))

    def _find_dataset_row(self, dataset):
        return self.dataset_order.find_row(dataset)

    def _on_dataset_rows_moved(self, source_parent, source_start, source_end, dest_parent, dest_row):
        """
        ツリーのドラッグ&ドロップ後、project.datasets をツリーの並び(=描画の重なり順)に合わせる。
        同じフォルダ内の並べ替えだけ Undo でき、フォルダをまたぐ移動はフォルダ構造と同じく Undo の対象外。
        """
        reordered = self.dataset_order.tree_order()

        if len(reordered) != len(self.project.datasets):
            logger.warning(
                "データセットの並べ替え同期に失敗しました (表示数 %d, 実際 %d)。",
                len(reordered), len(self.project.datasets)
            )
            return

        old_order = list(self.project.datasets)
        # Dataset の == は使えないので同一性で比べる
        if [id(d) for d in reordered] == [id(d) for d in old_order]:
            return

        if source_parent == dest_parent:
            command = ReorderDatasetsCommand(
                self.project, old_order, reordered,
                on_applied=self._on_dataset_order_applied,
                description="データセットの並べ替え"
            )
            self.undo_stack.push(command)
        else:
            self.project.datasets = reordered
            self._update_plot()

    def _on_dataset_order_applied(self):
        """ドロップ処理の最中にツリーを触ると Qt の処理とぶつかるので、同期と再描画は次のイベントループに回す。"""
        QTimer.singleShot(0, self._sync_dataset_list_and_replot)

    def _sync_dataset_list_and_replot(self):
        self._sync_dataset_list_widget_order()
        self._update_plot()

    def _refresh_after_dataset_property_change(self, dataset, changed_keys=(), old_values=None, new_values=None):
        """
        Undo/Redo でデータセットの属性が変わった後に、ツリーの表示・プロパティ欄・描画を合わせる。
        描き直すのは関係する軸だけ。on_applied は Undo と Redo のどちらの後かを教えないので、
        subplot_target の新旧どちらの軸も描き直す。
        """
        item = self._get_dataset_tree_item(dataset)
        if item is not None:
            if item.text(0) != dataset.name:
                item.setText(0, dataset.name)
            item.setIcon(0, make_dataset_style_icon(dataset))
            item.setIcon(DATASET_TREE_VISIBILITY_COLUMN, make_dataset_visibility_icon(dataset))
            apply_dataset_visibility_text_style(item, dataset)
            if item is self.ui.dataset_list_widget.currentItem():
                self.property_panel.update_ui_state()

        axis_index = dataset.subplot_target
        if axis_index >= len(self.canvas.all_axes) or axis_index >= len(self.project.all_plot_settings):
            self._update_plot()
            return

        axis_indices_to_refresh = {axis_index}
        if 'subplot_target' in changed_keys:
            if old_values and 'subplot_target' in old_values:
                axis_indices_to_refresh.add(old_values['subplot_target'])
            if new_values and 'subplot_target' in new_values:
                axis_indices_to_refresh.add(new_values['subplot_target'])
        axis_indices_to_refresh = {
            i for i in axis_indices_to_refresh
            if i < len(self.canvas.all_axes) and i < len(self.project.all_plot_settings)
        }

        layout_mode = getattr(self.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            rows, cols = 0, 0
        else:
            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()

        for idx in axis_indices_to_refresh:
            self.canvas.update_single_axis(
                idx, self.project.datasets, self.project.all_plot_settings[idx],
                rows=rows, cols=cols,
                share_x_axis=getattr(self.project, 'share_x_axis', False),
                share_y_axis=getattr(self.project, 'share_y_axis', False),
                panel_labels_enabled=self.project.panel_labels_enabled,
            )
        is_secondary_visible = any(sa is not None for sa in self.canvas.all_secondary_axes)
        self.tick_direction_y2_label.setVisible(is_secondary_visible)
        self.major_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self.minor_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self.y2_label_text_label.setVisible(is_secondary_visible)
        self.y2_label_text_edit.setVisible(is_secondary_visible)

        self._reapply_editor_row_highlight()
        self._refresh_minimap()
        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()
        self._notify_plugins_datasets_changed()

    def _push_dataset_property_command(self, dataset, old_values: dict, new_values: dict, description: str,
                                       skip_if_unchanged=True):
        """
        Dataset のプロパティ変更を Undo/Redo 可能なコマンドとして発行する共通ヘルパー。
        old_values と new_values が同じ (実質的に変更なし) 場合は何もしない。
        値に DataFrame を含むときは == で比べられないので skip_if_unchanged=False で呼ぶ。
        """
        if skip_if_unchanged and old_values == new_values:
            return
        command = SetDatasetPropertiesCommand(
            dataset, old_values, new_values,
            on_applied=lambda: self._refresh_after_dataset_property_change(
                dataset, changed_keys=new_values.keys(), old_values=old_values, new_values=new_values
            ),
            description=description
        )
        self.undo_stack.push(command)

    def _on_duplicate_dataset(self):
        """選択中のデータセットを、元と同じフォルダに複製する。"""
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

            # DataFrame まで独立させる
            new_dataset = copy.deepcopy(original_dataset)

            new_dataset.name = f"{original_dataset.name} (copy)"

            new_item = self.dataset_order.append(new_dataset, item.parent())
            new_items.append(new_item)

        self.ui.dataset_list_widget.clearSelection()
        for item in new_items:
            item.setSelected(True)
        self.ui.dataset_list_widget.setCurrentItem(new_items[-1])
        self.ui.dataset_list_widget.blockSignals(False)

        self.property_panel.update_ui_state()
        self._update_plot()

    def _on_show_data_editor(self):
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        # 同じデータセットのエディタが開いていれば、作り直さず(並べ替え・位置・選択が消えるので)前に出すだけ
        if self.data_editor_dialog is not None and self.data_editor_dialog.dataset is dataset:
            self.data_editor_dialog.show()
            self.data_editor_dialog.raise_()
            self.data_editor_dialog.activateWindow()
            return

        if self.data_editor_dialog:
            self.data_editor_dialog.close()
            # close() は隠すだけで、親(このタブ)にぶら下がったまま残り続けるので破棄する
            self.data_editor_dialog.deleteLater()
            del self.data_editor_dialog
            self.data_editor_dialog = None

        self.data_editor_dialog = DataEditorDialog(dataset, self)

        self.data_editor_dialog.dataChanged.connect(self.property_panel.on_data_structure_changed)

        # エディタで選んだ行をグラフ上で強調する
        self.data_editor_dialog.rowsHighlighted.connect(self._on_editor_rows_highlighted)

        # 開いたままグラフを操作できるよう非モーダル
        self.data_editor_dialog.show()

    def _on_dataset_tree_item_clicked(self, item, column):
        """
        目アイコンの列のクリックで表示/非表示を切り替える。
        クリックした項目が複数選択に含まれていれば、選択中のすべてをまとめて切り替える。
        """
        if column != DATASET_TREE_VISIBILITY_COLUMN:
            return
        dataset = item.data(0, Qt.ItemDataRole.UserRole)
        if dataset is None:
            return

        new_value = not dataset.visible

        # Dataset の == は使えないので、in ではなく同一性で調べる
        selected_datasets = self._get_selected_datasets()
        is_part_of_multi_selection = len(selected_datasets) > 1 and any(
            ds is dataset for ds in selected_datasets
        )
        targets = selected_datasets if is_part_of_multi_selection else [dataset]

        is_batch = len(targets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"表示/非表示の一括切替 ({len(targets)}件)")
        for ds in targets:
            self._push_dataset_property_command(
                ds,
                {'visible': ds.visible},
                {'visible': new_value},
                description="データセットの表示/非表示切替"
            )
        if is_batch:
            self.undo_stack.endMacro()
