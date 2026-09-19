# tests/test_tick_length.py
"""
目盛線の長さの設定(実機フィードバック)。

- 長さは pt の絶対値で指定する(軸サイズに対する倍率にはしない、ユーザーと合意)。
- 補助目盛は「自動」を持ち、主目盛の長さ × MINOR_TICK_LENGTH_RATIO になる。
- キーを持たない既存プロジェクトは matplotlib 既定(3.5 / 2.0)のまま描かれる。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFormLayout

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.gui.canvas import (
    DEFAULT_MAJOR_TICK_LENGTH,
    MINOR_TICK_LENGTH_AUTO,
    MINOR_TICK_LENGTH_RATIO,
    MplCanvas,
    _resolve_tick_lengths,
)
from graphica.gui.main_window import PlotterApp


def _dataset(**kwargs):
    df = pd.DataFrame({"x": [400.0, 500.0, 600.0], "y": [1.0, 2.0, 3.0]})
    return Dataset(name="d", df=df, x_col_name="x", y_col_name="y", **kwargs)


def _tick_length(axis, which):
    """描画後の目盛線の長さ(pt)。Tick の tick1line はマーカーサイズが長さ。"""
    axis.figure.canvas.draw()
    ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
    assert ticks, f"{which} 目盛りが1本も無い"
    return ticks[0].tick1line.get_markersize()


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


# --- 長さの決定 ---

def test_defaults_match_matplotlib_so_existing_projects_are_unchanged():
    assert _resolve_tick_lengths({}) == (pytest.approx(3.5), pytest.approx(2.0))
    assert DEFAULT_MAJOR_TICK_LENGTH == matplotlib.rcParamsDefault["xtick.major.size"]
    assert DEFAULT_MAJOR_TICK_LENGTH * MINOR_TICK_LENGTH_RATIO == pytest.approx(
        matplotlib.rcParamsDefault["xtick.minor.size"])


def test_auto_minor_length_follows_the_major_length():
    major, minor = _resolve_tick_lengths({"major_tick_length": 7.0, "minor_tick_length": -1})
    assert major == pytest.approx(7.0)
    assert minor == pytest.approx(4.0)


@pytest.mark.parametrize("auto_value", [-1, MINOR_TICK_LENGTH_AUTO, None])
def test_any_negative_or_missing_minor_length_means_auto(auto_value):
    _, minor = _resolve_tick_lengths({"major_tick_length": 3.5, "minor_tick_length": auto_value})
    assert minor == pytest.approx(2.0)


def test_explicit_minor_length_is_used_as_is():
    assert _resolve_tick_lengths({"major_tick_length": 3.5, "minor_tick_length": 5.0})[1] == pytest.approx(5.0)


def test_zero_is_a_valid_explicit_length():
    assert _resolve_tick_lengths({"major_tick_length": 0.0, "minor_tick_length": 0.0}) == (0.0, 0.0)


# --- 描画への反映 ---

def test_lengths_are_applied_to_both_axes(canvas):
    settings = {"major_tick_length": 8.0, "minor_tick_length": 5.0,
                "x_minor_ticks_visible": True, "y_minor_ticks_visible": True}
    canvas.redraw_all([_dataset()], 1, 1, [settings])
    ax = canvas.all_axes[0]
    for axis in (ax.xaxis, ax.yaxis):
        assert _tick_length(axis, "major") == pytest.approx(8.0)
        assert _tick_length(axis, "minor") == pytest.approx(5.0)


def test_legacy_settings_draw_matplotlib_default_lengths(canvas):
    canvas.redraw_all([_dataset()], 1, 1, [{"x_minor_ticks_visible": True}])
    ax = canvas.all_axes[0]
    assert _tick_length(ax.xaxis, "major") == pytest.approx(3.5)
    assert _tick_length(ax.xaxis, "minor") == pytest.approx(2.0)


def test_secondary_y_axis_uses_the_same_lengths(canvas):
    ds = _dataset(use_secondary_y=True)
    canvas.redraw_all([ds], 1, 1, [{"major_tick_length": 9.0, "minor_tick_length": -1}])
    secondary_ax = canvas.all_secondary_axes[0]
    assert secondary_ax is not None
    assert _tick_length(secondary_ax.yaxis, "major") == pytest.approx(9.0)


def test_secondary_x_axis_uses_the_major_length(canvas):
    settings = {"x_secondary_axis_source_unit": "nm", "x_secondary_axis_target_unit": "eV",
                "major_tick_length": 6.0}
    canvas.redraw_all([_dataset()], 1, 1, [settings])
    ax = canvas.all_axes[0]
    secondary_x = [child for child in ax.child_axes if child.get_xlabel() == "eV(エネルギー)"]
    assert len(secondary_x) == 1
    assert _tick_length(secondary_x[0].xaxis, "major") == pytest.approx(6.0)


def test_single_axis_redraw_keeps_the_lengths(canvas):
    settings = {"major_tick_length": 7.5}
    canvas.redraw_all([_dataset()], 1, 1, [settings])
    canvas.update_single_axis(0, [_dataset()], settings)
    assert _tick_length(canvas.all_axes[0].xaxis, "major") == pytest.approx(7.5)


# --- 設定パネル ---

@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.show()
    QApplication.instance().processEvents()
    yield w
    w.close()


def test_length_row_sits_right_after_tick_width(window):
    form = window.ui.formLayout_3
    width_row, _ = form.getWidgetPosition(window.ui.tick_width_spinbox)
    length_row, _ = form.getWidgetPosition(window.tick_length_label)
    assert length_row == width_row + 1
    field = form.itemAt(length_row, QFormLayout.ItemRole.FieldRole).layout()
    assert field.itemAt(0).widget() is window.major_tick_length_spinbox
    assert field.itemAt(1).widget() is window.minor_tick_length_spinbox


def test_panel_defaults_show_matplotlib_default_and_auto(window):
    assert window.major_tick_length_spinbox.value() == pytest.approx(3.5)
    assert window.minor_tick_length_spinbox.text() == "自動"
    settings = window._gather_settings_from_ui()
    assert settings["major_tick_length"] == pytest.approx(3.5)
    assert settings["minor_tick_length"] == -1


def test_auto_is_stored_as_minus_one_and_restored_as_auto(window):
    window._apply_settings_to_ui_controls({"major_tick_length": 5.0, "minor_tick_length": 3.0})
    assert window._gather_settings_from_ui()["minor_tick_length"] == pytest.approx(3.0)
    window._apply_settings_to_ui_controls({"major_tick_length": 5.0, "minor_tick_length": -1})
    assert window.minor_tick_length_spinbox.text() == "自動"
    assert window._gather_settings_from_ui()["minor_tick_length"] == -1


def test_one_step_up_from_auto_is_zero_not_another_negative(window):
    spin = window.minor_tick_length_spinbox
    spin.setValue(MINOR_TICK_LENGTH_AUTO)
    spin.stepUp()
    assert spin.value() == pytest.approx(0.0)


def test_changing_the_length_redraws_the_plot(window):
    window._add_dataset_with_undo(_dataset())
    window.major_tick_length_spinbox.setValue(10.0)
    window.minor_tick_length_spinbox.setValue(MINOR_TICK_LENGTH_AUTO)
    QApplication.instance().processEvents()
    assert _tick_length(window.canvas.all_axes[0].xaxis, "major") == pytest.approx(10.0)
