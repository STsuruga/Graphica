# tests/test_project_io_mixin.py
"""
gui/mixins/project_io_mixin.py の ProjectIOMixin に対するテスト。

PlotterApp のインスタンス化パターンは tests/test_main_window.py の
_make_isolated_plotter_app に倣う (QSettingsを一時ファイルにリダイレクトする)。

_on_show_preferences はモーダルダイアログ (PreferencesDialog) を表示するため、
tests/test_dataset_mixin.py の FakeNormalizeDialog と同じパターンで、実際の
ウィジェット構築や exec() を行わない軽量なフェイクに差し替える。
"""
import json

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QInputDialog

import gui.main_window as main_window_module
import gui.mixins.project_io_mixin as project_io_mixin_module
from gui.main_window import PlotterApp
from gui.dialogs import PreferencesDialog


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _patch_preferences_dialog(monkeypatch, accepted=True, settings_tuple=None, disabled_plugin_names=None):
    """
    PreferencesDialog を、実ウィジェットを構築せず exec() でイベントループを
    ブロックしないフェイクに差し替える。呼び出し側 (_on_show_preferences) が
    渡したコンストラクタ引数は captured['kwargs']/captured['args'] に記録する。
    """
    captured = {}

    class FakePreferencesDialog(PreferencesDialog):
        def __init__(self, *args, **kwargs):
            # 実ダイアログの __init__ (QWidget構築) は一切呼ばない
            captured['args'] = args
            captured['kwargs'] = kwargs

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def get_settings(self):
            return settings_tuple

        def get_disabled_plugin_names(self):
            return disabled_plugin_names if disabled_plugin_names is not None else set()

    monkeypatch.setattr(project_io_mixin_module, "PreferencesDialog", FakePreferencesDialog)
    return captured


# --- _on_save_project / _on_load_project (manual_save/manual_load への委譲) ---

def test_on_save_project_delegates_to_manual_save(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "manual_save", lambda: calls.append(True))

    window._on_save_project()

    assert calls == [True]


def test_on_load_project_delegates_to_manual_load(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "manual_load", lambda: calls.append(True))

    window._on_load_project()

    assert calls == [True]


# --- _on_configure_autosave_interval / _apply_autosave_interval ---

def test_configure_autosave_interval_applies_new_value(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *a, **k: (7, True)))

    window._on_configure_autosave_interval()

    assert window.autosave_timer.isActive()
    assert window.autosave_timer.interval() == 7 * 60 * 1000
    assert window.settings.value("autosave_interval_min") == 7


def test_configure_autosave_interval_cancelled_leaves_state_unchanged(tmp_path, monkeypatch):
    """ダイアログでキャンセルされた場合(ok=False)、何も変更されないこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._apply_autosave_interval(10)
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *a, **k: (99, False)))

    window._on_configure_autosave_interval()

    assert window.autosave_timer.interval() == 10 * 60 * 1000


def test_apply_autosave_interval_zero_disables_autosave(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._apply_autosave_interval(5)
    assert window.autosave_timer.isActive()

    window._apply_autosave_interval(0)

    assert not window.autosave_timer.isActive()
    assert "無効" in window.autosave_interval_action.text()


def test_apply_autosave_interval_positive_enables_autosave_and_updates_menu_text(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    window._apply_autosave_interval(15)

    assert window.autosave_timer.isActive()
    assert window.autosave_timer.interval() == 15 * 60 * 1000
    assert "15" in window.autosave_interval_action.text()


# --- _on_show_preferences ---

def test_on_show_preferences_cancelled_applies_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    original_dark_mode = window.canvas.dark_mode
    _patch_preferences_dialog(monkeypatch, accepted=False)

    window._on_show_preferences()

    assert window.canvas.dark_mode == original_dark_mode


def test_on_show_preferences_applies_dark_mode_and_autosave_changes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._apply_autosave_interval(0)
    original_dark_mode = window.canvas.dark_mode

    new_settings = (
        not original_dark_mode,  # dark_mode
        20,                      # autosave_minutes
        "ja",                    # language (same as current -> no message expected unless changed)
        "",                      # autosave_dir (unchanged)
        1000,                    # point_label_max_points (unchanged default)
        False,                   # snap_to_grid
        10,                      # snap_grid_interval
    )
    _patch_preferences_dialog(monkeypatch, accepted=True, settings_tuple=new_settings)

    window._on_show_preferences()
    QApplication.instance().processEvents()

    assert window.canvas.dark_mode == (not original_dark_mode)
    assert window.autosave_timer.isActive()
    assert window.autosave_timer.interval() == 20 * 60 * 1000


def test_on_show_preferences_applies_autosave_dir_change(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    new_dir = str(tmp_path / "custom_autosave")

    current_minutes = 0
    new_settings = (
        window.canvas.dark_mode, current_minutes, "ja", new_dir, 1000, False, 10,
    )
    _patch_preferences_dialog(monkeypatch, accepted=True, settings_tuple=new_settings)

    window._on_show_preferences()

    assert window.settings.value("autosave_dir", "", type=str) == new_dir
    assert new_dir in window._autosave_filename


def test_on_show_preferences_applies_point_label_max_and_redraws(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    new_settings = (
        window.canvas.dark_mode, 0, "ja", "", 2500, False, 10,
    )
    _patch_preferences_dialog(monkeypatch, accepted=True, settings_tuple=new_settings)

    window._on_show_preferences()

    assert window.canvas.point_label_max_points == 2500
    assert window.settings.value("point_label_max_points", type=int) == 2500


def test_on_show_preferences_applies_snap_to_grid_changes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    new_settings = (
        window.canvas.dark_mode, 0, "ja", "", 1000, True, 25,
    )
    _patch_preferences_dialog(monkeypatch, accepted=True, settings_tuple=new_settings)

    window._on_show_preferences()

    assert window.snap_to_grid_enabled is True
    assert window.snap_grid_interval_px == 25
    assert window.settings.value("snap_to_grid_enabled", type=bool) is True
    assert window.settings.value("snap_grid_interval_px", type=int) == 25


def test_on_show_preferences_language_change_shows_restart_notice(tmp_path, monkeypatch):
    """表示言語が変更された場合、次回起動時に反映される旨のメッセージが出ること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    from core.i18n import get_language
    other_language = "en" if get_language() != "en" else "ja"

    new_settings = (
        window.canvas.dark_mode, 0, other_language, "", 1000, False, 10,
    )
    _patch_preferences_dialog(monkeypatch, accepted=True, settings_tuple=new_settings)

    info_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_show_preferences()

    assert len(info_calls) == 1
    assert window.settings.value("language") == other_language


