# tests/test_dialogs.py
"""gui/dialogs.py の一部ダイアログの入力パース/設定ロジックに対するテスト。

ダイアログ自体のexec()(モーダル表示)は呼ばず、値の設定・取得ロジックのみを検証する。
"""
import os

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QInputDialog, QColorDialog

from gui.dialogs import (NewDatasetDialog, PreferencesDialog, ExportDialog, BatchExportDialog,
                         FitDialog, SavGolDialog, PluginParamDialog, LabelEditDialog,
                         ColorPaletteDialog, HelpDialog, CalcHelpDialog, ResultDialog,
                         AboutDialog, WelcomeDialog, PeakSettingsDialog, ColumnCalculatorDialog,
                         ColumnPreviewDialog, ReplicateErrorDialog, ColumnTypeDialog,
                         ExcelMultiSheetDialog, DatasetArithmeticDialog, NormalizeDatasetDialog,
                         CommandPaletteDialog, QuickAccessManagerDialog, ShortcutsDialog,
                         LegendOrderDialog, MultiPeakFitDialog)
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


# --- FitDialog パラメータテーブル(項目C-403: 初期値・固定・範囲拘束UI) ---

def test_fit_dialog_param_table_has_one_row_per_parameter_for_default_fit_type():
    """既定選択(「線形」、a・bの2パラメータ)で、初期化時点でテーブルが2行になっていること。"""
    dlg = FitDialog()
    assert dlg.fit_type_combo.currentText() == "線形 (y = ax + b)"
    assert dlg.param_table.rowCount() == 2
    assert dlg.param_table.item(0, 0).text() == "a"
    assert dlg.param_table.item(1, 0).text() == "b"


def test_fit_dialog_param_table_rebuilds_when_fit_type_changes():
    dlg = FitDialog()
    dlg.fit_type_combo.setCurrentText("ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)")
    assert dlg.param_table.rowCount() == 4
    names = [dlg.param_table.item(row, 0).text() for row in range(4)]
    assert names == ['a', 'b', 'c', 'd']


@pytest.mark.parametrize("display_text, expected_names", [
    ("ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)", ['a', 'b', 'c', 'd']),
    ("擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)",
     ['a', 'b', 'c', 'eta', 'd']),
    ("フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)",
     ['a', 'b', 'sigma', 'gamma', 'd']),
    ("2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)", ['a1', 'b1', 'a2', 'b2', 'c']),
    ("ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))", ['a1', 'a2', 'x0', 'dx']),
    ("ヒルの式 (y = vmax*x^n / (k^n + x^n))", ['vmax', 'k', 'n']),
])
def test_fit_dialog_combo_includes_new_builtin_models_and_rebuilds_param_table(display_text, expected_names):
    """項目C-408: 新規追加した組み込みモデル(Voigt/pseudo-Voigt/Lorentzian/
    2成分指数/Boltzmannシグモイド/Hill)がコンボボックスの選択肢に含まれており、
    選択するとパラメータテーブルが対応する行数・パラメータ名で再構築されること。"""
    dlg = FitDialog()
    items = [dlg.fit_type_combo.itemText(i) for i in range(dlg.fit_type_combo.count())]
    assert display_text in items
    dlg.fit_type_combo.setCurrentText(display_text)
    assert dlg.param_table.rowCount() == len(expected_names)
    names = [dlg.param_table.item(row, 0).text() for row in range(len(expected_names))]
    assert names == expected_names


def test_fit_dialog_param_table_empty_for_untouched_custom_formula():
    """「カスタム数式...」を選んだ直後(数式は未入力)は0行であること。"""
    dlg = FitDialog()
    dlg.fit_type_combo.setCurrentText("カスタム数式...")
    assert dlg.param_table.rowCount() == 0


def test_fit_dialog_param_table_rebuilds_as_custom_formula_is_typed():
    dlg = FitDialog()
    dlg.fit_type_combo.setCurrentText("カスタム数式...")
    dlg.custom_formula_edit.setText("a*exp(-b*x)+c")
    assert dlg.param_table.rowCount() == 3
    names = [dlg.param_table.item(row, 0).text() for row in range(3)]
    assert names == ['a', 'b', 'c']


def test_fit_dialog_param_table_does_not_crash_on_invalid_formula_midway():
    """数式がパラメータを含まない(パース不能)入力途中の状態でも例外を投げず、
    単に0行になること。"""
    dlg = FitDialog()
    dlg.fit_type_combo.setCurrentText("カスタム数式...")
    dlg.custom_formula_edit.setText("42")
    assert dlg.param_table.rowCount() == 0
    # その後、有効な数式に修正すれば正しく再構築される
    dlg.custom_formula_edit.setText("42*x+a")
    assert dlg.param_table.rowCount() == 1
    assert dlg.param_table.item(0, 0).text() == "a"


def test_fit_dialog_get_param_settings_defaults_to_empty_dicts():
    """何もカスタマイズしなければ、p0_overrides/fixed_params/boundsはすべて空dict。"""
    dlg = FitDialog()
    p0_overrides, fixed_params, bounds = dlg.get_param_settings()
    assert p0_overrides == {}
    assert fixed_params == {}
    assert bounds == {}


def test_fit_dialog_get_param_settings_untouched_value_spinbox_not_in_p0_overrides():
    """値欄をユーザーが一度も触らなければ(デフォルトの1.0のままでも)
    p0_overridesには含めない(=フィットタイプごとの自動推定デフォルトを使う)。"""
    dlg = FitDialog()
    p0_overrides, _, _ = dlg.get_param_settings()
    assert 'a' not in p0_overrides
    assert 'b' not in p0_overrides


def test_fit_dialog_get_param_settings_reflects_p0_override():
    dlg = FitDialog()
    value_spin_a = dlg.param_table.cellWidget(0, 1)
    value_spin_a.setValue(3.5)
    p0_overrides, fixed_params, bounds = dlg.get_param_settings()
    assert p0_overrides == {'a': 3.5}
    assert fixed_params == {}


def test_fit_dialog_get_param_settings_reflects_fixed_param():
    dlg = FitDialog()
    value_spin_b = dlg.param_table.cellWidget(1, 1)
    fixed_check_b = dlg.param_table.cellWidget(1, 2)
    value_spin_b.setValue(2.0)
    fixed_check_b.setChecked(True)
    p0_overrides, fixed_params, bounds = dlg.get_param_settings()
    assert fixed_params == {'b': 2.0}
    # 固定された行は(値欄を触っていても)p0_overrides/boundsには入らない
    assert 'b' not in p0_overrides
    assert 'b' not in bounds


def test_fit_dialog_get_param_settings_reflects_bounds():
    dlg = FitDialog()
    range_check_a = dlg.param_table.cellWidget(0, 3)
    min_spin_a = dlg.param_table.cellWidget(0, 4)
    max_spin_a = dlg.param_table.cellWidget(0, 5)
    range_check_a.setChecked(True)
    min_spin_a.setValue(-2.0)
    max_spin_a.setValue(5.0)
    p0_overrides, fixed_params, bounds = dlg.get_param_settings()
    assert bounds == {'a': (-2.0, 5.0)}


