# tests/test_cursor_mixin.py
"""
gui/mixins/cursor_mixin.py (データカーソル機能、項目のクリックで座標を読み取る
「データカーソル」モードおよび常時有効なグラフ要素の直接クリック選択(項目35))
に対するテスト。

tests/test_main_window.py の test_turning_off_cursor_mode_does_not_disable_click_to_select
はこのファイルには含めない(既に別ファイルにある回帰テスト)。それ以外の
_toggle_cursor_mode / _on_mouse_move / _on_element_pick / _on_pick の挙動を
このファイルでカバーする。
"""
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from gui.canvas import LTTB_DOWNSAMPLE_THRESHOLD
from gui.data_editor import DataEditorDialog
from core.dataset import Dataset


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


def _add_dataset(window, plot_type="Line", **kwargs):
    ds = Dataset(
        name="d", df=pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}),
        x_col_name="x", y_col_name="y", plot_type=plot_type, **kwargs,
    )
    window.project.datasets.append(ds)
    window._update_plot()
    return ds


# --------------------------------------------------------------------
# _toggle_cursor_mode
# --------------------------------------------------------------------

def test_toggle_cursor_mode_on_turns_off_annotation_mode_first(tmp_path, monkeypatch):
    """データカーソルと注釈モードは排他: カーソルONで注釈モードが自動的にOFFになる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_action.setChecked(True)
    window.annotation_mode_enabled = True

    window._toggle_cursor_mode(True)

    assert window.annotation_action.isChecked() is False
    assert window.annotation_mode_enabled is False
    assert window.cursor_mode_enabled is True


def test_toggle_cursor_mode_on_sets_picker_and_connects_pick_event(tmp_path, monkeypatch):
    """カーソルON時、既存の全Line/Collectionにset_picker(5)が設定され、pick_eventが接続される"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    line = window.canvas.all_axes[0].get_lines()[0]

    window._toggle_cursor_mode(True)

    assert line.get_picker() == 5
    assert window.cursor_connection_id is not None
    assert window.coordinate_label.text() == "クリックしてデータを選択"


def test_toggle_cursor_mode_on_swallows_set_picker_attribute_error(tmp_path, monkeypatch, caplog):
    """
    一部のArtistがset_pickerをサポートしない場合(AttributeError)でも、
    モードON処理全体は落ちずに続行すること。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    line = window.canvas.all_axes[0].get_lines()[0]

    def _raise_attribute_error(*args, **kwargs):
        raise AttributeError("set_picker not supported by this artist")

    monkeypatch.setattr(line, "set_picker", _raise_attribute_error)

    with caplog.at_level("WARNING", logger="gui.mixins.cursor_mixin"):
        window._toggle_cursor_mode(True)  # 例外が伝播しないこと

    assert window.cursor_connection_id is not None


def test_toggle_cursor_mode_off_disconnects_and_clears_pending_annotation(tmp_path, monkeypatch):
    """カーソルOFF時、pick_eventの接続が切断され、表示中の注釈があれば削除される"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window._toggle_cursor_mode(True)

    ax = window.canvas.all_axes[0]
    fake_annotation = ax.annotate("dummy", xy=(1, 1))
    window.cursor_annotation = fake_annotation

    window._toggle_cursor_mode(False)

    assert window.cursor_connection_id is None
    assert window.cursor_annotation is None
    assert fake_annotation.axes is None  # remove()済み
    assert window.coordinate_label.text() == "X= ---, Y= ---"


def test_toggle_cursor_mode_off_without_pending_annotation_is_noop(tmp_path, monkeypatch):
    """表示中の注釈が無い状態でOFFにしても何も起きない(Noneチェックの分岐)"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._toggle_cursor_mode(True)
    assert window.cursor_annotation is None

    window._toggle_cursor_mode(False)

    assert window.cursor_annotation is None
    assert window.cursor_connection_id is None


# --------------------------------------------------------------------
# _on_mouse_move
# --------------------------------------------------------------------

def test_on_mouse_move_updates_label_with_primary_axis_prefix(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]

    window._on_mouse_move(SimpleNamespace(inaxes=ax, xdata=1.23456, ydata=9.8765))

    assert window.coordinate_label.text() == "P1: X= 1.235, Y= 9.877"


def test_on_mouse_move_updates_label_with_secondary_axis_prefix(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, use_secondary_y=True)
    sec_ax = window.all_secondary_axes[0]
    assert sec_ax is not None

    window._on_mouse_move(SimpleNamespace(inaxes=sec_ax, xdata=2.0, ydata=3.0))

    assert window.coordinate_label.text() == "P1(Y2): X= 2, Y= 3"


def test_on_mouse_move_updates_label_with_unknown_axis_prefix(tmp_path, monkeypatch):
    """all_axes/all_secondary_axesのどちらにも属さないAxesの場合は '?: ' 表示になる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    stray_fig, stray_ax = plt.subplots()
    try:
        window._on_mouse_move(SimpleNamespace(inaxes=stray_ax, xdata=5.0, ydata=6.0))
        assert window.coordinate_label.text() == "?: X= 5, Y= 6"
    finally:
        plt.close(stray_fig)


