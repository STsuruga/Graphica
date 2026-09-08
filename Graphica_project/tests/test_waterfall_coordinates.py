# tests/test_waterfall_coordinates.py
"""
ウォーターフォール(積み重ね)表示の座標系に関するテスト
(改善ボード A-1 / A-4)。

A-1: トレースは
        表示X = データX + index * offset_x
        表示Y = データY * depth_scale + index * offset_y
     の位置に描かれる。マウス操作をデータ行へ対応づける4箇所
     (範囲選択マスク / データカーソル / データエディタ連動ハイライト /
     ピーク配置)は、必ず MplCanvas.display_to_data() を経由すること。

A-4: 積み重ねインデックスの採番は「非表示のトレースも数に含めて」行う
     (ユーザー判断により「非表示でも位置を保持する=隙間が空く」で確定)。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from gui.canvas import MplCanvas, WATERFALL_DEPTH_SHRINK_MIN_SCALE
from core.dataset import Dataset


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def _make_waterfall_dataset(name, x, y, offset_x=1.0, offset_y=2.0, **kwargs):
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(
        name=name, df=df, x_col_name="x", y_col_name="y",
        plot_type='Line', color='#112233', waterfall_enabled=True,
        waterfall_offset_x=offset_x, waterfall_offset_y=offset_y, **kwargs
    )


X = [0.0, 1.0, 2.0]
Y = [1.0, 2.0, 3.0]


# --- 変換パラメータの記録 (A-1) ---

def test_no_transform_recorded_for_non_waterfall_dataset(canvas):
    """ウォーターフォール無効のデータセットは辞書に現れず、
    data_to_display/display_to_data は恒等変換になる。"""
    ds = Dataset(name="plain", df=pd.DataFrame({"x": X, "y": Y}),
                 x_col_name="x", y_col_name="y", plot_type='Line', color='#112233')
    canvas.redraw_all([ds], 1, 1, [{}])

    assert canvas.get_waterfall_transform(ds) is None
    assert canvas.data_to_display(ds, 5.0, 7.0) == (5.0, 7.0)
    assert canvas.display_to_data(ds, 5.0, 7.0) == (5.0, 7.0)


def test_transform_recorded_with_stacking_index_and_offsets(canvas):
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    assert canvas.get_waterfall_transform(ds0) == {
        'index': 0, 'offset_x': 1.0, 'offset_y': 2.0, 'depth_scale': 1.0}
    assert canvas.get_waterfall_transform(ds1) == {
        'index': 1, 'offset_x': 1.0, 'offset_y': 2.0, 'depth_scale': 1.0}


def test_transform_lookup_accepts_dataset_id_as_well_as_dataset(canvas):
    ds = _make_waterfall_dataset("wf", X, Y)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas.get_waterfall_transform(ds.dataset_id) == canvas.get_waterfall_transform(ds)


def test_transform_is_cleared_when_waterfall_is_turned_off(canvas):
    ds = _make_waterfall_dataset("wf", X, Y)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas.get_waterfall_transform(ds) is not None

    ds.waterfall_enabled = False
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas.get_waterfall_transform(ds) is None


def test_category_x_axis_records_zero_x_offset(canvas):
    """文字列カテゴリX軸ではXオフセットを適用しないため、
    逆変換側にも 0 として記録される(でないとXだけ二重にずれる)。"""
    df0 = pd.DataFrame({"x": ["a", "b", "c"], "y": Y})
    df1 = pd.DataFrame({"x": ["a", "b", "c"], "y": Y})
    ds0 = Dataset(name="c0", df=df0, x_col_name="x", y_col_name="y", plot_type='Bar',
                  color='#112233', waterfall_enabled=True,
                  waterfall_offset_x=1.0, waterfall_offset_y=2.0)
    ds1 = Dataset(name="c1", df=df1, x_col_name="x", y_col_name="y", plot_type='Bar',
                  color='#334455', waterfall_enabled=True,
                  waterfall_offset_x=1.0, waterfall_offset_y=2.0)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    transform = canvas.get_waterfall_transform(ds1)
    assert transform['offset_x'] == 0.0
    assert transform['offset_y'] == 2.0
    # Xは素通し、Yだけがずれる
    assert canvas.display_to_data(ds1, 5.0, 9.0) == (5.0, 7.0)


# --- 変換そのものの正しさ (A-1) ---

def test_display_to_data_inverts_the_drawn_offsets(canvas):
    """描画された表示座標を display_to_data に通すと元のデータ座標に戻る
    (= 実際に描かれている位置と逆変換が一致している)。"""
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    drawn_x = np.asarray(ds1.artist.get_xdata(), dtype=float)
    drawn_y = np.asarray(ds1.artist.get_ydata(), dtype=float)
    # 実際にずれた位置に描かれていること(前提の確認)
    assert drawn_x == pytest.approx([v + 1.0 for v in X])
    assert drawn_y == pytest.approx([v + 2.0 for v in Y])

    back_x, back_y = canvas.display_to_data(ds1, drawn_x, drawn_y)
    assert back_x == pytest.approx(X)
    assert back_y == pytest.approx(Y)


def test_data_to_display_matches_what_was_actually_drawn(canvas):
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    disp_x, disp_y = canvas.data_to_display(ds1, np.asarray(X), np.asarray(Y))
    assert disp_x == pytest.approx(list(ds1.artist.get_xdata()))
    assert disp_y == pytest.approx(list(ds1.artist.get_ydata()))


def test_round_trip_with_depth_shrink_enabled(canvas):
    """奥行き縮小(項目120、C-514)が有効でも往復で元に戻る。"""
    ds0 = _make_waterfall_dataset("wf0", X, Y, waterfall_depth_shrink_enabled=True,
                                  waterfall_depth_shrink_ratio=0.1)
    ds1 = _make_waterfall_dataset("wf1", X, Y, waterfall_depth_shrink_enabled=True,
                                  waterfall_depth_shrink_ratio=0.1)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    transform = canvas.get_waterfall_transform(ds1)
    assert transform['depth_scale'] == pytest.approx(0.9)

    disp_x, disp_y = canvas.data_to_display(ds1, 4.0, 6.0)
    assert disp_y == pytest.approx(6.0 * 0.9 + 2.0)
    back_x, back_y = canvas.display_to_data(ds1, disp_x, disp_y)
    assert (back_x, back_y) == pytest.approx((4.0, 6.0))


def test_depth_scale_is_never_zero_so_inverse_cannot_divide_by_zero(canvas):
    """縮小率が極端でも depth_scale は下限クランプされるため、
    display_to_data のY逆変換がゼロ除算にならない。"""
    datasets = [
        _make_waterfall_dataset("wf%d" % i, X, Y, waterfall_depth_shrink_enabled=True,
                                waterfall_depth_shrink_ratio=0.9)
        for i in range(6)
    ]
    canvas.redraw_all(datasets, 1, 1, [{}])

    for ds in datasets:
        transform = canvas.get_waterfall_transform(ds)
        assert transform['depth_scale'] >= WATERFALL_DEPTH_SHRINK_MIN_SCALE
        back_x, back_y = canvas.display_to_data(ds, 1.0, 1.0)
        assert np.isfinite(back_y)


def test_transform_is_recorded_on_the_single_axis_redraw_path_too(canvas):
    """3つの再描画経路のうち update_single_axis を通った場合も同じ変換が記録される
    (経路ごとに採番がずれると、表示と操作の対応が壊れる)。"""
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])
    before = canvas.get_waterfall_transform(ds1)

    canvas.update_single_axis(0, [ds0, ds1], {})
    assert canvas.get_waterfall_transform(ds1) == before


# --- 非表示トレースの段を保持する (A-4) ---

def test_hidden_trace_keeps_its_slot_in_the_stack(canvas):
    """A-4: 3本のうち2本目を非表示にしても、3本目の積み重ねインデックスは
    2のまま(1に繰り上がらない)。隠した段は空いたままになる。"""
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    ds2 = _make_waterfall_dataset("wf2", X, Y)

    canvas.redraw_all([ds0, ds1, ds2], 1, 1, [{}])
    assert canvas.get_waterfall_transform(ds2)['index'] == 2
    y_before = list(ds2.artist.get_ydata())

    ds1.visible = False
    canvas.redraw_all([ds0, ds1, ds2], 1, 1, [{}])

    assert canvas.get_waterfall_transform(ds2)['index'] == 2
    assert list(ds2.artist.get_ydata()) == pytest.approx(y_before)
    # 隠したトレースは描画対象から外れる(変換も記録されない)
    assert canvas.get_waterfall_transform(ds1) is None


def test_hidden_trace_is_not_drawn(canvas):
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    ds1.visible = False
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    drawn = list(canvas.all_axes[0].lines)
    assert len(drawn) == 1
    assert list(drawn[0].get_ydata()) == pytest.approx(Y)


@pytest.mark.parametrize("redraw", ["redraw_all", "update_single_axis", "add_free_axis"])
def test_hidden_trace_numbering_is_identical_across_all_redraw_paths(canvas, redraw):
    """A-4の対応方針どおり、3つの再描画経路すべてで同じ採番になること。"""
    ds0 = _make_waterfall_dataset("wf0", X, Y)
    ds1 = _make_waterfall_dataset("wf1", X, Y)
    ds2 = _make_waterfall_dataset("wf2", X, Y)
    ds1.visible = False
    datasets = [ds0, ds1, ds2]

    if redraw == "redraw_all":
        canvas.redraw_all(datasets, 1, 1, [{}])
    elif redraw == "update_single_axis":
        canvas.redraw_all(datasets, 1, 1, [{}])
        canvas.update_single_axis(0, datasets, {})
    else:
        # add_free_axis は末尾に新しいAxesを1つ足す。redraw_all([]) で
        # インデックス0のAxesが既にあるため、追加されるのはインデックス1。
        for ds in datasets:
            ds.subplot_target = 1
        canvas.redraw_all([], 1, 1, [{}])
        canvas.add_free_axis(datasets, {})

    assert canvas.get_waterfall_transform(ds0)['index'] == 0
    assert canvas.get_waterfall_transform(ds1) is None
    assert canvas.get_waterfall_transform(ds2)['index'] == 2


def test_hidden_2d_grid_dataset_is_still_excluded_from_drawing(canvas):
    """visibleフィルタを _draw_data 内へ移した際に、2Dマップ側の除外が
    抜け落ちていないこと。"""
    df = pd.DataFrame({"x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [1.0, 2.0, 3.0, 4.0]})
    ds = Dataset(name="map", df=df, x_col_name="x", y_col_name="y",
                 plot_type='Line', color='#112233', data_kind='2d_grid', z_col_name="z")
    ds.visible = False
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas._axis_2d_mappables.get(0) is None
