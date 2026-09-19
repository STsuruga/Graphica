# tests/test_unsaved_changes.py
"""
閉じる/別のプロジェクトを開く前の保存確認(v1.4.2)。

変更の有無は「保存したら書き出される内容」のハッシュ
(ProjectModel.content_fingerprint)を、直前の保存/読み込み時点と比べて判定する。
Undo スタックの clean 状態に頼らないのは、軸設定の変更・フォルダ操作・
列の計算など Undo の対象外の変更が多く、取りこぼすため。

tests/conftest.py はスイート全体で確認ダイアログを無効にしている
(モーダルで止まるため)。このファイルのテストだけが有効に戻す。
"""
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp, UNSAVED_CHANGES_PROMPT_ENV
from graphica.models.project import ProjectModel

from tests.test_main_app_window import _make_isolated_main_app_window


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _dataset(name="data"):
    x = np.linspace(0, 1, 10)
    return Dataset(name=name, df=pd.DataFrame({"x": x, "y": x * x}), x_col_name="x", y_col_name="y")


@pytest.fixture
def prompt_enabled(monkeypatch):
    monkeypatch.setenv(UNSAVED_CHANGES_PROMPT_ENV, "1")


@pytest.fixture
def answers(monkeypatch):
    """
    確認ダイアログで押すボタン(表示名)を、呼ばれた順に返すフェイク。
    実際の QMessageBox を組み立て、指定の文言のボタンを click() してから閉じる。
    """
    queue = []
    shown = []

    def fake_exec(box):
        shown.append((box.text(), box.informativeText()))
        label = queue.pop(0)
        for button in box.buttons():
            if button.text() == label:
                button.click()
                break
        else:
            raise AssertionError(f"ボタン「{label}」がありません: {[b.text() for b in box.buttons()]}")
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    return queue, shown


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.resize(1100, 700)
    w.show()
    _pump()
    yield w
    monkeypatch.setenv(UNSAVED_CHANGES_PROMPT_ENV, "0")
    w.close()


def _saved_window(window, tmp_path):
    window._add_dataset_with_undo(_dataset())
    path = str(tmp_path / "project.graphica")
    window._save_project_to_path(path)
    _pump()
    return path


# --- 変更の検出 ---

def test_conftest_disables_the_prompt_for_the_rest_of_the_suite():
    assert main_window_module._unsaved_changes_prompt_enabled() is False


def test_a_fresh_tab_has_nothing_to_save(window):
    assert window.has_unsaved_changes() is False


def test_adding_data_to_a_new_tab_is_unsaved(window):
    window._add_dataset_with_undo(_dataset())
    assert window.has_unsaved_changes() is True


def test_saving_clears_and_editing_sets_it_again(window, tmp_path):
    _saved_window(window, tmp_path)
    assert window.has_unsaved_changes() is False
    window.ui.title_text_edit.setText("新しいタイトル")
    _pump()
    assert window.has_unsaved_changes() is True


def test_redrawing_is_not_a_change(window, tmp_path):
    _saved_window(window, tmp_path)
    window._update_plot()
    _pump()
    assert window.has_unsaved_changes() is False


def test_switching_the_edited_subplot_is_not_a_change(window, tmp_path):
    window.subplot_rows_spinbox.setValue(2)
    _pump()
    _saved_window(window, tmp_path)
    window.active_axis_combo.setCurrentIndex(1)
    _pump()
    assert window.has_unsaved_changes() is False


def test_changes_outside_the_undo_stack_are_detected(window, tmp_path, monkeypatch):
    """フォルダの作成は Undo の対象外だが、保存内容は変わる。"""
    _saved_window(window, tmp_path)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("フォルダ", True)))
    window._on_new_folder()
    _pump()
    assert window.has_unsaved_changes() is True


def test_editing_data_values_directly_is_detected(window, tmp_path):
    _saved_window(window, tmp_path)
    window.project.datasets[0].df.loc[0, "y"] = 123.0
    assert window.has_unsaved_changes() is True


def test_undoing_back_to_the_saved_state_is_not_a_change(window, tmp_path):
    _saved_window(window, tmp_path)
    window.ui.plot_type_combo.setCurrentText("Scatter")
    _pump()
    assert window.has_unsaved_changes() is True
    window.undo_stack.undo()
    _pump()
    assert window.has_unsaved_changes() is False


def test_loading_a_project_starts_clean(window, tmp_path):
    path = _saved_window(window, tmp_path)
    window.ui.title_text_edit.setText("編集")
    _pump()
    window._load_project_from_path(path)
    _pump()
    assert window.has_unsaved_changes() is False


def test_restoring_from_autosave_counts_as_unsaved(window, tmp_path):
    path = _saved_window(window, tmp_path)
    window._load_project_from_path(path, add_to_recent=False)
    _pump()
    assert window._current_project_path is None
    assert window.has_unsaved_changes() is True


def test_fingerprint_ignores_the_active_axis_but_not_content():
    project = ProjectModel()
    project.all_plot_settings = [{"title": "a"}, {"title": "b"}]
    before = project.content_fingerprint()
    project.active_axis_index = 1
    assert project.content_fingerprint() == before
    project.all_plot_settings[1]["title"] = "c"
    assert project.content_fingerprint() != before


