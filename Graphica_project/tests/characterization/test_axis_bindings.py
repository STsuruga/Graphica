"""軸の設定の欄と値の対応(戻す・集める・止める・つなぐ)を、R-1a の前に固定する。

戻す順は値に効く(スピンボックスの範囲による丸め、見つからない選択肢の扱い、途中の例外で残る欄)ので、
既定値・古いプロジェクト・乱数で作った設定 200 通りを順に同じタブへ戻し、そのたびに集めた辞書(キーの順を含む)と
欄の有効/表示の状態を残す。欄を手で変えたときに書き戻される設定と、連動する欄の状態も残す。
"""
import json
import random
from pathlib import Path

import recorder
from scenario import pump
from test_operations import _new_tab

LEGACY_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "legacy_projects"

# 実装の表に頼らず、欄をここで名前で並べる(値の状態を残す欄と、連動して有効/表示が変わる欄)
PANEL_WIDGETS = (
    "ui.title_text_edit", "ui.x_label_text_edit", "ui.y_label_text_edit", "x_label_visible_checkbox",
    "y_label_visible_checkbox", "y2_label_text_edit",
    "ui.x_autoscale_checkbox", "ui.x_min_spinbox", "ui.x_max_spinbox", "ui.x_log_checkbox", "ui.x_invert_checkbox",
    "ui.x_major_tick_mode_combo", "ui.x_major_tick_interval_spinbox", "ui.x_minor_ticks_visible_checkbox",
    "ui.x_minor_tick_interval_spinbox", "x_log_minor_subs_combo", "x_log_minor_labels_checkbox",
    "x_tick_format_combo", "x_tick_decimals_spinbox", "x_secondary_axis_source_unit_combo",
    "x_secondary_axis_target_unit_combo",
    "ui.y_autoscale_checkbox", "ui.y_min_spinbox", "ui.y_max_spinbox", "ui.y_log_checkbox", "ui.y_invert_checkbox",
    "ui.y_major_tick_mode_combo", "ui.y_major_tick_interval_spinbox", "ui.y_minor_ticks_visible_checkbox",
    "ui.y_minor_tick_interval_spinbox", "y_log_minor_subs_combo", "y_log_minor_labels_checkbox",
    "y_tick_format_combo", "y_tick_decimals_spinbox",
    "ui.legend_visible_checkbox", "legend_loc_combo", "ui.grid_visible_checkbox", "ui.minor_grid_visible_checkbox",
    "x_major_grid_linestyle_combo", "x_major_grid_width_spinbox", "x_major_grid_alpha_spinbox",
    "x_minor_grid_linestyle_combo", "x_minor_grid_width_spinbox", "x_minor_grid_alpha_spinbox",
    "y_major_grid_linestyle_combo", "y_major_grid_width_spinbox", "y_major_grid_alpha_spinbox",
    "y_minor_grid_linestyle_combo", "y_minor_grid_width_spinbox", "y_minor_grid_alpha_spinbox",
    "major_tick_direction_combo", "minor_tick_direction_combo", "major_tick_direction_y2_combo",
    "minor_tick_direction_y2_combo", "x_ticks_visible_checkbox", "x_tick_labels_visible_checkbox",
    "y_ticks_visible_checkbox", "y_tick_labels_visible_checkbox",
    "ui.tick_font_button", "ui.tick_color_button", "ui.tick_width_spinbox", "major_tick_length_spinbox",
    "minor_tick_length_spinbox", "ui.axis_label_font_button", "ui.axis_label_color_button", "legend_font_button",
    "legend_color_button", "legend_order_button", "ui.spine_width_spinbox", "ui.spine_color_button",
    "colorbar_enabled_checkbox", "colorbar_position_combo", "colorbar_width_spinbox", "colorbar_label_edit",
)


def _widget(tab, path):
    obj = tab
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _panel_state(tab):
    return {path: [int(_widget(tab, path).isEnabled()), int(_widget(tab, path).isHidden())]
            for path in PANEL_WIDGETS}


def _compact(value):
    return json.dumps(recorder.to_jsonable(value), ensure_ascii=False, sort_keys=False)


def _record_redraws(tab, monkeypatch):
    """再描画は呼ばれた回数だけ残して描かない(描くと 1 回 0.3 秒かかり、残す値は描画に左右されない)。"""
    calls = []
    for name in ("_update_plot", "_update_plot_appearance"):
        monkeypatch.setattr(tab, name, lambda *args, _name=name, **kwargs: calls.append(_name))
    return calls


def _take(calls):
    taken = list(calls)
    calls.clear()
    return taken