def test_on_mouse_move_outside_axes_resets_label_when_cursor_mode_off(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_mode_enabled = False
    window.coordinate_label.setText("P1: X= 1, Y= 2")

    window._on_mouse_move(SimpleNamespace(inaxes=None, xdata=None, ydata=None))

    assert window.coordinate_label.text() == "X= ---, Y= ---"


def test_on_mouse_move_outside_axes_keeps_label_when_cursor_mode_on(tmp_path, monkeypatch):
    """カーソルモードON中にAxes外へ出ても、最後の座標表示を保持し続ける"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_mode_enabled = True
    window.coordinate_label.setText("P1: X= 1, Y= 2")

    window._on_mouse_move(SimpleNamespace(inaxes=None, xdata=None, ydata=None))

    assert window.coordinate_label.text() == "P1: X= 1, Y= 2"


# --------------------------------------------------------------------
# _on_element_pick (項目35: 常時有効なグラフ要素の直接クリック選択)
# --------------------------------------------------------------------

def test_on_element_pick_ignored_during_annotation_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.ui.dataset_list_widget.setCurrentItem(None)
    window.annotation_mode_enabled = True

    window._on_element_pick(SimpleNamespace(artist=ds.artist))

    assert window.ui.dataset_list_widget.currentItem() is None


def test_on_element_pick_ignored_during_layout_edit_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.ui.dataset_list_widget.setCurrentItem(None)
    window.layout_edit_mode_enabled = True

    window._on_element_pick(SimpleNamespace(artist=ds.artist))

    assert window.ui.dataset_list_widget.currentItem() is None


def test_on_element_pick_title_click_switches_active_axis(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.free_layout_checkbox.setChecked(True)
    window._on_add_free_subplot()  # 2枚構成にする
    assert len(window.all_axes) == 2
    window.active_axis_combo.setCurrentIndex(0)

    window._on_element_pick(SimpleNamespace(artist=window.all_axes[1].title))

    assert window.active_axis_combo.currentIndex() == 1


def test_on_element_pick_title_click_same_axis_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.active_axis_combo.setCurrentIndex(0)

    window._on_element_pick(SimpleNamespace(artist=window.all_axes[0].title))

    assert window.active_axis_combo.currentIndex() == 0


def test_on_element_pick_dataset_line_click_selects_tree_item(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    expected_item = window._get_dataset_tree_item(ds)
    window.ui.dataset_list_widget.setCurrentItem(None)
    assert window.ui.dataset_list_widget.currentItem() is None

    window._on_element_pick(SimpleNamespace(artist=ds.artist))

    assert window.ui.dataset_list_widget.currentItem() is expected_item


def test_on_element_pick_bar_patch_click_selects_tree_item(tmp_path, monkeypatch):
    """Barは単一Artistでなく複数Rectangle(patches)なので、patch単位のクリックで判定される"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Bar")
    assert hasattr(ds.artist, "patches") and len(ds.artist.patches) > 0
    expected_item = window._get_dataset_tree_item(ds)

    window._on_element_pick(SimpleNamespace(artist=ds.artist.patches[0]))

    assert window.ui.dataset_list_widget.currentItem() is expected_item


