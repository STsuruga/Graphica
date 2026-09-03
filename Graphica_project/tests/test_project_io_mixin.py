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


def test_on_save_project_as_delegates_to_manual_save_as(tmp_path, monkeypatch):
    """実機フィードバック(「プロジェクトの上書き保存と名前つけて保存を追加」)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "manual_save_as", lambda: calls.append(True))

    window._on_save_project_as()

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


# --- _on_save_plot_template (項目C-806: 新形式) ---

def test_on_save_plot_template_writes_style_file(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.ui.title_text_edit.setText("My Saved Title")
    out_path = tmp_path / "template.graphica-style"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), "Graphica Style Template (*.graphica-style)"))

    window._on_save_plot_template()

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["format_version"] == 1
    assert data["subplot_styles"][0]["title"] == "My Saved Title"


def test_on_save_plot_template_excludes_annotations_and_free_rect(tmp_path, monkeypatch):
    """注釈・凡例並び順・自由配置位置はスタイルとして不適切なため、
    保存されるsubplot_stylesには含まれないこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.project.all_plot_settings[0]['annotations'] = [{'type': 'text', 'text': 'hi'}]
    window.project.all_plot_settings[0]['legend_order'] = ['a', 'b']
    window.project.all_plot_settings[0]['free_rect'] = (0.1, 0.1, 0.5, 0.5)
    out_path = tmp_path / "template.graphica-style"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), ""))

    window._on_save_plot_template()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    saved_style = data["subplot_styles"][0]
    assert "annotations" not in saved_style
    assert "legend_order" not in saved_style
    assert "free_rect" not in saved_style


def test_on_save_plot_template_saves_all_subplots_and_dataset_styles(tmp_path, monkeypatch):
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_cols_spinbox.setValue(2)
    ds = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                 color="#ff0000")
    window._add_dataset(ds, None, select=False)
    out_path = tmp_path / "template.graphica-style"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), ""))

    window._on_save_plot_template()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["subplot_styles"]) == 2
    assert len(data["dataset_styles"]) == 1
    assert data["dataset_styles"][0]["color"] == "#ff0000"


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
    # (拡張子を明示しておかないと、拡張子未指定時の自動補完で別パスに
    #  ずれてしまい、ディレクトリと衝突しなくなってしまう)
    bad_path = tmp_path / "a_directory.graphica-style"
    bad_path.mkdir()
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(bad_path), ""))

    warn_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_save_plot_template()

    assert len(warn_calls) == 1


# --- _on_load_plot_template (項目C-806: 新形式) ---

def test_on_load_plot_template_new_format_applies_settings_to_ui(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    template_path = tmp_path / "template.graphica-style"
    template_path.write_text(
        json.dumps({
            "format_version": 1,
            "subplot_styles": [{"title": "Loaded Title", "x_label": "Loaded X"}],
            "dataset_styles": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), ""))

    window._on_load_plot_template()

    assert window.ui.title_text_edit.text() == "Loaded Title"
    assert window.ui.x_label_text_edit.text() == "Loaded X"
    active = window.project.all_plot_settings[window.project.active_axis_index]
    assert active["title"] == "Loaded Title"


def test_on_load_plot_template_new_format_preserves_annotations_and_free_rect(tmp_path, monkeypatch):
    """テンプレート適用後も、既存の注釈・凡例並び順・自由配置位置は
    上書きされず保持されること(スタイルだけが差し替わる)"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    existing_annotations = [{'type': 'text', 'text': 'keep me'}]
    window.project.all_plot_settings[0]['annotations'] = existing_annotations
    template_path = tmp_path / "template.graphica-style"
    template_path.write_text(
        json.dumps({
            "format_version": 1,
            "subplot_styles": [{"title": "New Title", "annotations": ["should be ignored"]}],
            "dataset_styles": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), ""))

    window._on_load_plot_template()

    assert window.project.all_plot_settings[0]['annotations'] == existing_annotations


def test_on_load_plot_template_new_format_cyclic_apply_across_subplots(tmp_path, monkeypatch):
    """サブプロット数がテンプレートより多くても、先頭からサイクリックに適用されること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_cols_spinbox.setValue(2)  # 2枚構成にする
    template_path = tmp_path / "template.graphica-style"
    template_path.write_text(
        json.dumps({
            "format_version": 1,
            "subplot_styles": [{"title": "Only Style"}],
            "dataset_styles": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), ""))

    window._on_load_plot_template()

    assert window.project.all_plot_settings[0]["title"] == "Only Style"
    assert window.project.all_plot_settings[1]["title"] == "Only Style"


def test_on_load_plot_template_new_format_applies_dataset_styles_cyclically(tmp_path, monkeypatch):
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1], "y": [2]}), x_col_name="x", y_col_name="y")
    ds2 = Dataset(name="d2", df=pd.DataFrame({"x": [1], "y": [2]}), x_col_name="x", y_col_name="y")
    window._add_dataset(ds1, None, select=False)
    window._add_dataset(ds2, None, select=False)
    template_path = tmp_path / "template.graphica-style"
    template_path.write_text(
        json.dumps({
            "format_version": 1,
            "subplot_styles": [{}],
            "dataset_styles": [{"color": "#00ff00", "linestyle": "--"}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), ""))

    window._on_load_plot_template()

    assert ds1.color == "#00ff00"
    assert ds1.linestyle == "--"
    assert ds2.color == "#00ff00"  # サイクリックに同じスタイルが2件目にも適用される
    assert ds2.linestyle == "--"


def test_on_load_plot_template_new_format_empty_subplot_styles_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.ui.title_text_edit.setText("unchanged")
    template_path = tmp_path / "empty.graphica-style"
    template_path.write_text(
        json.dumps({"format_version": 1, "subplot_styles": [], "dataset_styles": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(template_path), ""))

    warn_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_load_plot_template()

    assert len(warn_calls) == 1
    assert window.ui.title_text_edit.text() == "unchanged"


# --- _on_load_plot_template (項目C-806以前の旧形式との後方互換) ---

def test_on_load_plot_template_legacy_format_applies_settings_to_ui(tmp_path, monkeypatch):
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


def test_on_load_plot_template_legacy_format_empty_settings_shows_warning(tmp_path, monkeypatch):
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


# --- 設定・スタイルのエクスポート/インポート (項目C-109) ---

def test_on_export_settings_cancelled_writes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))

    window._on_export_settings()

    assert list(tmp_path.iterdir()) == []


