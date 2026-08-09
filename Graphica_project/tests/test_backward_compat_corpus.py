# tests/test_backward_compat_corpus.py
"""
後方互換コーパス + シリアライズのラウンドトリップ検証 (C-1205)。

tests/test_project_model_json_compat.py は「その場でPythonコードから
古い形式のdictを動的に生成」してテストする(既存の慣習)。このファイルは
それを補完し、tests/fixtures/legacy_projects/ 配下に実際に保存された
静的なファイル群(コーパス)を対象に、次の2点を検証する:

  1. 各コーパスファイルが例外を出さずに読み込め、想定通りのデータに
     なっていること(デフォルト値の補完を含む)。
  2. 読み込んだ状態を再保存し、もう一度読み込んでも安定した固定点に
     達すること(ラウンドトリップの安定性)。format_versionの移行チェーン
     (models/project.py の _migrate_project_data)は、この安定性を将来の
     フォーマット変更後も壊さないことが特に重要。

コーパスの生成方法・追加方法は tests/fixtures/legacy_projects/_generate_corpus.py
のdocstringを参照。
"""
import json
import os

import pandas as pd
import pytest

from models.project import CURRENT_FORMAT_VERSION, ProjectModel

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'legacy_projects')


def _fixture_path(filename):
    return os.path.join(FIXTURES_DIR, filename)


def test_v0_no_format_version_loads_and_is_treated_as_version_0():
    with open(_fixture_path('v0_no_format_version.graphica'), encoding='utf-8') as f:
        raw = json.load(f)
    assert 'format_version' not in raw  # コーパス自体の前提を確認

    project = ProjectModel()
    project.load_project(_fixture_path('v0_no_format_version.graphica'))

    assert len(project.datasets) == 1
    assert project.datasets[0].name == "旧バージョンの測定データ"
    assert project.datasets[0].color == '#2ca02c'
    assert list(project.datasets[0].df.columns) == ['x', 'y']


def test_v0_no_format_version_roundtrip_upgrades_to_current_version(tmp_path):
    """v0のファイルを読み込んで再保存すると、format_versionが現行版になり、
    以後は移行処理なしでそのまま安定して読み書きできる(固定点に達する)。"""
    project = ProjectModel()
    project.load_project(_fixture_path('v0_no_format_version.graphica'))

    resaved_path = tmp_path / "resaved.graphica"
    project.save_project(str(resaved_path))

    with open(resaved_path, encoding='utf-8') as f:
        resaved_raw = json.load(f)
    assert resaved_raw['format_version'] == CURRENT_FORMAT_VERSION

    reloaded = ProjectModel()
    reloaded.load_project(str(resaved_path))
    assert reloaded.datasets[0].name == project.datasets[0].name
    pd.testing.assert_frame_equal(reloaded.datasets[0].df, project.datasets[0].df)


def test_v0_dataset_missing_optional_fields_backfills_defaults():
    project = ProjectModel()
    project.load_project(_fixture_path('v0_dataset_missing_optional_fields.graphica'))

    ds = project.datasets[0]
    assert ds.name == "旧バージョンのデータセット"
    # dataclassのデフォルト値で補完されていること
    assert ds.alpha == 1.0
    assert ds.gradient_enabled is False
    assert ds.waterfall_enabled is False
    assert ds.show_point_labels is False
    assert ds.point_label_col_name is None
    assert ds.use_secondary_y is False
    assert ds.masked_row_indices == []
    assert isinstance(ds.dataset_id, str) and len(ds.dataset_id) > 0


def test_pre_folder_feature_pkl_loads_with_defaults():
    project = ProjectModel()
    project.load_project(_fixture_path('pre_folder_feature.pkl'))

    assert project.datasets[0].name == "Sample A"
    # dataset_group_tree が無い旧世代 -> フラットなツリーとして再構築される
    assert project.dataset_group_tree == {
        'name': '', 'children': [{'dataset': project.datasets[0]}]
    }
    # layout_mode が無い旧世代 -> デフォルトの'grid'
    assert project.layout_mode == 'grid'


def test_realistic_multi_dataset_project_loads_correctly():
    project = ProjectModel()
    project.load_project(_fixture_path('realistic_multi_dataset.graphica'))

    assert len(project.datasets) == 2
    assert project.datasets[0].name == "測定1"
    assert project.datasets[1].name == "測定2"
    assert project.datasets[1].subplot_target == 1
    folder = project.dataset_group_tree['children'][0]
    assert folder['name'] == '実験A'
    assert len(folder['children']) == 2
    assert len(project.all_plot_settings) == 2
    assert project.all_plot_settings[0]['annotations'][0]['text'] == 'ピーク'


@pytest.mark.parametrize('filename', [
    'v0_no_format_version.graphica',
    'v0_dataset_missing_optional_fields.graphica',
    'realistic_multi_dataset.graphica',
])
def test_graphica_corpus_roundtrip_reaches_stable_fixed_point(filename, tmp_path):
    """
    コーパスの各.graphicaファイルについて、読み込み->再保存->再読込を2回
    行い、2回目以降の保存結果(生のJSON)が完全に一致すること(=移行処理は
    最初の1回で完了し、以後は繰り返し適用しても内容が変化しない)を確認する。
    """
    project = ProjectModel()
    project.load_project(_fixture_path(filename))

    first_path = tmp_path / "first.graphica"
    project.save_project(str(first_path))

    reloaded = ProjectModel()
    reloaded.load_project(str(first_path))
    second_path = tmp_path / "second.graphica"
    reloaded.save_project(str(second_path))

    with open(first_path, encoding='utf-8') as f:
        first_raw = f.read()
    with open(second_path, encoding='utf-8') as f:
        second_raw = f.read()
    assert first_raw == second_raw


def test_pre_folder_feature_pkl_roundtrip_to_graphica_reaches_stable_fixed_point(tmp_path):
    """.pklのコーパスを読み込んで.graphicaとして保存した場合も、
    同様に安定した固定点に達すること。"""
    project = ProjectModel()
    project.load_project(_fixture_path('pre_folder_feature.pkl'))

    first_path = tmp_path / "first.graphica"
    project.save_project(str(first_path))

    reloaded = ProjectModel()
    reloaded.load_project(str(first_path))
    second_path = tmp_path / "second.graphica"
    reloaded.save_project(str(second_path))

    with open(first_path, encoding='utf-8') as f:
        first_raw = f.read()
    with open(second_path, encoding='utf-8') as f:
        second_raw = f.read()
    assert first_raw == second_raw
