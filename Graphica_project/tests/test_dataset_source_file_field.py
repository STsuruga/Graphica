# tests/test_dataset_source_file_field.py
"""
core/dataset.py の source_file / source_sheet フィールド(項目C-103: 元ファイルへの
リンク保持と再読み込み)の往復テスト。

_on_reload_dataset_from_source() 自体(GUIメニュー動作)のテストは
tests/test_dataset_mixin.py 側に置く。ここでは Dataset の永続化(pickle/.graphica両方)
の往復と後方互換フォールバックのみを検証する。
"""
import json

import pandas as pd

from core.dataset import Dataset
from models.project import ProjectModel


def _make_project_with_file_backed_dataset(source_file="C:/data/sample.csv", source_sheet=None):
    project = ProjectModel()
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y',
                 source_file=source_file, source_sheet=source_sheet)
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    return project


def test_dataset_source_file_and_sheet_default_to_none():
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    assert ds.source_file is None
    assert ds.source_sheet is None


def test_source_file_roundtrips_via_graphica_json(tmp_path):
    project = _make_project_with_file_backed_dataset(source_sheet="Sheet2")
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['datasets'][0]['source_file'] == "C:/data/sample.csv"
    assert raw['datasets'][0]['source_sheet'] == "Sheet2"

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].source_file == "C:/data/sample.csv"
    assert reloaded.datasets[0].source_sheet == "Sheet2"


def test_source_file_roundtrips_via_pkl(tmp_path):
    project = _make_project_with_file_backed_dataset()
    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].source_file == "C:/data/sample.csv"
    assert reloaded.datasets[0].source_sheet is None


def test_source_file_defaults_none_for_legacy_graphica_file_missing_key(tmp_path):
    """このフィールド導入前に保存された.graphicaファイル(キー自体が無い)を
    読み込んでも、クラッシュせずNoneにフォールバックすること。"""
    project = _make_project_with_file_backed_dataset()
    path = tmp_path / "legacy.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    del raw['datasets'][0]['source_file']
    del raw['datasets'][0]['source_sheet']
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].source_file is None
    assert reloaded.datasets[0].source_sheet is None


def test_source_file_defaults_none_for_legacy_pkl_missing_key():
    """導入前の.pklは、Dataset.__setstate__相当のフォールバックでNoneに補われる。"""
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    state = ds.__getstate__()
    del state['source_file']
    del state['source_sheet']  # 導入前の.pklを再現(意図的に欠落させる)
    ds2 = Dataset.__new__(Dataset)
    ds2.__setstate__(state)
    assert ds2.source_file is None
    assert ds2.source_sheet is None