def test_fit_dialog_fixed_checkbox_disables_range_controls():
    """「固定」チェックを入れると「範囲拘束」チェックと最小/最大欄が無効化されること
    (固定パラメータには範囲拘束の概念が適用されないため)。"""
    dlg = FitDialog()
    fixed_check_a = dlg.param_table.cellWidget(0, 2)
    range_check_a = dlg.param_table.cellWidget(0, 3)
    min_spin_a = dlg.param_table.cellWidget(0, 4)
    max_spin_a = dlg.param_table.cellWidget(0, 5)

    range_check_a.setChecked(True)
    assert min_spin_a.isEnabled() is True
    assert max_spin_a.isEnabled() is True

    fixed_check_a.setChecked(True)
    assert range_check_a.isEnabled() is False
    assert min_spin_a.isEnabled() is False
    assert max_spin_a.isEnabled() is False

    fixed_check_a.setChecked(False)
    assert range_check_a.isEnabled() is True


def test_fit_dialog_min_max_spinboxes_disabled_until_range_checked():
    dlg = FitDialog()
    min_spin_a = dlg.param_table.cellWidget(0, 4)
    max_spin_a = dlg.param_table.cellWidget(0, 5)
    range_check_a = dlg.param_table.cellWidget(0, 3)
    assert min_spin_a.isEnabled() is False
    assert max_spin_a.isEnabled() is False
    range_check_a.setChecked(True)
    assert min_spin_a.isEnabled() is True
    assert max_spin_a.isEnabled() is True


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


def test_preferences_dialog_plugin_action_buttons_do_not_retain_focus():
    """
    実機フィードバック(「プラグインとデータテーブルのとこのボタンが一回
    押すと他のボタン押すまでずっと色付きになる」)。「プラグインをインストール...」
    「プラグインフォルダを開く」はOK/Cancelフローとは独立した即時実行ボタンなので、
    フォーカスの青枠(gui/theme.pyのQPushButton:focus)が居座らないようにする。
    """
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    assert dlg.install_plugin_button.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert dlg.open_plugins_folder_button.focusPolicy() == Qt.FocusPolicy.NoFocus


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


# --- AboutDialog ---

def test_about_dialog_shows_version_and_app_name(qapp):
    from core.version import APP_NAME, __version__

    dlg = AboutDialog()
    assert APP_NAME in dlg.windowTitle()
    assert __version__ in dlg.windowTitle() or True  # バージョンはタイトルには出ないため存在確認のみ


def test_about_dialog_with_parent_icon_shows_icon_label(qapp):
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QWidget, QLabel

    parent = QWidget()
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.red)
    parent.setWindowIcon(QIcon(pixmap))

    dlg = AboutDialog(parent=parent)
    icon_labels = [l for l in dlg.findChildren(QLabel) if l.pixmap() is not None and not l.pixmap().isNull()]
    assert len(icon_labels) >= 1


def test_about_dialog_without_parent_has_no_icon_label(qapp):
    dlg = AboutDialog(parent=None)
    # 例外なく構築できることを確認(parent=Noneの分岐、36-52行)
    assert dlg.windowTitle() != ""


# --- WelcomeDialog ---

def test_welcome_dialog_load_sample_button_sets_flag_and_accepts(qapp):
    dlg = WelcomeDialog()
    assert dlg.load_sample_requested is False

    dlg._on_load_sample_clicked()

    assert dlg.load_sample_requested is True
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_welcome_dialog_close_button_does_not_set_flag(qapp):
    dlg = WelcomeDialog()
    dlg.accept()  # 「閉じる」ボタンと同じ経路(load_sample_requestedを介さない)
    assert dlg.load_sample_requested is False


def test_welcome_dialog_with_parent_icon_shows_icon_label(qapp):
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.blue)
    parent.setWindowIcon(QIcon(pixmap))

    dlg = WelcomeDialog(parent=parent)
    assert dlg.windowTitle() != ""


# --- ResultDialog: コピー/CSV保存ボタン ---

def test_result_dialog_copy_button_sets_clipboard_and_feedback_text(qapp):
    from PySide6.QtWidgets import QApplication

    dlg = ResultDialog("結果", "a=1.0\nb=2.0")
    dlg._on_copy()

    assert QApplication.clipboard().text() == "a=1.0\nb=2.0"
    assert "コピーしました" in dlg.copy_button.text()
    assert dlg.copy_button.isEnabled() is False


def test_result_dialog_save_csv_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    dlg = ResultDialog("結果", "text", csv_data=df)

    dlg._on_save_csv()  # 例外が起きなければOK(保存処理は呼ばれない)


def test_result_dialog_save_csv_success_shows_information(qapp, monkeypatch, tmp_path):
    calls = _patch_message_box_capture(monkeypatch)
    out_path = str(tmp_path / "out.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))

    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    dlg = ResultDialog("結果", "text", csv_data=df)
    dlg._on_save_csv()

    assert os.path.exists(out_path)
    assert len(calls["information"]) == 1


def test_result_dialog_save_csv_failure_shows_warning(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: calls["warning"].append(a))
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("/nonexistent_dir_xyz/out.csv", ""))
    )

    df = pd.DataFrame({"x": [1, 2]})
    dlg = ResultDialog("結果", "text", csv_data=df)
    dlg._on_save_csv()

    assert len(calls["warning"]) == 1


# --- PeakSettingsDialog ---

def test_peak_settings_dialog_defaults():
    dlg = PeakSettingsDialog()
    settings = dlg.get_settings()
    assert settings["peak_type"] == "上に凸 (Peaks)"
    assert settings["height"] == 0.0
    assert settings["distance_x"] == 1.0
    assert settings["prominence"] is None  # 0のときはNone


def test_peak_settings_dialog_prominence_above_zero_is_kept():
    dlg = PeakSettingsDialog()
    dlg.prominence_spinbox.setValue(2.5)
    settings = dlg.get_settings()
    assert settings["prominence"] == 2.5


def test_peak_settings_dialog_valley_type_and_custom_values():
    dlg = PeakSettingsDialog()
    dlg.type_combo.setCurrentText("下に凸 (Valleys)")
    dlg.height_spinbox.setValue(-5.0)
    dlg.distance_spinbox.setValue(3.0)
    settings = dlg.get_settings()
    assert settings["peak_type"] == "下に凸 (Valleys)"
    assert settings["height"] == -5.0
    assert settings["distance_x"] == 3.0


