# tests/test_dialogs.py
"""gui/dialogs.py の一部ダイアログの入力パース/設定ロジックに対するテスト。

ダイアログ自体のexec()(モーダル表示)は呼ばず、値の設定・取得ロジックのみを検証する。
"""
from gui.dialogs import (NewDatasetDialog, PreferencesDialog, ExportDialog, BatchExportDialog,
                         FitDialog, SavGolDialog)


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
