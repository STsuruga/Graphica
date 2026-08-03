# tests/test_dialogs.py
"""gui/dialogs.py の一部ダイアログの入力パース/設定ロジックに対するテスト。

ダイアログ自体のexec()(モーダル表示)は呼ばず、値の設定・取得ロジックのみを検証する。
"""
from gui.dialogs import NewDatasetDialog, PreferencesDialog, ExportDialog, BatchExportDialog


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


# --- PreferencesDialog (項目: オートセーブ保存先の指定) ---

def test_preferences_dialog_get_settings_returns_five_tuple():
    dlg = PreferencesDialog(dark_mode=True, autosave_minutes=10,
                             current_language="en", autosave_dir="/tmp/foo",
                             point_label_max_points=2000)
    dark_mode, minutes, lang, autosave_dir, point_label_max = dlg.get_settings()
    assert dark_mode is True
    assert minutes == 10
    assert lang == "en"
    assert autosave_dir == "/tmp/foo"
    assert point_label_max == 2000


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
