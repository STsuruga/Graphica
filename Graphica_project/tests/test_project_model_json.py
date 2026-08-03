# tests/test_project_model_json.py
"""
models/project.py の新しいJSON保存形式(.graphica)に対するテスト。
pickle(.pkl)形式は既存の tests/test_project_model.py で引き続き検証される。
このファイルでは、JSON形式での往復(round-trip)が
dtypeフィデリティ・numpy由来の値・オブジェクト同一性を保つことを確認する。
"""
import json

import numpy as np
import pandas as pd
import pytest

from core.dataset import Dataset
from models.project import ProjectModel


def make_dataset(**overrides):
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [10.0, 20.0, 30.0]})
    kwargs = dict(name="D1", df=df, x_col_name='x', y_col_name='y')
    kwargs.update(overrides)
    return Dataset(**kwargs)


def make_rich_project():
    """dtype混在のDataFrame・入れ子フォルダ・numpy由来の値を含むプロジェクトを作る"""
    project = ProjectModel()

    df1 = pd.DataFrame({
        'int_col': np.array([1, 2, 3], dtype='int64'),
        'float_col': [1.5, np.nan, 3.5],
        'datetime_col': pd.to_datetime(['2024-01-01', '2024-01-02', None]),
        'str_col': ['a', 'b', 'c'],
    })
    ds1 = Dataset(name="データ1", df=df1, x_col_name='int_col', y_col_name='float_col', color='#ff0000')
    ds1.masked_row_indices = [np.int64(1)]  # numpy.int64 が混ざるケースを再現

    df2 = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
    ds2 = Dataset(name="データ2", df=df2, x_col_name='a', y_col_name='b', subplot_target=1)

    project.datasets = [ds1, ds2]

    # 入れ子フォルダを含む dataset_group_tree
    project.dataset_group_tree = {
        'name': '',
        'children': [
            {'dataset': ds1},
            {
                'name': 'サブフォルダ',
                'children': [
                    {'dataset': ds2},
                ],
            },
        ],
    }

    project.all_plot_settings = [
        {
            'title': 'Plot 1',
            'annotations': [
                {
                    'type': 'text',
                    'text': 'ピーク',
                    'xy': (np.float64(1.5), np.float64(2.5)),
                    'xytext': (np.float64(2.0), np.float64(3.0)),
                    'color': '#00ff00',
                    'id': 'abc123',
                }
            ],
            'legend_order': ['データ1', 'データ2'],
            'free_rect': (np.float64(0.1), np.float64(0.1), np.float64(0.4), np.float64(0.4)),
        },
        {'title': 'Plot 2', 'annotations': [], 'legend_order': [], 'free_rect': None},
    ]
    project.active_axis_index = 1
    project.layout_rows = 1
    project.layout_cols = 2
    project.layout_mode = 'free'
    return project


def test_graphica_roundtrip_preserves_dataset_fields(tmp_path):
    project = make_rich_project()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    assert len(reloaded.datasets) == 2
    d1 = reloaded.datasets[0]
    assert d1.name == "データ1"
    assert d1.color == '#ff0000'
    d2 = reloaded.datasets[1]
    assert d2.subplot_target == 1
    assert reloaded.active_axis_index == 1
    assert reloaded.layout_rows == 1
    assert reloaded.layout_cols == 2
    assert reloaded.layout_mode == 'free'
    assert reloaded.current_filepath == str(path)


def test_graphica_roundtrip_preserves_dataframe_dtypes_exactly(tmp_path):
    project = make_rich_project()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    original_df = project.datasets[0].df
    reloaded_df = reloaded.datasets[0].df

    pd.testing.assert_frame_equal(reloaded_df, original_df, check_dtype=True)
    # 個別にdtypeも明示的に確認
    assert str(reloaded_df['int_col'].dtype) == 'int64'
    assert str(reloaded_df['float_col'].dtype) == 'float64'
    assert str(reloaded_df['datetime_col'].dtype).startswith('datetime64')
    assert str(reloaded_df['str_col'].dtype) == 'object'

    # NaN はNaNのまま (Noneやその他の値に化けていない)
    assert np.isnan(reloaded_df['float_col'].iloc[1])
    # NaT もNaTのまま
    assert pd.isna(reloaded_df['datetime_col'].iloc[2])


