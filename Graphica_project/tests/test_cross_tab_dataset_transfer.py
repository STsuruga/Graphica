# tests/test_cross_tab_dataset_transfer.py
"""
タブ間のデータセットコピー/移動(項目C-905)に対するテスト。
gui/mixins/dataset_mixin.py の _get_sibling_tabs/_on_copy_or_move_dataset_to_tab/
_remove_datasets_without_confirmation を、実際に複数タブを持つ MainAppWindow を
使って検証する(タブ=完全に独立した PlotterApp インスタンスという設計上、
単体 PlotterApp だけでは他タブの存在を再現できないため)。

セットアップは tests/test_main_app_window.py の _make_isolated_main_app_window
に倣う。
"""
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

import gui.main_app_window as main_app_window_module
import gui.main_window as main_window_module
import gui.app_context as app_context_module
import gui.mixins.dataset_mixin as dataset_mixin_module
from gui.main_app_window import MainAppWindow
from core.dataset import Dataset


def _make_isolated_main_app_window(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトし、起動時ダイアログが一切ブロックしない状態でMainAppWindowを1つ作る。"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_app_window_module, "QSettings", IsolatedQSettings)
    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    monkeypatch.setattr(app_context_module, "QSettings", IsolatedQSettings)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    class FakeWelcomeDialog:
        def __init__(self, *args, **kwargs):
            self.load_sample_requested = False
            # 項目C-912: 実際のWelcomeDialogはこれらも常に設定するため、
            # _show_welcome_dialog()の分岐でAttributeErrorにならないよう
            # フェイクでも同じ属性一式を用意する。
            self.selected_recent_file = None
            self.load_template_requested = False

        def exec(self):
            return 0

    monkeypatch.setattr(main_window_module, "WelcomeDialog", FakeWelcomeDialog)

    window = MainAppWindow()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _make_simple_dataset(name):
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [1.0, 2.0, 3.0]})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def _add_and_select(tab, dataset):
    tab._add_dataset(dataset, None, select=True)
    return dataset


# --- _get_sibling_tabs ---

def test_get_sibling_tabs_standalone_plotter_app_returns_empty(tmp_path, monkeypatch):
    """MainAppWindow無しの単体PlotterApp(主にテスト環境)では空リストになる"""
    from gui.main_window import PlotterApp

    settings_path = str(tmp_path / "settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)

    assert window._get_sibling_tabs() == []


def test_get_sibling_tabs_lists_other_tabs_with_titles(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    tab2 = window.add_new_project_tab()

    siblings = tab1._get_sibling_tabs()

    assert len(siblings) == 1
    title, widget = siblings[0]
    assert widget is tab2
    assert isinstance(title, str)


def test_get_sibling_tabs_excludes_self(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    window.add_new_project_tab()
    window.add_new_project_tab()

    siblings = tab1._get_sibling_tabs()

    assert all(widget is not tab1 for _, widget in siblings)
    assert len(siblings) == 2


# --- _on_copy_or_move_dataset_to_tab: コピー ---

def test_copy_no_selection_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    window.add_new_project_tab()

    tab1._on_copy_or_move_dataset_to_tab(move=False)  # 例外にならず何もしない


def test_copy_no_other_tabs_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    ds = _add_and_select(tab1, _make_simple_dataset("d0"))

    info_calls = []
    monkeypatch.setattr(
        dataset_mixin_module.QMessageBox, "information",
        staticmethod(lambda *a, **k: info_calls.append(a)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=False)

    assert len(info_calls) == 1
    assert ds in tab1.project.datasets  # 元タブには残ったまま


def test_copy_adds_independent_dataset_to_target_tab_and_keeps_source(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    tab2 = window.add_new_project_tab()
    ds = _add_and_select(tab1, _make_simple_dataset("d0"))

    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (window._tab_title_for(tab2), True)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=False)

    assert ds in tab1.project.datasets  # コピーなので元タブに残る
    assert len(tab2.project.datasets) == 1
    copied = tab2.project.datasets[0]
    assert copied is not ds
    assert copied.name == "d0"
    assert copied.dataset_id != ds.dataset_id  # コピー先で新しいIDが振られる
    # データが完全に独立している(参照共有していない)ことを確認
    copied.df.iloc[0, 1] = 999.0
    assert ds.df.iloc[0, 1] != 999.0


def test_copy_cancelled_dialog_transfers_nothing(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    tab2 = window.add_new_project_tab()
    _add_and_select(tab1, _make_simple_dataset("d0"))

    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("", False)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=False)

    assert len(tab2.project.datasets) == 0


def test_copy_multiple_selected_datasets(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    tab2 = window.add_new_project_tab()
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        tab1._add_dataset(ds, None, select=False)
    tab1.ui.dataset_list_widget.selectAll()

    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (window._tab_title_for(tab2), True)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=False)

    assert len(tab2.project.datasets) == 3
    assert len(tab1.project.datasets) == 3  # コピーなので元タブも3件のまま


# --- _on_copy_or_move_dataset_to_tab: 移動 ---

def test_move_removes_from_source_tab(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    tab2 = window.add_new_project_tab()
    ds = _add_and_select(tab1, _make_simple_dataset("d0"))

    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (window._tab_title_for(tab2), True)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=True)

    assert ds not in tab1.project.datasets
    assert len(tab2.project.datasets) == 1
    assert tab2.project.datasets[0].name == "d0"


def test_move_removes_tree_item_from_source_tab(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    tab2 = window.add_new_project_tab()
    ds = _add_and_select(tab1, _make_simple_dataset("d0"))

    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (window._tab_title_for(tab2), True)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=True)

    assert tab1._get_dataset_tree_item(ds) is None


def test_move_cancelled_dialog_keeps_dataset_in_source(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    tab1 = window.tab_widget.widget(0)
    window.add_new_project_tab()
    ds = _add_and_select(tab1, _make_simple_dataset("d0"))

    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("", False)),
    )

    tab1._on_copy_or_move_dataset_to_tab(move=True)

    assert ds in tab1.project.datasets
