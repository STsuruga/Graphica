"""SVG の書き出しで、プロット枠のクリッピングマスクを残すか外すか(gui/export_settings.plot_clip_masks_removed)。"""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

import graphica.gui.app_settings as app_settings_module  # noqa: E402
from graphica.core.dataset import Dataset  # noqa: E402
from graphica.gui.export_settings import plot_clip_masks_removed  # noqa: E402
from graphica.gui.main_window import PlotterApp  # noqa: E402


def _svg(fig, remove):
    buf = io.StringIO()
    with plot_clip_masks_removed(fig, remove):
        fig.savefig(buf, format="svg")
    return buf.getvalue()


@pytest.fixture
def figure():
    fig, ax = plt.subplots()
    x = np.linspace(0, 10, 50)
    ax.plot(x, np.sin(x))
    ax.scatter(x, np.cos(x))
    ax.fill_between(x, 0, np.sin(x), alpha=0.3)
    ax.bar([1, 2], [0.5, 0.7])
    ax.margins(0)
    yield fig
    plt.close(fig)


def test_series_inside_the_frame_lose_their_clip_masks(figure):
    assert "clip-path=" in _svg(figure, False)
    assert "clip-path=" not in _svg(figure, True)


def test_series_reaching_outside_the_frame_keep_their_masks(figure):
    """拡大して枠の外にデータがあると、外すと枠の外に描かれてしまうので残す。"""
    figure.axes[0].set_xlim(2, 5)
    assert "clip-path=" in _svg(figure, True)


def test_the_figure_is_left_as_it_was(figure):
    _svg(figure, True)
    assert all(artist.get_clip_on() for artist in figure.axes[0].get_children()
               if artist in figure.axes[0].lines or artist in figure.axes[0].collections)


def test_a_custom_clip_shape_is_kept(figure):
    """枠とは別の形で切り抜いたもの(グラデーションの塗りの画像など)は、その形を失わない。"""
    ax = figure.axes[0]
    shape = Polygon([[1, 0], [2, 0.5], [3, 0]], transform=ax.transData, visible=False)
    ax.add_patch(shape)
    line, = ax.plot([1, 3], [0.1, 0.1])
    line.set_clip_path(shape)
    with plot_clip_masks_removed(figure):
        assert line.get_clip_on()


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    x = np.linspace(0, 10, 6)
    w.project.datasets.append(Dataset(name="sample", df=pd.DataFrame({"x": x, "y": np.sin(x)}),
                                      x_col_name="x", y_col_name="y"))
    w._update_plot()
    QApplication.instance().processEvents()
    yield w
    w.close()


@pytest.mark.parametrize("remove", [False, True])
def test_the_export_tab_saves_svg_with_or_without_masks(window, monkeypatch, tmp_path, remove):
    panel = window.export_preview_panel
    assert not panel.svg_remove_clip_masks_checkbox.isChecked()
    panel.svg_remove_clip_masks_checkbox.setChecked(remove)
    out_path = tmp_path / "figure.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "")))
    panel._on_save_clicked()
    has_masks = "clip-path=" in out_path.read_text(encoding="utf-8")
    assert has_masks is not remove


def test_the_export_tab_copies_svg_without_masks(window):
    data = window.export_preview_panel._render_full_figure_bytes(
        4.0, 3.0, 100, fmt="svg", transparent=False, svg_remove_clip_masks=True)
    assert b"clip-path=" not in data


def test_batch_export_follows_the_option(window, tmp_path):
    for remove in (False, True):
        out_path = tmp_path / f"batch_{remove}.svg"
        window._save_figure_with_options(window.canvas.fig, str(out_path),
                                         {"format": "svg", "dpi": 100, "svg_remove_clip_masks": remove})
        assert ("clip-path=" in out_path.read_text(encoding="utf-8")) is not remove
    # 画面の図は書き出しの後も切り抜いたまま
    assert all(line.get_clip_on() for line in window.canvas.fig.axes[0].lines)
