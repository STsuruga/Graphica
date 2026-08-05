# tests/test_commands.py
"""core/commands.py (Undo/Redoコマンド) に対するテスト。"""
import numpy as np
import pandas as pd
import pytest

from core.dataset import Dataset
from core.commands import (
    EditCellCommand, AddRowCommand, DeleteRowsCommand,
    AddColumnCommand, DeleteColumnCommand,
    SetDatasetPropertiesCommand, ReorderDatasetsCommand,
    SetAnnotationsCommand, SetMaskedRowsCommand, RenameColumnCommand,
    AddDatasetCommand,
)


def make_dataset(**overrides):
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [10.0, 20.0, 30.0]})
    kwargs = dict(name="D1", df=df, x_col_name='x', y_col_name='y')
    kwargs.update(overrides)
    return Dataset(**kwargs)


def test_edit_cell_command_redo_undo():
    ds = make_dataset()
    cmd = EditCellCommand(ds, 0, 'y', old_value=10.0, new_value=999.0)
    cmd.redo()
    assert ds.df.loc[0, 'y'] == 999.0
    cmd.undo()
    assert ds.df.loc[0, 'y'] == 10.0


def test_add_row_command_redo_undo():
    ds = make_dataset()
    original_len = len(ds.df)
    cmd = AddRowCommand(ds)
    cmd.redo()
    assert len(ds.df) == original_len + 1
    cmd.undo()
    assert len(ds.df) == original_len


def test_delete_rows_command_redo_undo_preserves_order():
    ds = make_dataset()
    deleted_data = ds.df.loc[[1]].copy()
    cmd = DeleteRowsCommand(ds, [1], deleted_data)

    cmd.redo()
    assert list(ds.df['y']) == [10.0, 30.0]

    cmd.undo()
    assert list(ds.df.sort_index()['y']) == [10.0, 20.0, 30.0]


def test_add_column_command_redo_undo():
    ds = make_dataset()
    cmd = AddColumnCommand(ds, 'new_col')
    cmd.redo()
    assert 'new_col' in ds.df.columns
    cmd.undo()
    assert 'new_col' not in ds.df.columns


def test_add_column_command_undo_blocked_if_column_in_use():
    """
    追加した列がその後X/Y軸などに使われた場合、undo(列削除)すると
    プロットが壊れるため、コマンドは自身をobsoleteにして削除を中止する。
    """
    ds = make_dataset()
    cmd = AddColumnCommand(ds, 'new_col')
    cmd.redo()
    assert 'new_col' in ds.df.columns

    ds.y_col_name = 'new_col'  # 追加した列をY軸として使い始める
    cmd.undo()

    assert 'new_col' in ds.df.columns, "使用中の列がundoで削除されてしまった"
    assert cmd.isObsolete() is True


def test_delete_column_command_redo_undo():
    ds = make_dataset()
    deleted_column_data = ds.df['y'].copy()
    ds.remove_column('y')
    cmd = DeleteColumnCommand(ds, 'y', deleted_column_data)

    cmd.undo()  # 削除されたデータを復元
    assert 'y' in ds.df.columns
    pd.testing.assert_series_equal(ds.df['y'], deleted_column_data)


def test_delete_column_command_redo_blocked_if_column_in_use():
    """undo後、その列がX/Y軸として使われるようになっていたら、redo(再削除)を中止する"""
    ds = make_dataset()
    deleted_column_data = ds.df['y'].copy()
    ds.remove_column('y')
    cmd = DeleteColumnCommand(ds, 'y', deleted_column_data)
    cmd.undo()

    ds.y_col_name = 'y'  # 復元された列を使い始める
    cmd.redo()

    assert 'y' in ds.df.columns, "使用中の列がredoで削除されてしまった"
    assert cmd.isObsolete() is True


def test_set_dataset_properties_command_redo_undo():
    ds = make_dataset(color='#1f77b4', linewidth=1.5)
    calls = []
    cmd = SetDatasetPropertiesCommand(
        ds,
        old_values={'color': '#1f77b4', 'linewidth': 1.5},
        new_values={'color': '#ff0000', 'linewidth': 3.0},
        on_applied=lambda: calls.append('applied'),
    )
    cmd.redo()
    assert ds.color == '#ff0000'
    assert ds.linewidth == 3.0
    assert calls == ['applied']

    cmd.undo()
    assert ds.color == '#1f77b4'
    assert ds.linewidth == 1.5
    assert calls == ['applied', 'applied']


