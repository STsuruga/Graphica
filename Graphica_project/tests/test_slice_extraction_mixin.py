# tests/test_slice_extraction_mixin.py
"""gui/mixins/slice_extraction_mixin.py (項目C-511、2Dマップからのドラッグに
よる1Dスライス抽出) に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import numpy as np
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


def _add_2d_dataset(window, select=False, coef_x=2.0, coef_y=3.0, **kwargs):
    """z = coef_x*x + coef_y*y の既知の平面を持つ規則格子の2Dデータセットを追加する
    (extract_slice()の結果を厳密値で検証できるようにするため)。"""
    xs, ys = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0], [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    x, y, z = [], [], []
    for yi in ys:
        for xi in xs:
            x.append(xi)
            y.append(yi)
            z.append(coef_x * xi + coef_y * yi)
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    ds = Dataset(
        name="heatmap", df=df, x_col_name='x', y_col_name='y',
        data_kind='2d_grid', z_col_name='z', **kwargs,
    )
    window._add_dataset(ds, select=select)
    return ds


def _select_dataset(window, ds):
    item = window._get_dataset_tree_item(ds)
    assert item is not None, "データセットに対応するツリー項目が見つかりません"
    window.ui.dataset_list_widget.setCurrentItem(item)


# --- モード切り替え・相互排他制御(他5モードとの双方向) ---

def test_toggle_slice_extraction_mode_on_turns_off_cursor_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_action.setChecked(True)
    window.cursor_mode_enabled = True

    window._toggle_slice_extraction_mode(True)

    assert window.cursor_action.isChecked() is False
    assert window.cursor_mode_enabled is False
    assert window.slice_extraction_mode_enabled is True


def test_toggle_slice_extraction_mode_on_turns_off_annotation_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_action.setChecked(True)
    window.annotation_mode_enabled = True

    window._toggle_slice_extraction_mode(True)

    assert window.annotation_action.isChecked() is False
    assert window.annotation_mode_enabled is False


def test_toggle_slice_extraction_mode_on_turns_off_range_select_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.range_select_action.setChecked(True)
    window.range_select_mode_enabled = True

    window._toggle_slice_extraction_mode(True)

    assert window.range_select_action.isChecked() is False
    assert window.range_select_mode_enabled is False


def test_toggle_slice_extraction_mode_on_turns_off_layout_edit_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.layout_edit_action.setChecked(True)
    window.layout_edit_mode_enabled = True

    window._toggle_slice_extraction_mode(True)

    assert window.layout_edit_action.isChecked() is False
    assert window.layout_edit_mode_enabled is False


def test_toggle_slice_extraction_mode_on_turns_off_peak_placement_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.peak_placement_action.setChecked(True)
    window.peak_placement_mode_enabled = True

    window._toggle_slice_extraction_mode(True)

    assert window.peak_placement_action.isChecked() is False
    assert window.peak_placement_mode_enabled is False


def test_toggle_cursor_mode_on_turns_off_slice_extraction_mode(tmp_path, monkeypatch):
    """逆方向: スライス抽出モードが有効な状態で他モードをONにすると、
    スライス抽出モードがOFFになること(双方向の排他制御)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.slice_extraction_action.setChecked(True)
    window.slice_extraction_mode_enabled = True

    window._toggle_cursor_mode(True)

    assert window.slice_extraction_action.isChecked() is False
    assert window.slice_extraction_mode_enabled is False


def test_toggle_annotation_mode_on_turns_off_slice_extraction_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.slice_extraction_action.setChecked(True)
    window.slice_extraction_mode_enabled = True

    window._toggle_annotation_mode(True)

    assert window.slice_extraction_action.isChecked() is False
    assert window.slice_extraction_mode_enabled is False


def test_toggle_range_select_mode_on_turns_off_slice_extraction_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.slice_extraction_action.setChecked(True)
    window.slice_extraction_mode_enabled = True

    window._toggle_range_select_mode(True)

    assert window.slice_extraction_action.isChecked() is False
    assert window.slice_extraction_mode_enabled is False


def test_toggle_layout_edit_mode_on_turns_off_slice_extraction_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.slice_extraction_action.setChecked(True)
    window.slice_extraction_mode_enabled = True

    window._toggle_layout_edit_mode(True)

    assert window.slice_extraction_action.isChecked() is False
    assert window.slice_extraction_mode_enabled is False


def test_toggle_peak_placement_mode_on_turns_off_slice_extraction_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.slice_extraction_action.setChecked(True)
    window.slice_extraction_mode_enabled = True

    window._toggle_peak_placement_mode(True)

    assert window.slice_extraction_action.isChecked() is False
    assert window.slice_extraction_mode_enabled is False


def test_toggle_slice_extraction_mode_off_disconnects_and_clears_state(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._toggle_slice_extraction_mode(True)
    assert window._slice_extraction_press_cid is not None
    assert window._slice_extraction_motion_cid is not None
    assert window._slice_extraction_release_cid is not None

    window._toggle_slice_extraction_mode(False)

    assert window._slice_extraction_press_cid is None
    assert window._slice_extraction_motion_cid is None
    assert window._slice_extraction_release_cid is None
    assert window._slice_extraction_axes is None
    assert window._slice_extraction_start is None


# --- press / motion / release ---

def test_press_ignored_when_mode_disabled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)
    ax = window.all_axes[0]

    window._on_slice_extraction_press(_FakeMplEvent(ax, 1.0, 1.0))

    assert window._slice_extraction_axes is None


def test_press_ignored_for_non_left_button(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]

    window._on_slice_extraction_press(_FakeMplEvent(ax, 1.0, 1.0, button=2))

    assert window._slice_extraction_axes is None


