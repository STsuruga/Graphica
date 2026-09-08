# tests/test_waterfall_interaction.py
"""
ウォーターフォール(積み重ね)有効時に、マウス操作がデータ行と正しく
対応づけられることの回帰テスト(改善ボード A-1)。

対象の4箇所(いずれも以前は表示座標→データ座標の逆変換を行っておらず、
積み重ね2本目以降で操作が全てずれていた):

- 範囲選択マスク      gui/mixins/range_select_mixin.py の _apply_range_mask
- データカーソル      gui/mixins/cursor_mixin.py の _on_pick
- エディタ連動ハイライト gui/canvas.py の set_highlighted_points
- ピーク配置          gui/mixins/peak_placement_mixin.py の _on_peak_placement_press

座標変換そのもの(MplCanvas.display_to_data/data_to_display)の単体テストは
tests/test_waterfall_coordinates.py にある。こちらは「実際のGUI経路が
その変換を通っているか」を見る。
"""
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.dataset import Dataset

# 積み重ね2本目(index=1)のずれ量。X/Yとも、この分だけ表示座標がデータ座標から
# ずれている状態を作ってテストする。
OFFSET_X = 10.0
OFFSET_Y = 100.0

XS = [0.0, 1.0, 2.0, 3.0, 4.0]
YS = [0.0, 1.0, 4.0, 9.0, 16.0]


class _FakeMplEvent:
    def __init__(self, inaxes, xdata, ydata, button=1):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = ydata
        self.button = button


class _FakePickEvent:
    def __init__(self, artist, mouseevent, ind):
        self.artist = artist
        self.mouseevent = mouseevent
        self.ind = ind


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


def _add_waterfall_pair(window):
    """ウォーターフォール有効なデータセットを2つ追加し、2本目(index=1、
    つまり実際にずれて描かれている方)を選択状態にして返す。"""
    datasets = []
    for name in ("wf0", "wf1"):
        ds = Dataset(
            name=name, df=pd.DataFrame({"x": XS, "y": YS}),
            x_col_name="x", y_col_name="y", plot_type='Line', color='#112233',
            waterfall_enabled=True, waterfall_offset_x=OFFSET_X, waterfall_offset_y=OFFSET_Y,
        )
        window._add_dataset(ds, select=False)
        datasets.append(ds)

    second = datasets[1]
    item = window._get_dataset_tree_item(second)
    assert item is not None
    window.ui.dataset_list_widget.setCurrentItem(item)
    return datasets


# --- 範囲選択マスク ---

def test_range_select_masks_the_rows_under_the_drag_on_a_stacked_trace(tmp_path, monkeypatch):
    """2本目のトレースは X+10 の位置に描かれている。表示座標で [10.5, 12.5] を
    ドラッグしたら、データ座標の x=1,2 (visible_df の行1,2) がマスクされること。
    逆変換が無いと、生のx_data(0..4)には 10.5〜12.5 に該当する行が無いため
    1件もマスクされなかった。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _, second = _add_waterfall_pair(window)

    ax = window.all_axes[0]
    window._apply_range_mask(ax, 0.5 + OFFSET_X, 2.5 + OFFSET_X)

    assert sorted(second.masked_row_indices) == [1, 2]


def test_range_select_on_a_stacked_trace_does_not_mask_raw_coordinate_rows(tmp_path, monkeypatch):
    """回帰テスト(逆変換漏れの直接の症状): 生のデータ座標で 0.5〜2.5 を
    ドラッグしても、2本目のトレースはそこには描かれていないため何もマスク
    されない(表示座標として解釈すると x=-9.5〜-7.5 で、該当行が無い)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _, second = _add_waterfall_pair(window)

    ax = window.all_axes[0]
    window._apply_range_mask(ax, 0.5, 2.5)

    assert list(second.masked_row_indices) == []


def test_range_select_is_unchanged_without_waterfall(tmp_path, monkeypatch):
    """ウォーターフォール無効時は恒等変換であり、従来どおりの挙動のままであること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="plain", df=pd.DataFrame({"x": XS, "y": YS}),
                 x_col_name="x", y_col_name="y", plot_type='Line', color='#112233')
    window._add_dataset(ds, select=True)

    window._apply_range_mask(window.all_axes[0], 0.5, 2.5)

    assert sorted(ds.masked_row_indices) == [1, 2]


# --- データカーソル ---

def test_data_cursor_reports_data_values_not_shifted_display_values(tmp_path, monkeypatch):
    """データカーソルの注釈テキストは実測値(データ座標)を出すこと。
    以前はArtist上の座標(オフセット込み)をそのまま表示していた。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _, second = _add_waterfall_pair(window)

    artist = second.artist
    # index=1 の点(データ x=1, y=1)は、表示座標 (11, 101) に描かれている
    drawn_x = artist.get_xdata()[1]
    drawn_y = artist.get_ydata()[1]
    assert (drawn_x, drawn_y) == pytest.approx((1.0 + OFFSET_X, 1.0 + OFFSET_Y))

    window.cursor_mode_enabled = True  # _on_pick はモードOFFだと何もしない
    mouse = _FakeMplEvent(window.all_axes[0], drawn_x, drawn_y)
    window._on_pick(_FakePickEvent(artist, mouse, ind=[1]))

    assert window.cursor_annotation is not None
    assert window.cursor_annotation.get_text() == "X: 1\nY: 1"
    # 注釈が指す位置(矢印の先)は、実際に描かれている表示座標のままであること
    assert window.cursor_annotation.xy == pytest.approx((drawn_x, drawn_y))


