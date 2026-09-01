# tests/test_dataset_nan_policy_field.py
"""
core/dataset.py の nan_policy フィールド(項目C-201: 欠損値の方針設定)の往復テスト。
描画への実際の反映は tests/test_canvas.py の
「Dataset.nan_policy の描画への反映」節、UIの配線は tests/test_dataset_mixin.py の
「欠損値(NaN)の方針設定」節を参照。
"""
import json

import pandas as pd

from core.dataset import Dataset
from models.project import ProjectModel


def _make_project_with_nan_policy_dataset(nan_policy="ffill"):
    project = ProjectModel()
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y', nan_policy=nan_policy)
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    return project


def test_dataset_nan_policy_defaults_to_gap():
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    assert ds.nan_policy == 'gap'


def test_nan_policy_roundtrips_via_graphica_json(tmp_path):
    project = _make_project_with_nan_policy_dataset("drop")
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['datasets'][0]['nan_policy'] == "drop"

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].nan_policy == "drop"


def test_nan_policy_roundtrips_via_pkl(tmp_path):
    project = _make_project_with_nan_policy_dataset("ffill")
    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].nan_policy == "ffill"


def test_nan_policy_defaults_gap_for_legacy_graphica_file_missing_key(tmp_path):
    """このフィールド導入前に保存された.graphicaファイル(キー自体が無い)を
    読み込んでも、クラッシュせず既定の'gap'(導入前と同じ見た目)にフォールバックすること。"""
    project = _make_project_with_nan_policy_dataset()
    path = tmp_path / "legacy.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    del raw['datasets'][0]['nan_policy']
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].nan_policy == 'gap'


def test_nan_policy_defaults_gap_for_legacy_pkl_missing_key():
    """導入前の.pklは、Dataset.__setstate__相当のフォールバックで'gap'に補われる。"""
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    state = ds.__getstate__()
    del state['nan_policy']  # 導入前の.pklを再現(意図的に欠落させる)
    ds2 = Dataset.__new__(Dataset)
    ds2.__setstate__(state)
    assert ds2.nan_policy == 'gap'
