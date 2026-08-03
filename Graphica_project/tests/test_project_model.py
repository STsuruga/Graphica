# tests/test_project_model.py
"""models/project.py (プロジェクトの保存/読込、pickleセキュリティ) に対するテスト。"""
import io
import os
import pickle
import subprocess
import sys

import pandas as pd
import pytest

from core.dataset import Dataset
from models.project import ProjectModel


def make_project():
    project = ProjectModel()
    df1 = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [10.0, 20.0, 30.0]})
    df2 = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
    project.datasets = [
        Dataset(name="D1", df=df1, x_col_name='x', y_col_name='y', color='#ff0000'),
        Dataset(name="D2", df=df2, x_col_name='a', y_col_name='b', subplot_target=1),
    ]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': d} for d in project.datasets]}
    project.all_plot_settings = [{'title': 'Plot 1'}, {'title': 'Plot 2'}]
    project.active_axis_index = 1
    project.layout_rows = 1
    project.layout_cols = 2
    return project


def test_save_and_load_roundtrip(tmp_path):
    project = make_project()
    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    assert len(reloaded.datasets) == 2
    assert reloaded.datasets[0].name == "D1"
    assert reloaded.datasets[0].color == '#ff0000'
    pd.testing.assert_frame_equal(reloaded.datasets[0].df, project.datasets[0].df)
    assert reloaded.datasets[1].subplot_target == 1
    assert reloaded.all_plot_settings == [{'title': 'Plot 1'}, {'title': 'Plot 2'}]
    assert reloaded.active_axis_index == 1
    assert reloaded.layout_rows == 1
    assert reloaded.layout_cols == 2
    assert reloaded.current_filepath == str(path)


def test_save_updates_current_filepath(tmp_path):
    project = make_project()
    assert project.current_filepath == ""
    path = tmp_path / "p.pkl"
    project.save_project(str(path))
    assert project.current_filepath == str(path)


def test_load_missing_file_raises_filenotfounderror(tmp_path):
    project = ProjectModel()
    with pytest.raises(FileNotFoundError):
        project.load_project(str(tmp_path / "does_not_exist.pkl"))


def test_load_old_format_without_dataset_group_tree_rebuilds_flat_tree(tmp_path):
    """
    フォルダ機能追加前の古い形式の.pklを模倣する: dataset_group_tree キーが無い場合、
    全データセットがルート直下にあるものとして再構築されることを確認する。
    """
    ds = Dataset(name="Legacy", df=pd.DataFrame({'x': [1], 'y': [2]}), x_col_name='x', y_col_name='y')
    old_format_data = {
        'datasets': [ds],
        'all_plot_settings': [{}],
        'active_axis_index': 0,
        'layout_rows': 1,
        'layout_cols': 1,
        # 'dataset_group_tree' キーは意図的に省略
    }
    path = tmp_path / "legacy.pkl"
    with open(path, 'wb') as f:
        pickle.dump(old_format_data, f)

    project = ProjectModel()
    project.load_project(str(path))

    assert project.dataset_group_tree['children'] == [{'dataset': project.datasets[0]}]


def test_load_rejects_disallowed_classes(tmp_path):
    """
    許可リストにないクラス(このテストでは組み込みの例外クラスを流用)をトップレベルの
    値として含むpickleは、_RestrictedUnpickler によって拒否されることを確認する。
    core.dataset / numpy / pandas 以外のオブジェクトの復元を禁止する、pickleの
    任意コード実行対策のセキュリティ回帰テスト。
    """
    path = tmp_path / "malicious.pkl"
    # ValueError は許可リスト (numpy/pandas/core.dataset) に含まれないクラスの一例
    with open(path, 'wb') as f:
        pickle.dump({'datasets': [ValueError("not allowed")]}, f)

    project = ProjectModel()
    with pytest.raises(pickle.UnpicklingError):
        project.load_project(str(path))


def test_load_rejects_os_system_payload(tmp_path):
    """
    より直接的に、os.system のような危険な呼び出し可能オブジェクトを
    参照するpickleが拒否されることを確認する(実際にコードは実行されない)。
    """
    path = tmp_path / "exploit.pkl"

    class _Exploit:
        def __reduce__(self):
            # 復元時に os.system('echo pwned') を呼び出そうとするペイロード。
            # _RestrictedUnpickler が 'os' モジュールの解決を拒否するため、
            # find_class の時点でUnpicklingErrorになり、実行されない。
            return (os.system, ("echo pwned",))

    with open(path, 'wb') as f:
        pickle.dump({'datasets': [_Exploit()]}, f)

    project = ProjectModel()
    with pytest.raises(pickle.UnpicklingError):
        project.load_project(str(path))


def test_allowed_classes_still_load_correctly(tmp_path):
    """許可リストにある numpy/pandas/core.dataset のオブジェクトは正しく復元できることを確認する"""
    import numpy as np
    path = tmp_path / "allowed.pkl"
    data = {
        'datasets': [Dataset(
            name="D", df=pd.DataFrame({'x': np.array([1, 2, 3])}), x_col_name='x', y_col_name='x'
        )],
        'all_plot_settings': [{}],
        'active_axis_index': 0,
        'layout_rows': 1,
        'layout_cols': 1,
        'dataset_group_tree': {'name': '', 'children': []},
    }
    with open(path, 'wb') as f:
        pickle.dump(data, f)

    project = ProjectModel()
    project.load_project(str(path))  # 例外を出さずに読み込めることを確認
    assert project.datasets[0].name == "D"
    np.testing.assert_array_equal(project.datasets[0].df['x'].values, [1, 2, 3])