def test_on_export_settings_writes_expected_keys(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue("dark_mode", True)
    window.settings.setValue("point_label_max_points", 777)
    window.settings.setValue("language", "en")
    out_path = tmp_path / "settings.json"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))

    window._on_export_settings()

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["format_version"] == 1
    assert data["settings"]["dark_mode"] is True
    assert data["settings"]["point_label_max_points"] == 777
    assert data["settings"]["language"] == "en"


def test_on_export_settings_excludes_machine_specific_keys(tmp_path, monkeypatch):
    """autosave_dir/recent_files等のマシン固有の項目はエクスポート対象に含まれない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue("autosave_dir", r"C:\some\machine\specific\path")
    window.settings.setValue("recent_files", ["a.graphica", "b.graphica"])
    out_path = tmp_path / "settings.json"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))

    window._on_export_settings()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "autosave_dir" not in data["settings"]
    assert "recent_files" not in data["settings"]


def test_on_export_settings_appends_json_extension_if_missing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    out_path_no_ext = tmp_path / "settings"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path_no_ext), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))

    window._on_export_settings()

    assert (tmp_path / "settings.json").exists()


def test_on_import_settings_cancelled_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    window._on_import_settings()  # 例外にならないこと


def test_on_import_settings_roundtrip_applies_values(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    payload = {
        "format_version": 1,
        "settings": {
            "dark_mode": True,
            "point_label_max_points": 999,
            "quick_access_pinned_actions": ["a", "b"],
        },
    }
    in_path = tmp_path / "settings.json"
    in_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(in_path), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))

    window._on_import_settings()

    assert window.settings.value("dark_mode", type=bool) is True
    assert window.settings.value("point_label_max_points", type=int) == 999
    assert window.settings.value("quick_access_pinned_actions") == ["a", "b"]


def test_on_import_settings_ignores_unknown_keys(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    payload = {"format_version": 1, "settings": {"some_unknown_key": "value", "dark_mode": True}}
    in_path = tmp_path / "settings.json"
    in_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(in_path), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))

    window._on_import_settings()

    assert window.settings.value("some_unknown_key") is None
    assert window.settings.value("dark_mode", type=bool) is True


def test_on_import_settings_accepts_plain_dict_without_settings_wrapper(tmp_path, monkeypatch):
    """format_version/settingsラッパーを持たない素朴なdictも許容する"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    in_path = tmp_path / "settings.json"
    in_path.write_text(json.dumps({"dark_mode": True}), encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(in_path), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))

    window._on_import_settings()

    assert window.settings.value("dark_mode", type=bool) is True


def test_on_import_settings_malformed_json_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    in_path = tmp_path / "broken.json"
    in_path.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(in_path), ""))
    warn_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_import_settings()

    assert len(warn_calls) == 1


def test_on_import_settings_no_matching_keys_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    in_path = tmp_path / "settings.json"
    in_path.write_text(json.dumps({"format_version": 1, "settings": {"unknown_only": 1}}), encoding="utf-8")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(in_path), ""))
    info_calls = []
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_import_settings()

    assert len(info_calls) == 1


def test_export_then_import_settings_full_roundtrip(tmp_path, monkeypatch):
    """エクスポート→(値を変更)→インポートで元の値に戻ることを確認する結合テスト"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue("dark_mode", True)
    window.settings.setValue("point_label_max_points", 555)
    out_path = tmp_path / "roundtrip.json"
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName",
                         lambda *a, **k: (str(out_path), ""))
    monkeypatch.setattr(project_io_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: None))
    window._on_export_settings()

    window.settings.setValue("dark_mode", False)
    window.settings.setValue("point_label_max_points", 100)

    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName",
                         lambda *a, **k: (str(out_path), ""))
    window._on_import_settings()

    assert window.settings.value("dark_mode", type=bool) is True
    assert window.settings.value("point_label_max_points", type=int) == 555
