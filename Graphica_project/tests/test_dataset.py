# tests/test_dataset.py
"""core/dataset.py の Dataset データクラスに対するテスト。"""
import copy
import pickle

import numpy as np
import pandas as pd
import pytest

from core.dataset import Dataset


def make_dataset(**overrides):
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [10.0, 20.0, 30.0]})
    kwargs = dict(name="D1", df=df, x_col_name='x', y_col_name='y')
    kwargs.update(overrides)
    return Dataset(**kwargs)


def test_defaults():
    ds = make_dataset()
    assert ds.plot_type == 'Line'
    assert ds.color == '#1f77b4'
    assert ds.alpha == 1.0
    assert ds.show_point_labels is False
    assert ds.point_label_col_name is None
    assert ds.x_err_col_name is None
    assert ds.y_err_col_name is None
    assert ds.use_secondary_y is False
    assert ds.subplot_target == 0
    assert isinstance(ds.dataset_id, str) and len(ds.dataset_id) > 0


def test_dataset_id_is_unique_per_instance():
    a = make_dataset()
    b = make_dataset()
    assert a.dataset_id != b.dataset_id


def test_x_data_y_data_properties():
    ds = make_dataset()
    np.testing.assert_array_equal(ds.x_data, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(ds.y_data, [10.0, 20.0, 30.0])


def test_x_data_y_data_follow_column_name_change():
    df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
    ds = Dataset(name="D", df=df, x_col_name='a', y_col_name='b')
    ds.x_col_name = 'b'
    np.testing.assert_array_equal(ds.x_data, [3, 4])


def test_err_data_none_when_unset():
    ds = make_dataset()
    assert ds.x_err_data is None
    assert ds.y_err_data is None


def test_err_data_returns_values_when_set():
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [10.0, 20.0], 'yerr': [0.1, 0.2]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y', y_err_col_name='yerr')
    np.testing.assert_array_equal(ds.y_err_data, [0.1, 0.2])
    assert ds.x_err_data is None


def test_set_cell():
    ds = make_dataset()
    ds.set_cell(0, 'y', 999.0)
    assert ds.df.loc[0, 'y'] == 999.0


def test_add_row_and_delete_last_row():
    ds = make_dataset()
    original_len = len(ds.df)
    ds.add_row()
    assert len(ds.df) == original_len + 1
    assert ds.df.iloc[-1].isna().all()

    ds.delete_last_row()
    assert len(ds.df) == original_len
    pd.testing.assert_frame_equal(ds.df.reset_index(drop=True),
                                   make_dataset().df.reset_index(drop=True))


def test_delete_last_row_on_empty_df_is_noop():
    df = pd.DataFrame({'x': [], 'y': []})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')
    ds.delete_last_row()
    assert len(ds.df) == 0


def test_delete_rows_and_restore_rows_roundtrip():
    ds = make_dataset()
    original = ds.df.copy()

    deleted_data = ds.df.loc[[1]]
    ds.delete_rows([1])
    assert len(ds.df) == 2
    assert list(ds.df['y']) == [10.0, 30.0]
    # ★ 削除後もインデックスは振り直さない (restore_rows が正しい位置に
    #   戻せるように、元のラベルの欠番をそのまま保持する)
    assert list(ds.df.index) == [0, 2]

    ds.restore_rows(deleted_data)
    assert len(ds.df) == 3
    # 元の並び順 (インデックス順) で復元される
    pd.testing.assert_frame_equal(
        ds.df.reset_index(drop=True), original.reset_index(drop=True)
    )


def test_restore_rows_after_deleting_middle_row_keeps_correct_order():
    """
    回帰テスト: 中間の行を削除してUndo(復元)すると、隣の行と値が
    入れ替わってしまうバグがあった(delete_rows が reset_index していたため、
    restore_rows が古いラベルで正しい位置を特定できなくなっていた)。
    """
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0, 4.0, 5.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='x')

    deleted_data = ds.df.loc[[2]]  # x=3.0 の行
    ds.delete_rows([2])
    assert list(ds.df['x']) == [1.0, 2.0, 4.0, 5.0]

    ds.restore_rows(deleted_data)
    assert list(ds.df['x']) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_add_row_after_deleting_middle_row_does_not_collide():
    """delete_rows が残したインデックスの欠番と、add_row が新しく割り当てる
    ラベルが衝突しない(重複ラベルにならない)ことを確認する。"""
    ds = make_dataset()  # index [0, 1, 2]
    ds.delete_rows([1])  # index [0, 2] が残る
    ds.add_row()
    assert list(ds.df.index) == [0, 2, 3]
    assert ds.df.index.is_unique


def test_delete_multiple_rows():
    ds = make_dataset()
    ds.delete_rows([0, 2])
    assert len(ds.df) == 1
    assert list(ds.df['y']) == [20.0]


def test_is_column_in_use():
    ds = make_dataset(x_err_col_name='xerr', y_err_col_name='yerr')
    assert ds.is_column_in_use('x') is True
    assert ds.is_column_in_use('y') is True
    assert ds.is_column_in_use('xerr') is True
    assert ds.is_column_in_use('yerr') is True
    assert ds.is_column_in_use('unrelated') is False


def test_add_column_and_remove_column():
    ds = make_dataset()
    ds.add_column('new_col')
    assert 'new_col' in ds.df.columns
    assert ds.df['new_col'].isna().all()

    # 既存の列名では上書きされない (副作用がないことを確認)
    before = ds.df['x'].copy()
    ds.add_column('x')
    pd.testing.assert_series_equal(ds.df['x'], before)

    ds.remove_column('new_col')
    assert 'new_col' not in ds.df.columns