def test_graphica_roundtrip_masked_row_indices_are_plain_ints(tmp_path):
    project = make_rich_project()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    masked = reloaded.datasets[0].masked_row_indices
    assert masked == [1]
    for v in masked:
        assert type(v) is int  # numpy.int64ではなく素のint


def test_graphica_roundtrip_preserves_plot_settings_with_numpy_values(tmp_path):
    project = make_rich_project()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    # 保存されたファイルが正当なJSONであること自体も確認しておく
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['datasets'][0]['name'] == "データ1"

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    settings0 = reloaded.all_plot_settings[0]
    assert settings0['legend_order'] == ['データ1', 'データ2']
    free_rect = settings0['free_rect']
    assert list(free_rect) == [0.1, 0.1, 0.4, 0.4]

    annotation = settings0['annotations'][0]
    assert annotation['text'] == 'ピーク'
    assert list(annotation['xy']) == [1.5, 2.5]
    assert list(annotation['xytext']) == [2.0, 3.0]

    assert reloaded.all_plot_settings[1]['free_rect'] is None


def test_graphica_roundtrip_dataset_group_tree_shares_same_dataset_instances(tmp_path):
    """
    dataset_group_tree のリーフが指すDatasetは、reload後の datasets リストの
    対応する要素と同一インスタンス(is/id()で一致)でなければならない。
    """
    project = make_rich_project()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    tree = reloaded.dataset_group_tree
    # ルート直下1番目: ds1
    leaf0 = tree['children'][0]
    assert leaf0['dataset'] is reloaded.datasets[0]

    # サブフォルダ内: ds2
    subfolder = tree['children'][1]
    assert subfolder['name'] == 'サブフォルダ'
    leaf1 = subfolder['children'][0]
    assert leaf1['dataset'] is reloaded.datasets[1]


def test_pkl_path_still_works_after_json_support_added(tmp_path):
    """既存の.pkl保存/読込パスが、コード変更後も完全に同じ挙動であることの回帰確認"""
    project = ProjectModel()
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y', color='#00ff00')
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{'title': 'T'}]
    project.active_axis_index = 0
    project.layout_rows = 1
    project.layout_cols = 1

    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    assert reloaded.datasets[0].name == "D1"
    assert reloaded.datasets[0].color == '#00ff00'
    pd.testing.assert_frame_equal(reloaded.datasets[0].df, df)
    assert reloaded.dataset_group_tree['children'][0]['dataset'] is reloaded.datasets[0]
    assert reloaded.current_filepath == str(path)


def test_load_project_unsupported_extension_raises_value_error(tmp_path):
    path = tmp_path / "project.json"
    path.write_text("{}", encoding='utf-8')

    project = ProjectModel()
    with pytest.raises(ValueError):
        project.load_project(str(path))


def test_save_project_unsupported_extension_raises_value_error(tmp_path):
    project = make_dataset  # noqa: F841 (not used, just ensures import kept)
    project = ProjectModel()
    project.datasets = [make_dataset()]
    project.dataset_group_tree = {'name': '', 'children': []}
    with pytest.raises(ValueError):
        project.save_project(str(tmp_path / "project.txt"))


def test_graphica_load_skips_leaf_with_missing_dataset_id(tmp_path):
    """
    壊れた/手編集された.graphicaファイルを模倣する: dataset_group_tree内の
    dataset_idがdatasetsリストに存在しない場合、そのリーフはクラッシュせず
    スキップされることを確認する。
    """
    project = ProjectModel()
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    project.datasets = [ds]
    project.dataset_group_tree = {
        'name': '', 'children': [
            {'dataset': ds},
        ],
    }
    project.all_plot_settings = [{}]
    path = tmp_path / "corrupt.graphica"
    project.save_project(str(path))

    # 保存されたファイルを直接読み込み、リーフのdataset_idを壊れたIDに書き換える
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    raw['dataset_group_tree']['children'].append({'dataset_id': 'does-not-exist'})
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))  # 例外を出さずに読み込めることを確認

    assert len(reloaded.dataset_group_tree['children']) == 1
    assert reloaded.dataset_group_tree['children'][0]['dataset'] is reloaded.datasets[0]
