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
    assert ds.fit_result is None
    assert ds.fit_band_display is None


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


def test_restore_rows_does_not_relabel_unrelated_rows_after_an_earlier_permanent_deletion():
    """
    回帰テスト: restore_rows が reset_index(drop=True) していたため、それ以前に
    (今回のUndoとは無関係に)別の行が既に永久削除されていて欠番がある状態で
    delete_rows→restore_rows すると、既存の全行のラベルがずれて振り直されて
    しまい、それを前提にラベルを保持しているはずの他のコマンド(例:
    EditCellCommand.undo)が誤った行を書き換えたり、存在しないラベルへの
    set_cell がゴースト行を新規作成したりする実データ破損バグがあった。
    """
    df = pd.DataFrame({'x': [0.0, 1.0, 2.0, 3.0, 4.0], 'y': [0.0, 10.0, 20.0, 30.0, 40.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')

    # 1. 今回のUndo対象とは別の行(index 2)を、先に「普通に」永久削除しておく
    #    (ユーザーが不要な行を消して、そのままUndoせず作業を続けたケース)。
    ds.delete_rows([2])
    assert list(ds.df.index) == [0, 1, 3, 4]

    # 2. index 4 の行の値を編集(EditCellCommand相当)。
    ds.set_cell(4, 'y', 999.0)

    # 3. 別の行(index 3)を削除してUndo(restore_rows)する。
    deleted_data = ds.df.loc[[3]]
    ds.delete_rows([3])
    ds.restore_rows(deleted_data)

    # 4. 手順1の欠番(index 2)はrestore_rowsの後も保持されたままであるべきで、
    #    手順2で編集した index 4 の値がそのまま(ラベルがずれずに)残っている
    #    必要がある。
    assert list(ds.df.index) == [0, 1, 3, 4]
    assert ds.df.loc[4, 'y'] == 999.0
    # ゴースト行(NaN埋めの余計な行)が増えていないこと。
    assert len(ds.df) == 4


def test_add_row_after_deleting_middle_row_does_not_collide():
    """delete_rows が残したインデックスの欠番と、add_row が新しく割り当てる
    ラベルが衝突しない(重複ラベルにならない)ことを確認する。"""
    ds = make_dataset()  # index [0, 1, 2]
    ds.delete_rows([1])  # index [0, 2] が残る
    ds.add_row()
    assert list(ds.df.index) == [0, 2, 3]
    assert ds.df.index.is_unique


def test_delete_rows_prunes_stale_entries_from_masked_row_indices():
    """
    回帰テスト: マスクした行をそのまま永久削除すると、masked_row_indices に
    その行のラベルが残ったままになっていた。その後 add_row() が
    (df.index.max() + 1 で) 同じラベルを新しい行に再利用してしまい、
    新規追加した行が visible_df から除外されてグラフ/フィット/ピーク検出に
    一切現れなくなる(エラーも警告も出ない)というサイレントなデータ欠落
    バグがあった。
    """
    ds = make_dataset()  # index [0, 1, 2]
    ds.masked_row_indices = [2]
    ds.delete_rows([2])  # マスクしていた行をそのまま永久削除
    assert ds.masked_row_indices == []

    ds.add_row()  # 新しい行が (欠番の) index 2 を再利用する
    assert list(ds.df.index) == [0, 1, 2]
    # 新規行が古いマスクの影響を受けず、visible_df に含まれること。
    assert 2 in ds.visible_df.index


def test_delete_rows_leaves_unrelated_masked_row_indices_untouched():
    ds = make_dataset()  # index [0, 1, 2]
    ds.masked_row_indices = [0]
    ds.delete_rows([2])
    assert ds.masked_row_indices == [0]


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


def test_defaults_include_visible_field():
    """データセットリストの表示/非表示トグル(項目C-907)の新フィールドのデフォルト値。
    既定はTrue(=表示)であること。"""
    ds = make_dataset()
    assert ds.visible is True


def test_to_dict_from_dict_roundtrip_preserves_visible_field():
    """Dataset.to_dict()/from_dict() の往復で、visible フィールドが
    そのまま保持されることを確認する(項目C-907)。"""
    ds = make_dataset(visible=False)

    data = ds.to_dict()
    assert data['visible'] is False

    restored = Dataset.from_dict(data)
    assert restored.visible is False


def test_from_dict_missing_visible_key_falls_back_to_true():
    """visible キーが無い(この機能追加前に保存された)dict を読み込んでも、
    クラッシュせずデフォルト値 True (表示) で補われること(後方互換)。"""
    ds = make_dataset(name="Legacy")
    data = ds.to_dict()
    data.pop('visible', None)

    restored = Dataset.from_dict(data)

    assert restored.name == "Legacy"
    assert restored.visible is True


def test_pickle_roundtrip_preserves_visible_field():
    ds = make_dataset(visible=False)
    restored = pickle.loads(pickle.dumps(ds))
    assert restored.visible is False


def test_setstate_backfills_missing_visible_field_for_old_pickles():
    """visible フィールドが追加される前に保存された古い形式のpickleを模倣し、
    __setstate__ がデフォルト値True(表示)で補うことを確認する(項目C-907)。"""
    ds = make_dataset()
    state = ds.__getstate__()
    state.pop('visible', None)

    restored = Dataset.__new__(Dataset)
    restored.__setstate__(state)

    assert restored.visible is True


def test_defaults_include_gradient_fields():
    """プロットへのグラデーション適用(項目79)の新フィールドのデフォルト値"""
    ds = make_dataset()
    assert ds.gradient_enabled is False
    assert ds.gradient_color2 == '#ffffff'
    assert ds.gradient_target == 'line'


def test_to_dict_from_dict_roundtrip_preserves_gradient_fields():
    """Dataset.to_dict()/from_dict() の往復で、グラデーション関連フィールドが
    そのまま保持されることを確認する(項目79)。"""
    ds = make_dataset(
        color='#ff0000', gradient_enabled=True,
        gradient_color2='#00ff00', gradient_target='both',
    )
    ds.artist = object()  # to_dict()では除外されるはず

    data = ds.to_dict()
    assert 'artist' not in data
    assert data['gradient_enabled'] is True
    assert data['gradient_color2'] == '#00ff00'
    assert data['gradient_target'] == 'both'

    restored = Dataset.from_dict(data)
    assert restored.artist is None
    assert restored.gradient_enabled is True
    assert restored.gradient_color2 == '#00ff00'
    assert restored.gradient_target == 'both'
    assert restored.color == '#ff0000'
    pd.testing.assert_frame_equal(restored.df, ds.df)


def test_from_dict_missing_gradient_keys_falls_back_to_defaults():
    """gradient_enabled/gradient_color2/gradient_target キーが無い(この機能追加前に
    保存された)dict を読み込んでも、クラッシュせずデフォルト値で補われること。"""
    ds = make_dataset(name="Legacy")
    data = ds.to_dict()
    for missing_field in ('gradient_enabled', 'gradient_color2', 'gradient_target'):
        data.pop(missing_field, None)

    restored = Dataset.from_dict(data)

    assert restored.name == "Legacy"
    assert restored.gradient_enabled is False
    assert restored.gradient_color2 == '#ffffff'
    assert restored.gradient_target == 'line'


def test_to_dict_from_dict_roundtrip_preserves_fit_result():
    """Dataset.to_dict()/from_dict() の往復で、構造化フィット結果
    (項目C-401、fit_result)がそのまま保持されることを確認する。"""
    fit_result = {
        'fit_type': '線形 (y = ax + b)',
        'custom_formula': None,
        'param_names': ['a', 'b'],
        'params': [2.5, 1.3],
        'param_errors': [0.01, 0.02],
        'covariance': [[0.0001, 0.0], [0.0, 0.0004]],
        'r_squared': 0.999,
        'residuals': [0.1, -0.1],
        'residual_x': [1.0, 2.0],
        'weighted': False,
        'x_range': None,
        'source_dataset_id': 'abc123',
        'source_dataset_name': 'D1',
    }
    ds = make_dataset(name="Fit (D1)", fit_result=fit_result)

    data = ds.to_dict()
    assert data['fit_result'] == fit_result

    restored = Dataset.from_dict(data)
    assert restored.fit_result == fit_result


def test_from_dict_missing_fit_result_key_falls_back_to_none():
    """fit_result キーが無い(項目C-401追加前に保存された)dict を読み込んでも
    クラッシュせず、デフォルトのNoneで補われること。"""
    ds = make_dataset(name="Legacy")
    data = ds.to_dict()
    data.pop('fit_result', None)

    restored = Dataset.from_dict(data)

    assert restored.name == "Legacy"
    assert restored.fit_result is None


def test_pickle_roundtrip_preserves_fit_result():
    fit_result = {'fit_type': 'ガウシアン', 'params': [1.0, 2.0], 'r_squared': 0.98}
    ds = make_dataset(fit_result=fit_result)

    restored = pickle.loads(pickle.dumps(ds))

    assert restored.fit_result == fit_result


def test_to_dict_from_dict_roundtrip_preserves_fit_band_display():
    """項目C-405: fit_band_displayがto_dict()/from_dict()の往復で保持されること。"""
    ds = make_dataset(fit_band_display="prediction")

    data = ds.to_dict()
    assert data['fit_band_display'] == "prediction"

    restored = Dataset.from_dict(data)
    assert restored.fit_band_display == "prediction"


def test_from_dict_missing_fit_band_display_key_falls_back_to_none():
    ds = make_dataset(name="Legacy")
    data = ds.to_dict()
    data.pop('fit_band_display', None)

    restored = Dataset.from_dict(data)

    assert restored.fit_band_display is None


def test_defaults_include_waterfall_fields():
    """ウォーターフォールプロット(項目80、項目109で独立フラグに変更)の
    新フィールドのデフォルト値"""
    ds = make_dataset()
    assert ds.waterfall_enabled is False
    assert ds.waterfall_offset_x == 0.0
    assert ds.waterfall_offset_y == 1.0


def test_to_dict_from_dict_roundtrip_preserves_waterfall_fields():
    """Dataset.to_dict()/from_dict() の往復で、ウォーターフォール関連フィールドが
    そのまま保持されることを確認する(項目80/109)。plot_typeとは独立したフラグ
    なので、Scatter等の他のplot_typeと組み合わせても保持されることも確認する。"""
    ds = make_dataset(
        plot_type='Scatter', waterfall_enabled=True,
        waterfall_offset_x=1.5, waterfall_offset_y=2.5,
    )
    ds.artist = object()  # to_dict()では除外されるはず

    data = ds.to_dict()
    assert 'artist' not in data
    assert data['waterfall_enabled'] is True
    assert data['waterfall_offset_x'] == 1.5
    assert data['waterfall_offset_y'] == 2.5

    restored = Dataset.from_dict(data)
    assert restored.artist is None
    assert restored.plot_type == 'Scatter'
    assert restored.waterfall_enabled is True
    assert restored.waterfall_offset_x == 1.5
    assert restored.waterfall_offset_y == 2.5
    pd.testing.assert_frame_equal(restored.df, ds.df)


def test_from_dict_missing_waterfall_keys_falls_back_to_defaults():
    """waterfall_enabled/waterfall_offset_x/waterfall_offset_y キーが無い(この機能
    追加前に保存された)dict を読み込んでも、クラッシュせずデフォルト値で
    補われること。"""
    ds = make_dataset(name="Legacy")
    data = ds.to_dict()
    for missing_field in ('waterfall_enabled', 'waterfall_offset_x', 'waterfall_offset_y'):
        data.pop(missing_field, None)

    restored = Dataset.from_dict(data)

    assert restored.name == "Legacy"
    assert restored.waterfall_enabled is False
    assert restored.waterfall_offset_x == 0.0
    assert restored.waterfall_offset_y == 1.0


def test_from_dict_migrates_legacy_waterfall_plot_type():
    """項目109: ウォーターフォールを独立フラグに変更する前、短期間存在した
    plot_type='Waterfall' というdictを読み込んだ場合、plot_type='Line' +
    waterfall_enabled=True に自動的に読み替えられること(移行時の後方互換性)。"""
    ds = make_dataset(plot_type='Line', waterfall_offset_x=1.0, waterfall_offset_y=2.0)
    data = ds.to_dict()
    data['plot_type'] = 'Waterfall'  # 旧形式のdictを模擬
    data['waterfall_enabled'] = False  # 旧形式には無かったキーのはずだが念のため

    restored = Dataset.from_dict(data)

    assert restored.plot_type == 'Line'
    assert restored.waterfall_enabled is True


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


# ---------------------------------------------------------------------------
# visible_df キャッシュ (C-002): 1描画あたり最大4回のフィルタ処理を1回に
# ---------------------------------------------------------------------------

def _masked_dataset():
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0, 4.0], 'y': [10.0, 20.0, 30.0, 40.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    ds.masked_row_indices = [1]
    return ds


def test_visible_df_is_cached_across_repeated_access():
    """マスクあり(=フィルタ処理が実際に走る)の場合でも、何も変更していなければ
    2回目以降のvisible_dfアクセスは同一オブジェクトを返す(再フィルタしない)。"""
    ds = _masked_dataset()
    first = ds.visible_df
    second = ds.visible_df
    assert first is second


def test_visible_df_cache_invalidated_by_masked_row_indices_reassignment():
    ds = _masked_dataset()
    first = ds.visible_df
    assert len(first) == 3
    ds.masked_row_indices = [1, 2]
    second = ds.visible_df
    assert second is not first
    assert len(second) == 2


def test_visible_df_cache_invalidated_by_df_reassignment():
    ds = _masked_dataset()  # masked_row_indices=[1]
    _ = ds.visible_df  # キャッシュを作らせる
    new_df = pd.DataFrame({'x': [5.0, 6.0, 7.0], 'y': [50.0, 60.0, 70.0]})
    ds.df = new_df
    # マスク自体は引き継がれる(index=1が引き続き除外される)ため、
    # 新しいdfに対してマスクが正しく再適用されていることを確認する
    # (=古いdfに対する結果がキャッシュされたまま使い回されていないこと)。
    np.testing.assert_array_equal(ds.x_data, [5.0, 7.0])


def test_visible_df_cache_invalidated_by_set_cell():
    """set_cell はdfをインプレースで書き換えるため、Dataset自身が
    invalidate_visible_df_cache() を呼んでキャッシュを無効化する。"""
    ds = make_dataset()
    _ = ds.visible_df  # キャッシュを作らせる
    ds.set_cell(0, 'y', 999.0)
    assert ds.visible_df.loc[0, 'y'] == 999.0


def test_visible_df_cache_invalidated_by_add_column():
    ds = make_dataset()
    _ = ds.visible_df
    ds.add_column('new_col')
    assert 'new_col' in ds.visible_df.columns


def test_visible_df_cache_invalidated_by_external_in_place_mutation_after_explicit_call():
    """
    dataset.df[col] = ... のような外部からのインプレース変更は自動検知できない
    ため、呼び出し側が invalidate_visible_df_cache() を明示的に呼ぶ必要がある
    (gui/data_editor.py, gui/mixins/dataset_mixin.py の列計算機能が実際に行っている)。
    """
    ds = make_dataset()
    _ = ds.visible_df
    ds.df['z'] = [100.0, 200.0, 300.0]
    ds.invalidate_visible_df_cache()
    assert 'z' in ds.visible_df.columns
    np.testing.assert_array_equal(ds.visible_df['z'].values, [100.0, 200.0, 300.0])


def test_visible_df_cache_not_included_in_pickle_state():
    ds = _masked_dataset()
    _ = ds.visible_df  # キャッシュを作らせる
    state = ds.__getstate__()
    assert '_visible_df_cache' not in state
    assert '_visible_df_cache_version' not in state
    assert '_version' not in state


def test_visible_df_cache_survives_pickle_roundtrip_correctly():
    ds = _masked_dataset()
    _ = ds.visible_df
    restored = pickle.loads(pickle.dumps(ds))
    assert len(restored.visible_df) == 3
    restored.masked_row_indices = [1, 2]
    assert len(restored.visible_df) == 2
