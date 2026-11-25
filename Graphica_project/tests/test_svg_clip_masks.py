"""SVG/PDF の書き出しで、プロット枠の外にはみ出す部分を削るか(gui/export_settings.outside_frame_cropped)。

PowerPoint の「図形に変換」などはクリッピングマスクを捨てるので、枠の外のデータが残っていると枠の外に出る。
"""
import io
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

import graphica.gui.app_settings as app_settings_module  # noqa: E402
from graphica.core.dataset import Dataset  # noqa: E402
from graphica.gui.export_settings import is_croppable_format, outside_frame_cropped  # noqa: E402
from graphica.gui.main_window import PlotterApp  # noqa: E402


def _svg(fig, crop):
    buf = io.StringIO()
    with outside_frame_cropped(fig, crop):
        fig.savefig(buf, format="svg")
    return buf.getvalue()


def _spectrum():
    x = np.linspace(190, 800, 600)
    return x, 3.0 * np.exp(-((x - 230) / 20) ** 2) + 0.8 * np.exp(-((x - 295) / 12) ** 2) + 0.05


@pytest.fixture
def figure():
    """吸収スペクトルのピークが、決めた Y の範囲(0〜0.85)の上に突き抜けている図。"""
    fig, ax = plt.subplots()
    x, y = _spectrum()
    ax.plot(x, y, marker="o", markevery=50)
    ax.scatter(x[::40], y[::40])
    ax.fill_between(x, 0, y, alpha=0.2)
    ax.bar([250, 400], [2.0, 0.3], width=20)
    ax.add_collection(LineCollection([[(200, 0.1), (260, 2.0)]], colors=["red"]))
    ax.set_xlim(190, 800)
    ax.set_ylim(0, 0.85)
    yield fig
    plt.close(fig)


def _drawn_inside(fig):
    """削った状態で、枠で切り抜かれる系列の描く点がすべて枠の中にあるか(画面の座標)。"""
    ax = fig.axes[0]
    box = ax.bbox
    tolerance = 1e-6

    def inside(points):
        points = points[np.isfinite(points).all(axis=1)]
        return bool(((points[:, 0] >= box.x0 - tolerance) & (points[:, 0] <= box.x1 + tolerance)
                     & (points[:, 1] >= box.y0 - tolerance) & (points[:, 1] <= box.y1 + tolerance)).all())

    checks = []
    for line in ax.lines:
        checks.append(inside(line.get_transform().transform(np.asarray(line.get_xydata(), dtype=float))))
    for collection in ax.collections:
        if len(collection.get_offsets()) and np.asarray(collection.get_offsets()).any():
            # 散布図: パスはマーカーの形(点の大きさ)なので、点の位置だけを見る
            checks.append(inside(collection.get_offset_transform().transform(collection.get_offsets())))
            continue
        for path in collection.get_paths():
            if len(path.vertices):
                checks.append(inside(collection.get_transform().transform(path.vertices)))
    for patch in ax.patches:
        if patch.get_visible():
            checks.append(inside(patch.get_transform().transform(patch.get_path().vertices)))
    return all(checks)


def test_nothing_outside_the_frame_is_written_and_no_masks_are_needed(figure):
    assert "clip-path=" in _svg(figure, False)
    with outside_frame_cropped(figure):
        assert _drawn_inside(figure)
        assert not any(artist.get_clip_on() for artist in figure.axes[0].lines + figure.axes[0].collections)
    assert "clip-path=" not in _svg(figure, True)


def test_a_line_is_cut_at_the_frame_edge(figure):
    ax = figure.axes[0]
    with outside_frame_cropped(figure):
        x, y = ax.lines[0].get_data()
        finite = np.isfinite(y)
        # ピークの山は枠の上の縁(0.85)でちょうど切れ、区間の間は NaN で区切る
        assert np.nanmax(y) == pytest.approx(0.85)
        assert (~finite).any()


def test_markers_are_kept_only_inside_the_frame(figure):
    ax = figure.axes[0]
    with outside_frame_cropped(figure):
        marker_lines = [line for line in ax.lines if line.get_linestyle() == "None"]
        assert len(marker_lines) == 1 and ax.lines[0].get_marker() == "None"
        assert np.all(np.asarray(marker_lines[0].get_ydata(), dtype=float) <= 0.85)


def test_the_figure_is_left_as_it_was(figure):
    ax = figure.axes[0]
    before = (ax.lines[0].get_xydata().copy(), len(ax.lines), ax.get_ylim(), ax.patches[0].get_height())
    _svg(figure, True)
    assert np.array_equal(ax.lines[0].get_xydata(), before[0])
    assert (len(ax.lines), ax.get_ylim(), ax.patches[0].get_height()) == before[1:]
    assert ax.lines[0].get_marker() == "o" and ax.lines[0].get_clip_on()


def test_off_keeps_the_data_outside_the_frame(figure):
    svg = _svg(figure, False)
    assert "clip-path=" in svg
    with outside_frame_cropped(figure, False):
        assert not _drawn_inside(figure)


@pytest.mark.parametrize("fmt, croppable", [("svg", True), (".pdf", True), ("PNG", False), ("jpg", False)])
def test_only_vector_formats_are_cropped(fmt, croppable):
    assert is_croppable_format(fmt) is croppable


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    x, y = _spectrum()
    w.project.datasets.append(Dataset(name="sample", df=pd.DataFrame({"x": x, "y": y}),
                                      x_col_name="x", y_col_name="y"))
    # Y の範囲を決めて、ピークを枠の上に突き抜けさせる
    w.ui.y_autoscale_checkbox.setChecked(False)
    w.ui.y_min_spinbox.setValue(0.0)
    w.ui.y_max_spinbox.setValue(0.85)
    w._update_plot()
    QApplication.instance().processEvents()
    yield w
    w.close()


def _max_path_y(svg_text):
    """SVG の線のパスの y 座標のいちばん小さい値(画面の上ほど小さい)。"""
    values = [float(v) for v in re.findall(r"[ML] [-\d.]+ ([-\d.]+)", svg_text)]
    return min(values)


@pytest.mark.parametrize("crop", [False, True])
def test_the_export_tab_saves_with_or_without_the_outside_part(window, monkeypatch, tmp_path, crop):
    panel = window.export_preview_panel
    assert not panel.crop_outside_frame_checkbox.isChecked()
    panel.crop_outside_frame_checkbox.setChecked(crop)
    out_path = tmp_path / "figure.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "")))
    panel._on_save_clicked()
    assert ("clip-path=" in out_path.read_text(encoding="utf-8")) is not crop


def test_the_export_tab_copies_svg_without_the_outside_part(window):
    data = window.export_preview_panel._render_full_figure_bytes(
        4.0, 3.0, 100, fmt="svg", transparent=False, crop_outside_frame=True)
    assert b"clip-path=" not in data


def test_batch_export_follows_the_option_and_leaves_the_screen_figure_alone(window, tmp_path):
    for crop in (False, True):
        out_path = tmp_path / f"batch_{crop}.svg"
        window._save_figure_with_options(window.canvas.fig, str(out_path),
                                         {"format": "svg", "dpi": 100, "crop_outside_frame": crop})
        assert ("clip-path=" in out_path.read_text(encoding="utf-8")) is not crop
    line = window.canvas.fig.axes[0].lines[0]
    assert line.get_clip_on() and np.nanmax(np.asarray(line.get_ydata(), dtype=float)) > 0.85
