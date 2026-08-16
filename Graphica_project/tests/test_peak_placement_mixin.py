# tests/test_peak_placement_mixin.py
"""gui/mixins/peak_placement_mixin.py (項目C-410、グラフクリックによる多峰分離
フィットの初期値配置) に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import pandas as pd
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.dataset import Dataset


class _FakeMplEvent:
    """matplotlibの button_press_event を模した最小オブジェクト。"""
    def __init__(self, inaxes, xdata, ydata, button=1):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = ydata
        self.button = button


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
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


# --- モード切り替え・排他制御 ---

def test_toggle_peak_placement_mode_on_turns_off_cursor_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_action.setChecked(True)
    window.cursor_mode_enabled = True

    window._toggle_peak_placement_mode(True)

    assert window.cursor_action.isChecked() is False
    assert window.cursor_mode_enabled is False
    assert window.peak_placement_mode_enabled is True


def test_toggle_peak_placement_mode_on_turns_off_annotation_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_action.setChecked(True)
    window.annotation_mode_enabled = True

    window._toggle_peak_placement_mode(True)

    assert window.annotation_action.isChecked() is False
    assert window.annotation_mode_enabled is False


def test_toggle_peak_placement_mode_on_turns_off_range_select_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.range_select_action.setChecked(True)
    window.range_select_mode_enabled = True

    window._toggle_peak_placement_mode(True)

    assert window.range_select_action.isChecked() is False
    assert window.range_select_mode_enabled is False


def test_toggle_peak_placement_mode_on_turns_off_layout_edit_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.layout_edit_action.setChecked(True)
    window.layout_edit_mode_enabled = True

    window._toggle_peak_placement_mode(True)

    assert window.layout_edit_action.isChecked() is False
    assert window.layout_edit_mode_enabled is False


def test_toggle_cursor_mode_on_turns_off_peak_placement_mode(tmp_path, monkeypatch):
    """逆方向: ピーク配置モードが有効な状態でデータカーソルをONにすると、
    ピーク配置モードがOFFになること(双方向の排他制御)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.peak_placement_action.setChecked(True)
    window.peak_placement_mode_enabled = True

    window._toggle_cursor_mode(True)

    assert window.peak_placement_action.isChecked() is False
    assert window.peak_placement_mode_enabled is False


def test_toggle_annotation_mode_on_turns_off_peak_placement_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.peak_placement_action.setChecked(True)
    window.peak_placement_mode_enabled = True

    window._toggle_annotation_mode(True)

    assert window.peak_placement_action.isChecked() is False
    assert window.peak_placement_mode_enabled is False


def test_toggle_range_select_mode_on_turns_off_peak_placement_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.peak_placement_action.setChecked(True)
    window.peak_placement_mode_enabled = True

    window._toggle_range_select_mode(True)

    assert window.peak_placement_action.isChecked() is False
    assert window.peak_placement_mode_enabled is False


def test_toggle_layout_edit_mode_on_turns_off_peak_placement_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.peak_placement_action.setChecked(True)
    window.peak_placement_mode_enabled = True

    window._toggle_layout_edit_mode(True)

    assert window.peak_placement_action.isChecked() is False
    assert window.peak_placement_mode_enabled is False


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
