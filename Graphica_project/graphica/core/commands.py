import logging
from PySide6.QtGui import QUndoCommand

logger = logging.getLogger(__name__)


# コマンドは Dataset の公開メソッドだけを呼び、GUI を知らない。表の描き直しと通知は
# DataEditorDialog が QUndoStack.indexChanged で行う。

class EditCellCommand(QUndoCommand):
    def __init__(self, dataset, row_idx, col_name, old_value, new_value, description="セル編集"):
        """row_idx は dataset.df の index ラベル。"""
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
    def __init__(self, dataset, description="行追加"):
        super().__init__(description)
        self.dataset = dataset

    def redo(self):
        self.dataset.add_row()

    def undo(self):
        self.dataset.delete_last_row()


class DeleteRowsCommand(QUndoCommand):
    def __init__(self, dataset, row_indices, deleted_data, description="行削除"):
        """row_indices は df の index ラベル、deleted_data は Undo 用の消した行。"""
        super().__init__(description)
        self.dataset = dataset
        self.row_indices = row_indices
        self.deleted_data = deleted_data

    def redo(self):
        self.dataset.delete_rows(self.row_indices)

    def undo(self):
        self.dataset.restore_rows(self.deleted_data)


class AddColumnCommand(QUndoCommand):
    def __init__(self, dataset, col_name, description="列追加"):
        super().__init__(description)
        self.dataset = dataset
        self.col_name = col_name

    def redo(self):
        self.dataset.add_column(self.col_name)

    def undo(self):
        # 足した後にその列を X/Y にされていたら、消すと描画が壊れるので取り消さない
        if self.dataset.is_column_in_use(self.col_name):
            logger.warning("Undo不可: 列 '%s' はプロットに使用されています。", self.col_name)
            self.setObsolete(True)
            return
        self.dataset.remove_column(self.col_name)


class DeleteColumnCommand(QUndoCommand):
    def __init__(self, dataset, col_name, deleted_column_data, description="列削除"):
        super().__init__(description)
        self.dataset = dataset
        self.col_name = col_name
        self.deleted_column_data = deleted_column_data

    def redo(self):
        # 取り消し → 列を X/Y に設定 → やり直し、の順でも壊れないよう、ここでも確かめる
        if self.dataset.is_column_in_use(self.col_name):
            logger.warning("Redo不可: 列 '%s' はプロットに使用されています。", self.col_name)
            self.setObsolete(True)
            return
        self.dataset.remove_column(self.col_name)

    def undo(self):
        self.dataset.restore_column(self.col_name, self.deleted_column_data)


class RenameColumnCommand(QUndoCommand):
    """X/Y などの参照は Dataset.rename_column が新しい名前に付け替える。"""
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
    """Dataset の属性(色、線種、名前、描画先など)をまとめて変える。"""
    def __init__(self, dataset, old_values: dict, new_values: dict, on_applied, description="プロパティ変更"):
        """old_values / new_values は {属性名: 値}。on_applied は適用後の再描画など(GUI 側の仕事)。"""
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
    """行のマスクをまとめて切り替える。"""
    def __init__(self, dataset, old_masked_indices, new_masked_indices, description="行の除外/解除"):
        """マスクする行は df の index ラベルのリスト。"""
        super().__init__(description)
        self.dataset = dataset
        self.old_masked_indices = list(old_masked_indices)
        self.new_masked_indices = list(new_masked_indices)

    def redo(self):
        self.dataset.masked_row_indices = list(self.new_masked_indices)

    def undo(self):
        self.dataset.masked_row_indices = list(self.old_masked_indices)


class SetAnnotationsCommand(QUndoCommand):
    """1つの軸の注釈のリストを丸ごと置き換える(追加も削除もこれ)。"""
    def __init__(self, project, axis_index, old_annotations, new_annotations, on_applied, description="注釈の変更"):
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


class AddDatasetCommand(QUndoCommand):
    """データセットを1つ追加する(プラグインの処理と解析の結果用)。

    追加にはツリーの項目(フォルダの中の位置)が伴うので、追加と削除の処理そのものを GUI から受け取る。
    """
    def __init__(self, add_callback, remove_callback, description="データセットの追加"):
        """remove_callback は、直前に add_callback が足したものを取り除く。"""
        super().__init__(description)
        self.add_callback = add_callback
        self.remove_callback = remove_callback

    def redo(self):
        self.add_callback()

    def undo(self):
        self.remove_callback()


class RemoveDatasetCommand(QUndoCommand):
    """データセットやフォルダの削除。

    元の親フォルダの元の位置へ戻す必要があるので、削除と復元の処理そのものを GUI から受け取る。
    """
    def __init__(self, remove_callback, restore_callback, description="データセットの削除"):
        """restore_callback は、datasets の順とツリーの親・位置の両方を元に戻す。"""
        super().__init__(description)
        self.remove_callback = remove_callback
        self.restore_callback = restore_callback

    def redo(self):
        self.remove_callback()

    def undo(self):
        self.restore_callback()


class ReorderDatasetsCommand(QUndoCommand):
    """project.datasets の並び(描画の順と重なり)を変える。"""
    def __init__(self, project, old_order, new_order, on_applied, description="データセットの並べ替え"):
        """on_applied は一覧の同期と再描画。"""
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