def test_reorder_datasets_command_redo_undo():
    # ★ Dataset は df (DataFrame) を含む値ベースの __eq__ を持つため、
    # リストの比較は == ではなく id (オブジェクト同一性) で行う
    # (gui/mixins/dataset_mixin.py で採用されているのと同じ理由・同じ回避策)。
    def ids(datasets):
        return [id(d) for d in datasets]

    project = type('FakeProject', (), {})()
    ds_a, ds_b, ds_c = make_dataset(name="A"), make_dataset(name="B"), make_dataset(name="C")
    project.datasets = [ds_a, ds_b, ds_c]

    calls = []
    cmd = ReorderDatasetsCommand(
        project,
        old_order=[ds_a, ds_b, ds_c],
        new_order=[ds_c, ds_a, ds_b],
        on_applied=lambda: calls.append('applied'),
    )
    cmd.redo()
    assert ids(project.datasets) == ids([ds_c, ds_a, ds_b])
    assert calls == ['applied']

    cmd.undo()
    assert ids(project.datasets) == ids([ds_a, ds_b, ds_c])
    assert calls == ['applied', 'applied']


def test_set_annotations_command_redo_undo():
    project = type('FakeProject', (), {})()
    project.all_plot_settings = [{'annotations': []}]

    calls = []
    new_annotation = {'id': 'abc', 'type': 'text', 'text': 'hello', 'xy': (1, 2), 'xytext': (1, 2), 'color': '#000000'}
    cmd = SetAnnotationsCommand(
        project, axis_index=0,
        old_annotations=[], new_annotations=[new_annotation],
        on_applied=lambda: calls.append('applied'),
        description="注釈の追加",
    )
    cmd.redo()
    assert project.all_plot_settings[0]['annotations'] == [new_annotation]
    assert calls == ['applied']

    cmd.undo()
    assert project.all_plot_settings[0]['annotations'] == []
    assert calls == ['applied', 'applied']


def test_set_annotations_command_does_not_alias_input_lists():
    """コマンドが保持するold/new注釈リストは、呼び出し側の元のリストへの参照ではなく
    独立したコピーであるべき (呼び出し側が後でリストを変更してもコマンドは影響を受けない)。"""
    project = type('FakeProject', (), {})()
    project.all_plot_settings = [{'annotations': []}]

    old_list = []
    new_list = [{'id': 'x', 'type': 'text', 'text': 'a', 'xy': (0, 0), 'xytext': (0, 0), 'color': '#000000'}]
    cmd = SetAnnotationsCommand(project, 0, old_list, new_list, on_applied=lambda: None)

    new_list.append({'id': 'y', 'type': 'text', 'text': 'b', 'xy': (0, 0), 'xytext': (0, 0), 'color': '#000000'})
    cmd.redo()
    assert len(project.all_plot_settings[0]['annotations']) == 1


def test_rename_column_command_redo_undo():
    ds = make_dataset()  # x_col_name='x', y_col_name='y'
    cmd = RenameColumnCommand(ds, 'x', 'time')
    cmd.redo()
    assert 'time' in ds.df.columns
    assert ds.x_col_name == 'time'

    cmd.undo()
    assert 'x' in ds.df.columns
    assert 'time' not in ds.df.columns
    assert ds.x_col_name == 'x'


def test_set_masked_rows_command_redo_undo():
    ds = make_dataset()
    assert ds.masked_row_indices == []

    cmd = SetMaskedRowsCommand(ds, old_masked_indices=[], new_masked_indices=[1])
    cmd.redo()
    assert ds.masked_row_indices == [1]
    np.testing.assert_array_equal(ds.x_data, [1.0, 3.0])

    cmd.undo()
    assert ds.masked_row_indices == []
    np.testing.assert_array_equal(ds.x_data, [1.0, 2.0, 3.0])


def test_add_dataset_command_redo_calls_add_callback():
    calls = []
    cmd = AddDatasetCommand(
        add_callback=lambda: calls.append("add"),
        remove_callback=lambda: calls.append("remove"),
    )
    cmd.redo()
    assert calls == ["add"]


def test_add_dataset_command_undo_calls_remove_callback():
    calls = []
    cmd = AddDatasetCommand(
        add_callback=lambda: calls.append("add"),
        remove_callback=lambda: calls.append("remove"),
    )
    cmd.redo()
    cmd.undo()
    assert calls == ["add", "remove"]


def test_add_dataset_command_redo_undo_redo_round_trip():
    calls = []
    cmd = AddDatasetCommand(
        add_callback=lambda: calls.append("add"),
        remove_callback=lambda: calls.append("remove"),
    )
    cmd.redo()
    cmd.undo()
    cmd.redo()
    assert calls == ["add", "remove", "add"]


def test_add_dataset_command_default_description():
    cmd = AddDatasetCommand(add_callback=lambda: None, remove_callback=lambda: None)
    assert cmd.text() == "データセットの追加"


def test_add_dataset_command_custom_description():
    cmd = AddDatasetCommand(
        add_callback=lambda: None, remove_callback=lambda: None,
        description="データ処理: Smooth",
    )
    assert cmd.text() == "データ処理: Smooth"
