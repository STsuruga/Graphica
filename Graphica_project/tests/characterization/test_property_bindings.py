"""データセットのプロパティ欄の対応(選んだデータセットを欄に映す・欄の変更をデータセットに当てる)を、R-1b の前に固定する。

乱数で作ったデータセット 200 件を 1 つのタブに入れ、順に選んだとき(ときどき複数選択やフォルダ)の欄の値と
有効/表示の状態を残す。前の選択の値が残る欄もあるので、同じ順で選ぶ。欄を 1 つずつ変えたときに
データセットへ書き戻される値、Undo の履歴、再描画の呼び出しも残す。
"""
import dataclasses
import json
import random

import numpy as np
import pandas as pd
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QLabel, QLineEdit, QTextEdit, QToolButton)

import recorder
from scenario import pump
from test_operations import _new_tab, ds_a, ds_b, select

# 実装の表に頼らず、欄をここで名前で並べる
PANEL_WIDGETS = (
    "ui.legend_name_edit", "ui.plot_type_combo", "ui.linestyle_combo", "ui.linewidth_spinbox", "ui.marker_combo",
    "ui.markersize_spinbox", "color_picker_widget", "ui.smoothing_checkbox", "smoothing_method_label",
    "smoothing_method_combo", "alpha_spinbox", "gradient_checkbox", "gradient_color2_label", "gradient_color2_picker",
    "gradient_target_label", "gradient_target_combo", "waterfall_checkbox", "waterfall_offset_x_label",
    "waterfall_offset_x_spinbox", "waterfall_offset_y_label", "waterfall_offset_y_spinbox",
    "waterfall_occlusion_checkbox", "waterfall_depth_checkbox", "waterfall_depth_ratio_label",
    "waterfall_depth_ratio_spinbox", "point_labels_checkbox", "point_label_col_combo", "point_labels_limit_note",
    "use_secondary_y_checkbox", "subplot_target_combo", "error_display_combo", "nan_policy_combo", "data_2d_checkbox",
    "z_col_label", "z_col_combo", "colormap_label", "colormap_combo", "color_range_auto_checkbox", "vmin_label",
    "vmin_spinbox", "vmax_label", "vmax_spinbox", "map_display_mode_label", "map_display_mode_combo",
    "contour_levels_label", "contour_levels_spinbox", "grid_interp_method_label", "grid_interp_method_combo",
    "x_col_combo", "y_col_combo", "x_err_col_combo", "y_err_col_combo", "fit_info_label", "fit_info_textedit",
    "stats_summary_label", "dataset_mini_stats_label", "ui.remove_dataset_button", "duplicate_dataset_button",
    "view_edit_data_button", "auto_color_button", "fit_curve_button", "find_peaks_button",
)


def _widget(tab, path):
    obj = tab
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _value(widget):
    if hasattr(widget, "color_name"):
        return widget.color_name()
    if isinstance(widget, QComboBox):
        value = [widget.currentIndex(), widget.currentText(), widget.count()]
        data = widget.currentData()
        if data is not None:
            value.append(data)
        model = widget.model()
        if hasattr(model, "item"):
            disabled = [i for i in range(widget.count()) if not model.item(i).isEnabled()]
            if disabled:
                value.append({"disabled": disabled})
        return value
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QAbstractSpinBox):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QTextEdit):
        return widget.toPlainText()
    if isinstance(widget, QLabel):
        return widget.text()
    return None


def _panel_state(tab):
    state = {}
    for path in PANEL_WIDGETS:
        widget = _widget(tab, path)
        state[path] = [_value(widget), int(widget.isEnabled()), int(widget.isHidden())]
    state["sections"] = [int(button.isHidden()) for button in tab.findChildren(QToolButton)
                         if button.objectName() == "property_subsection_toggle"]
    return state


def _compact(value):
    return json.dumps(recorder.to_jsonable(value), ensure_ascii=False, sort_keys=False)


def _record_redraws(tab, monkeypatch):
    """再描画は呼ばれた回数だけ残して描かない(残す値は描画に左右されない)。"""
    calls = []
    for name in ("_update_plot", "_update_plot_appearance", "_refresh_after_dataset_property_change"):
        monkeypatch.setattr(tab, name, lambda *args, _name=name, **kwargs: calls.append(_name))
    return calls


def _take(items):
    taken = list(items)
    items.clear()
    return taken


_SKIPPED_FIELDS = {"df", "artist", "dataset_id", "provenance", "fit_result"}


def _attributes(dataset):
    return {f.name: getattr(dataset, f.name) for f in dataclasses.fields(dataset) if f.name not in _SKIPPED_FIELDS}


def _undo_texts(tab):
    return [tab.undo_stack.text(i) for i in range(tab.undo_stack.count())]


# --- 乱数のデータセット ---

