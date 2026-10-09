"""gui/dialog_dirs.py: ファイルダイアログを、用途ごとに前回のフォルダ(無ければ「ドキュメント」)で開く。

場所を渡さないと Qt は今の作業フォルダで開き、ショートカットから起動するとアプリ本体のフォルダになっていた。
"""
import os

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
import graphica.gui.dialog_dirs as dialog_dirs
import graphica.gui.notify as notify_module
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp


@pytest.fixture
def documents(tmp_path, monkeypatch):
    path = tmp_path / "Documents"
    path.mkdir()
    monkeypatch.setattr(dialog_dirs, "documents_dir", lambda: str(path))
    return path


def _same(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def test_nothing_remembered_opens_documents(documents):
    assert _same(dialog_dirs.start_dir(dialog_dirs.PROJECT), documents)


def test_each_purpose_remembers_its_own_folder(documents, tmp_path):
    projects, data = tmp_path / "projects", tmp_path / "data"
    projects.mkdir()
    data.mkdir()

    dialog_dirs.remember(dialog_dirs.PROJECT, str(projects / "a.gra"))
    dialog_dirs.remember(dialog_dirs.DATA, str(data))

    assert _same(dialog_dirs.start_dir(dialog_dirs.PROJECT), projects)
    assert _same(dialog_dirs.start_dir(dialog_dirs.DATA), data)
    assert _same(dialog_dirs.start_dir(dialog_dirs.EXPORT), documents)


def test_a_removed_folder_falls_back_to_documents(documents, tmp_path):
    gone = tmp_path / "gone"
    gone.mkdir()
    dialog_dirs.remember(dialog_dirs.PROJECT, str(gone))
    gone.rmdir()
    assert _same(dialog_dirs.start_dir(dialog_dirs.PROJECT), documents)


def test_preferred_folder_wins_when_it_exists(documents, tmp_path):
    remembered, preferred = tmp_path / "remembered", tmp_path / "preferred"
    remembered.mkdir()
    preferred.mkdir()
    dialog_dirs.remember(dialog_dirs.EXPORT, str(remembered))

    assert _same(dialog_dirs.start_dir(dialog_dirs.EXPORT, str(preferred)), preferred)
    assert _same(dialog_dirs.start_dir(dialog_dirs.EXPORT, str(tmp_path / "missing")), remembered)
    assert _same(dialog_dirs.start_dir(dialog_dirs.EXPORT, None), remembered)


def test_a_broken_setting_is_ignored(documents):
    app_settings_module.LAST_DIALOG_DIRS.write(app_settings_module.open_settings(), "{not json")
    assert _same(dialog_dirs.start_dir(dialog_dirs.PROJECT), documents)


def test_save_dialog_gets_the_folder_and_name_and_remembers_the_choice(documents, tmp_path, monkeypatch):
    chosen = tmp_path / "out" / "fig.png"
    chosen.parent.mkdir()
    seen = []
    monkeypatch.setattr(notify_module.QFileDialog, "getSaveFileName",
                        staticmethod(lambda parent, title, start, filters: seen.append(start) or (str(chosen), "PNG")))

    path, _ = dialog_dirs.get_save_file_name(None, dialog_dirs.EXPORT, "保存", "plot.png", "PNG (*.png)")

    assert path == str(chosen)
    assert _same(seen[0], documents / "plot.png")
    assert _same(dialog_dirs.start_dir(dialog_dirs.EXPORT), chosen.parent)


def test_cancelling_remembers_nothing(documents, monkeypatch):
    monkeypatch.setattr(notify_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a: ("", "")))
    dialog_dirs.get_open_file_name(None, dialog_dirs.DATA, "開く", "*.csv")
    assert _same(dialog_dirs.start_dir(dialog_dirs.DATA), documents)


def test_directory_dialog_remembers_the_folder(documents, tmp_path, monkeypatch):
    folder = tmp_path / "batch"
    folder.mkdir()
    monkeypatch.setattr(notify_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a: str(folder)))
    dialog_dirs.get_existing_directory(None, dialog_dirs.DATA, "フォルダ")
    assert _same(dialog_dirs.start_dir(dialog_dirs.DATA), folder)


# --- 作業中のものに合わせた場所 ---

@pytest.fixture
def window(tmp_path, monkeypatch, documents):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.instance().processEvents()
    yield w
    w.close()


def _capture_save_dialog(monkeypatch):
    seen = []
    monkeypatch.setattr(notify_module.QFileDialog, "getSaveFileName",
                        staticmethod(lambda parent, title, start, filters: seen.append(start) or ("", "")))
    return seen


def test_save_as_of_a_saved_project_opens_at_its_file(window, tmp_path, monkeypatch):
    project = tmp_path / "work" / "experiment.gra"
    project.parent.mkdir()
    window._current_project_path = str(project)
    seen = _capture_save_dialog(monkeypatch)

    window.manual_save_as()

    assert _same(seen[0], project)


def test_save_as_of_a_new_project_opens_next_to_the_data(window, tmp_path, monkeypatch):
    data = tmp_path / "measurements" / "run1.csv"
    data.parent.mkdir()
    window.project.datasets.append(Dataset(name="run1", df=pd.DataFrame({"x": [1], "y": [2]}),
                                           x_col_name="x", y_col_name="y", source_file=str(data)))
    seen = _capture_save_dialog(monkeypatch)

    window.manual_save_as()

    assert _same(seen[0], data.parent)


def test_save_as_without_data_or_project_opens_documents(window, documents, monkeypatch):
    seen = _capture_save_dialog(monkeypatch)
    window.manual_save_as()
    assert _same(seen[0], documents)


def test_export_of_a_saved_project_opens_beside_it_with_its_name(window, tmp_path, monkeypatch):
    project = tmp_path / "work" / "experiment.gra"
    project.parent.mkdir()
    window._current_project_path = str(project)
    seen = _capture_save_dialog(monkeypatch)

    window._on_export_python_script()

    assert _same(seen[0], project.parent / "experiment")
