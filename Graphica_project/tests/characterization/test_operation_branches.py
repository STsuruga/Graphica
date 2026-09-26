"""データセットの処理(gui/datasets/processing.py)の分岐を、操作ごとに固定する。

test_operations.py が既定値のまま OK した流れを見るのに対し、ここは途中で止まる流れを見る: 選択の数が違う、
点が足りない、ダイアログを取り消す、出力名が空、入力の確認で止まる、計算が失敗する、別の手法を選ぶ。
警告の題と文言、確認の順番、Undo に積むかどうか、例外が外に出るかどうかを、今の挙動として記録する。
"""
import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QLineEdit, QMessageBox,
                               QPlainTextEdit, QSpinBox)

import recorder
from test_operations import ds_a, ds_b, ds_dup, ds_text_x, run_case, select, _new_tab

ACCEPT = QDialog.DialogCode.Accepted
REJECT = QDialog.DialogCode.Rejected


# --- データ ---

def _ds(name, x, y, **columns):
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"x": x, "y": y, **columns})
    extra = {"y_err_col_name": "yerr"} if "yerr" in columns else {}
    return Dataset(df=df, name=name, x_col_name="x", y_col_name="y", **extra)


def ds_nan():
    return _ds("NaN", [np.nan] * 5, [np.nan] * 5)


def ds_one():
    return _ds("1点", [1.0], [2.0])


def ds_two():
    return _ds("2点", [1.0, 2.0], [2.0, 3.0])


def ds_far():
    x = np.linspace(100.0, 110.0, 11)
    return _ds("遠い", x, np.cos(x))


def ds_sparse():
    return _ds("まばら", [0.0, 10.0], [1.0, 2.0])


def ds_narrow():
    x = np.linspace(4.1, 4.2, 5)
    return _ds("狭い", x, x * 2)


def ds_b_err():
    b = ds_b()
    b.df["yerr"] = 0.02 + 0.005 * b.df["x"]
    b.y_err_col_name = "yerr"
    return b


def ds_zero():
    return _ds("ゼロ", np.linspace(0, 1, 5), np.zeros(5))


def ds_groups(labels):
    def make():
        n = len(labels)
        return _ds("群", np.arange(n, dtype=float), np.arange(n, dtype=float) ** 2, grp=labels)
    return make


def ds_all_text():
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"name": ["a", "b", "c"], "kind": ["p", "q", "r"]})
    return Dataset(df=df, name="文字だけ", x_col_name="name", y_col_name="kind")


def ds_spike():
    y = np.ones(20)
    y[7] = 50.0
    return _ds("とげ", np.arange(20, dtype=float), y)


def ds_text_dup():
    return _ds("文字の重複X", ["a", "a", "b"], [1.0, 2.0, 3.0])


def ds_nan_x():
    return _ds("Xが空", [np.nan] * 3, [1.0, 2.0, 3.0])


# --- 組み立て ---

def _one(action, make=ds_a, others=(ds_b,)):
    def build(app_env):
        target = make()
        tab = _new_tab(app_env, target, *[m() for m in others])
        select(tab, target)
        return tab, action
    return build


def _pair(action, make_a=ds_a, make_b=ds_b):
    def build(app_env):
        a, b = make_a(), make_b()
        tab = _new_tab(app_env, a, b)
        select(tab, a, b)
        return tab, action
    return build


def _empty_tab(action):
    def build(app_env):
        return _new_tab(app_env), action
    return build


def fill(**changes):
    """ダイアログの部品(属性名)に値を入れて OK する。"""
    def answer(dialog):
        for attr, value in changes.items():
            widget = getattr(dialog, attr)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value)
            elif isinstance(widget, QComboBox) and widget.isEditable():
                widget.setCurrentText(value)
            elif isinstance(widget, QComboBox):
                index = widget.findText(value)
                assert index >= 0, f"{attr} に {value!r} が無い"
                widget.setCurrentIndex(index)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)
            else:
                raise AssertionError(f"{attr} の部品 {type(widget).__name__} に値を入れられない")
        return ACCEPT
    return answer


def _twice(action):
    def run(tab):
        action(tab)
        action(tab)
    return run


def op(name):
    return lambda t: getattr(t.processing, name)()


