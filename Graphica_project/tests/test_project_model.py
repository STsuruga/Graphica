# tests/test_project_model.py
"""models/project.py (プロジェクトの保存/読込) に対するテスト。"""

import pandas as pd
import pytest

from graphica.core.dataset import Dataset
from graphica.models.project import ProjectModel


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
    path = tmp_path / "project.gra"
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
    path = tmp_path / "p.gra"
    project.save_project(str(path))
    assert project.current_filepath == str(path)


def test_load_missing_file_raises_filenotfounderror(tmp_path):
    project = ProjectModel()
    with pytest.raises(FileNotFoundError):
        project.load_project(str(tmp_path / "does_not_exist.gra"))


# --- ProjectModelのシグナル化(項目80、C-005、最小スコープ版) ---

def test_project_model_is_qobject():
    """QObjectを継承しており、シグナル/スロット機構が使えること。"""
    from PySide6.QtCore import QObject
    project = ProjectModel()
    assert isinstance(project, QObject)


def test_notify_changed_emits_changed_signal():
    project = ProjectModel()
    received = []
    project.changed.connect(lambda: received.append(True))

    project.notify_changed()

    assert received == [True]


def test_changed_signal_can_be_connected_directly():
    """notify_changed()を経由せず、changedシグナルへ直接connect/emitできること
    (将来、切り離しCanvas/ミニマップ等の独立した同期先が使う想定の経路)。"""
    project = ProjectModel()
    received = []
    project.changed.connect(lambda: received.append(True))

    project.changed.emit()

    assert received == [True]


def test_notify_changed_without_any_connection_does_not_raise():
    """何も接続されていない状態でnotify_changed()を呼んでも例外にならないこと
    (既存の約38箇所の直接呼び出しには一切影響しない、というスコープを裏付ける)。"""
    project = ProjectModel()
    project.notify_changed()  # 例外にならないこと


def test_legacy_graphica_extension_still_saves_and_loads(tmp_path):
    project = ProjectModel()
    project.all_plot_settings = [{'title': 'T'}]
    path = tmp_path / "old_name.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))
    assert reloaded.all_plot_settings[0]['title'] == 'T'


def test_pkl_is_refused_without_unpickling(tmp_path):
    """.pkl は中身を読まずに断る(細工された .pkl でもコードは実行されない)。"""
    path = tmp_path / "old.pkl"
    marker = tmp_path / "ran"
    path.write_bytes(b"cos\nsystem\n(S'echo > " + str(marker).encode() + b"'\ntR.")

    with pytest.raises(ValueError, match="旧形式"):
        ProjectModel().load_project(str(path))
    assert not marker.exists()


def test_saving_as_pkl_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ProjectModel().save_project(str(tmp_path / "x.pkl"))
    assert not (tmp_path / "x.pkl").exists()
