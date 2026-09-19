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
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFileDialog, QInputDialog, QMenu)

from graphica.core.commands import (SetDatasetPropertiesCommand, ReorderDatasetsCommand)
from graphica.core.dataset import Dataset
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
        """「データセット追加」ボタンからの読み込み（Excel対応版）"""
        # ★ .xls と .xlsx をフィルターに追加
        # プラグインがregister_importer()(項目B-1)で登録した拡張子も追加する
        plugin_extensions = get_registered_importer_extensions()
        plugin_pattern = ''.join(f' *{ext}' for ext in plugin_extensions)
        builtin_pattern = ' '.join(f'*{ext}' for ext in BUILTIN_DATA_FILE_EXTENSIONS)
        file_path, _ = QFileDialog.getOpenFileName(
            self, "データファイルを選択", "",
            f"Data Files ({builtin_pattern}{plugin_pattern});;All Files (*)"
        )
        if file_path:
            # 古い読み込み処理は捨てて、一番下にある load_data メソッドに処理を任せる
            self.load_data(file_path)

    def _on_create_new_dataset(self):
        """
        「新規データセット作成...」ボタンが押されたときの処理(項目63)。
        ファイル読み込みを介さず、名前・列名・初期行数を指定した空のDatasetを作成し、
        その場でデータエディタを開いて手入力できるようにする。
        """
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

        # 作成直後、そのままデータエディタを開いて手入力できるようにする
        self._on_show_data_editor()

    def _on_dataset_search_changed(self, text):
        """
        データセット検索ボックスの入力が変わるたびに呼ばれる。
        名前が検索文字列を含むデータセットだけを表示し、それ以外は非表示にする。
        フォルダは、中に一致するデータセットが1つでもあれば表示する
        (検索文字列が空のときはすべて表示する)。
        """
        query = text.strip().lower()

        def apply_filter(item):
            dataset = item.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                visible = (not query) or (query in dataset.name.lower())
                item.setHidden(not visible)
                return visible
            else:
                any_child_visible = False
                for i in range(item.childCount()):
                    if apply_filter(item.child(i)):
                        any_child_visible = True
                item.setHidden(bool(query) and not any_child_visible)
                return any_child_visible or not query

        root = self.ui.dataset_list_widget.invisibleRootItem()
        for i in range(root.childCount()):
            apply_filter(root.child(i))

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

    def _on_rename_dataset_folder(self):
        """
        実機フィードバック(「データセットのフォルダ名編集」)。選択中のフォルダの
        名前を変更する。フォルダ構造自体はUndo/Redo管理の対象外(_on_new_folder
        によるフォルダ作成も同様に非対応)のため、リネームも同じ方針で扱う。
        _capture_dataset_group_tree()は保存の都度ツリーウィジェットの表示
        テキストを読み取って構築するだけなので、setText(0, ...)だけで
        永続化上も反映される。
        """
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None or current_item.data(0, Qt.ItemDataRole.UserRole) is not None:
            return  # データセット項目、または未選択なら対象外
        old_name = current_item.text(0)
        new_name, ok = QInputDialog.getText(self, "フォルダ名を変更", "新しいフォルダ名:", text=old_name)
        if not ok or not new_name:
            return
        current_item.setText(0, new_name)

    def _set_folder_datasets_visibility(self, folder_item, visible):
        """folder_item配下(再帰的に、サブフォルダも含む)の全データセットの
        表示/非表示をまとめて切り替える(項目C-907の一括版)。"""
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
        """
        プロジェクト全体の全データセットの表示/非表示をまとめて切り替える
        (項目150、C-907の一括表示切替)。フォルダ限定の
        _set_folder_datasets_visibility とは異なり、フォルダ構造に関わらず
        プロジェクト内の全データセットを対象にする。
        """
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
        """「すべて表示」メニューの処理(項目150、C-907)。"""
        self._set_all_datasets_visibility(True)

    def _on_hide_all_datasets(self):
        """「すべて非表示」メニューの処理(項目150、C-907)。"""
        self._set_all_datasets_visibility(False)

    def _on_show_all_in_folder(self):
        """実機フィードバック(「フォルダの表示非表示追加」)。選択中のフォルダ内の
        全データセットを表示状態にする。"""
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None:
            return
        self._set_folder_datasets_visibility(current_item, True)

    def _on_hide_all_in_folder(self):
        """選択中のフォルダ内の全データセットを非表示状態にする。"""
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None:
            return
        self._set_folder_datasets_visibility(current_item, False)

    def _on_dataset_tree_context_menu(self, pos):
        menu = QMenu(self)
        populate_dataset_actions_menu(self, menu)
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

        ★ 改善ボード A-3: 以前はここで project.datasets を直接書き換えており
        Undo できなかった(誤削除するとデータ・スタイル・フィット結果・マスク・
        注釈がまとめて復旧不能になっていた)。実際の削除・復元処理は
        main_window._remove_dataset_items_with_undo() に集約し、
        RemoveDatasetCommand 経由で undo_stack に載せる。
        """
        selected_items = self.ui.dataset_list_widget.selectedItems()
        if not selected_items:
            return # 何も選択されていない

        # 選択された最上位アイテムだけを対象にする
        # (子アイテムも同時に選択されていても、親を消せば一緒に消えるため二重削除は避ける)
        self._remove_dataset_items_with_undo(self._top_level_selected_items(selected_items))

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
          複製などと同様、現状 Undo 非対応の単純な操作として扱う
          (フォルダ構造ごとのUndoは対象外)。削除は改善ボード A-3 で
          RemoveDatasetCommand によりUndo可能になっている。
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

    def _refresh_after_dataset_property_change(self, dataset, changed_keys=(), old_values=None, new_values=None):
        """
        Undo/Redo でデータセットのプロパティが変更された後の共通後処理。
        - 変更されたデータセットがリストに表示されている名前と食い違っていれば同期
        - 変更されたデータセットが現在選択中なら、プロパティパネルにも反映
        - グラフを再描画(軽量な該当Axesのみの更新で足りる)

        ★ 項目C-003フェーズ3a: 以前は`subplot_target`/`use_secondary_y`の
        変更を「軸の所属自体が変わる構造的な変更」として一律フルの
        `_update_plot()`(`redraw_all`、全Axes再構築)に振り分けていたが、
        実際には`use_secondary_y`は現在の`subplot_target`軸1つだけで完結し、
        `subplot_target`自体の変更も「旧軸から消える・新軸に現れる」という
        2つのAxesだけで完結する(Axesの枚数・GridSpec配置自体は変わらない)
        ため、`update_single_axis()`を対象Axesの数ぶん呼ぶだけで軽量に
        対応できる。`SetDatasetPropertiesCommand.on_applied`はredo/undo
        どちらの後でも同じコールバックが呼ばれる(方向を教えてくれない)ため、
        `old_values`/`new_values`の両方から`subplot_target`の候補値を集め、
        現在値(`dataset.subplot_target`)と合わせて集合として重複排除する
        ことで、redo/undoのどちら向きでも新旧両方のAxesを正しく更新できる。
        """
        item = self._get_dataset_tree_item(dataset)
        if item is not None:
            if item.text(0) != dataset.name:
                item.setText(0, dataset.name)
            item.setIcon(0, make_dataset_style_icon(dataset))
            # ★ 項目C-907: visible属性は変わっていなくても、目アイコン/文字色の
            #   再同期はコストが小さいためプロパティ変更のたびに毎回行う
            #   (visibleだけ選んで特別扱いする分岐を増やさないほうがシンプル)。
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
        self.property_panel.update_ui_state()
        self._update_plot()

    def _on_show_data_editor(self):
        """「データ表示/編集」ボタンが押されたときの処理。DataEditorDialog を表示する"""
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        # 0. 実機フィードバック(「データエディタが背面に行くと表に出すのが
        #    面倒」、ユーザー選択: 「タスクバー化+再クリックで最前面」):
        #    既に同じデータセットのエディタが開いている場合、閉じて作り直す
        #    (=ソート状態・スクロール位置・選択中の行が失われる)のではなく、
        #    既存のウィンドウをそのまま最前面に呼び戻すだけにする。
        if self.data_editor_dialog is not None and self.data_editor_dialog.dataset is dataset:
            self.data_editor_dialog.show()
            self.data_editor_dialog.raise_()
            self.data_editor_dialog.activateWindow()
            return

        # 1. もし別のデータセット用の古いダイアログが画面に残っていれば、閉じて削除する
        #    (これにより、常に選択中のデータセットに対応したエディタが表示される)
        if self.data_editor_dialog:
            self.data_editor_dialog.close() # ウィンドウを閉じる
            # ★ バグ修正: close()はQDialogを非表示にするだけでC++オブジェクトは
            # 破棄しない。このダイアログはself(メインウィンドウ)を親に持つため、
            # 別のデータセットに切り替えるたびに古いインスタンス(QTableWidgetや
            # 自身のQUndoStackごと)が非表示のまま親にぶら下がり続け、プロセス
            # 終了までメモリに残っていた(データエディタを開き直すたびに蓄積する
            # リーク)。deleteLater()で実際の破棄をスケジュールする。
            self.data_editor_dialog.deleteLater()
            del self.data_editor_dialog
            self.data_editor_dialog = None # 参照をクリア

        # 2. 新しい DataEditorDialog を作成し、インスタンス変数に保持する
        self.data_editor_dialog = DataEditorDialog(dataset, self)

        # 3. ダイアログの dataChanged シグナルを、メインウィンドウの
        #    property_panel.on_data_structure_changed スロットに接続する。
        #    (エディタでの変更を検知するため)
        self.data_editor_dialog.dataChanged.connect(self.property_panel.on_data_structure_changed)

        # 3b. データエディタで選択した行 <-> グラフ上のハイライトを連動させる
        self.data_editor_dialog.rowsHighlighted.connect(self._on_editor_rows_highlighted)

        # 4. exec() (モーダル) の代わりに show() (非モーダル) で表示する
        #    (エディタを開いたままメインウィンドウを操作できるようにするため)
        self.data_editor_dialog.show()

    def _on_dataset_tree_item_clicked(self, item, column):
        """
        データセットリスト(ツリー)のアイテムがクリックされたときの処理(項目C-907)。
        目アイコン専用列(DATASET_TREE_VISIBILITY_COLUMN)のクリックだけを拾い、
        対応するデータセットの表示/非表示 (visible) を Undo/Redo 可能にトグルする。
        削除ではなく非表示化なので、データやスタイル設定はそのまま保持される。

        複数選択中に、その選択に含まれるアイテムの目アイコンをクリックした場合は
        (property_panel.on_secondary_y_changed 等、既存の一括変更と同じ方針で) 選択中の全データセットへ
        まとめて適用する。選択に含まれないアイテムを単独クリックした場合は
        そのデータセット1件だけを切り替える。
        """
        if column != DATASET_TREE_VISIBILITY_COLUMN:
            return
        dataset = item.data(0, Qt.ItemDataRole.UserRole)
        if dataset is None:
            # フォルダアイテムには目アイコン列は無い(表示/非表示の対象外)
            return

        new_value = not dataset.visible

        # ★ Dataset は値ベースの __eq__ を持つ dataclass (df列を含むため
        #   `in` 演算子で == 比較されると DataFrame の真偽値判定エラーになる、
        #   _find_dataset_row のコメント参照)。選択中に含まれるかどうかは
        #   オブジェクト同一性(is)で判定する。
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