def test_restore_column():
    ds = make_dataset()
    column_data = ds.df['y'].copy()
    ds.remove_column('y')
    assert 'y' not in ds.df.columns

    ds.restore_column('y', column_data)
    assert 'y' in ds.df.columns
    pd.testing.assert_series_equal(ds.df['y'], column_data)


def test_remove_column_missing_is_noop():
    ds = make_dataset()
    columns_before = list(ds.df.columns)
    ds.remove_column('does_not_exist')
    assert list(ds.df.columns) == columns_before


def test_getstate_excludes_artist():
    ds = make_dataset()
    ds.artist = object()  # 通常はmatplotlibのArtistが入る
    state = ds.__getstate__()
    assert state['artist'] is None
    # 元のインスタンスの artist 自体は変更されない
    assert ds.artist is not None


def test_pickle_roundtrip_preserves_data_and_style():
    ds = make_dataset(color='#ff0000', alpha=0.5, subplot_target=2)
    ds.artist = object()

    restored = pickle.loads(pickle.dumps(ds))

    assert restored.artist is None
    assert restored.color == '#ff0000'
    assert restored.alpha == 0.5
    assert restored.subplot_target == 2
    pd.testing.assert_frame_equal(restored.df, ds.df)


def test_setstate_backfills_missing_fields_for_old_pickles():
    """
    新しいフィールド(alpha等)が追加される前に保存された古い形式のpickleを
    模倣し、__setstate__ がデフォルト値で補うことを確認する。
    """
    ds = make_dataset()
    state = ds.__getstate__()
    # 後から追加されたフィールドが無い「古い」状態を再現する
    for missing_field in ('alpha', 'show_point_labels', 'point_label_col_name', 'dataset_id'):
        state.pop(missing_field, None)

    restored = Dataset.__new__(Dataset)
    restored.__setstate__(state)

    assert restored.alpha == 1.0
    assert restored.show_point_labels is False
    assert restored.point_label_col_name is None
    assert isinstance(restored.dataset_id, str) and len(restored.dataset_id) > 0


def test_masked_rows_excluded_from_x_data_y_data():
    """外れ値のマスク機能(項目36): masked_row_indices の行は行を削除せず
    x_data/y_data から除外される(非破壊的)。"""
    ds = make_dataset()  # index [0, 1, 2], y = [10, 20, 30]
    ds.masked_row_indices = [1]
    np.testing.assert_array_equal(ds.x_data, [1.0, 3.0])
    np.testing.assert_array_equal(ds.y_data, [10.0, 30.0])
    # マスクしても行自体は削除されない
    assert len(ds.df) == 3


def test_masked_rows_excluded_from_err_data():
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [10.0, 20.0, 30.0], 'yerr': [0.1, 0.2, 0.3]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y', y_err_col_name='yerr')
    ds.masked_row_indices = [0]
    np.testing.assert_array_equal(ds.y_err_data, [0.2, 0.3])


def test_visible_df_with_no_masked_rows_returns_full_df():
    ds = make_dataset()
    assert ds.visible_df is ds.df


def test_unmasking_restores_full_x_data_y_data():
    ds = make_dataset()
    ds.masked_row_indices = [1]
    assert len(ds.x_data) == 2
    ds.masked_row_indices = []
    np.testing.assert_array_equal(ds.x_data, [1.0, 2.0, 3.0])


def test_rename_column_updates_dataframe_and_x_col_name():
    ds = make_dataset()  # x_col_name='x', y_col_name='y'
    ds.rename_column('x', 'time')
    assert 'time' in ds.df.columns
    assert 'x' not in ds.df.columns
    assert ds.x_col_name == 'time'
    assert ds.y_col_name == 'y'  # 無関係の列は変化しない


def test_rename_column_updates_err_and_point_label_col_names():
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [10.0, 20.0], 'yerr': [0.1, 0.2]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y', y_err_col_name='yerr',
                 point_label_col_name='yerr')
    ds.rename_column('yerr', 'y_error')
    assert ds.y_err_col_name == 'y_error'
    assert ds.point_label_col_name == 'y_error'
    np.testing.assert_array_equal(ds.y_err_data, [0.1, 0.2])


def test_rename_column_missing_column_is_noop():
    ds = make_dataset()
    columns_before = list(ds.df.columns)
    ds.rename_column('does_not_exist', 'new_name')
    assert list(ds.df.columns) == columns_before


def test_rename_column_same_name_is_noop():
    ds = make_dataset()
    ds.rename_column('x', 'x')
    assert ds.x_col_name == 'x'
    assert list(ds.df.columns) == ['x', 'y']


def test_deepcopy_produces_independent_dataframe():
    """データセット複製機能 (_on_duplicate_dataset) が依拠する deepcopy の挙動を確認する"""
    ds = make_dataset()
    clone = copy.deepcopy(ds)
    clone.df.loc[0, 'y'] = -1.0
    assert ds.df.loc[0, 'y'] == 10.0  # 元のdfは影響を受けない

    # ★ 注意: copy.deepcopy は dataset_id もそのまま複製するため、
    # 複製直後は元データセットと同じ dataset_id を持つ (呼び出し側が
    # 意図的に新しいIDへ差し替えない限り一意性は保証されない)。
    assert clone.dataset_id == ds.dataset_id
