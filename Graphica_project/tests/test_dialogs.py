# tests/test_dialogs.py
"""gui/dialogs.py の一部ダイアログの入力パース/設定ロジックに対するテスト。

ダイアログ自体のexec()(モーダル表示)は呼ばず、値の設定・取得ロジックのみを検証する。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.dialogs import (NewDatasetDialog, PreferencesDialog, ExportDialog, BatchExportDialog,
                         FitDialog, SavGolDialog, PluginParamDialog)
import core.plugin_install as plugin_install_module
from core.plugin_install import PluginInstallError
from core.plugin_types import PluginHookKind, PluginRegistrationError


# --- NewDatasetDialog (項目63: 空のテーブルから新規データセットを作成) ---

def test_new_dataset_dialog_defaults():
    dlg = NewDatasetDialog()
    assert dlg.get_dataset_name() == "新規データセット"
    assert dlg.get_column_names() == ["X", "Y"]
    assert dlg.get_row_count() == 5


def test_new_dataset_dialog_column_names_dedup_strip_and_skip_empty():
    dlg = NewDatasetDialog()
    dlg.columns_edit.setText(" A, B ,A, ,C")
    assert dlg.get_column_names() == ["A", "B", "C"]


def test_new_dataset_dialog_dataset_name_strips_whitespace():
    dlg = NewDatasetDialog()
    dlg.name_edit.setText("  My Data  ")
    assert dlg.get_dataset_name() == "My Data"


def test_new_dataset_dialog_row_count_reflects_spinbox():
    dlg = NewDatasetDialog()
    dlg.rows_spinbox.setValue(20)
    assert dlg.get_row_count() == 20


def test_new_dataset_dialog_no_column_names_returns_empty_list():
    dlg = NewDatasetDialog()
    dlg.columns_edit.setText("   ,  ,")
    assert dlg.get_column_names() == []


# --- FitDialog (項目C-402: 重み付きフィット, C-404: フィット範囲指定) ---

def test_fit_dialog_weighted_defaults_to_unchecked():
    dlg = FitDialog()
    assert dlg.get_weighted() is False


def test_fit_dialog_weighted_reflects_checkbox():
    dlg = FitDialog()
    dlg.weighted_checkbox.setChecked(True)
    assert dlg.get_weighted() is True


def test_fit_dialog_x_range_is_none_when_checkbox_unchecked():
    dlg = FitDialog(x_min=1.0, x_max=10.0)
    assert dlg.get_x_range() is None


def test_fit_dialog_x_range_prefills_from_constructor_args():
    dlg = FitDialog(x_min=2.5, x_max=9.5)
    dlg.range_checkbox.setChecked(True)
    assert dlg.get_x_range() == (2.5, 9.5)


def test_fit_dialog_x_range_spinboxes_disabled_until_checkbox_checked():
    dlg = FitDialog()
    assert dlg.range_min_spinbox.isEnabled() is False
    assert dlg.range_max_spinbox.isEnabled() is False
    dlg.range_checkbox.setChecked(True)
    assert dlg.range_min_spinbox.isEnabled() is True
    assert dlg.range_max_spinbox.isEnabled() is True


def test_fit_dialog_x_range_reflects_user_edited_spinbox_values():
    dlg = FitDialog()
    dlg.range_checkbox.setChecked(True)
    dlg.range_min_spinbox.setValue(-3.0)
    dlg.range_max_spinbox.setValue(7.0)
    assert dlg.get_x_range() == (-3.0, 7.0)


# --- SavGolDialog (項目C-301: 平滑化, C-302: 微分) ---

def test_savgol_dialog_defaults_to_smoothing():
    dlg = SavGolDialog("D1")
    window, polyorder, deriv, output_name = dlg.get_settings()
    assert deriv == 0
    assert output_name == "D1_smoothed"
    assert window >= 3
    assert polyorder >= 1


def test_savgol_dialog_mode_change_updates_output_name_and_deriv():
    dlg = SavGolDialog("D1")
    dlg.mode_combo.setCurrentText(SavGolDialog.MODE_DERIV1)
    _, _, deriv, output_name = dlg.get_settings()
    assert deriv == 1
    assert output_name == "D1_deriv1"

    dlg.mode_combo.setCurrentText(SavGolDialog.MODE_DERIV2)
    _, _, deriv, output_name = dlg.get_settings()
    assert deriv == 2
    assert output_name == "D1_deriv2"


def test_savgol_dialog_window_and_polyorder_reflect_spinboxes():
    dlg = SavGolDialog("D1")
    dlg.window_spinbox.setValue(11)
    dlg.polyorder_spinbox.setValue(3)
    window, polyorder, _, _ = dlg.get_settings()
    assert window == 11
    assert polyorder == 3


def test_savgol_dialog_window_max_capped_by_data_length():
    dlg = SavGolDialog("D1", max_window=7)
    assert dlg.window_spinbox.maximum() == 7


# --- PreferencesDialog (項目: オートセーブ保存先の指定) ---

def test_preferences_dialog_get_settings_returns_seven_tuple():
    dlg = PreferencesDialog(dark_mode=True, autosave_minutes=10,
                             current_language="en", autosave_dir="/tmp/foo",
                             point_label_max_points=2000,
                             snap_to_grid_enabled=True, snap_grid_interval_px=25)
    (dark_mode, minutes, lang, autosave_dir, point_label_max,
     snap_to_grid_enabled, snap_grid_interval_px) = dlg.get_settings()
    assert dark_mode is True
    assert minutes == 10
    assert lang == "en"
    assert autosave_dir == "/tmp/foo"
    assert point_label_max == 2000
    assert snap_to_grid_enabled is True
    assert snap_grid_interval_px == 25


# --- スナップ・トゥ・グリッド(項目84) ---

def test_preferences_dialog_snap_to_grid_defaults():
    """スナップ・トゥ・グリッドの既定値は無効・間隔10px。"""
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    assert dlg.snap_to_grid_checkbox.isChecked() is False
    assert dlg.snap_grid_interval_spinbox.value() == 10
    settings = dlg.get_settings()
    assert settings[5] is False
    assert settings[6] == 10


def test_preferences_dialog_snap_to_grid_checkbox_and_spinbox_round_trip():
    """チェックボックス/スピンボックスの操作が get_settings() の戻り値に反映されること
    (オートセーブ間隔のプリファレンスと同じ「spinbox + QSettings永続化」パターン)。"""
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5,
                             snap_to_grid_enabled=False, snap_grid_interval_px=10)

    dlg.snap_to_grid_checkbox.setChecked(True)
    dlg.snap_grid_interval_spinbox.setValue(50)

    settings = dlg.get_settings()
    assert settings[5] is True
    assert settings[6] == 50


def test_preferences_dialog_snap_grid_interval_spinbox_range():
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    assert dlg.snap_grid_interval_spinbox.minimum() == 1
    assert dlg.snap_grid_interval_spinbox.maximum() == 200


def test_preferences_dialog_defaults_to_empty_autosave_dir():
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    assert dlg.autosave_dir_edit.text() == ""
    assert dlg.get_settings()[3] == ""


def test_preferences_dialog_clear_autosave_dir_resets_to_empty():
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, autosave_dir="/tmp/foo")
    assert dlg.get_settings()[3] == "/tmp/foo"

    dlg._on_clear_autosave_dir()

    assert dlg.get_settings()[3] == ""
    assert dlg.autosave_dir_edit.text() == ""


# --- プラグインのzipインストール導線(項目E-2) ---

def _patch_message_box_capture(monkeypatch):
    """QMessageBox.information / .critical の呼び出しを記録するdictを返す"""
    calls = {"information": [], "critical": []}

    def fake_information(*args, **kwargs):
        calls["information"].append(args)

    def fake_critical(*args, **kwargs):
        calls["critical"].append(args)

    monkeypatch.setattr(QMessageBox, "information", staticmethod(fake_information))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(fake_critical))
    return calls


def test_install_plugin_cancelled_file_dialog_shows_nothing(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    calls = _patch_message_box_capture(monkeypatch)

    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    dlg._on_install_plugin()

    assert calls["information"] == []
    assert calls["critical"] == []


def test_install_plugin_success_shows_next_launch_wording(monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("/tmp/my_plugin.zip", ""))
    )
    monkeypatch.setattr(plugin_install_module, "install_plugin_zip", lambda zip_path: "my_plugin")
    calls = _patch_message_box_capture(monkeypatch)

    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    dlg._on_install_plugin()

    assert calls["critical"] == []
    assert len(calls["information"]) == 1
    message = calls["information"][0][2]
    assert "次回起動時" in message


def test_install_plugin_failure_shows_critical_message(monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("/tmp/bad_plugin.zip", ""))
    )

    def fake_install(zip_path):
        raise PluginInstallError("これはテスト用のエラーメッセージです")

    monkeypatch.setattr(plugin_install_module, "install_plugin_zip", fake_install)
    calls = _patch_message_box_capture(monkeypatch)

    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    dlg._on_install_plugin()

    assert calls["information"] == []
    assert len(calls["critical"]) == 1
    assert "これはテスト用のエラーメッセージです" in calls["critical"][0][2]


# --- 背景透過オプション(項目108) ---

def test_export_dialog_transparent_defaults_true_and_reflected_in_options():
    dlg = ExportDialog()
    assert dlg.transparent_checkbox.isChecked() is True
    assert dlg.get_options()["transparent"] is True

    dlg.transparent_checkbox.setChecked(False)
    assert dlg.get_options()["transparent"] is False


def test_batch_export_dialog_transparent_defaults_true_and_reflected_in_options():
    dlg = BatchExportDialog(subplot_count=2)
    assert dlg.get_common_options()["transparent"] is True

    dlg.transparent_checkbox.setChecked(False)
    assert dlg.get_common_options()["transparent"] is False


# --- SVG文字のアウトライン化オプション(項目88) ---

def test_export_dialog_svg_text_as_path_defaults_false_and_reflected_in_options():
    dlg = ExportDialog()
    assert dlg.svg_text_as_path_checkbox.isChecked() is False
    assert dlg.get_options()["svg_text_as_path"] is False

    dlg.svg_text_as_path_checkbox.setChecked(True)
    assert dlg.get_options()["svg_text_as_path"] is True


def test_batch_export_dialog_svg_text_as_path_defaults_false_and_reflected_in_options():
    dlg = BatchExportDialog(subplot_count=2)
    assert dlg.get_common_options()["svg_text_as_path"] is False

    dlg.svg_text_as_path_checkbox.setChecked(True)
    assert dlg.get_common_options()["svg_text_as_path"] is True


# --- register_exporter()由来の追加形式(項目B-2) ---

def test_batch_export_dialog_default_formats_without_extra_formats():
    dlg = BatchExportDialog(subplot_count=2)
    items = [dlg.format_combo.itemText(i) for i in range(dlg.format_combo.count())]
    assert items == ["PNG", "PDF", "SVG"]


def test_batch_export_dialog_appends_extra_formats():
    dlg = BatchExportDialog(subplot_count=2, extra_formats=["MyFormat"])
    items = [dlg.format_combo.itemText(i) for i in range(dlg.format_combo.count())]
    assert items == ["PNG", "PDF", "SVG", "MyFormat"]


def test_batch_export_dialog_extra_format_selectable_and_lowercased_in_options():
    dlg = BatchExportDialog(subplot_count=2, extra_formats=["MyFormat"])
    dlg.format_combo.setCurrentText("MyFormat")
    assert dlg.get_common_options()["format"] == "myformat"


# --- PluginParamDialog (項目C-1/C-2: register_processor/register_analyzerの
#     param_schemaからの自動フォーム生成) ---

def test_plugin_param_dialog_int_widget_default_and_range():
    schema = [{"name": "window", "label": "窓幅", "type": "int", "default": 5, "min": 1, "max": 99}]
    dlg = PluginParamDialog("Smooth", schema)
    assert dlg.get_values() == {"window": 5}


def test_plugin_param_dialog_int_widget_defaults_to_zero_when_no_default():
    schema = [{"name": "window", "type": "int"}]
    dlg = PluginParamDialog("Smooth", schema)
    assert dlg.get_values() == {"window": 0}


def test_plugin_param_dialog_float_widget_default_and_decimals():
    schema = [{"name": "threshold", "type": "float", "default": 0.25, "decimals": 2}]
    dlg = PluginParamDialog("Peaks", schema)
    assert dlg.get_values() == {"threshold": 0.25}


def test_plugin_param_dialog_bool_widget_default():
    schema = [{"name": "invert", "type": "bool", "default": True}]
    dlg = PluginParamDialog("Smooth", schema)
    assert dlg.get_values() == {"invert": True}


def test_plugin_param_dialog_bool_widget_defaults_to_false():
    schema = [{"name": "invert", "type": "bool"}]
    dlg = PluginParamDialog("Smooth", schema)
    assert dlg.get_values() == {"invert": False}


def test_plugin_param_dialog_choice_widget_default_selection():
    schema = [{"name": "mode", "type": "choice", "choices": ["A", "B", "C"], "default": "B"}]
    dlg = PluginParamDialog("Smooth", schema)
    assert dlg.get_values() == {"mode": "B"}


def test_plugin_param_dialog_str_widget_default_and_unknown_type_fallback():
    schema = [
        {"name": "label", "type": "str", "default": "hello"},
        {"name": "weird", "type": "unknown_type", "default": "fallback"},
    ]
    dlg = PluginParamDialog("Smooth", schema)
    assert dlg.get_values() == {"label": "hello", "weird": "fallback"}


def test_plugin_param_dialog_get_values_reflects_edited_widgets():
    schema = [
        {"name": "window", "type": "int", "default": 5},
        {"name": "mode", "type": "choice", "choices": ["A", "B"], "default": "A"},
    ]
    dlg = PluginParamDialog("Smooth", schema)
    window_widget = dlg._widgets["window"][1]
    mode_widget = dlg._widgets["mode"][1]
    window_widget.setValue(42)
    mode_widget.setCurrentText("B")
    assert dlg.get_values() == {"window": 42, "mode": "B"}


def test_plugin_param_dialog_empty_schema_returns_empty_values():
    dlg = PluginParamDialog("NoParams", [])
    assert dlg.get_values() == {}


def test_plugin_param_dialog_sets_window_title():
    dlg = PluginParamDialog("My Processor", [])
    assert dlg.windowTitle() == "My Processor"


# --- PreferencesDialogの「プラグイン」タブ(項目F-2) ---

def test_preferences_dialog_plugin_tab_shows_not_loaded_placeholder_when_records_none():
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=None)
    assert dlg.plugin_list.count() == 1
    item = dlg.plugin_list.item(0)
    assert not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable)


def test_preferences_dialog_plugin_tab_shows_empty_placeholder_when_no_plugins():
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=[])
    assert dlg.plugin_list.count() == 1
    item = dlg.plugin_list.item(0)
    assert not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable)


def test_preferences_dialog_plugin_tab_lists_loaded_plugin_with_checkbox():
    records = [{"name": "my_plugin", "info": {"name": "My Plugin", "version": "1.0",
                                               "author": "test"}, "error": None, "disabled": False}]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records)
    assert dlg.plugin_list.count() == 1
    item = dlg.plugin_list.item(0)
    assert "My Plugin" in item.text()
    assert item.checkState() == Qt.CheckState.Checked


def test_preferences_dialog_plugin_tab_shows_error_for_failed_plugin():
    records = [{"name": "broken_plugin", "info": None, "error": "plugin.json が見つかりません",
                "disabled": False}]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records)
    item = dlg.plugin_list.item(0)
    assert "plugin.json" in item.text()


def test_preferences_dialog_plugin_tab_disabled_plugin_starts_unchecked():
    records = [{"name": "my_plugin", "info": {"name": "My Plugin", "version": "1.0",
                                               "author": "test"}, "error": None, "disabled": True}]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records,
                             disabled_plugin_names={"my_plugin"})
    item = dlg.plugin_list.item(0)
    assert item.checkState() == Qt.CheckState.Unchecked
    assert "無効化中" in item.text()


def test_preferences_dialog_get_disabled_plugin_names_reflects_unchecked_items():
    records = [
        {"name": "plugin_a", "info": {"name": "A", "version": "1.0", "author": "t"},
         "error": None, "disabled": False},
        {"name": "plugin_b", "info": {"name": "B", "version": "1.0", "author": "t"},
         "error": None, "disabled": False},
    ]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records)
    assert dlg.get_disabled_plugin_names() == set()

    dlg.plugin_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dlg.get_disabled_plugin_names() == {"plugin_a"}


def test_preferences_dialog_get_disabled_plugin_names_preinitialized_from_constructor():
    records = [{"name": "plugin_a", "info": {"name": "A", "version": "1.0", "author": "t"},
                "error": None, "disabled": False}]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records,
                             disabled_plugin_names={"plugin_a"})
    assert dlg.get_disabled_plugin_names() == {"plugin_a"}


def test_preferences_dialog_hook_errors_tab_shows_placeholder_when_none():
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_registration_errors=[])
    assert dlg.plugin_hook_errors_list.count() == 1


def test_preferences_dialog_hook_errors_tab_lists_errors():
    errors = [PluginRegistrationError(
        plugin_name="my_plugin", hook_kind=PluginHookKind.FIT_FUNCTION, message="衝突しました"
    )]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_registration_errors=errors)
    assert dlg.plugin_hook_errors_list.count() == 1
    text = dlg.plugin_hook_errors_list.item(0).text()
    assert "my_plugin" in text
    assert "fit_function" in text
    assert "衝突しました" in text


def test_preferences_dialog_open_plugins_folder_button_calls_desktop_services(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("gui.dialogs.QDesktopServices.openUrl", staticmethod(lambda url: calls.append(url)))
    monkeypatch.setattr("core.app_paths.get_user_plugins_dir", lambda: str(tmp_path))

    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    dlg._on_open_plugins_folder()

    assert len(calls) == 1
    assert os.path.normpath(calls[0].toLocalFile()) == os.path.normpath(str(tmp_path))


def test_preferences_dialog_shows_error_for_intentionally_broken_plugin_end_to_end(tmp_path, monkeypatch):
    """
    F-2の完了条件そのものの再現: 意図的に壊した(plugin.jsonの無い)ダミー
    プラグインを置いた状態でロードし、その結果(get_loaded_plugin_records())を
    そのままPreferencesDialogに渡すと、管理UIにエラー理由が表示されること。
    """
    import core.plugin_api as plugin_api_module

    # _singleton_api はプロセス全体で共有されるため、他のテストが既にロード
    # 済みだとload_plugins_once()が何もせずキャッシュを返してしまう。
    # このテスト専用にNoneへ明示的に隔離してから読み込む
    # (tests/test_source_plugin_field.pyで一度踏んだのと同じ罠)。
    monkeypatch.setattr(plugin_api_module, "_singleton_api", None)
    monkeypatch.setattr(plugin_api_module, "_singleton_manager", None)

    plugin_dir = tmp_path / "broken_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("def register(api):\n    pass\n", encoding="utf-8")
    # plugin.json を意図的に置かない

    plugin_api_module.load_plugins_once(str(tmp_path))
    records = plugin_api_module.get_loaded_plugin_records()
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records)

    assert dlg.plugin_list.count() == 1
    item_text = dlg.plugin_list.item(0).text()
    assert "broken_plugin" in item_text
    assert "plugin.json" in item_text
