"""フィット・ピーク・転送(gui/datasets/fitting.py・peaks.py・transfer.py)の分岐を、操作ごとに固定する。

test_operations.py が既定値のまま OK した流れを見るのに対し、ここは途中で止まる流れを見る: 対象が無い、
実行中、取り消し、計算の失敗、見つからない、書き出しや読み込みの失敗。
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QMessageBox

import recorder
from test_operation_branches import REJECT, _one, _pair, ds_two, fill
from test_operations import ds_a, ds_b, ds_text_x, run_case, select, _new_tab, wait_idle

GAUSSIAN = "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)"


class _Busy:
    """実行中の計算の代わり。wait_idle が待たないよう、呼び終えたら外す。"""


def busy(runner_name, action):
    def run(tab):
        setattr(tab.fitting, runner_name, _Busy())
        try:
            action(tab)
        finally:
            setattr(tab.fitting, runner_name, None)
    return run


def fit(t):
    t.fitting.fit_current_dataset()


def batch_fit(t):
    t.fitting.batch_fit_selected()


def multi_peak(t):
    t.fitting.multi_peak_fit_current_dataset()


def _fit_then(after):
    def run(tab):
        tab.fitting.fit_current_dataset()
        wait_idle(tab)
        select(tab, tab.project.datasets[-1])
        after(tab)
    return run


def _burn_with(change):
    def after(tab):
        fitted = tab.project.datasets[-1]
        change(fitted)
        tab.fitting.burn_fit_result_annotation(fitted, fitted.fit_result)
    return after


def _off_axis(dataset):
    dataset.subplot_target = 5


def _no_points(dataset):
    dataset.df = dataset.df.iloc[0:0]
    dataset.invalidate_visible_df_cache()


def find_peaks(t):
    t.peaks.find_peaks()


def peak_labels(t):
    t.peaks.add_peak_labels()


NO_PEAKS = fill(height_spinbox=1000.0)


def unselected(action):
    def run(tab):
        tab.ui.dataset_list_widget.clearSelection()
        action(tab)
    return run


def ds_one_peak():
    from graphica.core.dataset import Dataset
    import numpy as np

    x = np.linspace(0, 10, 41)
    return Dataset(df=pd.DataFrame({"x": x, "y": np.exp(-((x - 5) ** 2))}), name="山1つ", x_col_name="x", y_col_name="y")


CASES = {
    # フィット
    "fit_no_dataset": (lambda env: (_new_tab(env), fit), []),
    "fit_busy": (_one(busy("fit_runner", fit)), []),
    "fit_cancel": (_one(fit), [("exec", REJECT)]),
    "fit_fails": (_one(fit, ds_two), [("exec", fill(fit_type_combo=GAUSSIAN))]),
    "fit_weighted_in_range": (_one(fit), [("exec", fill(fit_type_combo=GAUSSIAN, weighted_checkbox=True,
                                                         range_checkbox=True, range_min_spinbox=1.0,
                                                         range_max_spinbox=8.0))]),
    "fit_text_x": (_one(fit, ds_text_x), []),
    "batch_fit_needs_two": (_one(batch_fit), []),
    "batch_fit_busy": (_pair(busy("batch_fit_runner", batch_fit)), []),
    "batch_fit_cancel": (_pair(batch_fit), [("exec", REJECT)]),
    "batch_fit_partial_failure": (_pair(batch_fit, ds_a, ds_two), [("exec", fill(fit_type_combo=GAUSSIAN))]),
    "multi_peak_no_dataset": (lambda env: (_new_tab(env), multi_peak), []),
    "multi_peak_busy": (_one(busy("multi_peak_fit_runner", multi_peak)), []),
    "multi_peak_cancel": (_one(multi_peak), [("exec", REJECT)]),
    "show_fit_result_without_fit": (_one(lambda t: t.fitting.show_fit_result()), []),
    "show_fit_result_no_burn": (_one(_fit_then(lambda t: t.fitting.show_fit_result())),
                                [("question", QMessageBox.StandardButton.No)]),
    "burn_off_axis": (_one(_fit_then(_burn_with(_off_axis))), []),
    "burn_no_points": (_one(_fit_then(_burn_with(_no_points))), []),
    # ピーク
    "find_peaks_no_dataset": (lambda env: (_new_tab(env), find_peaks), []),
    "find_peaks_too_few": (_one(find_peaks, ds_two), []),
    "find_peaks_cancel": (_one(find_peaks), [("exec", REJECT)]),
    "find_peaks_none": (_one(find_peaks), [("exec", NO_PEAKS)]),
    "find_peaks_valleys": (_one(find_peaks), [("exec", fill(type_combo="下に凸 (Valleys)"))]),
    "find_peaks_text_x": (_one(find_peaks, ds_text_x), []),
    "find_peaks_twice": (_one(lambda t: (find_peaks(t), find_peaks(t))), []),
    "peak_labels_too_few": (_one(peak_labels, ds_two), []),
    "peak_labels_cancel": (_one(peak_labels), [("exec", REJECT)]),
    "peak_labels_none": (_one(peak_labels), [("exec", NO_PEAKS)]),
    "peak_labels_single": (_one(peak_labels, ds_one_peak), []),
    "peak_labels_text_x": (_one(peak_labels, ds_text_x), []),
    # 転送
    "export_nothing_selected": (lambda env: (_new_tab(env, ds_a()), unselected(lambda t: t.transfer.export_data())), []),
    "export_one_cancel": (_one(lambda t: t.transfer.export_data()), [("getSaveFileName", ("", ""))]),
    "export_many_format_cancel": (_pair(lambda t: t.transfer.export_data()), [("getItem", ("", False))]),
    "export_many_excel_cancel": (_pair(lambda t: t.transfer.export_data()),
                                 [("getItem", ("Excel (1ブックにシート分け)", True)), ("getSaveFileName", ("", ""))]),
    "export_many_folder_cancel": (_pair(lambda t: t.transfer.export_data()), [("getExistingDirectory", "")]),
    "copy_to_tab_nothing_selected": (lambda env: (_new_tab(env, ds_a()),
                                                  unselected(lambda t: t.transfer.copy_or_move_to_tab(False))), []),
    "copy_to_tab_no_other_tab": (_one(lambda t: t.transfer.copy_or_move_to_tab(False)), []),
    "copy_style_no_dataset": (lambda env: (_new_tab(env), lambda t: t.transfer.copy_style()), []),
    "paste_style_nothing_copied": (_one(lambda t: t.transfer.paste_style()), []),
    "paste_style_single": (_pair(lambda t: (t.transfer.copy_style(), select(t, t.project.datasets[1]),
                                            t.transfer.paste_style())), []),
    "reload_no_source": (_one(lambda t: t.transfer.reload_from_source()), []),
    "methods_text_no_provenance": (_one(lambda t: t.transfer.copy_methods_text()), []),
}


@pytest.mark.parametrize("name", list(CASES))
def test_feature_branch(app_env, modal_log, normalizer, name):
    build, answers = CASES[name]
    tab, action = build(app_env)
    modal_log.accept_defaults()
    for kind, *values in answers:
        modal_log.respond_to(kind, *values)
    recorder.check(f"feature_branches/{name}", run_case(tab, modal_log, action), normalizer)


def test_export_failures(app_env, modal_log, normalizer, tmp_path):
    a, b = ds_a(), ds_b()
    tab = _new_tab(app_env, a, b)
    modal_log.accept_defaults()
    missing = tmp_path / "無いフォルダ"
    results = {}

    select(tab, a)
    modal_log.respond_to("getSaveFileName", (str(missing / "one.csv"), "CSV Files (*.csv)"))
    results["one_csv"] = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    modal_log.respond_to("getSaveFileName", (str(tmp_path / "one"), "Excel Files (*.xlsx)"))
    results["one_excel_by_filter"] = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    results["one_excel_written"] = (tmp_path / "one.xlsx").exists()

    select(tab, a, b)
    modal_log.respond_to("getItem", ("Excel (1ブックにシート分け)", True))
    modal_log.respond_to("getSaveFileName", (str(missing / "book"), "Excel Files (*.xlsx)"))
    results["many_excel"] = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    modal_log.respond_to("getExistingDirectory", str(missing))
    results["many_folder"] = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    recorder.check("feature_branches/export_failures", results, normalizer)


def test_reload_failures(app_env, modal_log, normalizer, tmp_path):
    from graphica.core.dataset import Dataset

    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not an excel file")
    ds = Dataset(df=pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 2.0]}), name="元", x_col_name="x", y_col_name="y",
                 source_file=str(broken), source_sheet="Sheet1")
    tab = _new_tab(app_env, ds)
    select(tab, ds)
    modal_log.accept_defaults()
    results = {"unreadable": run_case(tab, modal_log, lambda t: t.transfer.reload_from_source())}
    ds.source_sheet = None
    ds.source_file = str(tmp_path / "無い.csv")
    results["missing_file"] = run_case(tab, modal_log, lambda t: t.transfer.reload_from_source())
    recorder.check("feature_branches/reload_failures", results, normalizer)


def test_copy_to_tab_cancelled(app_env, modal_log, normalizer):
    modal_log.accept_defaults()
    main = app_env.main_window(has_shown_welcome=True)
    first = main.tab_widget.widget(0)
    main.add_new_project_tab()
    main.tab_widget.setCurrentIndex(0)
    a = ds_a()
    first._add_dataset(a)
    first.undo_stack.clear()
    select(first, a)
    modal_log.respond_to("getItem", ("", False))
    recorder.check("feature_branches/copy_to_tab_cancelled",
                   run_case(first, modal_log, lambda t: t.transfer.copy_or_move_to_tab(True)), normalizer)