def _random_dataset(rng, index):
    from graphica.core.dataset import Dataset

    n = rng.choice([1, 3, 8])
    columns = {"x": np.round(np.linspace(0, 1, n) * rng.randint(1, 9), 3), "y": np.round(np.cos(np.arange(n)), 4)}
    for extra in ("z", "yerr", "label"):
        if rng.random() < 0.5:
            columns[extra] = [f"p{i}" for i in range(n)] if extra == "label" else np.round(np.sin(np.arange(n)), 3)
    if rng.random() < 0.1:
        columns["y"] = [np.nan] * n
    df = pd.DataFrame(columns)
    names = list(df.columns)
    kwargs = dict(
        plot_type=rng.choice(["Line", "Scatter", "Line+Scatter", "Area", "Bar", "Step", "Density Scatter",
                              "Z-Color Scatter", "Unknown"]),
        color=rng.choice(["#1f77b4", "#ff0000", "red", "not-a-color"]),
        linestyle=rng.choice(["-", "--", "dashed", ":", "-.", "None", "", "solid", "bogus"]),
        linewidth=rng.choice([0.0, 0.5, 1.5, 3.25, 100.0, -1.0]),
        marker=rng.choice([None, "o", "s", "^", "x", "bogus"]),
        markersize=rng.choice([0.0, 2.0, 6.0, 12.5, 500.0]),
        smoothing=rng.random() < 0.4,
        smoothing_method=rng.choice(["cubic_spline", "moving_average", "median", "gaussian", "bogus"]),
        alpha=rng.choice([0.0, 0.3, 1.0, 2.0]),
        gradient_enabled=rng.random() < 0.4,
        gradient_color2=rng.choice(["#ffffff", "#00ff00", "bogus"]),
        gradient_target=rng.choice(["line", "fill", "both", "bogus"]),
        waterfall_enabled=rng.random() < 0.4,
        waterfall_offset_x=rng.choice([0.0, 0.5, -3.0, 1e6]),
        waterfall_offset_y=rng.choice([0.0, 1.0, 2.5, -1e6]),
        waterfall_occlusion_enabled=rng.random() < 0.5,
        waterfall_depth_shrink_enabled=rng.random() < 0.5,
        waterfall_depth_shrink_ratio=rng.choice([0.0, 0.03, 0.2, 5.0]),
        show_point_labels=rng.random() < 0.3,
        point_label_col_name=rng.choice([None, "label", "y", "missing"]),
        x_err_col_name=rng.choice([None, None, "yerr", "missing"]),
        y_err_col_name=rng.choice([None, "yerr", "missing"]),
        error_display=rng.choice(["bar", "band", "both", "bogus"]),
        fit_info=rng.choice([None, None, "a = 1.0"]),
        nan_policy=rng.choice(["gap", "ffill", "drop", "bogus"]),
        use_secondary_y=rng.random() < 0.3,
        subplot_target=rng.choice([0, 0, 1, 5]),
        data_kind=rng.choice(["1d", "1d", "2d_grid"]),
        z_col_name=rng.choice([None, "z", "missing"]),
        grid_interp_method=rng.choice(["linear", "cubic", "nearest", "bogus"]),
        colormap=rng.choice(["viridis", "plasma", "bogus"]),
        vmin=rng.choice([None, None, 0.0, -2.5]),
        vmax=rng.choice([None, None, 1.0, 7.5]),
        map_display_mode=rng.choice(["heatmap", "contour", "contour_filled", "heatmap_contour", "bogus"]),
        contour_levels=rng.choice([1, 10, 25, 999]),
    )
    return Dataset(df=df, name=f"ds{index:03d}", x_col_name=rng.choice(["x", "x", "missing"]),
                   y_col_name=rng.choice(["y", "y", names[-1]]), **kwargs)


RANDOM_DATASETS = 200


def test_selecting_random_datasets_fills_the_panel(app_env, modal_log, normalizer, monkeypatch):
    tab = _new_tab(app_env)
    tab.subplot_cols_spinbox.setValue(2)
    pump()
    redraws = _record_redraws(tab, monkeypatch)
    modal_log.accept_defaults()
    rng = random.Random(20260927)
    datasets = [_random_dataset(rng, i) for i in range(RANDOM_DATASETS)]
    folder = tab._add_dataset_folder_item("F")
    for dataset in datasets:
        tab._add_dataset(dataset, folder if rng.random() < 0.2 else None, select=False)
    tab.undo_stack.clear()
    _take(redraws)

    tree = tab.ui.dataset_list_widget
    result = {}
    for index, dataset in enumerate(datasets):
        if index % 25 == 24:
            tree.clearSelection()
            tree.setCurrentItem(folder)
            pump(2)
            result[f"{index:03d}_folder"] = {"panel": _compact(_panel_state(tab)), "redraws": _take(redraws),
                                             "modals": modal_log.take()}
        if index % 10 == 9:
            select(tab, dataset, datasets[index - 1])
            kind = "pair"
        else:
            select(tab, dataset)
            kind = "one"
        result[f"{index:03d}_{kind}"] = {
            "panel": _compact(_panel_state(tab)),
            # 選ぶだけでデータセットや Undo の履歴が変わっていないこと
            "attributes_after": _compact(_attributes(dataset)),
            "undo": _undo_texts(tab),
            "redraws": _take(redraws),
            "modals": modal_log.take(),
        }
    recorder.check("property_bindings/select_random_datasets", result, normalizer)


