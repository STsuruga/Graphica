# tests/test_app_context.py
"""gui/app_context.py (AppContext, C-006) のテスト。"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QTabWidget, QWidget

import gui.app_context as app_context_module
from gui.app_context import AppContext
from gui.main_window import MAX_RECENT_FILES
from core.plugin_api import GraphicaPluginAPI


class _FakeMainAppWindow:
    """AppContextのテスト用。実際のMainAppWindow/PlotterAppは起動が重いため、
    active_plotter_app等が読む tab_widget だけを持つ最小限のダブル。"""

    def __init__(self):
        self.tab_widget = QTabWidget()


def _isolated_app_context(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でAppContextを1つ作る
    (実際のレジストリ/iniファイルを汚染しないため、tests/test_main_window.pyの
    _make_isolated_plotter_appと同じパターン)。"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_context_module, "QSettings", IsolatedQSettings)

    main_app_window = _FakeMainAppWindow()
    return AppContext(main_app_window), main_app_window


# --- 最近使ったファイル ---

def test_recent_files_starts_empty(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    assert ctx.get_recent_files() == []


def test_add_recent_file_inserts_at_front(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    ctx.add_recent_file("a.graphica")
    ctx.add_recent_file("b.graphica")
    files = ctx.get_recent_files()
    assert files[0].endswith("b.graphica")
    assert files[1].endswith("a.graphica")


def test_add_recent_file_moves_duplicate_to_front(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    ctx.add_recent_file("a.graphica")
    ctx.add_recent_file("b.graphica")
    ctx.add_recent_file("a.graphica")
    files = ctx.get_recent_files()
    assert len(files) == 2
    assert files[0].endswith("a.graphica")
    assert files[1].endswith("b.graphica")


def test_add_recent_file_respects_max_limit(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    for i in range(MAX_RECENT_FILES + 5):
        ctx.add_recent_file(f"file{i}.graphica")
    files = ctx.get_recent_files()
    assert len(files) == MAX_RECENT_FILES
    assert files[0].endswith(f"file{MAX_RECENT_FILES + 4}.graphica")


def test_clear_recent_files(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    ctx.add_recent_file("a.graphica")
    ctx.clear_recent_files()
    assert ctx.get_recent_files() == []


# --- 現在アクティブなタブへのアクセス ---

def test_active_plotter_app_is_none_without_tabs(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    assert ctx.active_plotter_app is None
    assert ctx.active_project is None
    assert ctx.active_undo_stack is None


def test_active_project_and_undo_stack_reflect_current_tab(tmp_path, monkeypatch):
    """
    アクティブタブが切り替わるたびに、active_project/active_undo_stackが
    「呼び出し時点の」現在のタブを反映すること(キャッシュしないこと)を確認する。
    プラグインコールバックが古いタブへの参照を握り続けてしまう既知の罠
    (core/plugin_api.pyのGraphicaPluginAPI._main_window)を、この設計では
    踏まないことの回帰テスト。
    """
    ctx, main_app_window = _isolated_app_context(tmp_path, monkeypatch)

    class _FakePlotterApp(QWidget):
        def __init__(self):
            super().__init__()
            self.project = object()
            self.undo_stack = object()

    tab1 = _FakePlotterApp()
    tab2 = _FakePlotterApp()
    main_app_window.tab_widget.addTab(tab1, "Tab1")
    main_app_window.tab_widget.addTab(tab2, "Tab2")

    main_app_window.tab_widget.setCurrentIndex(0)
    assert ctx.active_plotter_app is tab1
    assert ctx.active_project is tab1.project
    assert ctx.active_undo_stack is tab1.undo_stack

    main_app_window.tab_widget.setCurrentIndex(1)
    assert ctx.active_plotter_app is tab2
    assert ctx.active_project is tab2.project
    assert ctx.active_undo_stack is tab2.undo_stack


# --- プラグインレジストリ ---

def test_plugin_api_returns_graphica_plugin_api_instance(tmp_path, monkeypatch):
    ctx, _ = _isolated_app_context(tmp_path, monkeypatch)
    assert isinstance(ctx.plugin_api, GraphicaPluginAPI)