def _apply_and_gather(tab, modal_log, settings, redraws):
    """戻して集める。集めた辞書はキーの順ごと 1 行の文字列にする(200 通りを並べても読める大きさにするため)。"""
    active_before = _compact(tab.project.all_plot_settings[tab.project.active_axis_index])
    tab._apply_settings_to_ui_controls(settings)
    gathered = tab._gather_settings_from_ui()
    return {
        "gathered": _compact(list(gathered.items())),
        "attributes": _compact({"tick_width": getattr(tab, "_tick_width", None),
                                "spine_width": getattr(tab, "_spine_width", None)}),
        "panel": _compact(_panel_state(tab)),
        # 戻す間は信号を止めているので、今の軸の設定は書き換わらない
        "active_settings_unchanged": _compact(
            tab.project.all_plot_settings[tab.project.active_axis_index]) == active_before,
        "redraws": _take(redraws),
        "modals": modal_log.take(),
    }


# --- 乱数の設定 ---

TEXT_KEYS = ("title", "x_label", "y_label", "y2_label", "colorbar_label")
BOOL_KEYS = ("x_label_visible", "y_label_visible", "x_autoscale", "x_log", "x_invert", "x_minor_ticks_visible",
             "x_log_minor_labels", "y_autoscale", "y_log", "y_invert", "y_minor_ticks_visible", "y_log_minor_labels",
             "legend_visible", "grid_visible", "minor_grid_visible", "x_ticks_visible", "x_tick_labels_visible",
             "y_ticks_visible", "y_tick_labels_visible", "colorbar_enabled")
FLOAT_KEYS = ("x_min", "x_max", "x_major_tick_interval", "x_minor_tick_interval", "y_min", "y_max",
              "y_major_tick_interval", "y_minor_tick_interval", "x_major_grid_width", "x_major_grid_alpha",
              "x_minor_grid_width", "x_minor_grid_alpha", "y_major_grid_width", "y_major_grid_alpha",
              "y_minor_grid_width", "y_minor_grid_alpha", "tick_width", "major_tick_length", "minor_tick_length",
              "spine_width", "colorbar_width_fraction")
INDEX_KEYS = ("x_major_tick_mode", "x_tick_format_mode", "y_major_tick_mode", "y_tick_format_mode")
INT_KEYS = ("x_tick_decimals", "y_tick_decimals")
CHOICES = {
    "x_log_minor_subs": ("auto", "all", "few", "one", "unknown"),
    "y_log_minor_subs": ("auto", "all", "few", "one", "unknown"),
    "x_secondary_axis_source_unit": ("none", "nm", "eV", "cm-1", "Hz", "unknown"),
    "x_secondary_axis_target_unit": ("none", "nm", "eV", "cm-1", "Hz", "unknown"),
    "legend_loc": ("best", "upper right", "upper left", "lower left", "lower right", "center", "right"),
    "major_tick_direction": ("out", "in", "inout", "sideways"),
    "minor_tick_direction": ("out", "in", "inout", "sideways"),
    "major_tick_direction_y2": ("out", "in", "inout", "sideways"),
    "minor_tick_direction_y2": ("out", "in", "inout", "sideways"),
    "x_major_grid_linestyle": ("-", "--", ":", "-.", "dotted"),
    "x_minor_grid_linestyle": ("-", "--", ":", "-.", "dotted"),
    "y_major_grid_linestyle": ("-", "--", ":", "-.", "dotted"),
    "y_minor_grid_linestyle": ("-", "--", ":", "-.", "dotted"),
    "colorbar_position": ("right", "left", "top", "bottom", "middle"),
}
FONT_KEYS = ("tick_font", "axis_label_font", "legend_font")
COLOR_KEYS = ("tick_color", "axis_label_color", "legend_color", "spine_color")


def _random_float(rng):
    return rng.choice([
        round(rng.uniform(-10, 10), rng.randint(0, 6)), round(rng.uniform(-1e6, 1e6), 3), 0, -1, 1e12, -1e12,
        round(rng.uniform(0, 1), 7), rng.randint(-5, 50),
    ])


def _random_font(rng):
    font = {}
    if rng.random() < 0.8:
        font["family"] = rng.choice(["Arial", "DejaVu Sans", ["Yu Gothic", "Meiryo"], "NoSuchFont", ["Times New Roman"]])
    if rng.random() < 0.7:
        font["size"] = rng.randint(1, 40)
    if rng.random() < 0.6:
        font["weight"] = rng.choice(["bold", "normal"])
    if rng.random() < 0.6:
        font["style"] = rng.choice(["italic", "normal"])
    return font