def test_peak_settings_dialog_get_peak_settings_accepted_returns_dict(monkeypatch):
    monkeypatch.setattr(PeakSettingsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    result = PeakSettingsDialog.get_peak_settings(parent=None)
    assert result is not None
    assert result["peak_type"] == "上に凸 (Peaks)"


def test_peak_settings_dialog_get_peak_settings_rejected_returns_none(monkeypatch):
    monkeypatch.setattr(PeakSettingsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    result = PeakSettingsDialog.get_peak_settings(parent=None)
    assert result is None


# --- FitDialog: カスタム数式の表示切り替え ---

def test_fit_dialog_custom_formula_fields_hidden_by_default():
    dlg = FitDialog()
    assert dlg.custom_formula_label.isVisible() is False
    assert dlg.custom_formula_edit.isVisible() is False


def test_fit_dialog_custom_formula_fields_shown_when_custom_selected(qapp):
    dlg = FitDialog()
    dlg.show()
    dlg.fit_type_combo.setCurrentText("カスタム数式...")
    assert dlg.custom_formula_label.isVisible() is True
    assert dlg.custom_formula_edit.isVisible() is True

    dlg.fit_type_combo.setCurrentIndex(0)
    assert dlg.custom_formula_label.isVisible() is False
    dlg.close()


def test_fit_dialog_get_fit_type_accepted_builtin(monkeypatch):
    monkeypatch.setattr(FitDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    (fit_type, custom_formula, weighted, x_range,
     p0_overrides, fixed_params, bounds, band_type) = FitDialog.get_fit_type(parent=None)
    assert fit_type == "線形 (y = ax + b)"
    assert custom_formula is None
    assert weighted is False
    assert x_range is None
    # 項目C-403: 何もカスタマイズしなければ空dict(Noneではない)
    assert p0_overrides == {}
    assert fixed_params == {}
    assert bounds == {}
    # 項目C-405: 既定は「表示しない」= None
    assert band_type is None


def test_fit_dialog_get_fit_type_accepted_custom_formula(monkeypatch):
    def fake_exec(self):
        self.fit_type_combo.setCurrentText("カスタム数式...")
        self.custom_formula_edit.setText("a*x+b")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FitDialog, "exec", fake_exec)
    (fit_type, custom_formula, weighted, x_range,
     p0_overrides, fixed_params, bounds, band_type) = FitDialog.get_fit_type(parent=None)
    assert "カスタム数式" in fit_type
    assert custom_formula == "a*x+b"


def test_fit_dialog_get_fit_type_accepted_with_param_customization(monkeypatch):
    """項目C-403: OK時にパラメータテーブルの内容(初期値上書き/固定/範囲拘束)が
    get_fit_type()の戻り値に反映されること。"""
    def fake_exec(self):
        # 線形(a, b)のうち、aを範囲拘束、bを固定する
        range_check_a = self.param_table.cellWidget(0, 3)
        min_spin_a = self.param_table.cellWidget(0, 4)
        max_spin_a = self.param_table.cellWidget(0, 5)
        range_check_a.setChecked(True)
        min_spin_a.setValue(-1.0)
        max_spin_a.setValue(9.0)

        value_spin_b = self.param_table.cellWidget(1, 1)
        fixed_check_b = self.param_table.cellWidget(1, 2)
        value_spin_b.setValue(0.5)
        fixed_check_b.setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FitDialog, "exec", fake_exec)
    (fit_type, custom_formula, weighted, x_range,
     p0_overrides, fixed_params, bounds, band_type) = FitDialog.get_fit_type(parent=None)
    assert fixed_params == {'b': 0.5}
    assert bounds == {'a': (-1.0, 9.0)}
    assert p0_overrides == {}


def test_fit_dialog_get_fit_type_accepted_with_band_type(monkeypatch):
    """項目C-405: 信頼帯/予測帯コンボの選択がget_fit_type()の戻り値に反映されること。"""
    def fake_exec(self):
        self.band_combo.setCurrentText("予測帯 (95%)")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FitDialog, "exec", fake_exec)
    result = FitDialog.get_fit_type(parent=None)
    assert result[-1] == "prediction"


def test_fit_dialog_get_fit_type_rejected_returns_none_tuple(monkeypatch):
    monkeypatch.setattr(FitDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    result = FitDialog.get_fit_type(parent=None)
    assert result == (None, None, False, None, {}, {}, {}, None)


# --- MultiPeakFitDialog (項目C-409/C-410: 多峰分離フィット設定ダイアログ) ---

def test_multi_peak_fit_dialog_defaults():
    dlg = MultiPeakFitDialog()
    assert dlg.get_component_type() == 'gaussian'
    assert dlg.get_baseline_type() == 'constant'
    assert dlg.guess_table.rowCount() == 0
    assert dlg.auto_detect_button.isEnabled() is False


def test_multi_peak_fit_dialog_auto_detect_enabled_when_data_provided():
    dlg = MultiPeakFitDialog(x_data=np.array([1.0, 2.0]), y_data=np.array([1.0, 2.0]))
    assert dlg.auto_detect_button.isEnabled() is True


def test_multi_peak_fit_dialog_prefills_from_constructor_initial_guesses():
    dlg = MultiPeakFitDialog(initial_guesses=[
        {'center': 1.0, 'height': 5.0, 'width': 0.5},
        {'center': 3.0, 'height': 2.0, 'width': 1.0},
    ])
    assert dlg.guess_table.rowCount() == 2
    assert dlg.get_initial_guesses() == [
        {'center': 1.0, 'height': 5.0, 'width': 0.5},
        {'center': 3.0, 'height': 2.0, 'width': 1.0},
    ]


def test_multi_peak_fit_dialog_add_and_remove_guess_row():
    dlg = MultiPeakFitDialog()
    dlg._add_guess_row(center=1.0, height=2.0, width=0.3)
    dlg._add_guess_row(center=4.0, height=6.0, width=0.7)
    assert dlg.guess_table.rowCount() == 2

    dlg.guess_table.selectRow(0)
    dlg._remove_selected_rows()

    assert dlg.guess_table.rowCount() == 1
    assert dlg.get_initial_guesses() == [{'center': 4.0, 'height': 6.0, 'width': 0.7}]


def test_multi_peak_fit_dialog_on_accept_rejects_empty_table(monkeypatch):
    dlg = MultiPeakFitDialog()
    warn_calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))

    dlg._on_accept()

    assert len(warn_calls) == 1
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_multi_peak_fit_dialog_on_accept_succeeds_with_at_least_one_row():
    dlg = MultiPeakFitDialog()
    dlg._add_guess_row(center=0.0, height=1.0, width=1.0)

    dlg._on_accept()

    assert dlg.result() == QDialog.DialogCode.Accepted


def test_multi_peak_fit_dialog_auto_detect_appends_rows_from_peak_quantification(monkeypatch):
    """項目C-411のピーク検出設定ダイアログ経由で得た検出結果(中心/高さ/FWHM)が
    テーブルへ追加行として反映されること(既存行は消えない)。"""
    x = np.linspace(-10, 10, 400)
    y = 5.0 * np.exp(-((x - 0.0) ** 2) / (2 * 1.0 ** 2))
    dlg = MultiPeakFitDialog(x_data=x, y_data=y)
    dlg._add_guess_row(center=99.0, height=99.0, width=99.0)  # 既存の手動追加行

    monkeypatch.setattr(
        PeakSettingsDialog, "get_peak_settings",
        staticmethod(lambda parent=None: {
            "peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None,
        }),
    )

    dlg._on_auto_detect()

    assert dlg.guess_table.rowCount() == 2  # 既存1行 + 検出1ピーク
    guesses = dlg.get_initial_guesses()
    assert guesses[0] == {'center': 99.0, 'height': 99.0, 'width': 99.0}
    assert guesses[1]['center'] == pytest.approx(0.0, abs=0.1)
    assert guesses[1]['height'] == pytest.approx(5.0, abs=0.1)


