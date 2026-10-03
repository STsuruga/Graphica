"""マウスのモードに共通の扱い(gui/tools/pointer.py):
凡例の上で押した操作はモードで使わない、軸の外で離したら軸の縁で止めて確定する、ドラッグ中のプレビューは blit で描く。
イベントは matplotlib のイベントとしてキャンバスに流す。"""
import numpy as np
import pandas as pd
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.resize(1100, 700)
    w.show()
    for _ in range(5):
        QApplication.instance().processEvents()
    yield w
    w.close()


def _add(window, x=None, y=None, **kwargs):
    x = np.linspace(0, 10, 11) if x is None else x
    y = x * 10 if y is None else y
    ds = Dataset(name="d", df=pd.DataFrame({"x": x, "y": y}), x_col_name="x", y_col_name="y", **kwargs)
    window._add_dataset(ds, select=True)
    window.canvas.draw()
    return ds


def _fire(window, name, x, y, **kwargs):
    MouseEvent(name, window.canvas, x, y, **kwargs)._process()


def _legend_center(window):
    box = window.canvas.all_axes[0].get_legend().get_window_extent()
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def _px(ax, x, y):
    return tuple(int(v) for v in ax.transData.transform((x, y)))


# --- 凡例の上で押した操作 ---

@pytest.mark.parametrize("toggle, idle", [
    ("_toggle_annotation_mode", lambda w: w._annotation_drag_start is None),
    ("_toggle_range_select_mode", lambda w: w._range_select_axes is None),
    ("_toggle_peak_placement_mode", lambda w: w._pending_peak_guesses == []),
    ("_toggle_region_highlight_mode", lambda w: w._region_highlight_axes is None),
    ("_toggle_slice_extraction_mode", lambda w: w._slice_extraction_axes is None),
])
def test_pressing_on_the_legend_is_left_to_the_legend(window, toggle, idle):
    _add(window)
    getattr(window, toggle)(True)

    _fire(window, "button_press_event", *_legend_center(window), button=1)

    assert idle(window)


def test_layout_edit_does_not_grab_the_subplot_under_the_legend(window):
    _add(window)
    window.free_layout_checkbox.setChecked(True)
    window.canvas.draw()
    window._toggle_layout_edit_mode(True)

    _fire(window, "button_press_event", *_legend_center(window), button=1)

    assert window._layout_drag_state is None


# --- 軸の外で離したとき ---

def test_range_select_released_right_of_the_axes_masks_up_to_the_edge(window):
    ds = _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    window.canvas.draw()
    window._toggle_range_select_mode(True)

    _fire(window, "button_press_event", *_px(ax, 6.2, 50), button=1)
    _fire(window, "motion_notify_event", ax.bbox.x1 + 40, ax.bbox.y0 + 10, button=1)
    _fire(window, "button_release_event", ax.bbox.x1 + 40, ax.bbox.y0 + 10, button=1)

    assert ds.masked_row_indices == [7, 8, 9, 10]


def test_slice_released_outside_ends_at_the_edge(window):
    grid = Dataset(name="map", df=pd.DataFrame({"x": [0.0], "y": [0.0]}), x_col_name="x", y_col_name="y")
    window._add_dataset(grid, select=True)
    window.canvas.draw()
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    window.canvas.draw()
    window._toggle_slice_extraction_mode(True)
    applied = []
    window.mouse_tools["slice_extraction"]._apply_slice_extraction = lambda axes, start, end: applied.append(end)

    _fire(window, "button_press_event", *_px(ax, 2, 5), button=1)
    _fire(window, "button_release_event", ax.bbox.x1 + 50, int(_px(ax, 2, 5)[1]), button=1)

    assert len(applied) == 1
    assert applied[0][0] == pytest.approx(10)


# --- ドラッグ中のプレビュー ---

@pytest.mark.parametrize("toggle, tool, prefix, end", [
    ("_toggle_region_highlight_mode", "region_highlight", "_region_highlight", (7, 50)),
    ("_toggle_slice_extraction_mode", "slice_extraction", "_slice_extraction", (7, 80)),
])
def test_drag_preview_is_blitted_over_a_saved_background(window, monkeypatch, toggle, tool, prefix, end):
    _add(window)
    ax = window.canvas.all_axes[0]
    getattr(window, toggle)(True)
    _fire(window, "button_press_event", *_px(ax, 2, 50), button=1)
    state = window.mouse_tools[tool]
    assert getattr(state, f"{prefix}_background") is not None
    full_draws = []
    monkeypatch.setattr(window.canvas, "draw_idle", lambda *a, **k: full_draws.append(1))

    for step in (0.5, 1.0):
        x = 2 + (end[0] - 2) * step
        _fire(window, "motion_notify_event", *_px(ax, x, end[1]), button=1)

    preview = getattr(state, f"{prefix}_preview_artist")
    assert preview is not None and preview.get_animated()
    assert full_draws == []  # 動かしている間は全体を描き直さない
    # 同じ図形を使い回す(動くたびに足していかない)
    assert sum(1 for artist in ax.get_children() if artist is preview) == 1