def test_on_show_preferences_disabled_plugin_names_are_persisted(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    from gui.main_window import DISABLED_PLUGINS_SETTINGS_KEY

    new_settings = (
        window.canvas.dark_mode, 0, "ja", "", 1000, False, 10,
    )
    _patch_preferences_dialog(
        monkeypatch, accepted=True, settings_tuple=new_settings,
        disabled_plugin_names={"some_plugin"},
    )

    window._on_show_preferences()

    stored = window.settings.value(DISABLED_PLUGINS_SETTINGS_KEY)
    assert list(stored) == ["some_plugin"]


# --- _on_save_plot_template ---

def test_on_save_plot_template_writes_json_file(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.ui.title_text_edit.setText("My Saved Title")
    out_path = tmp_path / "template.json"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), "Plotter Template Files (*.json)"))

    window._on_save_plot_template()

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["plot_settings"]["title"] == "My Saved Title"


def test_on_save_plot_template_cancelled_writes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))

    window._on_save_plot_template()

    assert list(tmp_path.iterdir()) == []


def test_on_save_plot_template_write_failure_shows_warning(tmp_path, monkeypatch):
    """保存先が書き込み不能な場合(ここではディレクトリを指定して衝突させる)、
    警告ダイアログが出てクラッシュしないこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    # ディレクトリと同名のパスを渡すことで open(..., 'w') を確実に失敗させる
    bad_path = tmp_path / "a_directory"
    bad_path.mkdir()
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(bad_path), "Plotter Template Files (*.json)"))

    warn_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_save_plot_template()

    assert len(warn_calls) == 1


# --- _on_load_plot_template ---

def test_on_load_plot_template_applies_settings_to_ui(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    template_path = tmp_path / "template.json"
    template_path.write_text(
        json.dumps({"plot_settings": {"title": "Loaded Title", "x_label": "Loaded X"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), "Plotter Template Files (*.json)"))

    window._on_load_plot_template()

    assert window.ui.title_text_edit.text() == "Loaded Title"
    assert window.ui.x_label_text_edit.text() == "Loaded X"
    # _on_axis_setting_changed() を経由して all_plot_settings にも反映されること
    active = window.project.all_plot_settings[window.project.active_axis_index]
    assert active["title"] == "Loaded Title"


def test_on_load_plot_template_cancelled_leaves_ui_unchanged(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.ui.title_text_edit.setText("unchanged")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    window._on_load_plot_template()

    assert window.ui.title_text_edit.text() == "unchanged"


def test_on_load_plot_template_empty_settings_shows_warning(tmp_path, monkeypatch):
    """plot_settingsキーが空/存在しないファイルを読み込んだ場合、警告を出して何もしないこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.ui.title_text_edit.setText("unchanged")
    template_path = tmp_path / "empty_template.json"
    template_path.write_text(json.dumps({"plot_settings": {}}), encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), "Plotter Template Files (*.json)"))

    warn_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_load_plot_template()

    assert len(warn_calls) == 1
    assert window.ui.title_text_edit.text() == "unchanged"


def test_on_load_plot_template_malformed_json_shows_warning(tmp_path, monkeypatch):
    """壊れたJSONファイルを読み込もうとした場合、例外を捕捉して警告ダイアログを出すこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    template_path = tmp_path / "broken.json"
    template_path.write_text("{ this is not valid json", encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), "Plotter Template Files (*.json)"))

    warn_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_load_plot_template()

    assert len(warn_calls) == 1