def test_data_cursor_is_unchanged_without_waterfall(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="plain", df=pd.DataFrame({"x": XS, "y": YS}),
                 x_col_name="x", y_col_name="y", plot_type='Line', color='#112233')
    window._add_dataset(ds, select=True)

    artist = ds.artist
    window.cursor_mode_enabled = True
    mouse = _FakeMplEvent(window.all_axes[0], 2.0, 4.0)
    window._on_pick(_FakePickEvent(artist, mouse, ind=[2]))

    assert window.cursor_annotation.get_text() == "X: 2\nY: 4"


# --- データエディタ連動ハイライト ---

def test_editor_highlight_lands_on_the_stacked_trace(tmp_path, monkeypatch):
    """ハイライトの丸は、トレースが実際に描かれている表示座標に出ること。
    以前は生のデータ座標に描いていたため、トレース上ではない位置に出ていた。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _, second = _add_waterfall_pair(window)

    window.canvas.set_highlighted_points(second, [2])

    artist = window.canvas._highlight_artists[second.dataset_id]
    offsets = np.asarray(artist.get_offsets())
    assert offsets.shape == (1, 2)
    assert offsets[0] == pytest.approx([2.0 + OFFSET_X, 4.0 + OFFSET_Y])


def test_editor_highlight_is_unchanged_without_waterfall(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="plain", df=pd.DataFrame({"x": XS, "y": YS}),
                 x_col_name="x", y_col_name="y", plot_type='Line', color='#112233')
    window._add_dataset(ds, select=True)

    window.canvas.set_highlighted_points(ds, [2])

    offsets = np.asarray(window.canvas._highlight_artists[ds.dataset_id].get_offsets())
    assert offsets[0] == pytest.approx([2.0, 4.0])


# --- ピーク配置 ---

def test_peak_placement_guess_is_stored_in_data_coordinates(tmp_path, monkeypatch):
    """初期値は MultiPeakFitDialog 経由で生の x_data/y_data と突き合わされるため、
    データ座標で保持すること。仮マーカーはクリック位置(表示座標)に出す。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _, second = _add_waterfall_pair(window)
    window.peak_placement_mode_enabled = True

    ax = window.all_axes[0]
    click_x, click_y = 2.0 + OFFSET_X, 4.0 + OFFSET_Y
    window._on_peak_placement_press(_FakeMplEvent(ax, click_x, click_y))

    assert len(window._pending_peak_guesses) == 1
    guess = window._pending_peak_guesses[0]
    assert guess['center'] == pytest.approx(2.0)
    assert guess['height'] == pytest.approx(4.0)

    # 仮マーカーはクリックした場所(表示座標)に描かれている
    _guess, line, point = window._pending_peak_markers[0]
    assert point.get_xdata()[0] == pytest.approx(click_x)
    assert point.get_ydata()[0] == pytest.approx(click_y)


def test_peak_placement_right_click_deletes_the_marker_nearest_the_click(tmp_path, monkeypatch):
    """右クリック削除は表示座標どうしの比較で行うこと(guessはデータ座標なので、
    そのまま比較すると常に見当違いのマーカーが選ばれる/何も消えない)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_waterfall_pair(window)
    window.peak_placement_mode_enabled = True

    ax = window.all_axes[0]
    first_click = (1.0 + OFFSET_X, 1.0 + OFFSET_Y)
    second_click = (3.0 + OFFSET_X, 9.0 + OFFSET_Y)
    window._on_peak_placement_press(_FakeMplEvent(ax, *first_click))
    window._on_peak_placement_press(_FakeMplEvent(ax, *second_click))
    assert len(window._pending_peak_guesses) == 2

    # 2つ目のマーカーのすぐ上を右クリック
    window._on_peak_placement_press(_FakeMplEvent(ax, second_click[0], second_click[1], button=3))

    assert len(window._pending_peak_guesses) == 1
    assert window._pending_peak_guesses[0]['center'] == pytest.approx(1.0)


def test_peak_placement_is_unchanged_without_waterfall(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="plain", df=pd.DataFrame({"x": XS, "y": YS}),
                 x_col_name="x", y_col_name="y", plot_type='Line', color='#112233')
    window._add_dataset(ds, select=True)
    window.peak_placement_mode_enabled = True

    window._on_peak_placement_press(_FakeMplEvent(window.all_axes[0], 2.0, 4.0))

    guess = window._pending_peak_guesses[0]
    assert (guess['center'], guess['height']) == pytest.approx((2.0, 4.0))
    _guess, _line, point = window._pending_peak_markers[0]
    assert (point.get_xdata()[0], point.get_ydata()[0]) == pytest.approx((2.0, 4.0))
