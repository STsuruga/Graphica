import logging
from PySide6.QtGui import QUndoCommand

logger = logging.getLogger(__name__)


#==============================================================================
# Undo/Redo コマンドクラス群
#==============================================================================
# 各コマンドは Dataset (core層) の公開メソッドのみを呼び出し、
# GUI (DataEditorDialog) の内部実装には一切依存しない。
# テーブルUIの再描画や dataChanged シグナルの発行は、
# DataEditorDialog 側で QUndoStack.indexChanged に接続して行う。

class EditCellCommand(QUndoCommand):
    """
    テーブル内のセル値を編集するコマンド。
    DataEditorDialog の _on_cell_changed から発行されます。
    """
    def __init__(self, dataset, row_idx, col_name, old_value, new_value, description="セル編集"):
        """
        Args:
            dataset (Dataset): 編集対象の Dataset。
            row_idx: マスターDataFrame (dataset.df) のインデックス (loc用)。
            col_name (str): 編集対象の列名。
            old_value (any): 変更前の値。
            new_value (any): 変更後の値。
            description (str): Undo/Redoメニューに表示されるテキスト。
        """
        super().__init__(description)
        self.dataset = dataset
        self.row_idx = row_idx
        self.col_name = col_name
        self.old_value = old_value
        self.new_value = new_value

    def redo(self):
        self.dataset.set_cell(self.row_idx, self.col_name, self.new_value)

    def undo(self):
        self.dataset.set_cell(self.row_idx, self.col_name, self.old_value)


class AddRowCommand(QUndoCommand):
    """行を（末尾に）追加するコマンド"""
    def __init__(self, dataset, description="行追加"):
        super().__init__(description)
        self.dataset = dataset

    def redo(self):
        self.dataset.add_row()

    def undo(self):
        self.dataset.delete_last_row()


class DeleteRowsCommand(QUndoCommand):
    """選択された複数の行を削除するコマンド"""
    def __init__(self, dataset, row_indices, deleted_data, description="行削除"):
        """
        Args:
            dataset (Dataset): 編集対象の Dataset。
            row_indices (list): 削除するマスターDFのインデックス (loc用) のリスト。
            deleted_data (pd.DataFrame): 削除される行のデータ (undo用)。
            description (str): 説明テキスト。
        """
        super().__init__(description)
        self.dataset = dataset
        self.row_indices = row_indices
        self.deleted_data = deleted_data

    def redo(self):
        self.dataset.delete_rows(self.row_indices)

    def undo(self):
        self.dataset.restore_rows(self.deleted_data)


class AddColumnCommand(QUndoCommand):
    """（末尾に）列を追加するコマンド"""
    def __init__(self, dataset, col_name, description="列追加"):
        super().__init__(description)
        self.dataset = dataset
        self.col_name = col_name

    def redo(self):
        self.dataset.add_column(self.col_name)

    def undo(self):
        # ★ 安全性チェック:
        # もし redo (列追加) の後に、ユーザーがその列をプロット軸 (X/Y) に
        # 設定した場合、undo (列削除) するとプロットがエラーになる。
        # そのため、プロットに使われている場合は undo を中止する。
        if self.dataset.is_column_in_use(self.col_name):
            logger.warning("Undo不可: 列 '%s' はプロットに使用されています。", self.col_name)
            self.setObsolete(True)
            return
        self.dataset.remove_column(self.col_name)


class DeleteColumnCommand(QUndoCommand):
    """選択された列を削除するコマンド"""
    def __init__(self, dataset, col_name, deleted_column_data, description="列削除"):
        """
        Args:
            dataset (Dataset): 編集対象の Dataset。
            col_name (str): 削除する列名。
            deleted_column_data (pd.Series): 削除される列のデータ (undo用)。
            description (str): 説明テキスト。
        """
        super().__init__(description)
        self.dataset = dataset
        self.col_name = col_name
        self.deleted_column_data = deleted_column_data

    def redo(self):
        # ★ 安全性チェック:
        # (コマンド作成時にもチェックがあるが、undo -> プロット軸変更 -> redo の
        # パターンに対応するため、ここでもチェック)
        if self.dataset.is_column_in_use(self.col_name):
            logger.warning("Redo不可: 列 '%s' はプロットに使用されています。", self.col_name)
            self.setObsolete(True)
            return
        self.dataset.remove_column(self.col_name)

    def undo(self):
        self.dataset.restore_column(self.col_name, self.deleted_column_data)


class RenameColumnCommand(QUndoCommand):
    """列名を変更するコマンド(項目64)。X/Y軸等の参照追従はDataset.rename_column側で行う。"""
    def __init__(self, dataset, old_name, new_name, description="列名の変更"):
        super().__init__(description)
        self.dataset = dataset
        self.old_name = old_name
        self.new_name = new_name

    def redo(self):
        self.dataset.rename_column(self.old_name, self.new_name)

    def undo(self):
        self.dataset.rename_column(self.new_name, self.old_name)


