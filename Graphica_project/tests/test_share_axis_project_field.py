# tests/test_share_axis_project_field.py
"""models/project.py の share_x_axis / share_y_axis フィールド(C-601)の往復テスト。"""
import json

import pandas as pd

from core.dataset import Dataset
from models.project import ProjectModel


def _make_project():
    project = ProjectModel()
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    return project


def test_share_axis_defaults_to_false():
    project = ProjectModel()
    assert project.share_x_axis is False
    assert project.share_y_axis is False


def test_share_axis_roundtrips_via_graphica_json(tmp_path):
    project = _make_project()
    project.share_x_axis = True
    project.share_y_axis = True
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['share_x_axis'] is True
    assert raw['share_y_axis'] is True

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.share_x_axis is True
    assert reloaded.share_y_axis is True


def test_share_axis_roundtrips_via_pkl(tmp_path):
    project = _make_project()
    project.share_x_axis = True
    project.share_y_axis = False
    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.share_x_axis is True
    assert reloaded.share_y_axis is False


def test_share_axis_defaults_false_for_legacy_graphica_file_missing_key(tmp_path):
    """このフィールド導入前に保存された.graphicaファイル(キー自体が無い)を
    読み込んでも、クラッシュせずFalseにフォールバックすること。"""
    project = _make_project()
    path = tmp_path / "legacy.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    del raw['share_x_axis']
    del raw['share_y_axis']
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.share_x_axis is False
    assert reloaded.share_y_axis is False


def test_share_axis_defaults_false_for_legacy_pkl_missing_key(tmp_path):
    import pickle
    ds = _make_project().datasets[0]
    old_format_data = {
        'datasets': [ds],
        'all_plot_settings': [{}],
        'active_axis_index': 0,
        'layout_rows': 1,
        'layout_cols': 1,
        # 'share_x_axis' / 'share_y_axis' は意図的に省略(導入前の.pklを再現)
    }
    path = tmp_path / "legacy.pkl"
    with open(path, 'wb') as f:
        pickle.dump(old_format_data, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.share_x_axis is False
    assert reloaded.share_y_axis is False
