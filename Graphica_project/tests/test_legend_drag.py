# tests/test_legend_drag.py
"""
凡例のドラッグ位置の保持(v1.4.2)。

凡例は `legend_obj.draggable(True)` で動かせるはずだったが、このメソッドは
matplotlib 3.x で削除済みで、AttributeError を握りつぶしていたため実際には
動かせなかった。set_draggable(update='loc') に置き換え、離した位置を軸の設定
legend_position に保存して、再描画・プロジェクト保存をまたいで保つ。
"""
import numpy as np
import pandas as pd
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.gui.canvas import MplCanvas, _legend_position_from_settings
from graphica.gui.main_window import PlotterApp


def _dataset(name="data"):
    x = np.linspace(0, 10, 20)
    return Dataset(name=name, df=pd.DataFrame({"x": x, "y": np.sin(x)}), x_col_name="x", y_col_name="y")


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


@pytest.mark.parametrize("value, expected", [
    ([0.25, 0.5], (0.25, 0.5)),
    ((0.1, 0.9), (0.1, 0.9)),
    (None, None), ([], None), ([0.1], None), (["a", 1], None), ([float("nan"), 0.2], None),
])
def test_legend_position_is_validated(value, expected):
    assert _legend_position_from_settings({"legend_position": value}) == expected


def test_saved_position_overrides_the_location_choice():
    canvas = MplCanvas(width=4, height=3, dpi=80)
    canvas.redraw_all([_dataset()], 1, 1, [{"legend_loc": "upper right", "legend_position": [0.2, 0.3]}])
    assert canvas.all_axes[0].get_legend()._loc == (0.2, 0.3)


def test_projects_without_a_position_keep_the_location_choice():
    canvas = MplCanvas(width=4, height=3, dpi=80)
    canvas.redraw_all([_dataset()], 1, 1, [{"legend_loc": "upper right"}])
    assert canvas.all_axes[0].get_legend()._loc == 1  # 'upper right'


def test_legend_is_actually_draggable():
    canvas = MplCanvas(width=4, height=3, dpi=80)
    canvas.redraw_all([_dataset()], 1, 1, [{}])
    assert canvas.all_axes[0].get_legend().get_draggable() is True


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.resize(1100, 700)
    w.show()
    w._add_dataset_with_undo(_dataset())
    _pump()
    yield w
    w.close()


def _drag_legend(window, dx=120, dy=-90):
    canvas = window.canvas
    canvas.draw()
    legend = canvas.all_axes[0].get_legend()
    box = legend.get_window_extent()
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    MouseEvent("button_press_event", canvas, cx, cy, button=1)._process()
    MouseEvent("motion_notify_event", canvas, cx + dx, cy + dy, button=1)._process()
    MouseEvent("button_release_event", canvas, cx + dx, cy + dy, button=1)._process()
    _pump()
    return legend._loc


def test_dragged_position_is_saved_to_the_axis_settings(window):
    loc = _drag_legend(window)
    saved = window.project.all_plot_settings[0].get("legend_position")
    assert saved == pytest.approx([loc[0], loc[1]], abs=1e-3)


def test_dragged_position_survives_a_full_redraw(window):
    _drag_legend(window)
    saved = window.project.all_plot_settings[0]["legend_position"]
    window._update_plot()
    _pump()
    assert window.canvas.all_axes[0].get_legend()._loc == pytest.approx(tuple(saved))


def test_dragged_position_survives_changing_another_axis_setting(window):
    _drag_legend(window)
    saved = window.project.all_plot_settings[0]["legend_position"]
    window.ui.title_text_edit.setText("タイトル")
    _pump()
    assert window.project.all_plot_settings[0]["legend_position"] == saved
    assert window.canvas.all_axes[0].get_legend()._loc == pytest.approx(tuple(saved))


def test_choosing_a_location_again_discards_the_dragged_position(window):
    _drag_legend(window)
    window.legend_loc_combo.setCurrentText("lower left")
    _pump()
    assert window.project.all_plot_settings[0].get("legend_position") is None
    assert window.canvas.all_axes[0].get_legend()._loc == 3  # 'lower left'


def test_clicking_without_dragging_saves_nothing(window):
    window.canvas.draw()
    MouseEvent("button_release_event", window.canvas, 10, 10, button=1)._process()
    _pump()
    assert window.project.all_plot_settings[0].get("legend_position") is None


def test_dragged_position_is_kept_in_the_project_file(window, tmp_path):
    _drag_legend(window)
    saved = window.project.all_plot_settings[0]["legend_position"]
    path = str(tmp_path / "legend.graphica")
    window.project.save_project(path)
    window.project.load_project(path)
    assert window.project.all_plot_settings[0]["legend_position"] == saved