def _random_settings(rng):
    settings = {}
    for key in TEXT_KEYS:
        settings[key] = rng.choice(["", "Title", "$x^2$", "強度 (a.u.)", "a" * rng.randint(1, 30)])
    for key in BOOL_KEYS:
        settings[key] = rng.random() < 0.5
    for key in FLOAT_KEYS:
        settings[key] = _random_float(rng)
    for key in INDEX_KEYS:
        settings[key] = rng.randint(-1, 4)
    for key in INT_KEYS:
        settings[key] = rng.randint(-3, 12)
    for key, choices in CHOICES.items():
        settings[key] = rng.choice(choices)
    for key in FONT_KEYS:
        settings[key] = _random_font(rng)
    for key in COLOR_KEYS:
        settings[key] = "#%06x" % rng.randrange(0x1000000)
    # 古いプロジェクトのように一部のキーが無いもの、分ける前の共通キーだけを持つもの
    for key in list(settings):
        if rng.random() < 0.1:
            del settings[key]
    if rng.random() < 0.2:
        for key in ("x_ticks_visible", "y_ticks_visible", "x_tick_labels_visible", "y_tick_labels_visible"):
            settings.pop(key, None)
        settings["ticks_visible"] = rng.random() < 0.5
        settings["tick_labels_visible"] = rng.random() < 0.5
    if rng.random() < 0.5:
        items = list(settings.items())
        rng.shuffle(items)
        settings = dict(items)
    return settings


RANDOM_CASES = 200


def test_restore_then_gather_defaults_and_bad_values(app_env, modal_log, normalizer, monkeypatch):
    tab = _new_tab(app_env)
    redraws = _record_redraws(tab, monkeypatch)
    modal_log.accept_defaults()
    cases = {
        "defaults": {},
        "legacy_shared_tick_keys": {"ticks_visible": False, "tick_labels_visible": False},
        "unknown_choices": {"x_log_minor_subs": "x", "x_secondary_axis_source_unit": "x", "legend_loc": "x",
                            "colorbar_position": "x", "x_major_grid_linestyle": "x", "major_tick_direction": "x",
                            "x_major_tick_mode": 99, "x_tick_format_mode": -5},
        "legend_font_without_size": {"legend_font": {"family": "Arial", "weight": "bold"}},
        "minor_tick_length_none": {"minor_tick_length": None},
        "minor_tick_length_auto": {"minor_tick_length": -0.5},
        "text_x_min": {"title": "途中まで", "x_min": "abc", "y_min": 5},
        "none_legend_loc": {"legend_loc": None, "grid_visible": True},
        "none_font": {"tick_font": None, "tick_color": "#123456"},
        "defaults_again": {},
    }
    result = {name: _apply_and_gather(tab, modal_log, settings, redraws) for name, settings in cases.items()}
    recorder.check("axis_bindings/restore_edge_cases", result, normalizer)


def test_restore_then_gather_legacy_projects(app_env, modal_log, normalizer, monkeypatch):
    from graphica.models.project import ProjectModel

    tab = _new_tab(app_env)
    redraws = _record_redraws(tab, monkeypatch)
    modal_log.accept_defaults()
    result = {}
    for path in sorted(LEGACY_DIR.iterdir()):
        if path.suffix not in (".graphica", ".pkl"):
            continue
        project = ProjectModel()
        project.load_project(str(path))
        for index, settings in enumerate(project.all_plot_settings):
            result[f"{path.name}#{index}"] = _apply_and_gather(tab, modal_log, settings, redraws)
    assert result
    recorder.check("axis_bindings/restore_legacy_projects", result, normalizer)


def test_restore_then_gather_random_settings(app_env, modal_log, normalizer, monkeypatch):
    tab = _new_tab(app_env)
    redraws = _record_redraws(tab, monkeypatch)
    modal_log.accept_defaults()
    rng = random.Random(20260926)
    result = {}
    for index in range(RANDOM_CASES):
        settings = _random_settings(rng)
        result[f"{index:03d}"] = {"input": _compact(settings), **_apply_and_gather(tab, modal_log, settings, redraws)}
    recorder.check("axis_bindings/restore_random_settings", result, normalizer)


# --- 欄を手で変えたとき ---