# --- 確認ダイアログ ---

def test_no_prompt_without_changes(window, tmp_path, prompt_enabled, answers):
    _saved_window(window, tmp_path)
    queue, shown = answers
    assert window.confirm_unsaved_changes("タブを閉じる") is True
    assert shown == []


def test_cancel_stops_the_action(window, prompt_enabled, answers):
    window._add_dataset_with_undo(_dataset())
    queue, shown = answers
    queue.append("キャンセル")
    assert window.confirm_unsaved_changes("タブを閉じる") is False
    assert "無題のプロジェクト" in shown[0][0]
    assert "タブを閉じる" in shown[0][1]


def test_discard_continues_without_saving(window, tmp_path, prompt_enabled, answers):
    path = _saved_window(window, tmp_path)
    window.ui.title_text_edit.setText("編集")
    _pump()
    queue, shown = answers
    queue.append("保存しない")
    assert window.confirm_unsaved_changes("タブを閉じる") is True
    reloaded = ProjectModel()
    reloaded.load_project(path)
    assert reloaded.all_plot_settings[0].get("title", "") != "編集"


def test_save_writes_the_file_and_continues(window, tmp_path, prompt_enabled, answers):
    path = _saved_window(window, tmp_path)
    window.ui.title_text_edit.setText("保存するタイトル")
    _pump()
    queue, shown = answers
    queue.append("保存")
    assert window.confirm_unsaved_changes("タブを閉じる") is True
    reloaded = ProjectModel()
    reloaded.load_project(path)
    assert reloaded.all_plot_settings[0]["title"] == "保存するタイトル"


def test_save_as_cancelled_does_not_continue(window, prompt_enabled, answers, monkeypatch):
    window._add_dataset_with_undo(_dataset())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    queue, shown = answers
    queue.append("保存")
    assert window.confirm_unsaved_changes("タブを閉じる") is False


def test_open_project_asks_first_and_cancel_skips_the_file_dialog(window, prompt_enabled, answers, monkeypatch):
    window._add_dataset_with_undo(_dataset())
    opened = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: opened.append(1) or ("", "")))
    queue, shown = answers
    queue.append("キャンセル")
    window.manual_load()
    assert opened == []
    assert "別のプロジェクトを開く" in shown[0][1]


def test_open_recent_project_asks_first(window, tmp_path, prompt_enabled, answers, monkeypatch):
    other = ProjectModel()
    other_path = str(tmp_path / "other.graphica")
    other.save_project(other_path)
    window._add_dataset_with_undo(_dataset())
    queue, shown = answers
    queue.append("キャンセル")
    window._on_open_recent_file(other_path)
    assert len(window.project.datasets) == 1  # 読み込まれていない


# --- タブ/アプリを閉じる ---

@pytest.fixture
def app_window(tmp_path, monkeypatch):
    w = _make_isolated_main_app_window(tmp_path, monkeypatch)
    yield w
    monkeypatch.setenv(UNSAVED_CHANGES_PROMPT_ENV, "0")


def test_closing_a_modified_tab_can_be_cancelled(app_window, prompt_enabled, answers):
    second = app_window.add_new_project_tab()
    second._add_dataset_with_undo(_dataset())
    queue, shown = answers
    queue.append("キャンセル")
    app_window._on_tab_close_requested(app_window.tab_widget.indexOf(second))
    assert app_window.tab_widget.count() == 2


def test_closing_a_modified_tab_without_saving_closes_it(app_window, prompt_enabled, answers):
    second = app_window.add_new_project_tab()
    second._add_dataset_with_undo(_dataset())
    queue, shown = answers
    queue.append("保存しない")
    app_window._on_tab_close_requested(app_window.tab_widget.indexOf(second))
    assert app_window.tab_widget.count() == 1


def test_closing_an_unmodified_tab_does_not_ask(app_window, prompt_enabled, answers):
    app_window.add_new_project_tab()
    queue, shown = answers
    app_window._on_tab_close_requested(1)
    assert app_window.tab_widget.count() == 1
    assert shown == []


def test_quitting_is_cancelled_if_any_tab_is_cancelled(app_window, prompt_enabled, answers):
    second = app_window.add_new_project_tab()
    second._add_dataset_with_undo(_dataset())
    queue, shown = answers
    queue.append("キャンセル")
    event = QCloseEvent()
    app_window.closeEvent(event)
    assert event.isAccepted() is False
    assert app_window.tab_widget.currentWidget() is second  # どのタブか分かるよう前面に出す


def test_quitting_asks_each_modified_tab(app_window, prompt_enabled, answers):
    first = app_window.tab_widget.widget(0)
    first._add_dataset_with_undo(_dataset("a"))
    second = app_window.add_new_project_tab()
    second._add_dataset_with_undo(_dataset("b"))
    queue, shown = answers
    queue.extend(["保存しない", "保存しない"])
    event = QCloseEvent()
    app_window.closeEvent(event)
    assert len(shown) == 2
    assert event.isAccepted() is True
