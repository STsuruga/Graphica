# tests/test_source_plugin_field.py
"""
core/dataset.py の source_plugin フィールド(項目C-3)の往復テスト。

完了条件: プラグインで生成したDatasetを含むプロジェクトを保存 → プラグイン
無効化状態(プラグインAPIのシングルトンが一切ロードされていない状態)で再度開く
→ クラッシュせず通常データとして表示され、生成元プラグイン名が見える。
"""
import json
import pickle

import pandas as pd

import core.plugin_api as plugin_api_module
from core.dataset import Dataset
from models.project import ProjectModel


def _make_project_with_plugin_generated_dataset():
    project = ProjectModel()
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
    ds = Dataset(name="D1_processed", df=df, x_col_name='x', y_col_name='y',
                 source_plugin="cool_plugin")
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    return project


def test_dataset_source_plugin_defaults_to_none():
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    assert ds.source_plugin is None


def test_source_plugin_roundtrips_via_graphica_json(tmp_path):
    project = _make_project_with_plugin_generated_dataset()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['datasets'][0]['source_plugin'] == "cool_plugin"

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].source_plugin == "cool_plugin"


def test_source_plugin_roundtrips_via_pkl(tmp_path):
    project = _make_project_with_plugin_generated_dataset()
    path = tmp_path / "project.pkl"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].source_plugin == "cool_plugin"


def test_source_plugin_defaults_none_for_legacy_graphica_file_missing_key(tmp_path):
    """このフィールド導入前に保存された.graphicaファイル(キー自体が無い)を
    読み込んでも、クラッシュせずNoneにフォールバックすること。"""
    project = _make_project_with_plugin_generated_dataset()
    path = tmp_path / "legacy.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    del raw['datasets'][0]['source_plugin']
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.datasets[0].source_plugin is None


def test_source_plugin_defaults_none_for_legacy_pkl_missing_key(tmp_path):
    """導入前の.pklは、Dataset.__setstate__相当のフォールバックでNoneに補われる。"""
    df = pd.DataFrame({'x': [1.0], 'y': [2.0]})
    ds = Dataset(name="D1", df=df, x_col_name='x', y_col_name='y')
    state = ds.__getstate__()
    del state['source_plugin']  # 導入前の.pklを再現(意図的に欠落させる)
    ds2 = Dataset.__new__(Dataset)
    ds2.__setstate__(state)
    assert ds2.source_plugin is None


def test_plugin_generated_dataset_reopens_without_crash_when_plugin_api_unloaded(tmp_path, monkeypatch):
    """プラグイン無効化状態(_singleton_apiがNone、register()未呼び出し)でも、
    プロジェクトのロード自体はクラッシュせず、生成元プラグイン名が読み取れる。
    _singleton_apiはプロセス全体で共有されるため、他のテストが既にロード済みでも
    このテストの前提(無効化状態)が壊れないよう、テスト内で明示的に隔離する。"""
    monkeypatch.setattr(plugin_api_module, "_singleton_api", None)
    monkeypatch.setattr(plugin_api_module, "_singleton_manager", None)

    project = _make_project_with_plugin_generated_dataset()
    path = tmp_path / "project.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))  # プラグインAPIに一切触れずに読み込める

    dataset = reloaded.datasets[0]
    assert dataset.source_plugin == "cool_plugin"
    # 通常データと同様にx_data/y_dataへ普通にアクセスできる(壊れていない)
    assert list(dataset.y_data) == [3.0, 4.0]