EDITS = (
    ("ui.title_text_edit", lambda w: w.setText("手のタイトル")),
    ("ui.x_label_text_edit", lambda w: w.setText("X")),
    ("ui.y_label_text_edit", lambda w: w.setText("Y")),
    ("x_label_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("y_label_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("y2_label_text_edit", lambda w: w.setText("Y2")),
    ("ui.x_autoscale_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.x_min_spinbox", lambda w: w.setValue(-3.25)),
    ("ui.x_max_spinbox", lambda w: w.setValue(7.5)),
    ("ui.x_autoscale_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.x_log_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.x_invert_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.x_major_tick_mode_combo", lambda w: w.setCurrentIndex(1)),
    ("ui.x_major_tick_interval_spinbox", lambda w: w.setValue(2.5)),
    ("ui.x_minor_ticks_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.x_minor_tick_interval_spinbox", lambda w: w.setValue(0.25)),
    ("x_log_minor_subs_combo", lambda w: w.setCurrentIndex(2)),
    ("x_log_minor_labels_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("x_tick_format_combo", lambda w: w.setCurrentIndex(1)),
    ("x_tick_decimals_spinbox", lambda w: w.setValue(3)),
    ("x_secondary_axis_source_unit_combo", lambda w: w.setCurrentIndex(1)),
    ("x_secondary_axis_target_unit_combo", lambda w: w.setCurrentIndex(2)),
    ("ui.y_autoscale_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.y_min_spinbox", lambda w: w.setValue(-1.5)),
    ("ui.y_max_spinbox", lambda w: w.setValue(9.0)),
    ("ui.y_log_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.y_invert_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.y_major_tick_mode_combo", lambda w: w.setCurrentIndex(1)),
    ("ui.y_major_tick_interval_spinbox", lambda w: w.setValue(4.0)),
    ("ui.y_minor_ticks_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.y_minor_tick_interval_spinbox", lambda w: w.setValue(0.5)),
    ("y_log_minor_subs_combo", lambda w: w.setCurrentIndex(3)),
    ("y_log_minor_labels_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("y_tick_format_combo", lambda w: w.setCurrentIndex(2)),
    ("y_tick_decimals_spinbox", lambda w: w.setValue(1)),
    ("ui.legend_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.legend_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("legend_loc_combo", lambda w: w.setCurrentText("upper left")),
    ("ui.grid_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.minor_grid_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("x_major_grid_linestyle_combo", lambda w: w.setCurrentIndex(2)),
    ("x_major_grid_width_spinbox", lambda w: w.setValue(1.7)),
    ("x_major_grid_alpha_spinbox", lambda w: w.setValue(0.4)),
    ("x_minor_grid_linestyle_combo", lambda w: w.setCurrentIndex(3)),
    ("x_minor_grid_width_spinbox", lambda w: w.setValue(0.9)),
    ("x_minor_grid_alpha_spinbox", lambda w: w.setValue(0.3)),
    ("y_major_grid_linestyle_combo", lambda w: w.setCurrentIndex(1)),
    ("y_major_grid_width_spinbox", lambda w: w.setValue(1.1)),
    ("y_major_grid_alpha_spinbox", lambda w: w.setValue(0.6)),
    ("y_minor_grid_linestyle_combo", lambda w: w.setCurrentIndex(0)),
    ("y_minor_grid_width_spinbox", lambda w: w.setValue(0.3)),
    ("y_minor_grid_alpha_spinbox", lambda w: w.setValue(0.2)),
    ("major_tick_direction_combo", lambda w: w.setCurrentText("in")),
    ("minor_tick_direction_combo", lambda w: w.setCurrentText("inout")),
    ("major_tick_direction_y2_combo", lambda w: w.setCurrentText("in")),
    ("minor_tick_direction_y2_combo", lambda w: w.setCurrentText("inout")),
    ("x_ticks_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("x_tick_labels_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("y_ticks_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("y_tick_labels_visible_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("ui.tick_width_spinbox", lambda w: w.setValue(1.3)),
    ("major_tick_length_spinbox", lambda w: w.setValue(6.0)),
    ("minor_tick_length_spinbox", lambda w: w.setValue(2.0)),
    ("minor_tick_length_spinbox", lambda w: w.setValue(w.minimum())),
    ("ui.spine_width_spinbox", lambda w: w.setValue(2.2)),
    ("colorbar_enabled_checkbox", lambda w: w.setChecked(not w.isChecked())),
    ("colorbar_position_combo", lambda w: w.setCurrentIndex(2)),
    ("colorbar_width_spinbox", lambda w: w.setValue(0.1)),
    ("colorbar_label_edit", lambda w: w.setText("値")),
)


def test_editing_each_control_writes_the_active_axis(app_env, modal_log, normalizer, monkeypatch):
    from test_operations import ds_a

    tab = _new_tab(app_env, ds_a())
    redraws = _record_redraws(tab, monkeypatch)
    modal_log.accept_defaults()
    steps = []
    for path, edit in EDITS:
        before = dict(tab.project.all_plot_settings[tab.project.active_axis_index])
        edit(_widget(tab, path))
        pump()
        after = tab.project.all_plot_settings[tab.project.active_axis_index]
        changed = {key: after.get(key) for key in after if key not in before or before[key] != after[key]}
        steps.append({"edit": path, "changed": _compact(changed), "panel": _compact(_panel_state(tab)),
                      "redraws": _take(redraws), "modals": modal_log.take()})
    recorder.check("axis_bindings/edit_each_control", steps, normalizer)
