"""描画を固定する: プロットの種類 × 主なオプション × ライト/ダーク。軸の状態(JSON)と画素のハッシュを記録する。"""
import numpy as np
import pandas as pd
import pytest

import recorder
from scenario import dispose, pump

pytestmark = pytest.mark.pinned_os

PLOT_TYPES = ["Line", "Scatter", "Line+Scatter", "Area", "Bar", "Step", "Density Scatter", "Z-Color Scatter"]


def _frame(n=25, shift=0.0):
    x = np.linspace(0.0, 10.0, n)
    return pd.DataFrame({
        "x": x,
        "y": np.sin(x) + 2.0 + shift,
        "xerr": np.full(n, 0.15),
        "yerr": 0.1 + 0.02 * x,
        "z": np.cos(x) * 5.0,
        "label": [f"p{i}" for i in range(n)],
    })


def _dataset(name="ds", shift=0.0, **fields):
    from graphica.core.dataset import Dataset

    ds = Dataset(df=_frame(shift=shift), name=name, x_col_name="x", y_col_name="y")
    for key, value in fields.items():
        setattr(ds, key, value)
    return ds


def _add(tab, *datasets):
    for ds in datasets:
        tab._add_dataset(ds)


def _axis(tab, index=0, **values):
    settings = tab.project.all_plot_settings[index]
    settings.update(values)
    tab._apply_settings_to_ui_controls(tab.project.all_plot_settings[tab.project.active_axis_index])


def _plot_type_case(plot_type):
    def build(tab):
        _add(tab, _dataset(plot_type=plot_type, z_col_name="z"), _dataset("b", shift=1.0, plot_type=plot_type,
                                                                         color="#d62728", z_col_name="z"))
    return build


def _waterfall(depth):
    def build(tab):
        fields = dict(waterfall_enabled=True, waterfall_offset_x=0.5, waterfall_offset_y=0.8,
                      waterfall_depth_shrink_enabled=depth, waterfall_depth_shrink_ratio=0.05)
        _add(tab, _dataset("a", **fields), _dataset("b", color="#ff7f0e", **fields),
             _dataset("c", color="#2ca02c", **fields))
    return build


def _category_x(tab):
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"name": ["A", "B", "C", "D"], "value": [3.0, 1.0, 4.0, 1.5]})
    _add(tab, Dataset(df=df, name="cat", x_col_name="name", y_col_name="value", plot_type="Bar"))


def _date_x(tab):
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=12, freq="D"), "value": np.arange(12.0) ** 1.5})
    _add(tab, Dataset(df=df, name="days", x_col_name="date", y_col_name="value", plot_type="Line+Scatter"))


def _grid(mode):
    def build(tab):
        from graphica.core.dataset import Dataset

        xs, ys = np.meshgrid(np.linspace(0, 4, 9), np.linspace(0, 3, 7))
        df = pd.DataFrame({"x": xs.ravel(), "y": ys.ravel(), "z": (np.sin(xs) * np.cos(ys)).ravel()})
        _add(tab, Dataset(df=df, name="map", x_col_name="x", y_col_name="y", z_col_name="z", data_kind="2d_grid",
                          map_display_mode=mode, colormap="magma"))
    return build


def _secondary_y(tab):
    _add(tab, _dataset("left"), _dataset("right", shift=10.0, use_secondary_y=True, color="#9467bd"))
    _axis(tab, y2_label="右の軸")


def _secondary_x(tab):
    ds = _dataset("spectrum")
    ds.df["x"] = np.linspace(300.0, 800.0, 25)
    _add(tab, ds)
    _axis(tab, x_secondary_axis_source_unit="nm", x_secondary_axis_target_unit="eV")


def _log_axes(tab):
    ds = _dataset("pow")
    ds.df["x"] = np.logspace(0, 3, 25)
    ds.df["y"] = ds.df["x"] ** 1.5
    _add(tab, ds)
    _axis(tab, x_log=True, y_log=True)


def _axis_appearance(tab):
    _add(tab, _dataset())
    _axis(tab, title=r"題 $\alpha^2$", x_label="時間 (s)", y_label=r"強度 $I_0$", x_invert=True,
          x_autoscale=False, x_min=-1.0, x_max=12.0, grid_visible=True, minor_grid_visible=True,
          x_minor_ticks_visible=True, legend_loc="lower right")