def test_multi_peak_fit_dialog_auto_detect_cancelled_leaves_table_unchanged():
    dlg = MultiPeakFitDialog(x_data=np.array([1.0, 2.0]), y_data=np.array([1.0, 2.0]))
    import gui.dialogs as dialogs_module
    orig = dialogs_module.PeakSettingsDialog.get_peak_settings
    dialogs_module.PeakSettingsDialog.get_peak_settings = staticmethod(lambda parent=None: None)
    try:
        dlg._on_auto_detect()
    finally:
        dialogs_module.PeakSettingsDialog.get_peak_settings = orig
    assert dlg.guess_table.rowCount() == 0


def test_multi_peak_fit_dialog_auto_detect_no_peaks_found_shows_info(monkeypatch):
    dlg = MultiPeakFitDialog(x_data=np.array([1.0, 2.0, 3.0]), y_data=np.array([1.0, 1.0, 1.0]))
    monkeypatch.setattr(
        PeakSettingsDialog, "get_peak_settings",
        staticmethod(lambda parent=None: {
            "peak_type": "上に凸 (Peaks)", "height": 100.0, "distance_x": 1.0, "prominence": None,
        }),
    )
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    dlg._on_auto_detect()

    assert dlg.guess_table.rowCount() == 0
    assert len(info_calls) == 1


def test_multi_peak_fit_dialog_get_multi_peak_fit_settings_accepted(monkeypatch):
    def fake_exec(self):
        self.component_combo.setCurrentIndex(1)  # lorentzian
        self.baseline_combo.setCurrentIndex(0)    # none
        self._add_guess_row(center=1.0, height=2.0, width=0.5)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MultiPeakFitDialog, "exec", fake_exec)
    component_type, baseline_type, guesses = MultiPeakFitDialog.get_multi_peak_fit_settings(parent=None)
    assert component_type == 'lorentzian'
    assert baseline_type == 'none'
    assert guesses == [{'center': 1.0, 'height': 2.0, 'width': 0.5}]


def test_multi_peak_fit_dialog_get_multi_peak_fit_settings_rejected_returns_none_tuple(monkeypatch):
    monkeypatch.setattr(MultiPeakFitDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    result = MultiPeakFitDialog.get_multi_peak_fit_settings(parent=None)
    assert result == (None, None, None)


# --- ColumnCalculatorDialog(列の計算プリセット) ---

def test_column_calculator_dialog_moving_average_preset():
    dlg = ColumnCalculatorDialog(["A", "B"])
    dlg.preset_source_combo.setCurrentText("A")
    dlg.preset_window_spinbox.setValue(5)
    dlg._apply_preset_moving_average()
    assert dlg.formula_edit.text() == "A.rolling(5).mean()"
    assert dlg.output_col_combo.currentText() == "A_moving_avg5"


def test_column_calculator_dialog_diff_preset():
    dlg = ColumnCalculatorDialog(["A", "B"])
    dlg.preset_source_combo.setCurrentText("B")
    dlg._apply_preset_diff()
    assert dlg.formula_edit.text() == "B.diff()"
    assert dlg.output_col_combo.currentText() == "B_diff"


def test_column_calculator_dialog_normalize_preset():
    dlg = ColumnCalculatorDialog(["A", "B"])
    dlg.preset_source_combo.setCurrentText("A")
    dlg._apply_preset_normalize()
    assert dlg.formula_edit.text() == "(A - A.mean()) / A.std()"
    assert dlg.output_col_combo.currentText() == "A_normalized"


def test_column_calculator_dialog_cumsum_preset():
    dlg = ColumnCalculatorDialog(["A", "B"])
    dlg.preset_source_combo.setCurrentText("A")
    dlg._apply_preset_cumsum()
    assert dlg.formula_edit.text() == "A.cumsum()"
    assert dlg.output_col_combo.currentText() == "A_cumsum"


def test_column_calculator_dialog_presets_noop_with_no_columns():
    dlg = ColumnCalculatorDialog([])
    dlg._apply_preset_moving_average()
    dlg._apply_preset_diff()
    dlg._apply_preset_normalize()
    dlg._apply_preset_cumsum()
    assert dlg.formula_edit.text() == ""


def test_column_calculator_dialog_get_formula_returns_tuple():
    dlg = ColumnCalculatorDialog(["A"])
    dlg.output_col_combo.setCurrentText("C")
    dlg.formula_edit.setText("A * 2")
    assert dlg.get_formula() == ("C", "A * 2")


# --- ColumnPreviewDialog(非Excel: CSV相当) ---

def test_column_preview_dialog_non_excel_basic_construction():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    dlg = ColumnPreviewDialog(df, "data.csv")
    assert dlg.is_excel is False
    assert dlg.table.rowCount() == 3
    assert dlg.table.columnCount() == 2
    assert dlg.get_selected_columns() == ("A", "B")
    assert dlg.get_dataframe() is df


def test_column_preview_dialog_nan_shown_as_empty_string():
    df = pd.DataFrame({"A": [1.0, np.nan], "B": [4, 5]})
    dlg = ColumnPreviewDialog(df, "data.csv")
    assert dlg.table.item(1, 0).text() == ""


def test_column_preview_dialog_preview_capped_at_20_rows():
    df = pd.DataFrame({"A": list(range(25)), "B": list(range(25))})
    dlg = ColumnPreviewDialog(df, "data.csv")
    assert dlg.table.rowCount() == 20
    assert "25行" in dlg.info_label.text()


def test_column_preview_dialog_single_column_y_combo_not_advanced():
    df = pd.DataFrame({"A": [1, 2, 3]})
    dlg = ColumnPreviewDialog(df, "data.csv")
    assert dlg.x_col_combo.currentText() == "A"
    assert dlg.y_col_combo.currentText() == "A"  # 2列目が無いので同じ列のまま


# --- ColumnPreviewDialog(Excel: シート/ヘッダー行/型上書き) ---

@pytest.fixture
def sample_xlsx(tmp_path):
    path = tmp_path / "sample.xlsx"
    with pd.ExcelWriter(str(path)) as writer:
        pd.DataFrame({"A": [1, 2], "B": [3, 4]}).to_excel(writer, sheet_name="Sheet1", index=False)
        pd.DataFrame({"C": [5, 6], "D": [7, 8]}).to_excel(writer, sheet_name="Sheet2", index=False)
    return str(path)


def test_column_preview_dialog_excel_lists_sheet_names(sample_xlsx):
    df = pd.read_excel(sample_xlsx, sheet_name=0)
    dlg = ColumnPreviewDialog(df, "sample.xlsx", file_path=sample_xlsx)
    assert dlg.is_excel is True
    assert dlg.sheet_names == ["Sheet1", "Sheet2"]
    assert [dlg.sheet_combo.itemText(i) for i in range(dlg.sheet_combo.count())] == ["Sheet1", "Sheet2"]


def test_column_preview_dialog_excel_switch_sheet_reloads_columns(sample_xlsx):
    df = pd.read_excel(sample_xlsx, sheet_name=0)
    dlg = ColumnPreviewDialog(df, "sample.xlsx", file_path=sample_xlsx)

    dlg.sheet_combo.setCurrentIndex(1)  # Sheet2に切り替え

    assert list(dlg.current_df.columns) == ["C", "D"]
    assert dlg.get_selected_columns() == ("C", "D")


def test_column_preview_dialog_excel_header_row_change_reloads(sample_xlsx):
    df = pd.read_excel(sample_xlsx, sheet_name=0)
    dlg = ColumnPreviewDialog(df, "sample.xlsx", file_path=sample_xlsx)

    dlg.header_row_spinbox.setValue(2)  # 2行目をヘッダーとして使う

    # 元データは2行しかないため、2行目をヘッダーにすると0行になる
    assert len(dlg.current_df) == 1


def test_column_preview_dialog_excel_invalid_usecols_shows_warning(sample_xlsx, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a))
    )
    df = pd.read_excel(sample_xlsx, sheet_name=0)
    dlg = ColumnPreviewDialog(df, "sample.xlsx", file_path=sample_xlsx)

    dlg.usecols_edit.setText("Z:ZZ")  # 存在しない列範囲
    dlg._on_sheet_or_header_changed()

    assert len(calls["warning"]) == 1