class SetDatasetPropertiesCommand(QUndoCommand):
    """
    Dataset の1つ以上の属性 (色, 線種, 凡例名, 描画先など) をまとめて
    変更するための汎用 Undo/Redo コマンド。
    main_window (gui/mixins/dataset_mixin.py) のプロパティ変更スロットから発行される。
    """
    def __init__(self, dataset, old_values: dict, new_values: dict, on_applied, description="プロパティ変更"):
        """
        Args:
            dataset (Dataset): 変更対象の Dataset。
            old_values (dict): 変更前の {属性名: 値}。
            new_values (dict): 変更後の {属性名: 値}。
            on_applied (callable): redo/undo 後に呼ばれるコールバック
                (プロット再描画やUIパネルの同期を行う。GUI側の関心事のため
                コマンド自身はこれ以上 GUI の内部実装を知らない)。
            description (str): Undo/Redoメニューに表示されるテキスト。
        """
        super().__init__(description)
        self.dataset = dataset
        self.old_values = old_values
        self.new_values = new_values
        self.on_applied = on_applied

    def redo(self):
        for attr, value in self.new_values.items():
            setattr(self.dataset, attr, value)
        self.on_applied()

    def undo(self):
        for attr, value in self.old_values.items():
            setattr(self.dataset, attr, value)
        self.on_applied()


class SetMaskedRowsCommand(QUndoCommand):
    """
    行を削除せず「フィット/プロットから除外(マスク)」する/を解除するかを
    まとめて切り替えるUndo/Redoコマンド(項目36)。
    DataEditorDialog の「選択行を除外/解除」操作から発行される。
    """
    def __init__(self, dataset, old_masked_indices, new_masked_indices, description="行の除外/解除"):
        """
        Args:
            dataset (Dataset): 対象の Dataset。
            old_masked_indices (list): 変更前のマスク済み行インデックス(df.indexラベル)のリスト。
            new_masked_indices (list): 変更後のマスク済み行インデックスのリスト。
            description (str): Undo/Redoメニューに表示されるテキスト。
        """
        super().__init__(description)
        self.dataset = dataset
        self.old_masked_indices = list(old_masked_indices)
        self.new_masked_indices = list(new_masked_indices)

    def redo(self):
        self.dataset.masked_row_indices = list(self.new_masked_indices)

    def undo(self):
        self.dataset.masked_row_indices = list(self.old_masked_indices)


class SetAnnotationsCommand(QUndoCommand):
    """
    指定した軸 (project.all_plot_settings[axis_index]) の注釈(テキスト・矢印)
    リストをまとめて置き換えるUndo/Redoコマンド。追加・削除のどちらも、
    変更前後のリスト全体を保持するシンプルな方式で統一的に扱う。
    gui/mixins/annotation_mixin.py の注釈追加/削除処理から発行される。
    """
    def __init__(self, project, axis_index, old_annotations, new_annotations, on_applied, description="注釈の変更"):
        """
        Args:
            project (ProjectModel): 対象のプロジェクト。
            axis_index (int): 対象の軸 (all_plot_settings) のインデックス。
            old_annotations (list[dict]): 変更前の注釈リスト。
            new_annotations (list[dict]): 変更後の注釈リスト。
            on_applied (callable): redo/undo 後に呼ばれるコールバック (外観の再描画を行う)。
            description (str): Undo/Redoメニューに表示されるテキスト。
        """
        super().__init__(description)
        self.project = project
        self.axis_index = axis_index
        self.old_annotations = list(old_annotations)
        self.new_annotations = list(new_annotations)
        self.on_applied = on_applied

    def redo(self):
        self.project.all_plot_settings[self.axis_index]['annotations'] = list(self.new_annotations)
        self.on_applied()

    def undo(self):
        self.project.all_plot_settings[self.axis_index]['annotations'] = list(self.old_annotations)
        self.on_applied()


class ReorderDatasetsCommand(QUndoCommand):
    """
    project.datasets の並び順 (=プロットの描画順/重なり順) を変更する
    Undo/Redo コマンド。データセットリストのドラッグ&ドロップによる
    並べ替え (gui/mixins/dataset_mixin.py の _on_dataset_rows_moved) から発行される。
    """
    def __init__(self, project, old_order, new_order, on_applied, description="データセットの並べ替え"):
        """
        Args:
            project (ProjectModel): 対象のプロジェクト。
            old_order (list[Dataset]): 変更前の順序。
            new_order (list[Dataset]): 変更後の順序。
            on_applied (callable): redo/undo 後に呼ばれるコールバック
                (リスト表示の同期とプロット再描画を行う)。
            description (str): Undo/Redoメニューに表示されるテキスト。
        """
        super().__init__(description)
        self.project = project
        self.old_order = list(old_order)
        self.new_order = list(new_order)
        self.on_applied = on_applied

    def redo(self):
        self.project.datasets = list(self.new_order)
        self.on_applied()

    def undo(self):
        self.project.datasets = list(self.old_order)
        self.on_applied()
