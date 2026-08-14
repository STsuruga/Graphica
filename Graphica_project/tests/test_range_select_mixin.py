# tests/test_range_select_mixin.py
"""gui/mixins/range_select_mixin.py (項目C-909、グラフ上での範囲選択→マスク) に対するテスト。"""
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
    """
    window._add_dataset() を経由してデータセットを追加する。
    project.datasets.append() + _update_plot() だけでは、ツリーウィジェット側の
    QTreeWidgetItem が作られず _get_current_dataset()/_get_dataset_tree_item() が
    常にNoneを返す(この不具合を直接踏んで、QMessageBox.informationの
    モック忘れと同じヘッドレス環境でのハングを一度引き起こした)。
    """
    ds = Dataset(
        name="d", df=pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 4.0], "y": [0.0, 1.0, 4.0, 9.0, 16.0]}),
        x_col_name="x", y_col_name="y", **kwargs,
    )
    window._add_dataset(ds, select=select)
    return ds


def _select_dataset(window, ds):
    item = window._get_dataset_tree_item(ds)
    assert item is not None, "データセットに対応するツリー項目が見つかりません"
    window.ui.dataset_list_widget.setCurrentItem(item)


# --- モード切り替え・排他制御 ---

def test_toggle_range_select_mode_on_turns_off_cursor_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_action.setChecked(True)
    window.cursor_mode_enabled = True

    window._toggle_range_select_mode(True)

    assert window.cursor_action.isChecked() is False
    assert window.cursor_mode_enabled is False
    assert window.range_select_mode_enabled is True


def test_toggle_range_select_mode_on_turns_off_annotation_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_action.setChecked(True)
    window.annotation_mode_enabled = True

    window._toggle_range_select_mode(True)

    assert window.annotation_action.isChecked() is False
    assert window.annotation_mode_enabled is False


def test_toggle_range_select_mode_on_turns_off_layout_edit_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.layout_edit_action.setChecked(True)
    window.layout_edit_mode_enabled = True

    window._toggle_range_select_mode(True)

    assert window.layout_edit_action.isChecked() is False
    assert window.layout_edit_mode_enabled is False


def test_toggle_cursor_mode_on_turns_off_range_select_mode(tmp_path, monkeypatch):
    """逆方向: 範囲選択モードが有効な状態でデータカーソルをONにすると、
    範囲選択モードがOFFになること(双方向の排他制御)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.range_select_action.setChecked(True)
    window.range_select_mode_enabled = True

    window._toggle_cursor_mode(True)

    assert window.range_select_action.isChecked() is False
    assert window.range_select_mode_enabled is False


def test_toggle_annotation_mode_on_turns_off_range_select_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.range_select_action.setChecked(True)
    window.range_select_mode_enabled = True

    window._toggle_annotation_mode(True)

    assert window.range_select_action.isChecked() is False
    assert window.range_select_mode_enabled is False


def test_toggle_layout_edit_mode_on_turns_off_range_select_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.range_select_action.setChecked(True)
    window.range_select_mode_enabled = True

    window._toggle_layout_edit_mode(True)

    assert window.range_select_action.isChecked() is False
    assert window.range_select_mode_enabled is False


def test_toggle_range_select_mode_off_disconnects_and_clears_state(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._toggle_range_select_mode(True)
    assert window._range_select_press_cid is not None

    window._toggle_range_select_mode(False)

    assert window._range_select_press_cid is None
    assert window._range_select_motion_cid is None
    assert window._range_select_release_cid is None
    assert window._range_select_axes is None
    assert window._range_select_start_x is None


# --- press / motion / release ---

def test_press_ignored_when_mode_disabled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 1.0))

    assert window._range_select_axes is None


def test_press_ignored_for_non_left_button(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 1.0, button=2))

    assert window._range_select_axes is None


def test_press_stores_start_position(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 1.5, 2.5))

    assert window._range_select_axes is ax
    assert window._range_select_start_x == 1.5


def test_motion_draws_preview_rectangle(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]
    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 1.0))

    window._on_range_select_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert window._range_select_preview_artist is not None
    assert window._range_select_preview_artist in ax.patches


def test_motion_replaces_previous_preview_not_accumulates(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]
    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 1.0))

    window._on_range_select_motion(_FakeMplEvent(ax, 2.0, 1.0))
    window._on_range_select_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert sum(1 for p in ax.patches) == 1


def test_motion_ignored_when_not_dragging(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_motion(_FakeMplEvent(ax, 3.0, 1.0))

    assert window._range_select_preview_artist is None


# --- release / マスク適用 ---

def test_release_without_current_dataset_shows_info_and_masks_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_range_select_release(_FakeMplEvent(ax, 3.0, 1.0))

    assert ds.masked_row_indices == []
    assert len(info_calls) == 1


def test_release_click_without_drag_is_noop(tmp_path, monkeypatch):
    """開始点と終了点が同じ(ドラッグなしの単純クリック)場合は何もしない。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    _select_dataset(window, ds)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 1.0))
    window._on_range_select_release(_FakeMplEvent(ax, 1.0, 1.0))

    assert ds.masked_row_indices == []


def test_release_masks_points_within_dragged_range(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)  # x: 0,1,2,3,4
    _select_dataset(window, ds)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 0.0))
    window._on_range_select_release(_FakeMplEvent(ax, 3.0, 0.0))

    assert ds.masked_row_indices == [1, 2, 3]


def test_release_mask_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    _select_dataset(window, ds)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 1.0, 0.0))
    window._on_range_select_release(_FakeMplEvent(ax, 3.0, 0.0))
    assert ds.masked_row_indices == [1, 2, 3]

    window.undo_stack.undo()
    assert ds.masked_row_indices == []


def test_release_adds_to_existing_mask_rather_than_replacing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    ds.masked_row_indices = [0]
    _select_dataset(window, ds)
    window.range_select_mode_enabled = True
    ax = window.all_axes[0]

    window._on_range_select_press(_FakeMplEvent(ax, 3.0, 0.0))
    window._on_range_select_release(_FakeMplEvent(ax, 4.0, 0.0))

    assert ds.masked_row_indices == [0, 3, 4]


def test_release_on_different_axes_than_current_dataset_shows_info(tmp_path, monkeypatch):
    """カレントデータセットが描画されていないサブプロット上でドラッグした場合、
    誤爆を避けて何もマスクせず案内を出す。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    # 1行2列のグリッドにしてから、それぞれ別のサブプロットへデータセットを追加する
    # (tests/test_main_window.py の多サブプロットテストと同じ、実UIのスピンボックス
    # 経由でレイアウトを変更する確立済みパターン)。
    window.subplot_rows_spinbox.setValue(1)
    window.subplot_cols_spinbox.setValue(2)
    ds = _add_dataset(window, subplot_target=0)
    other_ds = _add_dataset(window, subplot_target=1)
    window._update_plot()
    _select_dataset(window, ds)  # dsを選択中だが、これから軸1側でドラッグする
    window.range_select_mode_enabled = True

    assert len(window.all_axes) == 2
    other_ax = window.all_axes[1]
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_range_select_press(_FakeMplEvent(other_ax, 1.0, 0.0))
    window._on_range_select_release(_FakeMplEvent(other_ax, 3.0, 0.0))

    assert ds.masked_row_indices == []
    assert other_ds.masked_row_indices == []
    assert len(info_calls) == 1