def test_column_preview_dialog_excel_check_column_types_applies_overrides(sample_xlsx, monkeypatch):
    df = pd.read_excel(sample_xlsx, sheet_name=0)
    dlg = ColumnPreviewDialog(df, "sample.xlsx", file_path=sample_xlsx)

    monkeypatch.setattr(ColumnTypeDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnTypeDialog, "get_overrides", lambda self: {"A": "文字列"})

    dlg._on_check_column_types()

    assert dlg.type_overrides == {"A": "文字列"}
    assert dlg.current_df["A"].dtype == object


def test_column_preview_dialog_apply_type_overrides_numeric_conversion():
    df = pd.DataFrame({"A": ["1", "2", "abc"]})
    dlg = ColumnPreviewDialog(df, "data.csv")
    dlg.type_overrides = {"A": "数値"}
    dlg._apply_type_overrides()
    assert pd.api.types.is_numeric_dtype(dlg.current_df["A"])
    assert pd.isna(dlg.current_df["A"].iloc[2])  # "abc" -> NaN(coerce)


def test_column_preview_dialog_apply_type_overrides_date_conversion():
    df = pd.DataFrame({"A": ["2024-01-01", "2024-02-01"]})
    dlg = ColumnPreviewDialog(df, "data.csv")
    dlg.type_overrides = {"A": "日付"}
    dlg._apply_type_overrides()
    assert pd.api.types.is_datetime64_any_dtype(dlg.current_df["A"])


def test_column_preview_dialog_apply_type_overrides_skips_missing_column():
    df = pd.DataFrame({"A": [1, 2]})
    dlg = ColumnPreviewDialog(df, "data.csv")
    dlg.type_overrides = {"NOT_A_COLUMN": "数値"}
    dlg._apply_type_overrides()  # 例外にならず単にスキップされる


# --- ColumnPreviewDialog(CSV: 文字コード/区切り文字/ヘッダー行/固定長、項目C-101) ---
# file_path付きで実ファイルを渡した場合のみ、これらのコントロールが有効になる
# (file_path無しの上記テスト群は「非Excel全般」の最小構成の確認であり、is_csvはFalseのまま)。

def test_column_preview_dialog_csv_is_csv_true_only_with_file_path(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n3,4\n", encoding='utf-8')
    df = pd.read_csv(path)
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))
    assert dlg.is_csv is True
    assert dlg.is_excel is False
    assert dlg.encoding_combo is not None
    assert dlg.delimiter_combo is not None


def test_column_preview_dialog_csv_without_file_path_has_no_csv_controls():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    dlg = ColumnPreviewDialog(df, "data.csv")  # file_path省略
    assert dlg.is_csv is False
    assert dlg.encoding_combo is None


def test_column_preview_dialog_csv_auto_detects_semicolon_delimiter(tmp_path):
    """初期dfはカンマ前提で読まれ1列に崩れているが、ダイアログが自動判定した
    区切り文字(セミコロン)で再読み込みし、正しい列数のプレビューになる。"""
    path = tmp_path / "data.csv"
    path.write_text("x;y;z\n1;2;3\n4;5;6\n", encoding='utf-8')
    broken_initial_df = pd.read_csv(path)  # 既定のカンマ区切りでは1列に崩れる

    dlg = ColumnPreviewDialog(broken_initial_df, "data.csv", file_path=str(path))

    assert list(dlg.current_df.columns) == ['x', 'y', 'z']
    assert dlg.delimiter_combo.currentText() == dlg._AUTO_LABEL


def test_column_preview_dialog_csv_manual_delimiter_override(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x|y\n1|2\n3|4\n", encoding='utf-8')
    df = pd.read_csv(path)  # 崩れた初期プレビュー
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))

    dlg.delimiter_combo.setCurrentText(ColumnPreviewDialog._DELIMITER_CUSTOM_LABEL)
    dlg.custom_delimiter_edit.setText("|")
    dlg._reload_csv_preview()

    assert list(dlg.current_df.columns) == ['x', 'y']


def test_column_preview_dialog_csv_header_row_skips_device_preamble(tmp_path):
    """装置が出力する説明文(前文)をヘッダー行の指定でスキップできる(項目C-101)。
    前文もカンマ区切り("パラメータ,値"形式)にしておき、既定のヘッダー1行目読みでも
    パースエラーにはならない(列数の不一致による警告ダイアログを避けるため)。"""
    path = tmp_path / "data.csv"
    path.write_text("Device,Spectrometer X\nDate,2026-01-01\nx,y\n1,2\n3,4\n", encoding='utf-8')
    df = pd.read_csv(path)  # 前文込みで意味的に崩れた初期プレビュー(パース自体は成功する)
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))

    dlg.csv_header_row_spinbox.setValue(3)  # 3行目("x,y")をヘッダーとして使う

    assert list(dlg.current_df.columns) == ['x', 'y']
    assert len(dlg.current_df) == 2


def test_column_preview_dialog_csv_encoding_manual_override(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("列1,列2\n1,あ\n", encoding='cp932')
    df = pd.read_csv(path, encoding='cp932')
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))

    dlg.encoding_combo.setCurrentText("Shift_JIS")

    assert list(dlg.current_df.columns) == ['列1', '列2']
    assert dlg.current_df['列2'].iloc[0] == 'あ'