def test_on_element_pick_unrelated_artist_is_ignored(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    window.ui.dataset_list_widget.setCurrentItem(None)

    window._on_element_pick(SimpleNamespace(artist=object()))  # 例外なく何もしない

    assert window.ui.dataset_list_widget.currentItem() is None


# --------------------------------------------------------------------
# _on_pick (データカーソルの座標読み取り)
# --------------------------------------------------------------------

def test_on_pick_disabled_cursor_mode_is_noop(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window)
    window.cursor_mode_enabled = False

    window._on_pick(SimpleNamespace(
        artist=ds.artist, mouseevent=SimpleNamespace(xdata=2.0, ydata=4.0), ind=[0],
    ))

    assert window.cursor_annotation is None


def test_on_pick_scatter_shows_annotation_at_clicked_point(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Scatter")
    window.cursor_mode_enabled = True

    window._on_pick(SimpleNamespace(
        artist=ds.artist, ind=[1], mouseevent=SimpleNamespace(xdata=2.0, ydata=4.0),
    ))

    assert window.cursor_annotation is not None
    assert "X: 2" in window.cursor_annotation.get_text()
    assert "Y: 4" in window.cursor_annotation.get_text()


def test_on_pick_line_shows_annotation_at_nearest_point(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Line")
    window.cursor_mode_enabled = True

    # (2.0, 4.0) は x=[1,2,3], y=[1,4,9] のうちインデックス1に厳密一致する
    window._on_pick(SimpleNamespace(
        artist=ds.artist, mouseevent=SimpleNamespace(xdata=2.0, ydata=4.0),
    ))

    assert window.cursor_annotation is not None
    assert "X: 2" in window.cursor_annotation.get_text()
    assert "Y: 4" in window.cursor_annotation.get_text()


def test_on_pick_unsupported_artist_is_ignored(tmp_path, monkeypatch):
    """get_offsets/get_xdataどちらも持たないArtistがクリックされた場合は何もしない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_mode_enabled = True

    window._on_pick(SimpleNamespace(
        artist=object(), mouseevent=SimpleNamespace(xdata=0.0, ydata=0.0),
    ))

    assert window.cursor_annotation is None


def test_on_pick_replaces_previous_annotation(tmp_path, monkeypatch):
    """2回目のクリックで、1回目に作られた注釈は削除されて1つだけ残る"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Line")
    window.cursor_mode_enabled = True

    window._on_pick(SimpleNamespace(
        artist=ds.artist, mouseevent=SimpleNamespace(xdata=1.0, ydata=1.0),
    ))
    first_annotation = window.cursor_annotation
    assert first_annotation is not None

    window._on_pick(SimpleNamespace(
        artist=ds.artist, mouseevent=SimpleNamespace(xdata=3.0, ydata=9.0),
    ))
    second_annotation = window.cursor_annotation

    assert second_annotation is not first_annotation
    assert first_annotation.axes is None  # 1つ目はremove()済み
    assert "X: 3" in second_annotation.get_text()


def test_on_pick_highlights_row_in_open_data_editor_dialog(tmp_path, monkeypatch):
    """
    データカーソルでのクリックが、開いているデータエディタの対応する行も
    選択状態にする(データ⇔グラフの双方向ハイライト、逆方向)ことを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Line")
    window.cursor_mode_enabled = True

    dialog = DataEditorDialog(ds, parent=window)
    window.data_editor_dialog = dialog
    try:
        window._on_pick(SimpleNamespace(
            artist=ds.artist, mouseevent=SimpleNamespace(xdata=2.0, ydata=4.0),
        ))

        assert dialog.get_selected_master_indices() == [1]
    finally:
        window.data_editor_dialog = None
        dialog.close()


def test_on_pick_does_not_touch_dialog_showing_a_different_dataset(tmp_path, monkeypatch):
    """開いているデータエディタが別のデータセットを表示中なら、行選択には触れない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Line")
    other_ds = Dataset(
        name="other", df=pd.DataFrame({"x": [10, 20], "y": [30, 40]}),
        x_col_name="x", y_col_name="y",
    )
    window.cursor_mode_enabled = True

    dialog = DataEditorDialog(other_ds, parent=window)
    window.data_editor_dialog = dialog
    try:
        window._on_pick(SimpleNamespace(
            artist=ds.artist, mouseevent=SimpleNamespace(xdata=2.0, ydata=4.0),
        ))

        assert dialog.get_selected_master_indices() == []
    finally:
        window.data_editor_dialog = None
        dialog.close()


# NOTE: gui/mixins/cursor_mixin.py の _on_pick 末尾 (238行目, "except IndexError:
# pass") は、pick_eventで返るindが常にvisible_df基準で描画された同じArtistの
# 範囲内に収まる(コード内コメントの通り)ため、実際のユーザー操作では到達しない
# 防御的分岐であり、意図的にテストを省略する。


def test_on_pick_maps_downsampled_index_back_to_correct_row(tmp_path, monkeypatch):
    """
    項目C-1001(表示用ダウンサンプリング)の回帰テスト: LTTBで間引かれた
    データセットをクリックした場合、pick_eventのindは「間引き後の配列上の
    位置」であって「元のvisible_df上の位置」ではない。
    gui.canvas.MplCanvas.downsample_index_map を経由して正しい元の行に
    変換されないと、間引かれた点をクリックするたびに無関係な行が
    データエディタでハイライトされてしまう(このテストが検出したい不具合)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    n = LTTB_DOWNSAMPLE_THRESHOLD + 5000
    x = np.arange(n, dtype=float)
    y = np.sin(x / 100.0)
    ds = Dataset(
        name="big", df=pd.DataFrame({"x": x, "y": y}),
        x_col_name="x", y_col_name="y", plot_type="Line",
    )
    window.project.datasets.append(ds)
    window._update_plot()

    # ダウンサンプリングが実際に適用されたことの前提確認
    assert ds.dataset_id in window.canvas.downsample_index_map
    index_map = window.canvas.downsample_index_map[ds.dataset_id]
    assert len(index_map) < n

    window.cursor_mode_enabled = True
    dialog = DataEditorDialog(ds, parent=window)
    window.data_editor_dialog = dialog
    try:
        # 間引き後の配列上で3番目の点(ind=3)をクリックしたことにする。
        # artistには間引き後のx/yしか無いため、その値をそのままクリック座標にする。
        rendered_x = ds.artist.get_xdata()
        rendered_y = ds.artist.get_ydata()
        click_ind = 3
        window._on_pick(SimpleNamespace(
            artist=ds.artist,
            mouseevent=SimpleNamespace(xdata=rendered_x[click_ind], ydata=rendered_y[click_ind]),
        ))

        expected_original_row = int(index_map[click_ind])
        assert dialog.get_selected_master_indices() == [expected_original_row]
    finally:
        window.data_editor_dialog = None
        dialog.close()


def test_on_pick_without_downsampling_uses_index_directly(tmp_path, monkeypatch):
    """間引きが適用されていない(閾値以下の)データセットでは、従来通り
    indをそのままvisible_df.indexに使う(downsample_index_mapに現れないため)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add_dataset(window, plot_type="Line")
    assert ds.dataset_id not in window.canvas.downsample_index_map

    window.cursor_mode_enabled = True
    dialog = DataEditorDialog(ds, parent=window)
    window.data_editor_dialog = dialog
    try:
        window._on_pick(SimpleNamespace(
            artist=ds.artist, mouseevent=SimpleNamespace(xdata=2.0, ydata=4.0),
        ))
        assert dialog.get_selected_master_indices() == [1]
    finally:
        window.data_editor_dialog = None
        dialog.close()


# --------------------------------------------------------------------
# マウス操作拡充(項目C-908): ホイールズーム + 中ボタンドラッグパン
# --------------------------------------------------------------------

def test_scroll_zoom_ignored_when_not_over_an_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    xlim_before = ax.get_xlim()

    window._on_scroll_zoom(SimpleNamespace(inaxes=None, xdata=None, ydata=None, button='up'))

    assert ax.get_xlim() == xlim_before


def test_scroll_up_zooms_in_narrowing_the_range(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    window._on_scroll_zoom(SimpleNamespace(inaxes=ax, xdata=5.0, ydata=5.0, button='up'))

    new_xlim = ax.get_xlim()
    assert (new_xlim[1] - new_xlim[0]) < 10  # 範囲が狭まった(ズームイン)


def test_scroll_down_zooms_out_widening_the_range(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    window._on_scroll_zoom(SimpleNamespace(inaxes=ax, xdata=5.0, ydata=5.0, button='down'))

    new_xlim = ax.get_xlim()
    assert (new_xlim[1] - new_xlim[0]) > 10  # 範囲が広がった(ズームアウト)


def test_scroll_zoom_centers_on_cursor_not_axes_midpoint(tmp_path, monkeypatch):
    """カーソル位置がAxesの中心からずれている場合、ズーム後もカーソル位置が
    (中心固定ズームと違い)同じ相対位置に留まることを確認する。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    # カーソル位置 x=8(範囲の右寄り)でズームイン
    window._on_scroll_zoom(SimpleNamespace(inaxes=ax, xdata=8.0, ydata=5.0, button='up'))

    new_xlim = ax.get_xlim()
    # 8はズーム前は範囲の右へ寄っていた(relx = (10-8)/10 = 0.2、
    # つまり右端からの距離が20%)。ズーム後も同じ比率で右端に近いはず。
    new_width = new_xlim[1] - new_xlim[0]
    relx_after = (new_xlim[1] - 8.0) / new_width
    assert relx_after == pytest.approx(0.2, abs=1e-6)


def test_middle_button_press_ignored_for_left_button(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]

    window._on_middle_button_press_pan(SimpleNamespace(button=1, inaxes=ax, xdata=5.0, ydata=5.0))

    assert window._middle_pan_axes is None


def test_middle_button_press_ignored_when_not_over_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")

    window._on_middle_button_press_pan(SimpleNamespace(button=2, inaxes=None, xdata=None, ydata=None))

    assert window._middle_pan_axes is None


def test_middle_button_press_stores_pan_state(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    window._on_middle_button_press_pan(SimpleNamespace(button=2, inaxes=ax, xdata=3.0, ydata=4.0))

    assert window._middle_pan_axes is ax
    assert window._middle_pan_start_data == (3.0, 4.0)
    assert window._middle_pan_start_xlim == (0, 10)
    assert window._middle_pan_start_ylim == (0, 10)


def test_middle_button_motion_shifts_axes_by_drag_delta(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    window._on_middle_button_press_pan(SimpleNamespace(button=2, inaxes=ax, xdata=5.0, ydata=5.0))
    # カーソルが左に2、下に1動いた(=データがまだそのxlim/ylimのままなら
    # event.xdata/ydataはそれぞれ3.0/4.0になる)と仮定してモーションイベントを発火
    window._on_middle_button_motion_pan(SimpleNamespace(inaxes=ax, xdata=3.0, ydata=4.0))

    # dx = start(5) - current(3) = 2 だけ右に(=カーソルに追従して左に)ずれるはず
    new_xlim = ax.get_xlim()
    new_ylim = ax.get_ylim()
    assert new_xlim == pytest.approx((2.0, 12.0))
    assert new_ylim == pytest.approx((1.0, 11.0))


def test_middle_button_motion_ignored_when_not_dragging(tmp_path, monkeypatch):
    """press無しでmotionだけ来ても(_middle_pan_axesがNoneのまま)何もしない。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    xlim_before = ax.get_xlim()

    window._on_middle_button_motion_pan(SimpleNamespace(inaxes=ax, xdata=3.0, ydata=4.0))

    assert ax.get_xlim() == xlim_before


def test_middle_button_motion_ignored_for_different_axes(tmp_path, monkeypatch):
    """ドラッグ開始時と別のAxes上でのモーションは無視する(サブプロット間の
    誤爆を防ぐ)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    ax.set_xlim(0, 10)
    window._on_middle_button_press_pan(SimpleNamespace(button=2, inaxes=ax, xdata=5.0, ydata=5.0))

    other_ax = ax.figure.add_subplot(111)  # ダミーの別Axes
    xlim_before = ax.get_xlim()
    window._on_middle_button_motion_pan(SimpleNamespace(inaxes=other_ax, xdata=1.0, ydata=1.0))

    assert ax.get_xlim() == xlim_before


def test_middle_button_release_clears_pan_state(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    window._on_middle_button_press_pan(SimpleNamespace(button=2, inaxes=ax, xdata=5.0, ydata=5.0))
    assert window._middle_pan_axes is not None

    window._on_middle_button_release_pan(SimpleNamespace(button=2))

    assert window._middle_pan_axes is None
    assert window._middle_pan_start_data is None


def test_middle_button_release_ignored_for_other_buttons(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window, plot_type="Line")
    ax = window.canvas.all_axes[0]
    window._on_middle_button_press_pan(SimpleNamespace(button=2, inaxes=ax, xdata=5.0, ydata=5.0))

    window._on_middle_button_release_pan(SimpleNamespace(button=1))

    assert window._middle_pan_axes is ax  # 左ボタンのreleaseでは解除されない
