"""データセットの複製が ID(dataset_id)まで写していた不具合。

ID で引くもの(ウォーターフォールの段、保存したデータセット一覧の並び、統計値ラベルなど)が元と複製を取り違え、
ウォーターフォールでは2本が同じ段で重なり、保存して開き直すと一覧が「複製」2つになって元が消えていた。
"""
import json

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp
from graphica.models.project import ProjectModel


def _ds(name, **kwargs):
    return Dataset(name=name, df=pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}),
                   x_col_name="x", y_col_name="y", **kwargs)


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "s.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.instance().processEvents()
    yield w
    w.close()


def _duplicate(window, dataset):
    window._add_dataset(dataset, None, select=True)
    window._on_duplicate_dataset()
    return window.project.datasets[-1]


def test_a_duplicate_gets_its_own_id(window):
    original = _ds("orig")
    copy = _duplicate(window, original)
    assert copy.name == "orig (copy)"
    assert copy.dataset_id != original.dataset_id


def test_a_duplicated_waterfall_trace_gets_the_next_step(window):
    original = _ds("orig", waterfall_enabled=True, waterfall_offset_y=1.0)
    copy = _duplicate(window, original)
    window._update_plot()

    assert window.canvas.get_waterfall_transform(original)['index'] == 0
    assert window.canvas.get_waterfall_transform(copy)['index'] == 1
    assert list(original.artist.get_ydata()) == pytest.approx([3.0, 4.0])
    assert list(copy.artist.get_ydata()) == pytest.approx([4.0, 5.0])


def test_save_and_reopen_keeps_both_in_the_list(window, tmp_path):
    original = _ds("orig")
    _duplicate(window, original)
    path = str(tmp_path / "p.gra")
    window._save_project_to_path(path)

    project = ProjectModel()
    project.load_project(path)

    leaves = [child['dataset'].name for child in project.dataset_group_tree['children']]
    assert leaves == ["orig", "orig (copy)"]


# --- 複製が ID まで写していたころに保存したファイル ---

def _write_project_with_shared_ids(path, tree_children):
    first, second = _ds("orig"), _ds("orig (copy)")
    second.dataset_id = first.dataset_id
    data = {
        'format_version': 1,
        'datasets': [first.to_dict(), second.to_dict()],
        'dataset_group_tree': {'name': '', 'children': tree_children(first.dataset_id)},
        'all_plot_settings': [{'annotations': [{'type': 'stat', 'dataset_id': first.dataset_id, 'stat': 'mean'}]}],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return first.dataset_id


def test_an_old_file_with_shared_ids_opens_with_both_in_the_list(tmp_path):
    path = tmp_path / "old.gra"
    shared = _write_project_with_shared_ids(
        path, lambda dataset_id: [{'dataset_id': dataset_id}, {'dataset_id': dataset_id}])

    project = ProjectModel()
    project.load_project(str(path))

    leaves = [child['dataset'] for child in project.dataset_group_tree['children']]
    assert [ds.name for ds in leaves] == ["orig", "orig (copy)"]
    assert leaves[0] is project.datasets[0] and leaves[1] is project.datasets[1]
    # 2本目に新しい ID。1本目を指していた統計値ラベルはそのまま1本目を指す
    assert project.datasets[0].dataset_id == shared
    assert project.datasets[1].dataset_id != shared
    assert project.all_plot_settings[0]['annotations'][0]['dataset_id'] == project.datasets[0].dataset_id


def test_shared_ids_inside_folders_are_assigned_in_order(tmp_path):
    path = tmp_path / "old.gra"
    _write_project_with_shared_ids(path, lambda dataset_id: [
        {'name': 'F1', 'children': [{'dataset_id': dataset_id}]},
        {'name': 'F2', 'children': [{'dataset_id': dataset_id}]},
    ])

    project = ProjectModel()
    project.load_project(str(path))

    folders = project.dataset_group_tree['children']
    assert [f['children'][0]['dataset'].name for f in folders] == ["orig", "orig (copy)"]


def test_an_extra_leaf_for_a_shared_id_is_dropped_not_duplicated(tmp_path):
    """ID の数より葉が多い壊れたファイルでも、同じデータセットを2回並べない。"""
    path = tmp_path / "old.gra"
    _write_project_with_shared_ids(path, lambda dataset_id: [{'dataset_id': dataset_id}] * 3)

    project = ProjectModel()
    project.load_project(str(path))

    assert [child['dataset'].name for child in project.dataset_group_tree['children']] == ["orig", "orig (copy)"]