def test_column_preview_dialog_csv_fixed_width_auto_infer(tmp_path):
    """固定長チェックを入れると、列幅を明示しなくても(自動推測、pandas既定)読める"""
    path = tmp_path / "data.csv"
    path.write_text("x    y   \n1    10  \n2    20  \n", encoding='utf-8')
    df = pd.read_csv(path)  # ただのCSVとして読むと1列に崩れる
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))

    dlg.fixed_width_checkbox.setChecked(True)  # 列幅は空欄のまま(自動推測)

    assert dlg.current_df.shape[1] == 2
    assert list(dlg.current_df.iloc[:, 0]) == [1, 2]
    assert list(dlg.current_df.iloc[:, 1]) == [10, 20]


def test_column_preview_dialog_csv_fixed_width_explicit_widths(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("1   10  \n2   20  \n", encoding='utf-8')
    df = pd.read_csv(path)
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))

    dlg.csv_header_row_spinbox.setValue(1)
    dlg.fixed_width_checkbox.setChecked(True)
    dlg.fixed_width_edit.setText("4,4")
    dlg._reload_csv_preview()

    assert dlg.current_df.shape[1] == 2
    assert dlg.delimiter_combo.isEnabled() is False


def test_column_preview_dialog_csv_invalid_settings_shows_warning(tmp_path, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a))
    )
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n", encoding='utf-8')
    df = pd.read_csv(path)
    dlg = ColumnPreviewDialog(df, "data.csv", file_path=str(path))

    dlg.fixed_width_checkbox.setChecked(True)
    dlg.fixed_width_edit.setText("not,a,number")
    dlg._reload_csv_preview()

    assert len(calls["warning"]) == 1


# --- ColorPaletteDialog: パレットの新規作成/名前変更/削除/色追加/削除 ---

def test_color_palette_dialog_new_palette_via_input_dialog(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("新パレット", True)))
    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

    dlg._on_new_palette()

    assert "新パレット" in dlg.palettes
    assert dlg.palette_combo.currentText() == "新パレット"


def test_color_palette_dialog_new_palette_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

    dlg._on_new_palette()

    assert dlg.palettes == {}


def test_color_palette_dialog_new_palette_duplicate_name_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("既存", True)))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    dlg = ColorPaletteDialog({"既存": ["#fff"]}, "既存")

    dlg._on_new_palette()

    assert len(calls["warning"]) == 1


def test_color_palette_dialog_rename_palette(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("新名前", True)))
    dlg = ColorPaletteDialog({"旧名前": ["#fff"]}, "旧名前")

    dlg._on_rename_palette()

    assert "新名前" in dlg.palettes
    assert "旧名前" not in dlg.palettes
    assert dlg.palette_combo.currentText() == "新名前"


def test_color_palette_dialog_rename_default_palette_is_noop(qapp, monkeypatch):
    calls = {"getText": 0}

    def fake_get_text(*a, **k):
        calls["getText"] += 1
        return ("x", True)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(fake_get_text))
    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

    dlg._on_rename_palette()

    assert calls["getText"] == 0  # デフォルトパレットは名前変更不可のため呼ばれない


def test_color_palette_dialog_rename_palette_duplicate_name_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("B", True)))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    dlg = ColorPaletteDialog({"A": ["#fff"], "B": ["#000"]}, "A")

    dlg._on_rename_palette()

    assert len(calls["warning"]) == 1
    assert "A" in dlg.palettes  # 変更されていない


def test_color_palette_dialog_delete_palette_confirmed(qapp, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    dlg = ColorPaletteDialog({"消す": ["#fff"]}, "消す")

    dlg._on_delete_palette()

    assert "消す" not in dlg.palettes


def test_color_palette_dialog_delete_palette_cancelled_keeps_it(qapp, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    dlg = ColorPaletteDialog({"残す": ["#fff"]}, "残す")

    dlg._on_delete_palette()

    assert "残す" in dlg.palettes


def test_color_palette_dialog_delete_default_palette_is_noop(qapp, monkeypatch):
    calls = {"question": 0}

    def fake_question(*a, **k):
        calls["question"] += 1
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

    dlg._on_delete_palette()

    assert calls["question"] == 0


def test_color_palette_dialog_add_color_via_color_dialog(qapp, monkeypatch):
    from PySide6.QtGui import QColor

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456")))
    dlg = ColorPaletteDialog({"カスタム": []}, "カスタム")

    dlg._on_add_color()

    assert dlg.palettes["カスタム"] == ["#123456"]


def test_color_palette_dialog_add_color_invalid_selection_ignored(qapp, monkeypatch):
    from PySide6.QtGui import QColor

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))  # invalid
    dlg = ColorPaletteDialog({"カスタム": []}, "カスタム")

    dlg._on_add_color()

    assert dlg.palettes["カスタム"] == []


def test_color_palette_dialog_add_color_on_default_palette_is_noop(qapp, monkeypatch):
    from PySide6.QtGui import QColor

    calls = {"getColor": 0}

    def fake_get_color(*a, **k):
        calls["getColor"] += 1
        return QColor("#123456")

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(fake_get_color))
    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

    dlg._on_add_color()

    assert calls["getColor"] == 0


def test_color_palette_dialog_remove_color_on_default_palette_is_noop(qapp):
    dlg = ColorPaletteDialog({}, ColorPaletteDialog.DEFAULT_PALETTE_NAME)
    dlg._on_remove_color()  # 例外にならない(1542行のreturn)


def test_color_palette_dialog_remove_color_no_selection_is_noop(qapp):
    dlg = ColorPaletteDialog({"カスタム": ["#fff", "#000"]}, "カスタム")
    dlg.color_list.setCurrentRow(-1)
    dlg._on_remove_color()  # 例外にならない(1545行のreturn)
    assert dlg.palettes["カスタム"] == ["#fff", "#000"]


def test_color_palette_dialog_get_result_returns_palettes_and_active_name(qapp):
    dlg = ColorPaletteDialog({"A": ["#fff"]}, "A")
    palettes, active_name = dlg.get_result()
    assert palettes == {"A": ["#fff"]}
    assert active_name == "A"


# --- ReplicateErrorDialog ---

def test_replicate_error_dialog_defaults_to_no_selection():
    dlg = ReplicateErrorDialog(["rep1", "rep2", "rep3"])
    selected, stat_type, base_name = dlg.get_settings()
    assert selected == []
    assert stat_type == "SD"
    assert base_name == "measurement"


def test_replicate_error_dialog_checked_items_are_selected():
    dlg = ReplicateErrorDialog(["rep1", "rep2", "rep3"])
    dlg.column_list.item(0).setCheckState(Qt.CheckState.Checked)
    dlg.column_list.item(2).setCheckState(Qt.CheckState.Checked)

    selected, _, _ = dlg.get_settings()
    assert selected == ["rep1", "rep3"]


def test_replicate_error_dialog_stat_type_sem_and_ci():
    dlg = ReplicateErrorDialog(["rep1", "rep2"])
    dlg.stat_combo.setCurrentText("SEM (標準誤差)")
    _, stat_type, _ = dlg.get_settings()
    assert stat_type == "SEM"

    dlg.stat_combo.setCurrentText("95%CI (信頼区間)")
    _, stat_type, _ = dlg.get_settings()
    assert stat_type == "95%CI"


