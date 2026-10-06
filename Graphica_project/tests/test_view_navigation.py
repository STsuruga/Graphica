"""gui/tools/view_navigation.py: 軸の上のホイール・ドラッグ・ダブルクリック、矩形ズームと右クリックで戻す、
プロットのダブルクリックでのリセット、中ボタンのパン。イベントは matplotlib のイベントとしてキャンバスに流す。"""
import numpy as np
import pandas as pd
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QToolBar

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp
from graphica.gui.tools.view_navigation import RECT_ZOOM_MIN_PX


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


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
    _pump()
    yield w
    w.close()


def _add(window, name="d", x=None, y=None, **kwargs):
    x = np.linspace(0, 10, 11) if x is None else x
    y = x * 10 if y is None else y
    ds = Dataset(name=name, df=pd.DataFrame({"x": x, "y": y}), x_col_name="x", y_col_name="y", **kwargs)
    window.project.datasets.append(ds)
    window._update_plot()
    window.canvas.draw()
    return ds


def _nav(window):
    return window.view_navigation


def _fire(window, name, x, y, **kwargs):
    MouseEvent(name, window.canvas, x, y, **kwargs)._process()


def _band(window, axis_key, index=0):
    return next(b for b in _nav(window).axis_bands() if b.subplot_index == index and b.axis_key == axis_key)


def _band_center(window, axis_key, index=0):
    box = _band(window, axis_key, index).bbox
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def _to_px(ax, x, y):
    # matplotlib のイベントは座標を整数のピクセルに切り捨てるので、期待値もその位置で計算する
    px, py = ax.transData.transform((x, y))
    return int(px), int(py)


def _limits(*axes):
    return [v for ax in axes for v in (*ax.get_xlim(), *ax.get_ylim())]


def _to_data(ax, px, py):
    return ax.transData.inverted().transform((px, py))


def _drag(window, start, end, button=1, steps=4):
    _fire(window, "button_press_event", *start, button=button)
    for i in range(1, steps + 1):
        t = i / steps
        _fire(window, "motion_notify_event", start[0] + (end[0] - start[0]) * t,
              start[1] + (end[1] - start[1]) * t, button=button)
    _fire(window, "button_release_event", *end, button=button)


# --- 軸の帯 ---

