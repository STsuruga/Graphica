# tests/test_region_highlight_mixin.py
"""gui/mixins/region_highlight_mixin.py (項目C-701、領域ハイライト) に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import pandas as pd
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.dataset import Dataset


class _FakeMplEvent:
    """matplotlibの button_press_event / motion_notify_event / button_release_event
    を模した最小オブジェクト。"""
    def __init__(self, inaxes, xdata, ydata, button=1):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = ydata
        self.button = button


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る"""
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

def test_toggle_region_highlight_mode_on_turns_off_cursor_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_action.setChecked(True)
    window.cursor_mode_enabled = True

    window._toggle_region_highlight_mode(True)

    assert window.cursor_action.isChecked() is False
    assert window.cursor_mode_enabled is False
    assert window.region_highlight_mode_enabled is True


def test_toggle_region_highlight_mode_on_turns_off_annotation_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_action.setChecked(True)
    window.annotation_mode_enabled = True

    window._toggle_region_highlight_mode(True)

    assert window.annotation_action.isChecked() is False
    assert window.annotation_mode_enabled is False


def test_toggle_region_highlight_mode_on_turns_off_range_select_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.range_select_action.setChecked(True)
    window.range_select_mode_enabled = True

    window._toggle_region_highlight_mode(True)

    assert window.range_select_action.isChecked() is False
    assert window.range_select_mode_enabled is False


def test_toggle_other_modes_on_turn_off_region_highlight_mode(tmp_path, monkeypatch):
    """逆方向: 領域ハイライトモードが有効な状態で他のモードをONにすると、
    領域ハイライトモードがOFFになること(双方向の排他制御)。"""
    for toggle_name in (
        '_toggle_cursor_mode', '_toggle_annotation_mode', '_toggle_range_select_mode',
        '_toggle_peak_placement_mode', '_toggle_slice_extraction_mode', '_toggle_layout_edit_mode',
    ):
        window = _make_isolated_plotter_app(tmp_path, monkeypatch)
        window.region_highlight_action.setChecked(True)
        window.region_highlight_mode_enabled = True

        getattr(window, toggle_name)(True)

        assert window.region_highlight_action.isChecked() is False, toggle_name
        assert window.region_highlight_mode_enabled is False, toggle_name


def test_toggle_region_highlight_mode_off_disconnects_and_clears_state(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._toggle_region_highlight_mode(True)
    assert window._region_highlight_press_cid is not None

    window._toggle_region_highlight_mode(False)

    assert window._region_highlight_press_cid is None
    assert window._region_highlight_motion_cid is None
    assert window._region_highlight_release_cid is None
    assert window._region_highlight_axes is None
    assert window._region_highlight_start is None


# --- press / motion ---

def test_press_ignored_when_mode_disabled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))

    assert window._region_highlight_axes is None


def test_press_stores_start_position(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 1.5, 2.5))

    assert window._region_highlight_axes is ax
    assert window._region_highlight_start == (1.5, 2.5)


def test_motion_below_threshold_draws_no_preview(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]
    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))

    window._on_region_highlight_motion(_FakeMplEvent(ax, 1.0001, 1.0001))

    assert window._region_highlight_preview_artist is None


def test_motion_horizontal_drag_draws_preview_rectangle(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]
    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))

    window._on_region_highlight_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert window._region_highlight_preview_artist is not None
    assert window._region_highlight_preview_artist in ax.patches


def test_motion_replaces_previous_preview_not_accumulates(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]
    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))

    window._on_region_highlight_motion(_FakeMplEvent(ax, 2.0, 1.0))
    window._on_region_highlight_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert sum(1 for _ in ax.patches) == 1


# --- release: 縦帯/横帯の追加 ---

def test_release_click_without_drag_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 1.0, 1.0))

    settings = window.project.all_plot_settings[ds.subplot_target]
    assert settings.get('annotations', []) == []


def test_release_horizontal_drag_adds_vspan(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 3.0, 1.0))

    settings = window.project.all_plot_settings[ds.subplot_target]
    annotations = settings.get('annotations', [])
    assert len(annotations) == 1
    assert annotations[0]['type'] == 'vspan'
    assert annotations[0]['range'] == (1.0, 3.0)


def test_release_vertical_drag_adds_hspan(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 1.0, 12.0))

    settings = window.project.all_plot_settings[ds.subplot_target]
    annotations = settings.get('annotations', [])
    assert len(annotations) == 1
    assert annotations[0]['type'] == 'hspan'
    assert annotations[0]['range'] == (1.0, 12.0)


def test_release_range_is_sorted_regardless_of_drag_direction(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 3.0, 1.0))  # 右から左へドラッグ
    window._on_region_highlight_release(_FakeMplEvent(ax, 1.0, 1.0))

    settings = window.project.all_plot_settings[ds.subplot_target]
    assert settings['annotations'][0]['range'] == (1.0, 3.0)


def test_release_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]

    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 3.0, 1.0))
    settings = window.project.all_plot_settings[ds.subplot_target]
    assert len(settings.get('annotations', [])) == 1

    window.undo_stack.undo()
    assert window.project.all_plot_settings[ds.subplot_target].get('annotations', []) == []

    window.undo_stack.redo()
    assert len(window.project.all_plot_settings[ds.subplot_target].get('annotations', [])) == 1


def test_release_on_different_axes_than_press_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_rows_spinbox.setValue(1)
    window.subplot_cols_spinbox.setValue(2)
    ds = _add_dataset(window, subplot_target=0)
    _add_dataset(window, subplot_target=1)
    window._update_plot()
    window.region_highlight_mode_enabled = True

    ax0, ax1 = window.all_axes[0], window.all_axes[1]
    window._on_region_highlight_press(_FakeMplEvent(ax0, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax1, 3.0, 1.0))

    assert window.project.all_plot_settings[0].get('annotations', []) == []
    assert window.project.all_plot_settings[1].get('annotations', []) == []


# --- 右クリックでの削除 ---

def test_right_click_inside_vspan_deletes_after_confirmation(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]
    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 3.0, 1.0))
    assert len(window.project.all_plot_settings[ds.subplot_target]['annotations']) == 1

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window._on_region_highlight_press(_FakeMplEvent(ax, 2.0, 5.0, button=3))  # 帯の内側

    assert window.project.all_plot_settings[ds.subplot_target].get('annotations', []) == []


def test_right_click_outside_vspan_does_not_delete(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]
    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 3.0, 1.0))

    calls = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: calls.append(a) or QMessageBox.StandardButton.Yes))
    window._on_region_highlight_press(_FakeMplEvent(ax, 10.0, 5.0, button=3))  # 帯の外側

    assert len(window.project.all_plot_settings[ds.subplot_target]['annotations']) == 1
    assert calls == []


def test_right_click_delete_declined_keeps_region(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.region_highlight_mode_enabled = True
    ax = window.all_axes[0]
    window._on_region_highlight_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_region_highlight_release(_FakeMplEvent(ax, 3.0, 1.0))

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    window._on_region_highlight_press(_FakeMplEvent(ax, 2.0, 5.0, button=3))

    assert len(window.project.all_plot_settings[ds.subplot_target]['annotations']) == 1