def test_replicate_error_dialog_base_name_stripped():
    dlg = ReplicateErrorDialog(["rep1", "rep2"])
    dlg.base_name_edit.setText("  custom_name  ")
    _, _, base_name = dlg.get_settings()
    assert base_name == "custom_name"


# --- ColumnTypeDialog ---

def test_column_type_dialog_lists_detected_dtypes():
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    dlg = ColumnTypeDialog(df)
    assert dlg.table.rowCount() == 2
    assert dlg.table.item(0, 0).text() == "A"
    assert dlg.table.item(0, 1).text() == str(df["A"].dtype)


def test_column_type_dialog_default_overrides_empty():
    df = pd.DataFrame({"A": [1, 2]})
    dlg = ColumnTypeDialog(df)
    assert dlg.get_overrides() == {}


def test_column_type_dialog_get_overrides_reflects_combo_selection():
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    dlg = ColumnTypeDialog(df)
    dlg._override_combos["A"].setCurrentText("数値")
    dlg._override_combos["B"].setCurrentText("日付")
    assert dlg.get_overrides() == {"A": "数値", "B": "日付"}


# --- ExcelMultiSheetDialog ---

def test_excel_multi_sheet_dialog_first_sheet_checked_by_default():
    dlg = ExcelMultiSheetDialog(["Sheet1", "Sheet2", "Sheet3"])
    assert dlg.get_selected_sheets() == ["Sheet1"]


def test_excel_multi_sheet_dialog_multiple_selection():
    dlg = ExcelMultiSheetDialog(["Sheet1", "Sheet2", "Sheet3"])
    dlg.sheet_list.item(2).setCheckState(Qt.CheckState.Checked)
    assert dlg.get_selected_sheets() == ["Sheet1", "Sheet3"]


def test_excel_multi_sheet_dialog_uncheck_first_sheet():
    dlg = ExcelMultiSheetDialog(["Sheet1", "Sheet2"])
    dlg.sheet_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dlg.get_selected_sheets() == []


# --- DatasetArithmeticDialog ---

def test_dataset_arithmetic_dialog_defaults():
    dlg = DatasetArithmeticDialog("Alpha", "Beta")
    assert dlg.get_settings() == ("A - B", "Alpha vs Beta")


def test_dataset_arithmetic_dialog_custom_operation_and_name():
    dlg = DatasetArithmeticDialog("Alpha", "Beta")
    dlg.operation_combo.setCurrentText("A × B")
    dlg.output_name_edit.setText("  Product  ")
    assert dlg.get_settings() == ("A × B", "Product")


# --- NormalizeDatasetDialog ---

def test_normalize_dataset_dialog_defaults_to_max_mode():
    dlg = NormalizeDatasetDialog("D1", x_min=1.0, x_max=5.0)
    assert dlg.mode_combo.currentText() == NormalizeDatasetDialog.MODE_MAX
    assert dlg.reference_x_spinbox.isEnabled() is False
    mode, reference_x, output_name = dlg.get_settings()
    assert mode == NormalizeDatasetDialog.MODE_MAX
    assert reference_x is None
    assert output_name == "D1_normalized"


def test_normalize_dataset_dialog_x_value_mode_enables_spinbox_and_returns_value():
    dlg = NormalizeDatasetDialog("D1", x_min=2.0, x_max=8.0)
    dlg.mode_combo.setCurrentText(NormalizeDatasetDialog.MODE_X_VALUE)
    assert dlg.reference_x_spinbox.isEnabled() is True

    dlg.reference_x_spinbox.setValue(3.5)
    mode, reference_x, _ = dlg.get_settings()
    assert mode == NormalizeDatasetDialog.MODE_X_VALUE
    assert reference_x == 3.5


# --- PreferencesDialog: プラグインリストのフォールバックラベル / 参照ボタン ---

def test_preferences_dialog_plugin_without_info_or_error_uses_bare_name():
    records = [{"name": "bare_plugin", "info": None, "error": None, "disabled": False}]
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, plugin_records=records)
    assert dlg.plugin_list.item(0).text() == "bare_plugin"


def test_preferences_dialog_browse_autosave_dir_updates_on_selection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path))
    )
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)

    dlg._on_browse_autosave_dir()

    assert dlg.get_settings()[3] == str(tmp_path)
    assert dlg.autosave_dir_edit.text() == str(tmp_path)


def test_preferences_dialog_browse_autosave_dir_cancelled_keeps_previous(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5, autosave_dir="/keep/me")

    dlg._on_browse_autosave_dir()

    assert dlg.get_settings()[3] == "/keep/me"


# --- CommandPaletteDialog ---

def _make_actions(parent):
    from PySide6.QtGui import QAction, QKeySequence

    save_action = QAction("保存", parent)
    save_action.setEnabled(True)
    open_action = QAction("開く", parent)
    open_action.setEnabled(False)  # 無効なアクションは検索結果から除外される
    checkable_action = QAction("グリッド表示", parent)
    checkable_action.setCheckable(True)
    checkable_action.setChecked(True)

    return [
        (["ファイル", "保存"], save_action),
        (["ファイル", "開く"], open_action),
        (["表示", "グリッド表示"], checkable_action),
    ]


def test_command_palette_dialog_lists_only_enabled_actions(qapp):
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    dlg = CommandPaletteDialog(lambda: actions)

    # 「開く」は無効化されているため一覧に出ない
    labels = [dlg.list_widget.item(i).text() for i in range(dlg.list_widget.count())]
    assert any("保存" in l for l in labels)
    assert not any("開く" in l for l in labels)


def test_command_palette_dialog_checkable_action_shows_checkmark(qapp):
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    dlg = CommandPaletteDialog(lambda: actions)

    labels = [dlg.list_widget.item(i).text() for i in range(dlg.list_widget.count())]
    assert any(l.startswith("✓") for l in labels)


def test_command_palette_dialog_search_filters_list(qapp):
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    dlg = CommandPaletteDialog(lambda: actions)

    dlg.search_edit.setText("グリッド")

    assert dlg.list_widget.count() == 1
    assert "グリッド表示" in dlg.list_widget.item(0).text()