def test_press_stores_start_position(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]

    window._on_slice_extraction_press(_FakeMplEvent(ax, 1.5, 2.5))

    assert window._slice_extraction_axes is ax
    assert window._slice_extraction_start == (1.5, 2.5)


def test_motion_draws_preview_line(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    window._on_slice_extraction_press(_FakeMplEvent(ax, 1.0, 1.0))

    window._on_slice_extraction_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert window._slice_extraction_preview_artist is not None
    assert window._slice_extraction_preview_artist in ax.lines


def test_motion_replaces_previous_preview_not_accumulates(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    window._on_slice_extraction_press(_FakeMplEvent(ax, 1.0, 1.0))
    n_lines_before = len(ax.lines)

    window._on_slice_extraction_motion(_FakeMplEvent(ax, 2.0, 1.0))
    window._on_slice_extraction_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert len(ax.lines) == n_lines_before + 1


def test_motion_ignored_when_not_dragging(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]

    window._on_slice_extraction_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert window._slice_extraction_preview_artist is None


def test_release_click_without_drag_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_2d_dataset(window)
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    n_datasets_before = len(window.project.datasets)

    window._on_slice_extraction_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_slice_extraction_release(_FakeMplEvent(ax, 1.0, 1.0))

    assert len(window.project.datasets) == n_datasets_before


def test_release_without_current_dataset_shows_info_and_creates_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_2d_dataset(window)  # 追加はするが選択(select=False)はしない
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    n_datasets_before = len(window.project.datasets)

    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_slice_extraction_press(_FakeMplEvent(ax, 0.0, 5.0))
    window._on_slice_extraction_release(_FakeMplEvent(ax, 10.0, 5.0))

    assert len(window.project.datasets) == n_datasets_before
    assert len(info_calls) == 1


def test_release_with_non_2d_current_dataset_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)  # 通常の1Dデータセット
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    n_datasets_before = len(window.project.datasets)

    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_slice_extraction_press(_FakeMplEvent(ax, 0.0, 1.0))
    window._on_slice_extraction_release(_FakeMplEvent(ax, 3.0, 1.0))

    assert len(window.project.datasets) == n_datasets_before
    assert len(info_calls) == 1


def test_release_on_different_axes_than_current_dataset_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_rows_spinbox.setValue(1)
    window.subplot_cols_spinbox.setValue(2)
    ds = _add_2d_dataset(window, subplot_target=0)
    other_ds = _add_dataset(window, subplot_target=1)
    window._update_plot()
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True

    assert len(window.all_axes) == 2
    other_ax = window.all_axes[1]
    n_datasets_before = len(window.project.datasets)
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_slice_extraction_press(_FakeMplEvent(other_ax, 1.0, 0.0))
    window._on_slice_extraction_release(_FakeMplEvent(other_ax, 3.0, 0.0))

    assert len(window.project.datasets) == n_datasets_before
    assert len(info_calls) == 1


def test_release_creates_horizontal_slice_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_2d_dataset(window, coef_x=2.0, coef_y=3.0)
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    n_datasets_before = len(window.project.datasets)

    window._on_slice_extraction_press(_FakeMplEvent(ax, 0.0, 4.0))
    window._on_slice_extraction_release(_FakeMplEvent(ax, 10.0, 4.0))

    assert len(window.project.datasets) == n_datasets_before + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == f"Slice ({ds.name})"
    assert new_ds.provenance is not None
    assert new_ds.provenance['operation'] == '2d_slice'
    assert new_ds.provenance['params']['axis_kind'] == 'x'
    assert new_ds.provenance['source_dataset_ids'] == [ds.dataset_id]
    # z = 2x + 3*4 = 2x + 12 のはず
    np.testing.assert_allclose(new_ds.y_data, 2.0 * new_ds.x_data + 12.0, atol=1e-6)


def test_release_creates_vertical_slice_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_2d_dataset(window, coef_x=2.0, coef_y=3.0)
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]

    window._on_slice_extraction_press(_FakeMplEvent(ax, 4.0, 0.0))
    window._on_slice_extraction_release(_FakeMplEvent(ax, 4.0, 10.0))

    new_ds = window.project.datasets[-1]
    assert new_ds.provenance['params']['axis_kind'] == 'y'
    # z = 2*4 + 3y = 8 + 3y のはず
    np.testing.assert_allclose(new_ds.y_data, 8.0 + 3.0 * new_ds.x_data, atol=1e-6)


def test_release_creates_diagonal_slice_dataset_with_distance_axis(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_2d_dataset(window, coef_x=1.0, coef_y=1.0)
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]

    window._on_slice_extraction_press(_FakeMplEvent(ax, 0.0, 0.0))
    window._on_slice_extraction_release(_FakeMplEvent(ax, 10.0, 10.0))

    new_ds = window.project.datasets[-1]
    assert new_ds.provenance['params']['axis_kind'] == 'distance'
    assert new_ds.x_data[0] == 0.0


def test_release_clears_preview_artist(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_2d_dataset(window)
    _select_dataset(window, ds)
    window.slice_extraction_mode_enabled = True
    ax = window.all_axes[0]
    window._on_slice_extraction_press(_FakeMplEvent(ax, 0.0, 4.0))
    window._on_slice_extraction_motion(_FakeMplEvent(ax, 5.0, 4.0))
    assert window._slice_extraction_preview_artist is not None

    window._on_slice_extraction_release(_FakeMplEvent(ax, 10.0, 4.0))

    assert window._slice_extraction_preview_artist is None
