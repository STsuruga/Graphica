# tests/test_panel_labels_project_field.py
"""models/project.py の panel_labels_enabled フィールド(C-712)の往復テスト。"""
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


def test_panel_labels_enabled_defaults_to_false():
    assert ProjectModel().panel_labels_enabled is False


def test_panel_labels_enabled_roundtrips_via_graphica_json(tmp_path):
    project = _make_project()
    project.panel_labels_enabled = True
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['panel_labels_enabled'] is True

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.panel_labels_enabled is True


def test_panel_labels_enabled_roundtrips_via_pkl(tmp_path):
    project = _make_project()
    project.panel_labels_enabled = True
    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.panel_labels_enabled is True


def test_panel_labels_enabled_defaults_false_for_legacy_graphica_file_missing_key(tmp_path):
    """このフィールド導入前に保存された.graphicaファイル(キー自体が無い)を
    読み込んでも、クラッシュせずFalseにフォールバックすること。"""
    project = _make_project()
    path = tmp_path / "legacy.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    del raw['panel_labels_enabled']
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.panel_labels_enabled is False


def test_panel_labels_enabled_defaults_false_for_legacy_pkl_missing_key(tmp_path):
    import pickle
    ds = _make_project().datasets[0]
    old_format_data = {
        'datasets': [ds],
        'all_plot_settings': [{}],
        'active_axis_index': 0,
        'layout_rows': 1,
        'layout_cols': 1,
        # 'panel_labels_enabled' は意図的に省略(導入前の.pklを再現)
    }
    path = tmp_path / "legacy.pkl"
    with open(path, 'wb') as f:
        pickle.dump(old_format_data, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.panel_labels_enabled is False