def _annotations(tab):
    _add(tab, _dataset())
    ds_id = tab.project.datasets[0].dataset_id
    _axis(tab, annotations=[
        {"id": "t", "type": "text", "text": "注目", "xy": (2.0, 3.0), "xytext": (2.0, 3.0), "color": "#000000"},
        {"id": "a", "type": "arrow", "text": "ピーク", "xy": (1.6, 3.0), "xytext": (4.0, 3.4), "color": "#aa0000",
         "arrow_style": "->", "arrow_curvature": 0.2},
        {"id": "s", "type": "stat", "dataset_id": ds_id, "stat": "mean", "xy": (0.05, 0.95), "color": "#000000"},
        {"id": "v", "type": "vspan", "range": (6.0, 7.5), "color": "#ffcc00", "alpha": 0.3},
        {"id": "h", "type": "hspan", "range": (1.2, 1.5), "color": "#00ccff", "alpha": 0.3},
    ])


def _inset(tab):
    _add(tab, _dataset())
    _axis(tab, annotations=[{"id": "i", "type": "inset", "corner": "右上", "size": 0.35,
                             "zoom_x_range": (4.0, 6.0), "color": "#000000"}])


def _subplots_panel_labels(tab):
    tab.subplot_rows_spinbox.setValue(2)
    pump()
    tab.project.panel_labels_enabled = True
    _add(tab, _dataset("top"), _dataset("bottom", subplot_target=1, color="#e377c2"))


def _legend_dragged(tab):
    _add(tab, _dataset("a"), _dataset("b", shift=1.0, color="#17becf"))
    _axis(tab, legend_position=[0.3, 0.2])


def _dataset_options(**fields):
    def build(tab):
        _add(tab, _dataset(**fields))
    return build


def _masked_and_hidden(tab):
    _add(tab, _dataset("masked", masked_row_indices=[3, 4, 5, 10]), _dataset("hidden", shift=1.0, visible=False))


def _nan_policy(policy):
    def build(tab):
        ds = _dataset(nan_policy=policy)
        ds.df.loc[[5, 6, 12], "y"] = np.nan
        _add(tab, ds)
    return build


CASES = {
    **{f"type_{t.replace(' ', '_').replace('+', 'plus')}": _plot_type_case(t) for t in PLOT_TYPES},
    "errors_bar": _dataset_options(x_err_col_name="xerr", y_err_col_name="yerr", error_display="bar"),
    "errors_band": _dataset_options(y_err_col_name="yerr", error_display="band"),
    "errors_both_scatter": _dataset_options(plot_type="Scatter", y_err_col_name="yerr", error_display="both"),
    "smoothing_spline": _dataset_options(smoothing=True, smoothing_method="cubic_spline", marker="s"),
    "smoothing_moving_average": _dataset_options(plot_type="Line+Scatter", smoothing=True,
                                                 smoothing_method="moving_average"),
    "gradient_line": _dataset_options(gradient_enabled=True),
    "gradient_area_both": _dataset_options(plot_type="Area", gradient_enabled=True, gradient_target="both"),
    "point_labels": _dataset_options(plot_type="Scatter", show_point_labels=True, point_label_col_name="label"),
    "masked_and_hidden": _masked_and_hidden,
    "nan_gap": _nan_policy("gap"),
    "nan_ffill": _nan_policy("ffill"),
    "nan_drop": _nan_policy("drop"),
    "waterfall": _waterfall(False),
    "waterfall_depth": _waterfall(True),
    "category_x": _category_x,
    "date_x": _date_x,
    "log_axes": _log_axes,
    "axis_appearance": _axis_appearance,
    "secondary_y": _secondary_y,
    "secondary_x_units": _secondary_x,
    "map_heatmap": _grid("heatmap"),
    "map_contour": _grid("contour"),
    "map_contour_filled": _grid("contour_filled"),
    "map_heatmap_contour": _grid("heatmap_contour"),
    "annotations": _annotations,
    "inset": _inset,
    "subplots_panel_labels": _subplots_panel_labels,
    "legend_dragged": _legend_dragged,
}


def _figure_state(tab):
    figure = tab.canvas.fig
    rgba = recorder.rgba_of_figure(figure)
    return {
        "size_px": [int(v) for v in figure.get_size_inches() * figure.dpi],
        "facecolor": recorder.color_hex(figure.get_facecolor()),
        "texts": [t.get_text() for t in figure.texts],
        "axes": [recorder.axes_state(ax) for ax in figure.axes],
    }, rgba


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_rendering(app_env, modal_log, normalizer, theme):
    states, images = {}, {}
    for name, build in CASES.items():
        tab = app_env.tab(dark=theme == "dark", size=(1500, 1000))
        build(tab)
        tab._update_plot()
        pump()
        state, rgba = _figure_state(tab)
        state["modals"] = modal_log.take()
        states[name] = state
        images[name] = rgba
        dispose(tab)
    recorder.check(f"rendering/{theme}", states, normalizer)
    recorder.check_pixels(f"rendering/{theme}", images)