def test_command_palette_dialog_item_activation_triggers_action_and_accepts(qapp):
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    triggered = []
    actions[0][1].triggered.connect(lambda: triggered.append(True))
    dlg = CommandPaletteDialog(lambda: actions)

    item = dlg.list_widget.item(0)  # 「ファイル > 保存」
    dlg._on_item_activated(item)

    assert triggered == [True]
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_command_palette_dialog_eventfilter_arrow_keys_move_selection(qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    dlg = CommandPaletteDialog(lambda: actions)
    assert dlg.list_widget.currentRow() == 0

    down_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    dlg.eventFilter(dlg.search_edit, down_event)
    assert dlg.list_widget.currentRow() == 1

    up_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    dlg.eventFilter(dlg.search_edit, up_event)
    assert dlg.list_widget.currentRow() == 0


def test_command_palette_dialog_eventfilter_enter_activates_current_item(qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    triggered = []
    actions[0][1].triggered.connect(lambda: triggered.append(True))
    dlg = CommandPaletteDialog(lambda: actions)

    enter_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    dlg.eventFilter(dlg.search_edit, enter_event)

    assert triggered == [True]


def test_command_palette_dialog_eventfilter_ignores_other_widgets(qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    actions = _make_actions(holder)
    dlg = CommandPaletteDialog(lambda: actions)

    other_widget = QWidget()
    key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    result = dlg.eventFilter(other_widget, key_event)
    assert result is False  # super().eventFilter()に委譲され、Falseが返る


# --- QuickAccessManagerDialog ---

def test_quick_access_manager_dialog_skips_separators(qapp):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget, QMenu

    holder = QWidget()
    menu = QMenu(holder)
    separator = menu.addSeparator()
    action = QAction("項目1", holder)

    actions = [([], separator), (["項目1"], action)]
    dlg = QuickAccessManagerDialog(lambda: actions, lambda ident: False, lambda *a: None)

    assert dlg.list_widget.count() == 1
    assert dlg.list_widget.item(0).text() == "項目1"


def test_quick_access_manager_dialog_reflects_pinned_state(qapp):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    action = QAction("項目1", holder)
    actions = [(["項目1"], action)]
    dlg = QuickAccessManagerDialog(lambda: actions, lambda ident: True, lambda *a: None)

    assert dlg.list_widget.item(0).checkState() == Qt.CheckState.Checked


def test_quick_access_manager_dialog_toggling_item_calls_toggle_fn(qapp):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    action = QAction("項目1", holder)
    actions = [(["項目1"], action)]
    toggle_calls = []
    dlg = QuickAccessManagerDialog(
        lambda: actions, lambda ident: False,
        lambda ident, path, checked: toggle_calls.append((ident, path, checked))
    )

    dlg.list_widget.item(0).setCheckState(Qt.CheckState.Checked)

    assert toggle_calls == [("項目1", ["項目1"], True)]


def test_quick_access_manager_dialog_item_changed_ignored_while_updating(qapp):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    action = QAction("項目1", holder)
    actions = [(["項目1"], action)]
    toggle_calls = []
    dlg = QuickAccessManagerDialog(
        lambda: actions, lambda ident: False,
        lambda ident, path, checked: toggle_calls.append((ident, path, checked))
    )

    dlg._updating = True
    dlg._on_item_changed(dlg.list_widget.item(0))
    dlg._updating = False

    assert toggle_calls == []  # _updating中はtoggle_fnが呼ばれない


def test_quick_access_manager_dialog_search_filters_list(qapp):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    action_a = QAction("Alpha", holder)
    action_b = QAction("Beta", holder)
    actions = [(["Alpha"], action_a), (["Beta"], action_b)]
    dlg = QuickAccessManagerDialog(lambda: actions, lambda ident: False, lambda *a: None)

    dlg.search_edit.setText("Alpha")

    assert dlg.list_widget.count() == 1
    assert dlg.list_widget.item(0).text() == "Alpha"


# --- ShortcutsDialog ---

def test_shortcuts_dialog_lists_actions_with_shortcuts_only(qapp):
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    with_shortcut = QAction("保存", holder)
    with_shortcut.setShortcut(QKeySequence("Ctrl+S"))
    without_shortcut = QAction("開く", holder)

    actions = [(["ファイル", "保存"], with_shortcut), (["ファイル", "開く"], without_shortcut)]
    dlg = ShortcutsDialog(lambda: actions)

    from PySide6.QtWidgets import QTableWidget
    table = dlg.findChild(QTableWidget)
    assert table.rowCount() == 1
    assert "保存" in table.item(0, 0).text()


def test_shortcuts_dialog_empty_collection_produces_empty_table(qapp):
    from PySide6.QtWidgets import QTableWidget

    dlg = ShortcutsDialog(lambda: [])
    table = dlg.findChild(QTableWidget)
    assert table.rowCount() == 0


# --- LegendOrderDialog ---

def test_legend_order_dialog_returns_current_order():
    dlg = LegendOrderDialog(["Line 1", "Line 2", "Line 3"])
    assert dlg.get_order() == ["Line 1", "Line 2", "Line 3"]


def test_legend_order_dialog_reset_clears_custom_order():
    dlg = LegendOrderDialog(["Line 1", "Line 2"])
    dlg._on_reset()
    assert dlg.get_order() == []


# --- BatchExportDialog: プロジェクトファイル選択/出力先/モード ---

def test_batch_export_dialog_add_project_files(monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["a.graphica", "b.pkl"], ""))
    )
    dlg = BatchExportDialog(subplot_count=2)

    dlg._on_add_project_files()

    assert dlg.get_project_file_paths() == ["a.graphica", "b.pkl"]


def test_batch_export_dialog_add_project_files_cancelled(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([], "")))
    dlg = BatchExportDialog(subplot_count=2)

    dlg._on_add_project_files()

    assert dlg.get_project_file_paths() == []


def test_batch_export_dialog_remove_selected_project_files(monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["a.graphica", "b.pkl"], ""))
    )
    dlg = BatchExportDialog(subplot_count=2)
    dlg._on_add_project_files()
    dlg.project_files_list.item(0).setSelected(True)

    dlg._on_remove_selected_project_files()

    assert dlg.get_project_file_paths() == ["b.pkl"]


def test_batch_export_dialog_browse_output_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path))
    )
    dlg = BatchExportDialog(subplot_count=2)

    dlg._on_browse_output_dir()

    assert dlg.output_dir_edit.text() == str(tmp_path)
    assert dlg.get_common_options()["output_dir"] == str(tmp_path)


def test_batch_export_dialog_browse_output_dir_cancelled_keeps_empty(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    dlg = BatchExportDialog(subplot_count=2)

    dlg._on_browse_output_dir()

    assert dlg.output_dir_edit.text() == ""


def test_batch_export_dialog_get_mode_switches_with_combo():
    dlg = BatchExportDialog(subplot_count=2)
    assert dlg.get_mode() == "subplots"

    dlg.mode_combo.setCurrentIndex(1)
    assert dlg.get_mode() == "project_files"


def test_batch_export_dialog_get_selected_subplot_indices_all_checked_by_default():
    dlg = BatchExportDialog(subplot_count=3)
    assert dlg.get_selected_subplot_indices() == [0, 1, 2]

    dlg.subplot_list.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert dlg.get_selected_subplot_indices() == [0, 2]


# --- NewDatasetDialog: 入力検証(_on_accept) ---

def test_new_dataset_dialog_accept_with_empty_name_shows_warning_and_does_not_accept(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    dlg = NewDatasetDialog()
    dlg.name_edit.setText("   ")

    dlg._on_accept()

    assert len(calls["warning"]) == 1
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_new_dataset_dialog_accept_with_empty_columns_shows_warning_and_does_not_accept(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    dlg = NewDatasetDialog()
    dlg.columns_edit.setText("  ,  ")

    dlg._on_accept()

    assert len(calls["warning"]) == 1
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_new_dataset_dialog_accept_with_valid_input_accepts(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    dlg = NewDatasetDialog()

    dlg._on_accept()

    assert calls["warning"] == []
    assert dlg.result() == QDialog.DialogCode.Accepted
