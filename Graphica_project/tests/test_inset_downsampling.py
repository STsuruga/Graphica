# tests/test_inset_downsampling.py
"""
インセット(拡大図、項目138/C-711)内の描画が、本体と同じLTTB表示用
ダウンサンプリング(項目C-1001)を通ることのテスト(改善ボード E-1)。

インセットは注釈として実装されており、注釈は再描画のたびに全削除→全再生成
されるため、間引きを通さないと大きなデータでインセットを1つ置いただけで
再描画のたびに数万〜数十万点を描き直すことになっていた(#138実装時の抜け)。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from gui.canvas import (
    MplCanvas, LTTB_DOWNSAMPLE_THRESHOLD, LTTB_DOWNSAMPLE_TARGET_POINTS,
)
from core.dataset import Dataset


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def _make_dataset(n, name="big", x=None, plot_type='Line'):
    if x is None:
        x = np.linspace(0.0, 100.0, n)
    y = np.sin(x)
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y",
                   plot_type=plot_type, color='#112233')


def _inset_settings(x_min=0.0, x_max=100.0):
    return {'annotations': [{
        'type': 'inset', 'corner': '右上', 'size': 0.4,
        'zoom_x_range': (x_min, x_max), 'color': '#000000',
    }]}


def _inset_line_lengths(canvas, axis_index=0):
    """描画されたインセットAxes内の、各Line2Dの点数を返す。"""
    lengths = []
    for artist in canvas._annotation_artists.get(axis_index, []):
        if isinstance(artist, matplotlib.axes.Axes):
            lengths.extend(len(line.get_xdata()) for line in artist.lines)
    return lengths


# --- _downsample_for_inset 単体 ---

def test_small_data_is_returned_untouched(canvas):
    x = np.linspace(0.0, 1.0, 100)
    y = np.sin(x)
    out_x, out_y = canvas._downsample_for_inset(x, y)
    assert out_x is x
    assert out_y is y


def test_data_above_the_threshold_is_downsampled(canvas):
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    x = np.linspace(0.0, 100.0, n)
    y = np.sin(x)
    out_x, out_y = canvas._downsample_for_inset(x, y)
    assert len(out_x) == LTTB_DOWNSAMPLE_TARGET_POINTS
    assert len(out_y) == LTTB_DOWNSAMPLE_TARGET_POINTS
    # LTTBは合成点を作らず元データの実点だけを選ぶ。両端は必ず残る。
    assert out_x[0] == pytest.approx(x[0])
    assert out_x[-1] == pytest.approx(x[-1])


def test_exactly_at_the_threshold_is_not_downsampled(canvas):
    x = np.linspace(0.0, 100.0, LTTB_DOWNSAMPLE_THRESHOLD)
    y = np.sin(x)
    out_x, _ = canvas._downsample_for_inset(x, y)
    assert len(out_x) == LTTB_DOWNSAMPLE_THRESHOLD


def test_full_resolution_skips_downsampling(canvas):
    """エクスポートの「フル解像度」オプション時は、インセットも全点描画する。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    x = np.linspace(0.0, 100.0, n)
    y = np.sin(x)
    out_x, _ = canvas._downsample_for_inset(x, y, full_resolution=True)
    assert len(out_x) == n


def test_non_ascending_x_is_not_downsampled(canvas):
    """LTTBはXが昇順であることを前提とするため、降順/非単調なXは
    本体側と同じく全点描画のまま(形状を誤って変えるより安全側に倒す)。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    x = np.linspace(100.0, 0.0, n)  # 降順
    y = np.sin(x)
    out_x, _ = canvas._downsample_for_inset(x, y)
    assert len(out_x) == n


# --- 実際のインセット描画経路 ---

def test_inset_drawing_goes_through_the_downsampler(canvas):
    """回帰テスト(E-1の本体): 大きなデータでインセットを描くと、
    インセット内のLine2Dは間引き後の点数になっていること。"""
    ds = _make_dataset(LTTB_DOWNSAMPLE_THRESHOLD + 5000)
    canvas.redraw_all([ds], 1, 1, [_inset_settings()])

    lengths = _inset_line_lengths(canvas)
    assert lengths == [LTTB_DOWNSAMPLE_TARGET_POINTS]


def test_inset_drawing_keeps_small_data_intact(canvas):
    ds = _make_dataset(500)
    canvas.redraw_all([ds], 1, 1, [_inset_settings()])

    assert _inset_line_lengths(canvas) == [500]


def test_inset_downsamples_after_the_zoom_range_filter_not_before(canvas):
    """間引きの判定は「拡大範囲でフィルタした後の点数」で行うこと。
    全体では閾値超えでも、拡大範囲に入る点が少なければ間引かれない。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 5000
    ds = _make_dataset(n)
    # 全体 0〜100 のうち 0〜1 だけを拡大 -> 範囲内は全体の約1%
    canvas.redraw_all([ds], 1, 1, [_inset_settings(0.0, 1.0)])

    lengths = _inset_line_lengths(canvas)
    assert len(lengths) == 1
    assert lengths[0] < LTTB_DOWNSAMPLE_THRESHOLD
    assert lengths[0] != LTTB_DOWNSAMPLE_TARGET_POINTS  # 間引かれていない


def test_inset_downsamples_scatter_datasets_too(canvas):
    """本体の_draw_dataと違い、plot_typeによる出し分けは行わない。
    インセット内はplot_typeに関わらず常に単純な折れ線として描く仕様のため、
    「マーカーの疎密が情報だからScatterは対象外」という理由が当てはまらない。"""
    ds = _make_dataset(LTTB_DOWNSAMPLE_THRESHOLD + 5000, plot_type='Scatter')
    canvas.redraw_all([ds], 1, 1, [_inset_settings()])

    assert _inset_line_lengths(canvas) == [LTTB_DOWNSAMPLE_TARGET_POINTS]


def test_inset_export_at_full_resolution_draws_every_point(canvas):
    n = LTTB_DOWNSAMPLE_THRESHOLD + 5000
    ds = _make_dataset(n)
    canvas.redraw_all([ds], 1, 1, [_inset_settings()], full_resolution=True)

    assert _inset_line_lengths(canvas) == [n]


def test_inset_downsampling_applies_on_the_single_axis_redraw_path(canvas):
    ds = _make_dataset(LTTB_DOWNSAMPLE_THRESHOLD + 5000)
    settings = _inset_settings()
    canvas.redraw_all([ds], 1, 1, [settings])

    canvas.update_single_axis(0, [ds], settings)

    assert _inset_line_lengths(canvas) == [LTTB_DOWNSAMPLE_TARGET_POINTS]


def test_inset_downsampling_applies_on_the_light_appearance_redraw_path(canvas):
    """軽量再描画パス(ダークモード切替・パネルラベル切替で通る)でも
    注釈は作り直されるため、そちらでも間引きが効いていること。"""
    ds = _make_dataset(LTTB_DOWNSAMPLE_THRESHOLD + 5000)
    settings = _inset_settings()
    canvas.redraw_all([ds], 1, 1, [settings])

    canvas.update_all_axes_appearance_and_data([ds], 1, 1, [settings])

    assert _inset_line_lengths(canvas) == [LTTB_DOWNSAMPLE_TARGET_POINTS]


def test_hidden_dataset_is_still_excluded_from_the_inset(canvas):
    ds = _make_dataset(1000)
    ds.visible = False
    canvas.redraw_all([ds], 1, 1, [_inset_settings()])

    assert _inset_line_lengths(canvas) == []
