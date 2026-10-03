# tests/test_peak_placement_mixin.py
"""gui/mixins/peak_placement_mixin.py (項目C-410、グラフクリックによる多峰分離
フィットの初期値配置) に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import pandas as pd
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.gui.main_window import PlotterApp
from graphica.core.dataset import Dataset


class _FakeMplEvent:
    """matplotlibの button_press_event を模した最小オブジェクト。"""
    def __init__(self, inaxes, xdata, ydata, button=1):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = ydata
        self.button = button
        # 本物のイベントと同じく、Figure のピクセル座標も持つ(モードは軸の外へのはみ出しや凡例の判定に使う)
        if inaxes is not None and xdata is not None and ydata is not None:
            self.x, self.y = inaxes.transData.transform((xdata, ydata))
        else:
            self.x = self.y = None


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _add_dataset(window, select=False, **kwargs):
    ds = Dataset(
        name="d", df=pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 4.0], "y": [0.0, 1.0, 4.0, 9.0, 16.0]}),
        x_col_name="x", y_col_name="y", **kwargs,
    )
    window._add_dataset(ds, select=select)
    return ds


# --- モード切り替え(ほかのモードとの排他は test_mouse_modes.py) ---

def test_toggle_peak_placement_mode_off_disconnects(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._toggle_peak_placement_mode(True)
    assert window._peak_placement_press_cid is not None

    window._toggle_peak_placement_mode(False)

    assert window._peak_placement_press_cid is None


# --- クリックでの追加/削除 ---

def test_press_ignored_when_mode_disabled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    ax = window.all_axes[0]

    window._on_peak_placement_press(_FakeMplEvent(ax, 1.0, 1.0))

    assert window._pending_peak_guesses == []


def test_left_click_adds_pending_guess(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.peak_placement_mode_enabled = True
    ax = window.all_axes[0]

    window._on_peak_placement_press(_FakeMplEvent(ax, 1.5, 3.0))

    assert len(window._pending_peak_guesses) == 1
    guess = window._pending_peak_guesses[0]
    assert guess['center'] == 1.5
    assert guess['height'] == 3.0
    assert guess['width'] > 0
    assert len(window._pending_peak_markers) == 1


def test_left_click_ignored_outside_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.peak_placement_mode_enabled = True

    window._on_peak_placement_press(_FakeMplEvent(None, None, None))

    assert window._pending_peak_guesses == []


def test_multiple_clicks_accumulate_guesses(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.peak_placement_mode_enabled = True
    ax = window.all_axes[0]

    window._on_peak_placement_press(_FakeMplEvent(ax, 1.0, 2.0))
    window._on_peak_placement_press(_FakeMplEvent(ax, 3.0, 4.0))

    assert len(window._pending_peak_guesses) == 2
    assert [g['center'] for g in window._pending_peak_guesses] == [1.0, 3.0]


def test_right_click_removes_nearest_guess(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.peak_placement_mode_enabled = True
    ax = window.all_axes[0]

    window._on_peak_placement_press(_FakeMplEvent(ax, 1.0, 2.0))
    window._on_peak_placement_press(_FakeMplEvent(ax, 3.0, 4.0))
    assert len(window._pending_peak_guesses) == 2

    # 1.0付近をクリックした点に最も近い位置で右クリック
    window._on_peak_placement_press(_FakeMplEvent(ax, 1.05, 2.05, button=3))

    assert len(window._pending_peak_guesses) == 1
    assert window._pending_peak_guesses[0]['center'] == 3.0
    assert len(window._pending_peak_markers) == 1


def test_right_click_with_no_pending_guesses_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.peak_placement_mode_enabled = True
    ax = window.all_axes[0]

    window._on_peak_placement_press(_FakeMplEvent(ax, 1.0, 2.0, button=3))

    assert window._pending_peak_guesses == []


# --- クリア ---

def test_clear_pending_peak_guesses_removes_markers_and_guesses(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.peak_placement_mode_enabled = True
    ax = window.all_axes[0]
    window._on_peak_placement_press(_FakeMplEvent(ax, 1.0, 2.0))
    window._on_peak_placement_press(_FakeMplEvent(ax, 3.0, 4.0))
    assert len(window._pending_peak_guesses) == 2

    window._clear_pending_peak_guesses()

    assert window._pending_peak_guesses == []
    assert window._pending_peak_markers == []
