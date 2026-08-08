# tests/test_dialogs.py
"""gui/dialogs.py の一部ダイアログの入力パース/設定ロジックに対するテスト。

ダイアログ自体のexec()(モーダル表示)は呼ばず、値の設定・取得ロジックのみを検証する。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.dialogs import (NewDatasetDialog, PreferencesDialog, ExportDialog, BatchExportDialog,
                         FitDialog, SavGolDialog, PluginParamDialog, LabelEditDialog,
                         ColorPaletteDialog, HelpDialog, CalcHelpDialog, ResultDialog)
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


# --- LabelEditDialog(項目H-2-4: タイトル/軸ラベルのポップアップ編集) ---

_SAMPLE_PALETTE = [("α", "alpha"), ("Ω", "Omega")]


def test_label_edit_dialog_prefills_initial_text_and_title():
    dlg = LabelEditDialog("初期テキスト", "タイトルを編集", _SAMPLE_PALETTE)
    assert dlg.get_text() == "初期テキスト"
    assert dlg.windowTitle() == "タイトルを編集"


def test_label_edit_dialog_get_text_reflects_manual_edits():
    dlg = LabelEditDialog("", "X軸ラベルを編集", _SAMPLE_PALETTE)
    dlg.text_edit.setText("手入力したテキスト")
    assert dlg.get_text() == "手入力したテキスト"


def test_label_edit_dialog_decoration_buttons_have_no_focus_policy(qapp):
    """
    バグ回帰テスト(実機フィードバック: 「選択してボタン押しても文字選択しろと
    出る」が一度直したはずなのに再発)。

    当初はQPushButton.pressedで選択範囲を先読みする方式で対処したが、
    QTest.mouseClick()で実際のクリックを再現するとそれでも直っていなかった
    (下のtest_label_edit_dialog_bold_button_survives_a_real_mouse_click参照)。
    真因は「clickedが遅い」ことではなく、QPushButtonの既定フォーカスポリシー
    (StrongFocus)により、Qtがマウス押下イベントをボタンへ配送する前にフォーカス
    をボタン側へ移してしまい、その時点でtext_edit側の選択状態が失われていた
    こと。本質的な修正は装飾ボタン自体にフォーカスを渡さないことなので、
    focusPolicyがNoFocusになっていることを直接検証する。
    """
    from PySide6.QtWidgets import QPushButton, QToolButton

    dlg = LabelEditDialog("Peak XYZ", "タイトルを編集", _SAMPLE_PALETTE)
    decoration_tooltips = {"太字", "イタリック", "上付き文字", "下付き文字"}
    decoration_buttons = [
        b for b in dlg.findChildren(QPushButton) if b.toolTip() in decoration_tooltips
    ]
    assert len(decoration_buttons) == 4  # OK/Cancel(QDialogButtonBox側)は対象外
    for button in decoration_buttons:
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus
    for button in dlg.findChildren(QToolButton):
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_label_edit_dialog_bold_button_survives_a_real_mouse_click(qapp):
    """
    上と対になる、実際のマウスクリック(QTest.mouseClick、press+releaseを
    通常のイベントパイプライン経由で配送する)を使った回帰テスト。
    .pressed.emit()や_capture_pending_selection()を手動で呼ぶテストは
    「配線が正しいか」までしか検証できず、Qtの実際のフォーカス遷移タイミングに
    起因するこのバグを見逃していた実例(このテスト自体がその教訓)。
    """
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    dlg = LabelEditDialog("Peak XYZ", "タイトルを編集", _SAMPLE_PALETTE)
    dlg.show()
    dlg.text_edit.setFocus()
    dlg.text_edit.setSelection(0, 4)  # "Peak"
    assert dlg.text_edit.hasSelectedText()

    bold_button = next(
        b for b in dlg.findChildren(QPushButton) if b.toolTip() == "太字"
    )
    QTest.mouseClick(bold_button, Qt.MouseButton.LeftButton)

    assert dlg.get_text() == r"$\mathbf{Peak}$ XYZ"
    dlg.close()


# --- 複数のmathtext装飾を重ねて適用する(実機フィードバック: 「mathtextを
#     複数適用しようとすると(例: イタリック+ボールド、上付き+ボールド)
#     バグる」) ---

def test_apply_wrap_combines_bold_then_italic_into_boldsymbol(qapp):
    """
    太字を適用した直後の選択範囲(装飾操作後は結果全体が自動選択される)に
    続けてイタリックを適用すると、単純な入れ子("$\\mathit{$\\mathbf{...}}$"
    のような不正な二重$)にはならず、太字とイタリックを同時に表現できる
    \\boldsymbolに置き換わることを確認する。
    """
    dlg = LabelEditDialog("wavelength", "タイトルを編集", _SAMPLE_PALETTE)
    dlg.text_edit.setSelection(0, len("wavelength"))
    dlg._capture_pending_selection()
    dlg._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}")
    assert dlg.get_text() == r"$\mathbf{wavelength}$"

    dlg._capture_pending_selection()  # 直前の結果全体が選択されている状態を再現
    dlg._apply_wrap("italic", lambda s: f"\\mathit{{{s}}}")

    assert dlg.get_text() == r"$\boldsymbol{wavelength}$"
    assert dlg.get_text().count("$") == 2  # $の入れ子になっていない


def test_apply_wrap_combines_italic_then_bold_into_boldsymbol(qapp):
    """上と対称のケース(先にイタリック、後から太字)。"""
    dlg = LabelEditDialog("wavelength", "タイトルを編集", _SAMPLE_PALETTE)
    dlg.text_edit.setSelection(0, len("wavelength"))
    dlg._capture_pending_selection()
    dlg._apply_wrap("italic", lambda s: f"\\mathit{{{s}}}")

    dlg._capture_pending_selection()
    dlg._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}")

    assert dlg.get_text() == r"$\boldsymbol{wavelength}$"


def test_apply_wrap_combines_superscript_then_bold_without_nested_dollar_signs(qapp):
    """
    「上付き+ボールド」の組み合わせも回帰対象。太字/イタリックのような
    フォントクラスの合成(\\boldsymbol化)は不要だが、単純な二重$のバグは
    こちらにも共通するため、有効なmathtext構文になることを確認する。
    """
    import matplotlib.mathtext as mathtext

    dlg = LabelEditDialog("wavelength", "タイトルを編集", _SAMPLE_PALETTE)
    dlg.text_edit.setSelection(0, len("wavelength"))
    dlg._capture_pending_selection()
    dlg._apply_wrap("super", lambda s: f"{{}}^{{{s}}}")

    dlg._capture_pending_selection()
    dlg._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}")

    text = dlg.get_text()
    assert text.count("$") == 2
    mathtext.MathTextParser('path').parse(text, dpi=100)  # 例外を投げなければOK


def test_apply_wrap_without_prior_wrapping_still_wraps_plain_selection(qapp):
    """通常の(初回の)装飾適用は従来通り動作することの回帰確認。"""
    dlg = LabelEditDialog("Peak XYZ", "タイトルを編集", _SAMPLE_PALETTE)
    dlg.text_edit.setSelection(0, 4)  # "Peak"
    dlg._capture_pending_selection()
    dlg._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}")

    assert dlg.get_text() == r"$\mathbf{Peak}$ XYZ"


# --- ダイアログ内のライブプレビュー(実機フィードバック: 「ボタンを押して
#     mathtext形式で書かれたラベルが出力されるんじゃなくて実際にボールドとか
#     イタリックとかが適用されてるテキストが見れるようにしたい」) ---

def test_label_edit_dialog_has_preview_label_rendering_initial_text(qapp):
    dlg = LabelEditDialog("wavelength", "タイトルを編集", _SAMPLE_PALETTE)
    pixmap = dlg.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()


def test_label_edit_dialog_preview_updates_when_text_changes(qapp):
    dlg = LabelEditDialog("", "タイトルを編集", _SAMPLE_PALETTE)
    empty_pixmap = dlg.preview_label.pixmap()

    dlg.text_edit.setText("wavelength")

    filled_pixmap = dlg.preview_label.pixmap()
    assert (filled_pixmap.width(), filled_pixmap.height()) != (
        empty_pixmap.width(), empty_pixmap.height(),
    )


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


# --- ColorPaletteDialog(項目H-2-6、実機での目視確認で発覚したバグの回帰) ---

def test_color_palette_dialog_lists_one_row_per_color(qapp):
    palettes = {"カスタム": ["#e6194b", "#3cb44b"]}
    dlg = ColorPaletteDialog(palettes, "カスタム")
    assert dlg.color_list.count() == 2


def test_color_palette_dialog_row_widget_shows_readable_hex_text(qapp):
    """
    バグ回帰テスト: 以前はQListWidgetItem.setBackground()/setForeground()で
    行全体を色で塗り明るさに応じて白/黒文字にしていたが、QSSが::itemに
    何かひとつでもプロパティを当てるとBackgroundRole/ForegroundRoleを
    無視してしまうため、実機ではリストの地の色のまま文字色だけが適用され、
    明るい色/暗い色の一部が読めなくなっていた(例: ライトモードで青・緑は
    白文字を選択するため白地に白文字で消える)。setItemWidget()による
    スウォッチ+通常文字色のテキストラベルに置き換えたことを確認する。
    """
    from PySide6.QtWidgets import QLabel

    palettes = {"カスタム": ["#1f77b4", "#ff7f0e"]}
    dlg = ColorPaletteDialog(palettes, "カスタム")

    row_widget = dlg.color_list.itemWidget(dlg.color_list.item(0))
    assert row_widget is not None
    labels = row_widget.findChildren(QLabel)
    text_label = next(l for l in labels if l.text() == "#1f77b4")
    # テキストラベル自体には色固有のスタイルが付いていない
    # (=常にテーマの通常文字色で描画され、可読性の問題が起きない)
    assert "background-color" not in text_label.styleSheet()

    # 色そのものはスウォッチ(小さな正方形)側にだけ反映されている
    swatch = next(l for l in labels if "#1f77b4" in l.styleSheet())
    assert "background-color: #1f77b4" in swatch.styleSheet()


def test_color_palette_dialog_no_longer_uses_background_foreground_roles(qapp):
    """
    setBackground()/setForeground()経由の着色に戻っていないことを確認する
    (QSSに無視される既知の問題があるため、意図的にsetItemWidget方式へ
    移行した)。
    """
    from PySide6.QtCore import Qt

    palettes = {"カスタム": ["#e6194b"]}
    dlg = ColorPaletteDialog(palettes, "カスタム")
    item = dlg.color_list.item(0)
    assert item.background().style() == Qt.BrushStyle.NoBrush  # 未設定(デフォルト)のまま


def test_color_palette_dialog_remove_selected_color_uses_row_selection(qapp):
    """setItemWidget化した後もcurrentRow()による行選択が機能することの確認
    (_on_remove_colorが依存している)。"""
    palettes = {"カスタム": ["#e6194b", "#3cb44b"]}
    dlg = ColorPaletteDialog(palettes, "カスタム")
    dlg.color_list.setCurrentRow(0)

    dlg._on_remove_color()

    assert dlg.palettes["カスタム"] == ["#3cb44b"]


def test_color_palette_dialog_default_palette_uses_matplotlib_cycle(qapp):
    import matplotlib as mpl

    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)
    expected_count = len(mpl.rcParams['axes.prop_cycle'].by_key()['color'])
    assert dlg.color_list.count() == expected_count


# --- HelpDialog/CalcHelpDialog(項目H-2-6、実機での目視確認で発覚したバグの
#     回帰): 表の見出し行が背景色#f0f0f0をハードコードしており、ダークモードで
#     ほぼ見えなくなっていた ---

def test_help_dialog_does_not_hardcode_header_row_background(qapp):
    from PySide6.QtWidgets import QTextBrowser

    dlg = HelpDialog()
    text_browser = dlg.findChild(QTextBrowser)
    assert "#f0f0f0" not in text_browser.toHtml()


def test_help_dialog_header_row_stylesheet_uses_dark_tokens_in_dark_mode(qapp):
    from gui import theme

    theme.apply_theme(qapp, dark=True)
    dlg = HelpDialog()
    from PySide6.QtWidgets import QTextBrowser
    text_browser = dlg.findChild(QTextBrowser)
    stylesheet = text_browser.document().defaultStyleSheet()
    assert theme.DARK_TOKENS["surface_2"] in stylesheet
    assert theme.DARK_TOKENS["text_primary"] in stylesheet
    theme.apply_theme(qapp, dark=False)  # 他のテストに影響しないよう戻す


def test_calc_help_dialog_does_not_hardcode_header_row_background(qapp):
    from PySide6.QtWidgets import QTextBrowser

    dlg = CalcHelpDialog()
    text_browser = dlg.findChild(QTextBrowser)
    assert "#f0f0f0" not in text_browser.toHtml()


def test_calc_help_dialog_header_row_stylesheet_uses_light_tokens_in_light_mode(qapp):
    from gui import theme
    from PySide6.QtWidgets import QTextBrowser

    theme.apply_theme(qapp, dark=False)
    dlg = CalcHelpDialog()
    text_browser = dlg.findChild(QTextBrowser)
    stylesheet = text_browser.document().defaultStyleSheet()
    assert theme.LIGHT_TOKENS["surface_2"] in stylesheet
    assert theme.LIGHT_TOKENS["text_primary"] in stylesheet


def test_help_dialog_refresh_theme_updates_stylesheet_after_live_toggle(qapp):
    """
    回帰テスト: HelpDialog/CalcHelpDialogは非モーダル(show())で開いたまま
    ダークモードを切り替えられるが、以前は見出し行の色を__init__時点の
    テーマトークンで固定していたため、開いたまま切り替えると古い色の
    ままになっていた。refresh_theme()を呼べば現在のテーマに追従することを
    確認する。
    """
    from gui import theme
    from PySide6.QtWidgets import QTextBrowser

    theme.apply_theme(qapp, dark=False)
    dlg = HelpDialog()
    text_browser = dlg.findChild(QTextBrowser)
    assert theme.LIGHT_TOKENS["surface_2"] in text_browser.document().defaultStyleSheet()

    theme.apply_theme(qapp, dark=True)
    dlg.refresh_theme()
    assert theme.DARK_TOKENS["surface_2"] in text_browser.document().defaultStyleSheet()
    theme.apply_theme(qapp, dark=False)  # 他のテストに影響しないよう戻す


def test_calc_help_dialog_refresh_theme_updates_stylesheet_after_live_toggle(qapp):
    from gui import theme
    from PySide6.QtWidgets import QTextBrowser

    theme.apply_theme(qapp, dark=False)
    dlg = CalcHelpDialog()
    text_browser = dlg.findChild(QTextBrowser)

    theme.apply_theme(qapp, dark=True)
    dlg.refresh_theme()
    assert theme.DARK_TOKENS["surface_2"] in text_browser.document().defaultStyleSheet()
    theme.apply_theme(qapp, dark=False)


# --- ResultDialog(曲線フィット結果の残差プロット) ---

def test_result_dialog_residual_plot_uses_dark_theme_facecolor(qapp):
    """
    回帰テスト: 残差プロットはgui/canvas.pyのMplCanvasとは別の独立した
    Figureをその場で作っており、以前はmatplotlib既定の白背景+黒文字の
    まま固定されていた(ダイアログ本体はダークモードに追従するのに、
    残差プロットだけ白いまま浮いて見えていた)。
    """
    import matplotlib.colors as mcolors
    from gui import theme
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    theme.apply_theme(qapp, dark=True)
    try:
        dlg = ResultDialog(
            "フィット結果", "a=1.0", residual_x=[1, 2, 3], residual_y=[0.1, -0.1, 0.05]
        )
        canvas = dlg.findChild(FigureCanvasQTAgg)
        assert canvas is not None
        assert mcolors.to_rgba(canvas.figure.get_facecolor()) == mcolors.to_rgba(
            theme.DARK_TOKENS['surface']
        )
    finally:
        theme.apply_theme(qapp, dark=False)