def test_each_subplot_has_x_and_y_bands_outside_the_plot(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    x_band = _band(window, 'x').bbox
    y_band = _band(window, 'y').bbox
    assert x_band.y1 == pytest.approx(ax.bbox.y0) and x_band.y0 < ax.bbox.y0
    assert y_band.x1 == pytest.approx(ax.bbox.x0) and y_band.x0 < ax.bbox.x0
    assert not any(b.axis_key == 'y2' for b in _nav(window).axis_bands())


def test_secondary_axis_gets_its_own_band_on_the_right(window):
    _add(window)
    _add(window, name="d2", use_secondary_y=True)
    secondary = window.canvas.all_secondary_axes[0]
    band = _band(window, 'y2')
    assert band.ax is secondary
    assert band.bbox.x0 == pytest.approx(window.canvas.all_axes[0].bbox.x1)


# --- 軸の上のホイール ---

def test_wheel_on_x_axis_zooms_only_x_around_the_cursor(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ylim = ax.get_ylim()
    cx, cy = _band_center(window, 'x')
    px = _to_px(ax, 3.0, 0)[0]
    under_cursor = _to_data(ax, px, 0)[0]

    _fire(window, "scroll_event", px, cy, step=1, button='up')

    x0, x1 = ax.get_xlim()
    assert x1 - x0 == pytest.approx(10 / 1.2)
    assert _to_data(ax, px, 0)[0] == pytest.approx(under_cursor)  # カーソルの下の値は動かない
    assert ax.get_ylim() == ylim


def test_wheel_down_on_y_axis_zooms_out(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_ylim(0, 100)
    cx, cy = _band_center(window, 'y')

    _fire(window, "scroll_event", cx, cy, step=-1, button='down')

    y0, y1 = ax.get_ylim()
    assert y1 - y0 == pytest.approx(120)


def test_wheel_inside_the_plot_no_longer_zooms(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    px, py = _to_px(ax, 5, 50)

    _fire(window, "scroll_event", px, py, step=1, button='up')

    assert ax.get_xlim() == xlim and ax.get_ylim() == ylim


def test_wheel_on_log_axis_keeps_the_value_under_the_cursor(window):
    _add(window, x=np.linspace(1, 10, 10), y=np.logspace(0, 4, 10))
    window.project.all_plot_settings[0]['y_log'] = True
    window._update_plot()
    window.canvas.draw()
    ax = window.canvas.all_axes[0]
    cx, _ = _band_center(window, 'y')
    py = _to_px(ax, 1, 100.0)[1]
    under_cursor = _to_data(ax, 0, py)[1]

    _fire(window, "scroll_event", cx, py, step=2, button='up')

    y0, y1 = ax.get_ylim()
    assert y0 > 0 and y1 > 0
    assert _to_data(ax, 0, py)[1] == pytest.approx(under_cursor, rel=1e-6)


def test_wheel_on_secondary_axis_changes_only_the_secondary_range(window):
    _add(window)
    _add(window, name="d2", use_secondary_y=True)
    ax = window.canvas.all_axes[0]
    secondary = window.canvas.all_secondary_axes[0]
    ylim = ax.get_ylim()
    y2lim = secondary.get_ylim()
    cx, cy = _band_center(window, 'y2')

    _fire(window, "scroll_event", cx, cy, step=1, button='up')

    assert ax.get_ylim() == ylim
    assert secondary.get_ylim() != y2lim


# --- 軸の上のドラッグ ---

def test_dragging_the_x_axis_moves_x_with_the_cursor(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ylim = ax.get_ylim()
    _, cy = _band_center(window, 'x')
    start_px = _to_px(ax, 4.0, 0)[0]
    grabbed = _to_data(ax, start_px, 0)[0]

    # 途中の位置でも、つかんだ値がカーソルの下にあり続ける(差を取る基準がずれない)
    _fire(window, "button_press_event", start_px, cy, button=1)
    for dx in (10, 20, 30, 40, 50):
        _fire(window, "motion_notify_event", start_px + dx, cy, button=1)
        assert _to_data(ax, start_px + dx, 0)[0] == pytest.approx(grabbed)
    _fire(window, "button_release_event", start_px + 50, cy, button=1)

    assert ax.get_ylim() == ylim
    assert _nav(window)._pan is None


def test_dragging_the_y_axis_moves_only_y(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    xlim = ax.get_xlim()
    cx, cy = _band_center(window, 'y')
    before = _to_data(ax, 0, cy)[1]

    _drag(window, (cx, cy), (cx, cy - 40))

    assert ax.get_xlim() == xlim
    assert _to_data(ax, 0, cy - 40)[1] == pytest.approx(before)


# --- 軸の上のダブルクリック ---

def test_double_click_on_axis_resets_to_the_set_min_max(window):
    _add(window)
    settings = window.project.all_plot_settings[0]
    settings.update({'x_autoscale': False, 'x_min': 2.0, 'x_max': 8.0})
    window._update_plot()
    window.canvas.draw()
    ax = window.canvas.all_axes[0]
    ax.set_xlim(4, 5)
    ylim = ax.get_ylim()

    _fire(window, "button_press_event", *_band_center(window, 'x'), button=1, dblclick=True)

    assert ax.get_xlim() == pytest.approx((2.0, 8.0))
    assert ax.get_ylim() == ylim


def test_double_click_on_autoscaled_axis_shows_the_whole_data(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    full = ax.get_ylim()
    ax.set_ylim(30, 40)

    _fire(window, "button_press_event", *_band_center(window, 'y'), button=1, dblclick=True)

    assert ax.get_ylim() == pytest.approx(full)


def test_axis_reset_keeps_an_inverted_axis_inverted(window):
    _add(window)
    settings = window.project.all_plot_settings[0]
    settings.update({'x_autoscale': False, 'x_min': 0.0, 'x_max': 10.0, 'x_invert': True})
    window._update_plot()
    window.canvas.draw()
    ax = window.canvas.all_axes[0]
    ax.set_xlim(7, 6)

    _nav(window).reset_axis(0, 'x')

    assert ax.get_xlim() == pytest.approx((10.0, 0.0))


# --- 矩形ズーム・右クリックで戻す ---

def test_dragging_in_the_plot_zooms_to_the_rectangle(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    start, end = _to_px(ax, 2, 20), _to_px(ax, 6, 70)
    (x0, y0), (x1, y1) = _to_data(ax, *start), _to_data(ax, *end)

    _drag(window, start, end)

    assert ax.get_xlim() == pytest.approx((x0, x1))
    assert ax.get_ylim() == pytest.approx((y0, y1))


def test_rectangle_zoom_also_zooms_the_secondary_axis(window):
    _add(window)
    _add(window, name="d2", y=np.linspace(0, 1, 11), use_secondary_y=True)
    ax = window.canvas.all_axes[0]
    secondary = window.canvas.all_secondary_axes[0]
    start, end = _to_px(ax, 2, 20), _to_px(ax, 6, 70)
    y2_expected = (_to_data(secondary, *start)[1], _to_data(secondary, *end)[1])

    _drag(window, start, end)

    assert secondary.get_ylim() == pytest.approx(y2_expected)


def test_small_drag_is_a_click_not_a_zoom(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    start = _to_px(ax, 5, 50)

    _drag(window, start, (start[0] + 40, start[1] + RECT_ZOOM_MIN_PX - 1))

    assert ax.get_xlim() == xlim and ax.get_ylim() == ylim


def test_no_rectangle_zoom_while_a_mode_is_active(window):
    _add(window)
    window._toggle_cursor_mode(True)
    ax = window.canvas.all_axes[0]
    xlim, ylim = ax.get_xlim(), ax.get_ylim()

    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 6, 70))

    assert ax.get_xlim() == xlim and ax.get_ylim() == ylim
    assert _nav(window)._rect_zoom is None


def test_dragging_the_legend_does_not_zoom(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    box = ax.get_legend().get_window_extent()
    center = ((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)

    _drag(window, center, (center[0] - 150, center[1] - 100))

    assert ax.get_xlim() == xlim and ax.get_ylim() == ylim


def test_right_click_goes_back_one_rectangle_zoom_at_a_time(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    original = _limits(ax)
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 8, 80))
    first = _limits(ax)
    _drag(window, _to_px(ax, 3, 30), _to_px(ax, 5, 50))

    _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=3)
    assert _limits(ax) == pytest.approx(first)
    _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=3)
    assert _limits(ax) == pytest.approx(original)
    # それより前は無いので何もしない
    _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=3)
    assert _limits(ax) == pytest.approx(original)


def test_right_click_does_not_go_back_in_a_mode_that_uses_right_click(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 8, 80))
    zoomed = (ax.get_xlim(), ax.get_ylim())
    window._toggle_peak_placement_mode(True)

    _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=3)

    assert (ax.get_xlim(), ax.get_ylim()) == zoomed


def test_axis_wheel_and_drag_are_not_undone_by_right_click(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    _fire(window, "scroll_event", *_band_center(window, 'x'), step=1, button='up')
    after_wheel = ax.get_xlim()

    _fire(window, "button_press_event", *ax.bbox.get_points().mean(axis=0), button=3)

    assert ax.get_xlim() == after_wheel


# --- プロットのダブルクリック ---

def test_double_click_in_the_plot_resets_all_axes_of_the_subplot(window):
    _add(window)
    _add(window, name="d2", y=np.linspace(0, 1, 11), use_secondary_y=True)
    ax = window.canvas.all_axes[0]
    secondary = window.canvas.all_secondary_axes[0]
    full = _limits(ax, secondary)
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 6, 70))

    _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=1, dblclick=True)

    assert _limits(ax, secondary) == pytest.approx(full)
    # リセットしたら戻る先は無い
    assert not _nav(window).zoom_back(0)


def test_double_click_is_left_to_a_mode_that_uses_clicks(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_xlim(3, 4)
    window._toggle_peak_placement_mode(True)

    _fire(window, "button_press_event", *_to_px(ax, 3.5, 40), button=1, dblclick=True)

    assert ax.get_xlim() == (3, 4)


def test_double_click_on_the_legend_does_not_reset(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_xlim(3, 4)
    window.canvas.draw()
    box = ax.get_legend().get_window_extent()

    _fire(window, "button_press_event", (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, button=1, dblclick=True)

    assert ax.get_xlim() == (3, 4)


# --- 中ボタンのパン ---

def test_middle_drag_follows_the_cursor_on_every_step(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 100)
    start = _to_px(ax, 5, 50)
    grabbed = _to_data(ax, *start)

    _fire(window, "button_press_event", *start, button=2)
    for step in range(1, 6):
        current = (start[0] + 10 * step, start[1] - 7 * step)
        _fire(window, "motion_notify_event", *current, button=2)
        assert _to_data(ax, *current) == pytest.approx(grabbed)
    _fire(window, "button_release_event", *current, button=2)
    assert _nav(window)._pan is None


def test_middle_drag_pans_the_secondary_axis_too(window):
    _add(window)
    _add(window, name="d2", y=np.linspace(0, 1, 11), use_secondary_y=True)
    secondary = window.canvas.all_secondary_axes[0]
    ax = window.canvas.all_axes[0]
    start = _to_px(ax, 5, 50)
    grabbed = _to_data(secondary, *start)[1]

    _drag(window, start, (start[0], start[1] + 60), button=2)

    assert _to_data(secondary, start[0], start[1] + 60)[1] == pytest.approx(grabbed)


# --- マウスカーソルの形・ツールバー ---

def test_cursor_shape_changes_over_axis_bands(window):
    _add(window)
    canvas = window.canvas
    _fire(window, "motion_notify_event", *_band_center(window, 'x'))
    assert canvas.cursor().shape() == Qt.CursorShape.SizeHorCursor
    _fire(window, "motion_notify_event", *_band_center(window, 'y'))
    assert canvas.cursor().shape() == Qt.CursorShape.SizeVerCursor
    _fire(window, "motion_notify_event", *_to_px(canvas.all_axes[0], 5, 50))
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_plot_toolbar_has_no_matplotlib_navigation_buttons(window):
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

    assert isinstance(window.plot_toolbar, QToolBar)
    assert not window.findChildren(NavigationToolbar2QT)
    texts = {action.text() for action in window.plot_toolbar.actions()}
    for removed in ("Home", "Back", "Forward", "Pan", "Zoom", "Subplots", "Customize", "Save"):
        assert removed not in texts
    assert window.cursor_action in window.plot_toolbar.actions()
    assert window.reset_zoom_action in window.plot_toolbar.actions()



def test_legend_dragged_onto_an_axis_band_is_still_dragged_not_panned(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    xlim = ax.get_xlim()
    legend = ax.get_legend()
    # 凡例を x 軸の帯の上に置く(軸に対する座標で、枠の少し下)
    legend.set_loc((0.4, -0.12))
    window.canvas.draw()
    box = legend.get_window_extent()
    center = ((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
    assert _nav(window).axis_band_at(*center) is not None

    _drag(window, center, (center[0] + 60, center[1]))

    assert ax.get_xlim() == xlim


# --- マウスで変えた範囲を、描き直しても保つ ---

def test_a_rectangle_zoom_survives_a_full_redraw(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 6, 70))
    zoomed = _limits(ax)

    window.redraw()

    assert _limits(window.canvas.all_axes[0]) == pytest.approx(zoomed)


def test_an_axis_wheel_zoom_survives_an_appearance_redraw_and_keeps_the_other_axis(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    y_before = ax.get_ylim()
    _fire(window, "scroll_event", *_band_center(window, 'x'), step=1, button='up')
    x_zoomed = ax.get_xlim()

    window.redraw_appearance()
    window.redraw()

    ax = window.canvas.all_axes[0]
    assert ax.get_xlim() == pytest.approx(x_zoomed)
    assert ax.get_ylim() == pytest.approx(y_before)


def test_changing_the_range_setting_of_that_axis_wins_over_the_mouse(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 6, 70))
    zoomed_y = ax.get_ylim()

    window.project.all_plot_settings[0].update({'x_autoscale': False, 'x_min': 1.0, 'x_max': 9.0})
    window.redraw()

    ax = window.canvas.all_axes[0]
    assert ax.get_xlim() == pytest.approx((1.0, 9.0))
    assert ax.get_ylim() == pytest.approx(zoomed_y)  # Y の設定は変えていないので保つ


@pytest.mark.parametrize("reset", ["double_click", "reset_button"])
def test_a_reset_is_not_undone_by_the_next_redraw(window, reset):
    _add(window)
    ax = window.canvas.all_axes[0]
    full = _limits(ax)
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 6, 70))

    if reset == "double_click":
        _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=1, dblclick=True)
    else:
        window._reset_zoom()
    window.redraw()

    assert _limits(window.canvas.all_axes[0]) == pytest.approx(full)


def test_going_back_past_the_first_zoom_lets_the_axes_follow_the_settings_again(window):
    _add(window)
    ax = window.canvas.all_axes[0]
    _drag(window, _to_px(ax, 2, 20), _to_px(ax, 6, 70))
    _fire(window, "button_press_event", *_to_px(ax, 4, 40), button=3)

    _add(window, name="wide", x=np.linspace(0, 20, 21))  # 自動の範囲が広がる

    assert window.canvas.all_axes[0].get_xlim()[1] == pytest.approx(20)


def test_views_of_removed_subplots_are_dropped(window):
    _add(window)
    window.canvas.view_overrides[5] = {'x': ((0.0, 1.0), ())}

    window.canvas.draw()

    assert 5 not in window.canvas.view_overrides


# --- ホイールの量(macOS のピクセル単位のスクロール・慣性・速さの設定) ---

class _FakeWheel:
    """Qt の QWheelEvent の代わり。angleDelta は 1/8 度単位(ホイール1段 = 120)。"""

    def __init__(self, angle_y, phase=Qt.ScrollPhase.NoScrollPhase):
        self._angle_y = angle_y
        self._phase = phase

    def angleDelta(self):
        from PySide6.QtCore import QPoint
        return QPoint(0, self._angle_y)

    def phase(self):
        return self._phase


def _wheel_x(window, step, angle_y, phase=Qt.ScrollPhase.NoScrollPhase):
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    cx, cy = _band_center(window, 'x')
    _fire(window, "scroll_event", cx, cy, step=step, button='up' if angle_y > 0 else 'down',
          guiEvent=_FakeWheel(angle_y, phase))
    x0, x1 = ax.get_xlim()
    return x1 - x0


def test_wheel_uses_angle_delta_not_the_pixel_step_from_macos(window):
    """macOS のトラックパッドでは matplotlib の step がピクセル数(ここでは 40)になる。段の数で拡大する。"""
    _add(window)
    assert _wheel_x(window, step=40, angle_y=120) == pytest.approx(10 / 1.2)


def test_small_trackpad_movement_zooms_only_a_little(window):
    _add(window)
    assert _wheel_x(window, step=6, angle_y=12) == pytest.approx(10 / 1.2 ** 0.1)


def test_one_wheel_event_is_capped(window):
    """速く払って1回で何段分も来ても、1回で変わるのは MAX_WHEEL_ZOOM_PER_EVENT 倍まで。"""
    from graphica.gui.tools.view_navigation import MAX_WHEEL_ZOOM_PER_EVENT
    _add(window)
    assert _wheel_x(window, step=400, angle_y=1200) == pytest.approx(10 / MAX_WHEEL_ZOOM_PER_EVENT)
    assert _wheel_x(window, step=-400, angle_y=-1200) == pytest.approx(10 * MAX_WHEEL_ZOOM_PER_EVENT)


def test_momentum_scroll_after_lifting_the_fingers_does_not_zoom(window):
    _add(window)
    assert _wheel_x(window, step=40, angle_y=120, phase=Qt.ScrollPhase.ScrollMomentum) == pytest.approx(10)


@pytest.mark.parametrize("speed, base", [("slow", 1.1), ("normal", 1.2), ("fast", 1.4)])
def test_wheel_zoom_speed_setting(window, speed, base):
    _add(window)
    app_settings_module.WHEEL_ZOOM_SPEED.write(window.settings, speed)
    assert _wheel_x(window, step=1, angle_y=120) == pytest.approx(10 / base)


def test_unknown_wheel_zoom_speed_falls_back_to_normal(window):
    _add(window)
    app_settings_module.WHEEL_ZOOM_SPEED.write(window.settings, "warp")
    assert _wheel_x(window, step=1, angle_y=120) == pytest.approx(10 / 1.2)