# --- 欄を手で変えたとき ---

def _set_text_and_finish(widget, text):
    widget.setText(text)
    widget.editingFinished.emit()


EDITS = (
    ("ui.legend_name_edit", lambda w: _set_text_and_finish(w, "新しい名前")),
    ("ui.plot_type_combo", lambda w: w.setCurrentText("Scatter")),
    ("ui.plot_type_combo", lambda w: w.setCurrentText("Area")),
    ("ui.linestyle_combo", lambda w: w.setCurrentIndex(1)),
    ("ui.linewidth_spinbox", lambda w: w.setValue(2.75)),
    ("ui.marker_combo", lambda w: w.setCurrentText("None")),
    ("ui.marker_combo", lambda w: w.setCurrentIndex(2)),
    ("ui.markersize_spinbox", lambda w: w.setValue(9.0)),
    ("color_picker_widget", lambda w: w.colorChanged.emit("#123456")),
    ("ui.plot_type_combo", lambda w: w.setCurrentText("Line")),
    ("ui.smoothing_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("smoothing_method_combo", lambda w: w.setCurrentIndex(2)),
    ("alpha_spinbox", lambda w: w.setValue(0.4)),
    ("gradient_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("gradient_color2_picker", lambda w: w.colorChanged.emit("#abcdef")),
    ("gradient_target_combo", lambda w: w.setCurrentIndex(1)),
    ("waterfall_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("waterfall_offset_x_spinbox", lambda w: w.setValue(0.75)),
    ("waterfall_offset_y_spinbox", lambda w: w.setValue(2.5)),
    ("waterfall_occlusion_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("waterfall_depth_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("waterfall_depth_ratio_spinbox", lambda w: w.setValue(0.1)),
    ("point_labels_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("point_label_col_combo", lambda w: w.setCurrentText("x")),
    ("point_label_col_combo", lambda w: w.setCurrentIndex(0)),
    ("use_secondary_y_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("subplot_target_combo", lambda w: w.setCurrentIndex(1)),
    ("error_display_combo", lambda w: w.setCurrentIndex(1)),
    ("nan_policy_combo", lambda w: w.setCurrentIndex(2)),
    ("data_2d_checkbox", lambda w: w.setChecked(True)),
    ("colormap_combo", lambda w: w.setCurrentIndex(3)),
    ("map_display_mode_combo", lambda w: w.setCurrentIndex(2)),
    ("contour_levels_spinbox", lambda w: w.setValue(15)),
    ("grid_interp_method_combo", lambda w: w.setCurrentText("nearest")),
    ("color_range_auto_checkbox", lambda w: w.setChecked(False)),
    ("vmin_spinbox", lambda w: w.setValue(-0.5)),
    ("vmax_spinbox", lambda w: w.setValue(3.5)),
    ("color_range_auto_checkbox", lambda w: w.setChecked(True)),
    ("data_2d_checkbox", lambda w: w.setChecked(False)),
    ("x_col_combo", lambda w: w.setCurrentText("yerr")),
    ("y_err_col_combo", lambda w: w.setCurrentIndex(0)),
)

BATCH_EDITS = (
    ("ui.linewidth_spinbox", lambda w: w.setValue(4.5)),
    ("alpha_spinbox", lambda w: w.setValue(0.6)),
    ("ui.plot_type_combo", lambda w: w.setCurrentText("Step")),
    ("use_secondary_y_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("waterfall_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("point_labels_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("color_picker_widget", lambda w: w.colorChanged.emit("#654321")),
)


def _run_edits(tab, edits, datasets, redraws, modal_log):
    steps = []
    for path, edit in edits:
        before = [_attributes(ds) for ds in datasets]
        undo_before = tab.undo_stack.count()
        edit(_widget(tab, path))
        pump()
        changes = []
        for ds, old in zip(datasets, before):
            new = _attributes(ds)
            changes.append({key: new[key] for key in new if repr(new[key]) != repr(old[key])})
        steps.append({
            "edit": path,
            "changed": _compact(changes),
            "undo_added": _undo_texts(tab)[undo_before:],
            "panel": _compact(_panel_state(tab)),
            "redraws": _take(redraws),
            "modals": modal_log.take(),
        })
    return steps


def test_editing_each_control_writes_the_selected_datasets(app_env, modal_log, normalizer, monkeypatch):
    a, b = ds_a(), ds_b()
    for ds in (a, b):
        ds.df["z"] = np.linspace(0.0, 1.0, len(ds.df))
    tab = _new_tab(app_env, a, b)
    tab.subplot_cols_spinbox.setValue(2)
    pump()
    redraws = _record_redraws(tab, monkeypatch)
    modal_log.accept_defaults()
    select(tab, a)
    _take(redraws)
    single = _run_edits(tab, EDITS, [a, b], redraws, modal_log)
    select(tab, a, b)
    _take(redraws)
    batch = _run_edits(tab, BATCH_EDITS, [a, b], redraws, modal_log)
    recorder.check("property_bindings/edit_each_control",
                   {"single": single, "batch": batch, "undo": _undo_texts(tab)}, normalizer)