# 名前: (組み立て, 台本 [(種類, 答え), ...])
CASES = {
    # データセット間演算
    "arithmetic_cancel": (_pair(op("arithmetic")), [("exec", REJECT)]),
    "arithmetic_empty_name": (_pair(op("arithmetic")), [("exec", fill(output_name_edit="  "))]),
    "arithmetic_all_nan": (_pair(op("arithmetic"), ds_nan, ds_a), []),
    "arithmetic_no_overlap": (_pair(op("arithmetic"), ds_a, ds_far), []),
    "arithmetic_a_outside_overlap": (_pair(op("arithmetic"), ds_sparse, ds_narrow), []),
    "arithmetic_errors_a_div_b": (_pair(op("arithmetic"), ds_a, ds_b_err),
                                  [("exec", fill(operation_combo="A ÷ B"))]),
    "arithmetic_b_minus_a": (_pair(op("arithmetic")), [("exec", fill(operation_combo="B - A"))]),
    "arithmetic_a_plus_b": (_pair(op("arithmetic")), [("exec", fill(operation_combo="A + B"))]),
    "arithmetic_a_times_b": (_pair(op("arithmetic")), [("exec", fill(operation_combo="A × B"))]),
    "arithmetic_b_div_a": (_pair(op("arithmetic")), [("exec", fill(operation_combo="B ÷ A"))]),
    # X軸アライメント
    "align_needs_two": (_one(op("align_selected")), []),
    "align_cancel": (_pair(op("align_selected")), [("exec", REJECT)]),
    "align_empty_name": (_pair(op("align_selected")), [("exec", fill(output_name_edit=""))]),
    "align_calc_error": (_pair(op("align_selected"), ds_a, ds_one), []),
    # 平均±SD
    "mean_sd_needs_two": (_one(op("mean_and_sd_of_selected")), []),
    "mean_sd_too_few_points": (_pair(op("mean_and_sd_of_selected"), ds_a, ds_one), []),
    "mean_sd_no_overlap": (_pair(op("mean_and_sd_of_selected"), ds_a, ds_far), []),
    "mean_sd_name_cancel": (_pair(op("mean_and_sd_of_selected")), [("getText", ("x", False))]),
    "mean_sd_name_blank": (_pair(op("mean_and_sd_of_selected")), [("getText", ("  ", True))]),
    "mean_sd_name_padded": (_pair(op("mean_and_sd_of_selected")), [("getText", ("  平均  ", True))]),
    # 規格化
    "normalize_no_dataset": (_empty_tab(op("normalize")), []),
    "normalize_all_nan": (_one(op("normalize"), ds_nan), []),
    "normalize_cancel": (_one(op("normalize")), [("exec", REJECT)]),
    "normalize_empty_name": (_one(op("normalize")), [("exec", fill(output_name_edit=""))]),
    "normalize_at_x": (_one(op("normalize")), [("exec", fill(mode_combo="特定X値での強度基準",
                                                            reference_x_spinbox=5.0))]),
    "normalize_x_out_of_range": (_one(op("normalize")), [("exec", fill(mode_combo="特定X値での強度基準",
                                                                      reference_x_spinbox=1000.0))]),
    "normalize_zero_reference": (_one(op("normalize"), ds_zero), []),
    # Savitzky-Golay
    "savgol_too_few": (_one(op("savgol_smooth"), ds_two), []),
    "savgol_cancel": (_one(op("savgol_smooth")), [("exec", REJECT)]),
    "savgol_empty_name": (_one(op("savgol_smooth")), [("exec", fill(output_name_edit=""))]),
    "savgol_second_derivative": (_one(op("savgol_smooth")), [("exec", fill(mode_combo="2次微分",
                                                                          window_spinbox=7))]),
    "savgol_calc_error": (_one(op("savgol_smooth")), [("exec", fill(window_spinbox=3, polyorder_spinbox=5))]),
    # ベースライン補正
    "baseline_too_few": (_one(op("baseline_correction"), ds_two), []),
    "baseline_cancel": (_one(op("baseline_correction")), [("exec", REJECT)]),
    "baseline_empty_name": (_one(op("baseline_correction")), [("exec", fill(output_name_edit=""))]),
    "baseline_polynomial": (_one(op("baseline_correction")),
                            [("exec", fill(method_combo="多項式(反復フィット)"))]),
    "baseline_rubberband_with_curve": (_one(op("baseline_correction")),
                                       [("exec", fill(method_combo="ラバーバンド(下側凸包)",
                                                      add_baseline_checkbox=True))]),
    "baseline_manual": (_one(op("baseline_correction")),
                        [("exec", fill(method_combo="手動点", manual_anchor_edit="0, 2.5\n9, 10"))]),
    "baseline_manual_bad_text": (_one(op("baseline_correction")),
                                 [("exec", fill(method_combo="手動点", manual_anchor_edit="0, abc"))]),
    "baseline_manual_empty": (_one(op("baseline_correction")),
                              [("exec", fill(method_combo="手動点", manual_anchor_edit=""))]),
    # 区間積分
    "interval_integral_too_few": (_one(op("interval_integral"), ds_one), []),
    "interval_integral_cancel": (_one(op("interval_integral")), [("exec", REJECT)]),
    "interval_integral_simpson_baseline": (_one(op("interval_integral")),
                                           [("exec", fill(method_combo="Simpson則", subtract_baseline_checkbox=True,
                                                          range_min_spinbox=2.0, range_max_spinbox=7.0))]),
    "interval_integral_reversed_range": (_one(op("interval_integral")),
                                         [("exec", fill(range_min_spinbox=7.0, range_max_spinbox=2.0))]),
    "interval_integral_twice": (_one(_twice(op("interval_integral"))), []),
    # 累積積分
    "cumulative_integral_too_few": (_one(op("cumulative_integral"), ds_one), []),
    "cumulative_integral_cancel": (_one(op("cumulative_integral")), [("exec", REJECT)]),
    "cumulative_integral_empty_name": (_one(op("cumulative_integral")), [("exec", fill(output_name_edit=""))]),
    "cumulative_integral_simpson": (_one(op("cumulative_integral")), [("exec", fill(method_combo="Simpson則"))]),
    # 列の値で分割
    "split_cancel": (_one(op("split_by_column")), [("getItem", ("grp", False))]),
    "split_single_group": (_one(op("split_by_column"), ds_groups(["a"] * 4)), [("getItem", ("grp", True))]),
    "split_blank_rows": (_one(op("split_by_column"), ds_groups(["a", None, "b", "a", None])),
                         [("getItem", ("grp", True))]),
    "split_all_blank": (_one(op("split_by_column"), ds_groups([None, None, None])), [("getItem", ("grp", True))]),
    "split_many_groups_no": (_one(op("split_by_column"), ds_groups([f"g{i}" for i in range(31)])),
                             [("getItem", ("grp", True)), ("question", QMessageBox.StandardButton.No)]),
    "split_many_groups_yes": (_one(op("split_by_column"), ds_groups([f"g{i}" for i in range(31)])),
                              [("getItem", ("grp", True)), ("question", QMessageBox.StandardButton.Yes)]),
    # リサンプリング
    "resample_too_few": (_one(op("resample"), ds_one), []),
    "resample_cancel": (_one(op("resample")), [("exec", REJECT)]),
    "resample_empty_name": (_one(op("resample")), [("exec", fill(output_name_edit=""))]),
    "resample_onto_other_dataset": (_one(op("resample")), [("exec", fill(source_combo="他のデータセットのX格子"))]),
    "resample_no_other_dataset": (_one(op("resample"), others=()),
                                  [("exec", fill(source_combo="他のデータセットのX格子"))]),
    "resample_other_without_x": (_one(op("resample"), others=(ds_nan_x,)),
                                 [("exec", fill(source_combo="他のデータセットのX格子"))]),
    "resample_same_start_stop": (_one(op("resample")), [("exec", fill(source_combo="等間隔グリッド",
                                                                     linspace_start_spinbox=3.0,
                                                                     linspace_stop_spinbox=3.0))]),
    "resample_cubic_extrapolate": (_one(op("resample")), [("exec", fill(source_combo="等間隔グリッド",
                                                                       linspace_start_spinbox=-2.0,
                                                                       linspace_stop_spinbox=12.0,
                                                                       method_combo="3次スプライン補間",
                                                                       extrapolate_checkbox=True))]),
    # ヒストグラム / KDE
    "histogram_no_numeric": (_one(op("histogram_or_kde"), ds_all_text), []),
    "histogram_cancel": (_one(op("histogram_or_kde")), [("exec", REJECT)]),
    "histogram_empty_name": (_one(op("histogram_or_kde")), [("exec", fill(output_name_edit=""))]),
    "histogram_kde": (_one(op("histogram_or_kde")), [("exec", fill(mode_combo="カーネル密度推定(KDE)"))]),
    "histogram_kde_constant": (_one(op("histogram_or_kde"), ds_zero),
                               [("exec", fill(mode_combo="カーネル密度推定(KDE)", column_combo="y"))]),
    "histogram_text_x_column": (_one(op("histogram_or_kde"), ds_text_x), []),
    # 重複 X
    "duplicate_x_cancel": (_one(op("detect_duplicate_x"), ds_dup), [("exec", REJECT)]),
    "duplicate_x_average_empty_name": (_one(op("detect_duplicate_x"), ds_dup), [("exec", fill(output_name_edit=""))]),
    "duplicate_x_remove": (_one(op("detect_duplicate_x"), ds_dup),
                           [("exec", fill(mode_combo="除去(先頭以外をマスク)"))]),
    "duplicate_x_remove_twice": (_one(_twice(op("detect_duplicate_x")), ds_dup),
                                 [("exec", fill(mode_combo="除去(先頭以外をマスク)"),
                                   fill(mode_combo="除去(先頭以外をマスク)"))]),
    # 行フィルタ
    "filter_rows_cancel": (_one(op("filter_rows")), [("exec", REJECT)]),
    "filter_rows_bad_formula": (_one(op("filter_rows")), [("exec", fill(formula_edit="no_such_column > 1"))]),
    "filter_rows_nothing_new": (_one(op("filter_rows")), [("exec", fill(formula_edit="y > -1000"))]),
    "filter_rows_numeric_result": (_one(op("filter_rows")), [("exec", fill(formula_edit="y - y"))]),
    # 外れ値
    "outliers_too_few": (_one(op("detect_outliers"), ds_one), []),
    "outliers_cancel": (_one(op("detect_outliers")), [("exec", REJECT)]),
    "outliers_iqr": (_one(op("detect_outliers"), ds_spike), [("exec", fill(method_combo="IQR(四分位範囲)"))]),
    "outliers_mask_found": (_one(op("detect_outliers"), ds_spike), [("exec", fill(apply_mask_checkbox=True))]),
    "outliers_mask_none_found": (_one(op("detect_outliers")), [("exec", fill(apply_mask_checkbox=True))]),
    "outliers_constant": (_one(op("detect_outliers"), ds_zero), []),
    "outliers_twice": (_one(_twice(op("detect_outliers")), ds_spike), []),
    # 文字の X 列(カテゴリ軸)
    "mean_sd_text_x": (_pair(op("mean_and_sd_of_selected"), ds_text_x, ds_a), []),
    "savgol_text_x": (_one(op("savgol_smooth"), ds_text_x), []),
    "baseline_text_x": (_one(op("baseline_correction"), ds_text_x), []),
    "interval_integral_text_x": (_one(op("interval_integral"), ds_text_x), []),
    "cumulative_integral_text_x": (_one(op("cumulative_integral"), ds_text_x), []),
    "resample_text_x": (_one(op("resample"), ds_text_x), []),
    "resample_onto_text_x": (_one(op("resample"), others=(ds_text_x,)),
                             [("exec", fill(source_combo="他のデータセットのX格子"))]),
    "outliers_text_x": (_one(op("detect_outliers"), ds_text_x), []),
    "duplicate_x_average_text_x": (_one(op("detect_duplicate_x"), ds_text_dup), []),
    # バッチ列計算
    "batch_column_needs_two": (_one(op("batch_column_calculate")), []),
    "batch_column_cancel": (_pair(op("batch_column_calculate")), [("exec", REJECT)]),
    "batch_column_empty": (_pair(op("batch_column_calculate")), [("exec", fill(formula_edit=""))]),
    "batch_column_partial_failure": (_pair(op("batch_column_calculate"), ds_a, ds_text_x),
                                     [("exec", fill(output_col_combo="z", formula_edit="y * 2"))]),
}


@pytest.mark.parametrize("name", list(CASES))
def test_processing_branch(app_env, modal_log, normalizer, name):
    build, answers = CASES[name]
    tab, action = build(app_env)
    modal_log.accept_defaults()
    for kind, *values in answers:
        modal_log.respond_to(kind, *values)
    recorder.check(f"operation_branches/{name}", run_case(tab, modal_log, action), normalizer)
