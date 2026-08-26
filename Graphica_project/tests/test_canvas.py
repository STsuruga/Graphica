# tests/test_canvas.py
"""gui/canvas.py の純粋なヘルパー関数(凡例順序・目盛りロケータ/フォーマッタ)に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
from matplotlib.collections import LineCollection
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import pytest

from gui.canvas import (
    _apply_legend_order, _safe_multiple_locator,
    _sci_each_formatter, _apply_tick_format_mode, _apply_tick_decimal_places,
    MplCanvas, _HeadlessRenderCanvas, DEFAULT_POINT_LABEL_MAX_POINTS,
    LTTB_DOWNSAMPLE_THRESHOLD, LTTB_DOWNSAMPLE_TARGET_POINTS,
    GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS,
)
from core.dataset import Dataset


# --- _apply_legend_order ---

def test_apply_legend_order_no_order_returns_unchanged():
    lines, labels = _apply_legend_order(['l1', 'l2'], ['A', 'B'], order=None)
    assert lines == ['l1', 'l2']
    assert labels == ['A', 'B']


def test_apply_legend_order_reorders_by_given_order():
    lines, labels = _apply_legend_order(['l1', 'l2', 'l3'], ['A', 'B', 'C'], order=['C', 'A', 'B'])
    assert labels == ['C', 'A', 'B']
    assert lines == ['l3', 'l1', 'l2']


def test_apply_legend_order_unlisted_labels_appended_in_original_order():
    """orderに無いラベル(新規追加されたデータセット等)は、元の描画順のまま末尾に回る"""
    lines, labels = _apply_legend_order(['l1', 'l2', 'l3'], ['A', 'B', 'C'], order=['C'])
    assert labels == ['C', 'A', 'B']
    assert lines == ['l3', 'l1', 'l2']


# --- _safe_multiple_locator ---

def test_safe_multiple_locator_normal_interval_unchanged():
    locator = _safe_multiple_locator(1.0, axis_min=0, axis_max=10)
    assert isinstance(locator, ticker.MultipleLocator)
    assert locator._edge.step == pytest.approx(1.0)


def test_safe_multiple_locator_too_fine_interval_is_coarsened():
    """軸範囲に対して目盛りが多すぎる間隔を指定すると、自動的に粗く調整される"""
    locator = _safe_multiple_locator(0.001, axis_min=0, axis_max=1000)
    assert locator._edge.step > 0.001


def test_safe_multiple_locator_zero_range_unchanged():
    locator = _safe_multiple_locator(1.0, axis_min=5, axis_max=5)
    assert locator._edge.step == pytest.approx(1.0)


# --- _sci_each_formatter ---

def test_sci_each_formatter_zero():
    fmt = _sci_each_formatter()
    assert fmt(0) == "0"


def test_sci_each_formatter_positive_value():
    fmt = _sci_each_formatter()
    assert fmt(2.5e8) == r"$2.5\times10^{8}$"


def test_sci_each_formatter_negative_value():
    fmt = _sci_each_formatter()
    assert fmt(-3.0e5) == r"$-3.0\times10^{5}$"


def test_sci_each_formatter_rounding_carries_to_next_exponent():
    """仮数部が丸めで10.0になるケース(例: 9.999e9)は、桁を繰り上げて1.0×10^10に補正する"""
    fmt = _sci_each_formatter()
    assert fmt(9.999e9) == r"$1.0\times10^{10}$"


# --- _apply_tick_format_mode ---

@pytest.fixture
def axis():
    fig, ax = plt.subplots()
    yield ax.xaxis
    plt.close(fig)


def test_apply_tick_format_mode_auto_does_not_change_formatter(axis):
    original_formatter = axis.get_major_formatter()
    _apply_tick_format_mode(axis, mode=0)
    assert axis.get_major_formatter() is original_formatter


def test_apply_tick_format_mode_axis_end_scientific(axis):
    _apply_tick_format_mode(axis, mode=1)
    formatter = axis.get_major_formatter()
    assert isinstance(formatter, ticker.ScalarFormatter)


def test_apply_tick_format_mode_per_tick_scientific(axis):
    _apply_tick_format_mode(axis, mode=2)
    formatter = axis.get_major_formatter()
    assert isinstance(formatter, ticker.FuncFormatter)
    assert formatter(2.5e8) == r"$2.5\times10^{8}$"


def test_apply_tick_format_mode_always_plain(axis):
    _apply_tick_format_mode(axis, mode=3)
    formatter = axis.get_major_formatter()
    assert isinstance(formatter, ticker.ScalarFormatter)
    formatter.set_locs([1e8, 2e8, 3e8])
    label = formatter(2e8)
    assert "10^" not in label


# --- _apply_tick_decimal_places (実機フィードバック: 目盛りの小数点以下桁数) ---

def test_apply_tick_decimal_places_auto_does_not_change_formatter(axis):
    """-1(既定、「自動」)は_apply_tick_format_mode()が設定したフォーマッタを変更しない。"""
    _apply_tick_format_mode(axis, mode=1)
    formatter_after_mode = axis.get_major_formatter()
    _apply_tick_decimal_places(axis, -1)
    assert axis.get_major_formatter() is formatter_after_mode


def test_apply_tick_decimal_places_none_does_not_change_formatter(axis):
    original_formatter = axis.get_major_formatter()
    _apply_tick_decimal_places(axis, None)
    assert axis.get_major_formatter() is original_formatter


def test_apply_tick_decimal_places_zero_formats_as_integer():
    _apply_tick_decimal_places_and_check(0, 3.14159, "3")


def test_apply_tick_decimal_places_two_formats_two_digits():
    _apply_tick_decimal_places_and_check(2, 3.14159, "3.14")


def test_apply_tick_decimal_places_overrides_exponential_format_mode(axis):
    """
    指数表記モード(mode=1)が先に適用されていても、小数点以下桁数が
    明示的に指定されていれば常に固定小数点表記で上書きすること。
    """
    _apply_tick_format_mode(axis, mode=1)
    _apply_tick_decimal_places(axis, 1)
    formatter = axis.get_major_formatter()
    assert isinstance(formatter, ticker.FormatStrFormatter)
    assert formatter(1234.5) == "1234.5"


def _apply_tick_decimal_places_and_check(decimals, value, expected):
    fig, ax = plt.subplots()
    try:
        _apply_tick_decimal_places(ax.xaxis, decimals)
        formatter = ax.xaxis.get_major_formatter()
        assert isinstance(formatter, ticker.FormatStrFormatter)
        assert formatter(value) == expected
    finally:
        plt.close(fig)


# --- データ点ラベルの表示上限(項目105: 大量データでのフリーズ防止) ---

def _make_dataset(n_points, show_point_labels=True):
    df = pd.DataFrame({"x": range(n_points), "y": range(n_points)})
    return Dataset(name="d", df=df, x_col_name="x", y_col_name="y",
                    show_point_labels=show_point_labels)


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def test_point_labels_drawn_when_within_limit(canvas):
    canvas.point_label_max_points = 100
    ds = _make_dataset(10)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert len(canvas.all_axes[0].texts) == 10


def test_point_labels_skipped_when_over_limit(canvas):
    """点数がpoint_label_max_pointsを超えるデータセットには、フリーズ防止のためラベルを描画しない"""
    canvas.point_label_max_points = 5
    ds = _make_dataset(10)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert len(canvas.all_axes[0].texts) == 0


def test_point_labels_default_limit_matches_module_constant(canvas):
    assert canvas.point_label_max_points == DEFAULT_POINT_LABEL_MAX_POINTS


# --- SVGエクスポートでのテキスト保持(項目108) ---
# エクスポート/コピー機能は matplotlib.rc_context({'svg.fonttype': 'none'}) を
# 一時的に適用してからSVGを書き出すことで、目盛りの数字や凡例の文字を
# パス(図形)ではなく実際のテキスト要素として出力する。ここではその根幹の
# 仕組み(rc_contextの効果)を、実際に使われるMplCanvasの描画結果で検証する。

def test_svg_export_default_fonttype_does_not_preserve_text_elements(canvas):
    """デフォルト(svg.fonttype='path')では、ラベル文字は<text>要素として出力されない"""
    import io
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.all_axes[0].set_title("Sample Title")

    buf = io.BytesIO()
    canvas.fig.savefig(buf, format="svg")
    svg_text = buf.getvalue().decode("utf-8")
    assert "<text" not in svg_text


def test_svg_export_with_fonttype_none_preserves_text_elements(canvas):
    """svg.fonttype='none'を適用すると、タイトル等の文字が<text>要素として出力される"""
    import io
    import matplotlib as mpl
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.all_axes[0].set_title("Sample Title")

    buf = io.BytesIO()
    with mpl.rc_context({"svg.fonttype": "none"}):
        canvas.fig.savefig(buf, format="svg")
    svg_text = buf.getvalue().decode("utf-8")
    assert "<text" in svg_text


def test_svg_export_with_fonttype_path_outlines_text_elements(canvas):
    """svg.fonttype='path'(項目88)では、文字が<text>要素として出力されない"""
    import io
    import matplotlib as mpl
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.all_axes[0].set_title("Sample Title")

    buf = io.BytesIO()
    with mpl.rc_context({"svg.fonttype": "path"}):
        canvas.fig.savefig(buf, format="svg")
    svg_text = buf.getvalue().decode("utf-8")
    assert "<text" not in svg_text


# --- グリッド線の詳細カスタマイズ(項目82) ---
# X軸/Y軸・主目盛/補助目盛それぞれに独立した線種・太さ・透過度を設定できることと、
# 設定キーが無い(この機能追加前に保存された)プロジェクトを読み込んでも、
# 従来通りの見た目になることを検証する。

def _minor_gridlines(axis):
    """軸(xaxis/yaxis)の補助目盛グリッド線Line2Dのリストを返す。
    Axis.get_gridlines() は主目盛分しか返さないため、補助目盛側は
    get_minor_ticks() 経由で各Tickの.gridlineを取る。"""
    return [tick.gridline for tick in axis.get_minor_ticks()]


def test_grid_hidden_by_default_when_grid_visible_false(canvas):
    """grid_visible が無い(またはFalseの)設定では、主目盛グリッド線は非表示のまま"""
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert ax.xaxis.get_gridlines()[0].get_visible() is False
    assert ax.yaxis.get_gridlines()[0].get_visible() is False


def test_grid_major_style_defaults_match_previous_hardcoded_appearance():
    """grid_visible=True だが線種/太さ/透過度のキーが無い(旧プロジェクト)場合、
    この機能追加前と同じ見た目(実線・太さ0.8・alpha=1.0)になる(後方互換性)"""
    c = MplCanvas(width=4, height=3, dpi=80)
    ds = _make_dataset(5, show_point_labels=False)
    c.redraw_all([ds], 1, 1, [{'grid_visible': True}])
    ax = c.all_axes[0]
    for gridline in (ax.xaxis.get_gridlines()[0], ax.yaxis.get_gridlines()[0]):
        assert gridline.get_visible() is True
        assert gridline.get_linestyle() == '-'
        assert gridline.get_linewidth() == pytest.approx(0.8)
        assert gridline.get_alpha() == pytest.approx(1.0)
    plt.close(c.fig)


def test_grid_minor_style_defaults_match_previous_hardcoded_appearance():
    """補助グリッドについても同様に、旧来のデフォルト(破線・太さ0.5・alpha=1.0)を再現する"""
    c = MplCanvas(width=4, height=3, dpi=80)
    ds = _make_dataset(5, show_point_labels=False)
    settings = {
        'grid_visible': True, 'minor_grid_visible': True,
        'x_minor_ticks_visible': True, 'x_minor_tick_interval': 0.5,
        'y_minor_ticks_visible': True, 'y_minor_tick_interval': 0.5,
    }
    c.redraw_all([ds], 1, 1, [settings])
    ax = c.all_axes[0]
    for gridline in (_minor_gridlines(ax.xaxis)[0], _minor_gridlines(ax.yaxis)[0]):
        assert gridline.get_visible() is True
        assert gridline.get_linestyle() == '--'
        assert gridline.get_linewidth() == pytest.approx(0.5)
        assert gridline.get_alpha() == pytest.approx(1.0)
    plt.close(c.fig)


def test_grid_custom_style_applies_independently_per_axis_and_major_minor():
    """X/Y軸・主/補助それぞれに指定した独立の線種/太さ/透過度が、
    それぞれ対応するAxesのグリッド線にだけ反映されることを検証する"""
    c = MplCanvas(width=4, height=3, dpi=80)
    ds = _make_dataset(5, show_point_labels=False)
    settings = {
        'grid_visible': True, 'minor_grid_visible': True,
        'x_minor_ticks_visible': True, 'x_minor_tick_interval': 0.5,
        'y_minor_ticks_visible': True, 'y_minor_tick_interval': 0.5,
        'x_major_grid_linestyle': ':', 'x_major_grid_width': 2.0, 'x_major_grid_alpha': 0.3,
        'y_major_grid_linestyle': '-.', 'y_major_grid_width': 1.5, 'y_major_grid_alpha': 0.6,
        'x_minor_grid_linestyle': '--', 'x_minor_grid_width': 0.3, 'x_minor_grid_alpha': 0.2,
        'y_minor_grid_linestyle': ':', 'y_minor_grid_width': 0.4, 'y_minor_grid_alpha': 0.9,
    }
    c.redraw_all([ds], 1, 1, [settings])
    ax = c.all_axes[0]

    x_major = ax.xaxis.get_gridlines()[0]
    assert (x_major.get_linestyle(), x_major.get_linewidth(), x_major.get_alpha()) == (':', pytest.approx(2.0), pytest.approx(0.3))

    y_major = ax.yaxis.get_gridlines()[0]
    assert (y_major.get_linestyle(), y_major.get_linewidth(), y_major.get_alpha()) == ('-.', pytest.approx(1.5), pytest.approx(0.6))

    x_minor = _minor_gridlines(ax.xaxis)[0]
    assert (x_minor.get_linestyle(), x_minor.get_linewidth(), x_minor.get_alpha()) == ('--', pytest.approx(0.3), pytest.approx(0.2))

    y_minor = _minor_gridlines(ax.yaxis)[0]
    assert (y_minor.get_linestyle(), y_minor.get_linewidth(), y_minor.get_alpha()) == (':', pytest.approx(0.4), pytest.approx(0.9))
    plt.close(c.fig)


# --- プロットへのグラデーション適用(項目79) ---
# 線ストロークグラデーション(LineCollection)と塗りグラデーション(imshow+クリップ
# パス)の両方について、gradient_enabled=False(デフォルト)では従来どおりの
# 描画(回帰が無いこと)を、gradient_enabled=True では期待するArtist種別に
# 切り替わることを検証する。

def _make_line_dataset(gradient_enabled=False, gradient_target='line', plot_type='Line'):
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0], "y": [0.0, 1.0, 4.0, 9.0]})
    return Dataset(
        name="line_ds", df=df, x_col_name="x", y_col_name="y",
        plot_type=plot_type, color='#112233', gradient_color2='#ffffff',
        gradient_enabled=gradient_enabled, gradient_target=gradient_target,
    )


def _make_area_dataset(gradient_enabled=False, gradient_target='fill'):
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0, 2.0]})
    return Dataset(
        name="area_ds", df=df, x_col_name="x", y_col_name="y",
        plot_type='Area', color='#112233', gradient_color2='#ffffff',
        gradient_enabled=gradient_enabled, gradient_target=gradient_target,
    )


def test_gradient_disabled_line_matches_previous_line2d_behavior(canvas):
    """gradient_enabled=False(デフォルト)の 'Line' は、従来どおりLine2Dが1本だけ
    描画される(LineCollectionには切り替わらない、後方互換の回帰確認)"""
    ds = _make_line_dataset(gradient_enabled=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert isinstance(ds.artist, Line2D)
    assert len(ax.lines) == 1
    assert len(ax.collections) == 0


def test_gradient_disabled_area_matches_previous_artist_count(canvas):
    """gradient_enabled=False の 'Area' は、従来どおり fill_between(collection 1つ)
    + 輪郭のLine2D(1本)という組み合わせのまま変わらない"""
    ds = _make_area_dataset(gradient_enabled=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.lines) == 1
    assert len(ax.collections) == 1
    assert len(ax.images) == 0


def test_gradient_line_enabled_uses_linecollection_with_two_color_cmap(canvas):
    """gradient_target='line' で有効化すると、'Line'はLine2DではなくLineCollectionに
    切り替わり、cmapの両端が開始色(color)・終端色(gradient_color2)になる"""
    ds = _make_line_dataset(gradient_enabled=True, gradient_target='line')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]

    assert isinstance(ds.artist, LineCollection)
    assert len(ax.lines) == 0  # 通常のLine2Dとしては描画されない

    cmap = ds.artist.get_cmap()
    start_rgba = cmap(0.0)
    end_rgba = cmap(1.0)
    import matplotlib.colors as mcolors
    assert start_rgba[:3] == pytest.approx(mcolors.to_rgb('#112233'), abs=1e-6)
    assert end_rgba[:3] == pytest.approx(mcolors.to_rgb('#ffffff'), abs=1e-6)

    # 各線分に、線に沿った位置(0〜1)を表す配列が割り当てられている
    array = ds.artist.get_array()
    assert array is not None
    assert len(array) == len(ds.x_data) - 1


def test_gradient_line_enabled_autoscales_axis_to_data_range(canvas):
    """add_collection()経由のLineCollectionでも、通常のax.plot()と同様に
    軸のオートスケールがデータ範囲に追従すること(見落としがちな落とし穴の確認)"""
    ds = _make_line_dataset(gradient_enabled=True, gradient_target='line')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    assert x_min <= ds.x_data.min() and x_max >= ds.x_data.max()
    assert y_min <= ds.y_data.min() and y_max >= ds.y_data.max()


def test_gradient_target_fill_only_keeps_line_as_plain_line2d(canvas):
    """'Line'に対して(本来意味を持たない)gradient_target='fill'を指定しても
    クラッシュせず、線は従来通りの単色Line2Dのまま描画される(防御的な後方互換)"""
    ds = _make_line_dataset(gradient_enabled=True, gradient_target='fill', plot_type='Line')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert isinstance(ds.artist, Line2D)
    assert len(ax.collections) == 0


def test_gradient_fill_enabled_creates_clipped_imshow(canvas):
    """gradient_target='fill' の 'Area' は、fill_betweenの代わりにクリップパス付きの
    imshow(AxesImage)で塗り領域を描画する"""
    ds = _make_area_dataset(gradient_enabled=True, gradient_target='fill')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]

    assert len(ax.images) == 1
    image = ax.images[0]
    assert isinstance(image, AxesImage)
    assert image.get_clip_path() is not None
    assert ds.artist is image
    # 塗りに使われたのと同じ輪郭線(通常のLine2D、対象='fill'のみなのでグラデーション化されない)も引き続き描画される
    assert len(ax.lines) == 1


def test_gradient_both_target_on_area_creates_gradient_line_and_gradient_fill(canvas):
    """gradient_target='both' の 'Area' は、線・塗りの両方がグラデーション化される"""
    ds = _make_area_dataset(gradient_enabled=True, gradient_target='both')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]

    assert len(ax.images) == 1
    assert ax.images[0].get_clip_path() is not None
    assert len(ax.lines) == 0  # 輪郭線もLineCollection化されるため、Line2Dはゼロ本
    assert any(isinstance(c, LineCollection) for c in ax.collections)


def test_gradient_line_with_single_point_falls_back_to_plain_line(canvas):
    """データ点が1つ以下だとセグメントが作れないため、例外を出さず通常の線として描画する"""
    df = pd.DataFrame({"x": [1.0], "y": [2.0]})
    ds = Dataset(
        name="single", df=df, x_col_name="x", y_col_name="y",
        plot_type='Line', gradient_enabled=True, gradient_target='line',
    )
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert isinstance(ds.artist, Line2D)


# --- ウォーターフォールプロット(項目80、項目109で独立フラグに変更) ---
# plot_typeとは独立した waterfall_enabled=True のデータセットだけを対象に、
# 同一サブプロット上でリスト順に0始まりの積み重ねインデックスを振り、X/Yを
# それぞれ (index * waterfall_offset_x, index * waterfall_offset_y) だけずらして
# 描画する。実装は通常の2D Axesの範囲内(mpl_toolkits.mplot3dは使わない疑似3D)。
# plot_typeはLine/Scatter/Line+Scatter/Area/Barのどれでも組み合わせられる。

def _make_waterfall_dataset(name, x, y, offset_x=0.0, offset_y=1.0, plot_type='Line', **kwargs):
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(
        name=name, df=df, x_col_name="x", y_col_name="y",
        plot_type=plot_type, color='#112233', waterfall_enabled=True,
        waterfall_offset_x=offset_x, waterfall_offset_y=offset_y, **kwargs
    )


def test_waterfall_zero_offset_matches_plain_line_position(canvas):
    """offset=(0,0)の単独ウォーターフォール有効データセットは、積み重ね
    インデックス0番目として何もずらされないため、通常の'Line'と同じ位置に
    描画される(回帰防止のためのベースライン確認)。"""
    x, y = [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0]
    ds_line = Dataset(name="line", df=pd.DataFrame({"x": x, "y": y}),
                       x_col_name="x", y_col_name="y", plot_type='Line', color='#112233')
    ds_waterfall = _make_waterfall_dataset("wf", x, y, offset_x=0.0, offset_y=0.0)

    canvas.redraw_all([ds_line], 1, 1, [{}])
    line_x, line_y = list(ds_line.artist.get_xdata()), list(ds_line.artist.get_ydata())

    canvas.redraw_all([ds_waterfall], 1, 1, [{}])
    assert isinstance(ds_waterfall.artist, Line2D)
    assert list(ds_waterfall.artist.get_xdata()) == pytest.approx(line_x)
    assert list(ds_waterfall.artist.get_ydata()) == pytest.approx(line_y)


def test_waterfall_two_datasets_shift_by_stacking_index(canvas):
    """ウォーターフォール有効な2件のデータセットは、リスト順で0,1のインデックスを
    振られ、2件目はX方向に1*offset_x、Y方向に1*offset_yだけずれた位置に描画される。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds0 = _make_waterfall_dataset("wf0", x, y, offset_x=1.0, offset_y=2.0)
    ds1 = _make_waterfall_dataset("wf1", x, y, offset_x=1.0, offset_y=2.0)

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    assert list(ds0.artist.get_xdata()) == pytest.approx(x)
    assert list(ds0.artist.get_ydata()) == pytest.approx(y)
    assert list(ds1.artist.get_xdata()) == pytest.approx([v + 1.0 for v in x])
    assert list(ds1.artist.get_ydata()) == pytest.approx([v + 2.0 for v in y])


def test_waterfall_non_waterfall_datasets_unaffected_and_excluded_from_index(canvas):
    """同じサブプロットにウォーターフォール無効のデータセットが混在していても、
    積み重ねインデックスの計算には参加せず、位置も一切ずらされない。有効な
    データセット側のインデックス付番も、無効なデータセットを無視して有効な
    もの同士だけの順序で振られる。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds_line = Dataset(name="line", df=pd.DataFrame({"x": x, "y": y}),
                       x_col_name="x", y_col_name="y", plot_type='Line', color='#445566')
    ds_wf0 = _make_waterfall_dataset("wf0", x, y, offset_x=1.0, offset_y=2.0)
    ds_wf1 = _make_waterfall_dataset("wf1", x, y, offset_x=1.0, offset_y=2.0)

    # 無効なデータセットをリストの先頭・間に挟んでも結果が変わらないこと
    canvas.redraw_all([ds_line, ds_wf0, ds_wf1], 1, 1, [{}])

    assert list(ds_line.artist.get_xdata()) == pytest.approx(x)
    assert list(ds_line.artist.get_ydata()) == pytest.approx(y)
    # wf0 は0番目のまま(lineに割り込まれてもインデックスは変わらない)
    assert list(ds_wf0.artist.get_xdata()) == pytest.approx(x)
    assert list(ds_wf0.artist.get_ydata()) == pytest.approx(y)
    # wf1 は1番目
    assert list(ds_wf1.artist.get_xdata()) == pytest.approx([v + 1.0 for v in x])
    assert list(ds_wf1.artist.get_ydata()) == pytest.approx([v + 2.0 for v in y])


def test_waterfall_combines_with_scatter_plot_type(canvas):
    """項目109: ウォーターフォールはplot_typeとは独立したフラグなので、
    'Scatter'と組み合わせても(マーカー描画のまま)ずらされて描画される。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    from matplotlib.collections import PathCollection
    ds = _make_waterfall_dataset("wf_scatter", x, y, offset_x=1.0, offset_y=2.0,
                                  plot_type='Scatter')

    canvas.redraw_all([ds], 1, 1, [{}])

    assert isinstance(ds.artist, PathCollection)
    offsets = ds.artist.get_offsets()
    assert list(offsets[:, 0]) == pytest.approx(x)  # index 0 → シフト無し
    assert list(offsets[:, 1]) == pytest.approx(y)


def test_waterfall_combines_with_line_plus_scatter_plot_type(canvas):
    """項目109: 'Line+Scatter'と組み合わせても、線+マーカーの両方が
    積み重ねインデックス分ずれた位置に描画される。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds0 = _make_waterfall_dataset("wf0", x, y, offset_x=1.0, offset_y=2.0,
                                   plot_type='Line+Scatter')
    ds1 = _make_waterfall_dataset("wf1", x, y, offset_x=1.0, offset_y=2.0,
                                   plot_type='Line+Scatter')

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    assert isinstance(ds0.artist, Line2D)
    assert list(ds0.artist.get_xdata()) == pytest.approx(x)
    assert list(ds1.artist.get_xdata()) == pytest.approx([v + 1.0 for v in x])
    assert list(ds1.artist.get_ydata()) == pytest.approx([v + 2.0 for v in y])
    # linestyle/markerも通常通り指定・反映できる(専用種別ではなくなったため)
    assert ds1.artist.get_linestyle() == '-'


def test_waterfall_with_category_x_axis_does_not_crash(canvas):
    """文字列カテゴリX軸(Barの主要用途)にウォーターフォールを適用すると、
    以前はds.x_data(文字列のobject配列)に数値のXオフセットを加算しようとして
    TypeErrorでredraw_all全体がクラッシュしていた(過去の見落とし)。カテゴリ軸
    ではXオフセットをスキップし、Yオフセットのみ適用することで、縦方向の
    積み重ね表示自体は維持しつつクラッシュを防ぐ。"""
    x, y = ['a', 'b', 'c'], [1.0, 2.0, 3.0]
    ds0 = Dataset(name="wf0", df=pd.DataFrame({"x": x, "y": y}), x_col_name="x", y_col_name="y",
                   plot_type='Bar', color='#112233', waterfall_enabled=True,
                   waterfall_offset_x=1.0, waterfall_offset_y=2.0)
    ds1 = Dataset(name="wf1", df=pd.DataFrame({"x": x, "y": y}), x_col_name="x", y_col_name="y",
                   plot_type='Bar', color='#334455', waterfall_enabled=True,
                   waterfall_offset_x=1.0, waterfall_offset_y=2.0)

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])  # 例外が出なければOK

    ax = canvas.all_axes[0]
    assert len(ax.patches) == 6  # 2データセット x 3カテゴリ = 6本の棒


def test_grid_minor_hidden_when_minor_grid_visible_false():
    """主グリッドはONでも補助グリッドがOFFなら、補助目盛グリッド線は表示されない
    (X/Y独立カスタマイズ導入後も、この既存の on/off 挙動は変わらない)"""
    c = MplCanvas(width=4, height=3, dpi=80)
    ds = _make_dataset(5, show_point_labels=False)
    settings = {
        'grid_visible': True, 'minor_grid_visible': False,
        'x_minor_ticks_visible': True, 'x_minor_tick_interval': 0.5,
        'y_minor_ticks_visible': True, 'y_minor_tick_interval': 0.5,
    }
    c.redraw_all([ds], 1, 1, [settings])
    ax = c.all_axes[0]
    assert _minor_gridlines(ax.xaxis)[0].get_visible() is False
    assert _minor_gridlines(ax.yaxis)[0].get_visible() is False
    plt.close(c.fig)


# --- 誤差の表示形式(項目C-502: エラーバー/誤差バンド/両方) ---
# matplotlibの errorbar(fmt='none') 自体もキャップ/バー用のLineCollectionを
# ax.collectionsに追加するため、fill_between(PolyCollection)の有無は
# 型で区別する。

from matplotlib.collections import PolyCollection


def _make_dataset_with_yerr(error_display='bar'):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0], "yerr": [1.0, 2.0, 1.5]})
    return Dataset(name="d", df=df, x_col_name="x", y_col_name="y", y_err_col_name="yerr",
                    error_display=error_display)


def _poly_collections(ax):
    return [c for c in ax.collections if isinstance(c, PolyCollection)]


def test_error_display_bar_draws_errorbar_but_no_band(canvas):
    ds = _make_dataset_with_yerr(error_display='bar')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.containers) == 1  # errorbar
    assert _poly_collections(ax) == []  # fill_between(誤差バンド)無し


def test_error_display_band_draws_fill_between_but_no_errorbar(canvas):
    ds = _make_dataset_with_yerr(error_display='band')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.containers) == 0
    assert len(_poly_collections(ax)) == 1  # fill_between


def test_error_display_both_draws_errorbar_and_band(canvas):
    ds = _make_dataset_with_yerr(error_display='both')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.containers) == 1
    assert len(_poly_collections(ax)) == 1


def test_error_band_fill_between_covers_y_plus_minus_yerr(canvas):
    ds = _make_dataset_with_yerr(error_display='band')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    band = _poly_collections(ax)[0]
    path = band.get_paths()[0]
    ys = path.vertices[:, 1]
    # y ± yerr = [9,21], [18,22], [28.5,31.5] の範囲に収まっているはず
    assert ys.min() == pytest.approx(9.0)
    assert ys.max() == pytest.approx(31.5)


def test_error_display_without_error_columns_draws_neither(canvas):
    """X/Y誤差列が未設定なら、error_displayの値に関わらず何も描画しない"""
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [10.0, 20.0]})
    ds = Dataset(name="d", df=df, x_col_name="x", y_col_name="y", error_display='both')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.containers) == 0
    assert len(ax.collections) == 0


# --- 曲線フィットの信頼帯・予測帯(項目C-405) ---

def _make_fit_dataset_with_band(fit_band_display="confidence"):
    df = pd.DataFrame({
        "x_fit": [0.0, 1.0, 2.0],
        "y_fit": [1.0, 2.0, 3.0],
        "y_lower": [0.5, 1.5, 2.5],
        "y_upper": [1.5, 2.5, 3.5],
    })
    return Dataset(name="Fit (d)", df=df, x_col_name="x_fit", y_col_name="y_fit",
                    fit_band_display=fit_band_display)


def test_fit_band_display_confidence_draws_fill_between(canvas):
    ds = _make_fit_dataset_with_band(fit_band_display="confidence")
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(_poly_collections(ax)) == 1


def test_fit_band_display_none_draws_no_band(canvas):
    ds = _make_fit_dataset_with_band(fit_band_display=None)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert _poly_collections(ax) == []


def test_fit_band_display_set_but_columns_missing_draws_no_band():
    """fit_band_displayが設定されていても、実際にy_lower/y_upper列が無い
    (古いプロジェクトファイル等)場合は描画をスキップし、KeyErrorで落ちない。"""
    df = pd.DataFrame({"x_fit": [0.0, 1.0], "y_fit": [1.0, 2.0]})
    ds = Dataset(name="Fit (d)", df=df, x_col_name="x_fit", y_col_name="y_fit",
                 fit_band_display="confidence")
    c = MplCanvas()
    c.redraw_all([ds], 1, 1, [{}])
    ax = c.all_axes[0]
    assert _poly_collections(ax) == []
    plt.close(c.fig)


def test_fit_band_fill_between_covers_lower_to_upper(canvas):
    ds = _make_fit_dataset_with_band(fit_band_display="prediction")
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    band = _poly_collections(ax)[0]
    ys = band.get_paths()[0].vertices[:, 1]
    assert ys.min() == pytest.approx(0.5)
    assert ys.max() == pytest.approx(3.5)


def test_error_display_defaults_to_bar():
    ds = Dataset(name="d", df=pd.DataFrame({'x': [1], 'y': [1]}), x_col_name='x', y_col_name='y')
    assert ds.error_display == 'bar'


# --- パネルラベルの自動採番(項目C-712) ---

def test_panel_label_for_index_single_letters():
    assert MplCanvas._panel_label_for_index(0) == 'a'
    assert MplCanvas._panel_label_for_index(1) == 'b'
    assert MplCanvas._panel_label_for_index(25) == 'z'


def test_panel_label_for_index_double_letters_after_z():
    assert MplCanvas._panel_label_for_index(26) == 'aa'
    assert MplCanvas._panel_label_for_index(27) == 'ab'
    assert MplCanvas._panel_label_for_index(51) == 'az'
    assert MplCanvas._panel_label_for_index(52) == 'ba'


def test_redraw_all_draws_panel_labels_when_enabled(canvas):
    ds0 = _make_dataset(3, show_point_labels=False)
    ds1 = Dataset(name="d2", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}], panel_labels_enabled=True)
    texts0 = [t.get_text() for t in canvas.all_axes[0].texts]
    texts1 = [t.get_text() for t in canvas.all_axes[1].texts]
    assert "(a)" in texts0
    assert "(b)" in texts1


def test_redraw_all_omits_panel_labels_when_disabled(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}], panel_labels_enabled=False)
    assert list(canvas.all_axes[0].texts) == []


def test_redraw_all_panel_labels_default_to_disabled(canvas):
    """panel_labels_enabled引数を省略した既存の呼び出し(後方互換)では描画されない"""
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert list(canvas.all_axes[0].texts) == []


# --- 項目C-601: 軸共有(sharex/sharey) ---

def test_redraw_all_share_x_axis_links_axes_and_hides_inner_labels(canvas):
    ds0 = _make_dataset(3, show_point_labels=False)
    ds1 = Dataset(name="d2", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 2, 1, [{}, {}], share_x_axis=True)
    ax0, ax1 = canvas.all_axes
    assert ax0.get_shared_x_axes().joined(ax0, ax1)
    # 上段(row 0, 最下行ではない)はX軸目盛りラベルが隠れる
    assert ax0.xaxis.get_tick_params()['labelbottom'] is False
    # 最下行(row 1)はラベルを維持する
    assert ax1.xaxis.get_tick_params()['labelbottom'] is True


def test_redraw_all_share_y_axis_links_axes_and_hides_inner_labels(canvas):
    ds0 = _make_dataset(3, show_point_labels=False)
    ds1 = Dataset(name="d2", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}], share_y_axis=True)
    ax0, ax1 = canvas.all_axes
    assert ax0.get_shared_y_axes().joined(ax0, ax1)
    # 左列(col 0)はラベルを維持する
    assert ax0.yaxis.get_tick_params()['labelleft'] is True
    # 右列(col 1, 最左列ではない)はY軸目盛りラベルが隠れる
    assert ax1.yaxis.get_tick_params()['labelleft'] is False


def test_redraw_all_share_axis_default_disabled_no_linking(canvas):
    ds0 = _make_dataset(3, show_point_labels=False)
    ds1 = Dataset(name="d2", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}])
    ax0, ax1 = canvas.all_axes
    assert not ax0.get_shared_x_axes().joined(ax0, ax1)
    assert not ax0.get_shared_y_axes().joined(ax0, ax1)
    assert ax0.xaxis.get_tick_params()['labelbottom'] is True
    assert ax1.yaxis.get_tick_params()['labelleft'] is True


# --- 項目C-602: 単位変換の第2X軸 ---

def test_redraw_all_adds_secondary_x_axis_when_source_and_target_units_set(canvas):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [400.0, 500.0, 600.0], "y": [1.0, 2.0, 3.0]}),
                 x_col_name="x", y_col_name="y")
    settings = {'x_secondary_axis_source_unit': 'nm', 'x_secondary_axis_target_unit': 'eV'}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    secondary_axes = [child for child in ax.child_axes if child.get_xlabel() == 'eV(エネルギー)']
    assert len(secondary_axes) == 1


def test_redraw_all_omits_secondary_x_axis_when_units_not_set(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert ax.child_axes == []


def test_redraw_all_omits_secondary_x_axis_when_source_and_target_equal(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    settings = {'x_secondary_axis_source_unit': 'nm', 'x_secondary_axis_target_unit': 'nm'}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    assert ax.child_axes == []


def test_redraw_all_omits_secondary_x_axis_when_only_one_unit_set(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    settings = {'x_secondary_axis_source_unit': 'nm', 'x_secondary_axis_target_unit': 'none'}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    assert ax.child_axes == []


def test_redraw_all_skips_secondary_x_axis_when_range_includes_zero(canvas):
    """波長0nm相当はnm<->eV等の変換でinf/nanになりmatplotlibが例外を投げるため、
    そのケースでは第2X軸自体を追加せず、メインの描画は正常に完了すること
    (X軸範囲が0を含む場合のクラッシュ回避、実データでautoscaleが0始まりに
    なるのは珍しくない)。"""
    ds = Dataset(name="d", df=pd.DataFrame({"x": [0.0, 100.0, 200.0], "y": [1.0, 2.0, 3.0]}),
                 x_col_name="x", y_col_name="y")
    settings = {'x_secondary_axis_source_unit': 'nm', 'x_secondary_axis_target_unit': 'eV'}
    result = canvas.redraw_all([ds], 1, 1, [settings])  # 例外が出なければOK
    assert result is not None
    ax = canvas.all_axes[0]
    assert ax.child_axes == []


def test_secondary_x_axis_uses_bounded_locator_for_extreme_converted_range(canvas):
    """
    実機フィードバック(ログで確認): matplotlib.ticker "Locator attempting to
    generate N ticks...exceeds Locator.MAXTICKS"警告。nm<->cm^-1/Hz等の
    反比例変換では、主軸側は常識的な範囲でも第2X軸側の値域が桁違いに広がる
    ことがあり、既定のAutoLocatorに任せきりだと極端に多い目盛りを生成しようと
    していた。MaxNLocatorを明示していることで、変換後の値域がどれだけ
    極端でも目盛り本数が妥当な範囲に収まることを確認する。
    """
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1.0, 1000.0], "y": [1.0, 2.0]}),
                 x_col_name="x", y_col_name="y")
    settings = {'x_secondary_axis_source_unit': 'nm', 'x_secondary_axis_target_unit': 'Hz'}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    secondary_ax = [child for child in ax.child_axes if child.get_xlabel() == 'Hz(周波数)'][0]
    locator = secondary_ax.xaxis.get_major_locator()
    assert isinstance(locator, ticker.MaxNLocator)
    tick_values = locator.tick_values(*secondary_ax.get_xlim())
    assert len(tick_values) <= 20


def test_secondary_x_axis_ticks_reflect_converted_values(canvas):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [400.0, 500.0, 600.0], "y": [1.0, 2.0, 3.0]}),
                 x_col_name="x", y_col_name="y")
    settings = {'x_secondary_axis_source_unit': 'nm', 'x_secondary_axis_target_unit': 'eV'}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    secondary_ax = [child for child in ax.child_axes if child.get_xlabel() == 'eV(エネルギー)'][0]
    from core.unit_conversion import convert_x_axis_unit
    primary_xlim = ax.get_xlim()
    expected = convert_x_axis_unit(np.array(primary_xlim), 'nm', 'eV')
    np.testing.assert_allclose(sorted(secondary_ax.get_xlim()), sorted(expected), rtol=1e-6)


# --- 項目C-003フェーズ1: update_single_axis (1つのAxesだけの軽量再描画) ---

def test_update_single_axis_does_not_touch_other_axes_identity(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}])
    ax1_before = canvas.all_axes[1]

    canvas.update_single_axis(0, [ds0, ds1], {}, rows=1, cols=2)

    assert canvas.all_axes[1] is ax1_before
    assert len(canvas.all_axes[1].lines) == 1  # 他のAxesの中身も無傷


def test_update_single_axis_redraws_the_target_axis_data(canvas):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}), x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 1, 1, [{}])
    assert len(canvas.all_axes[0].lines) == 1

    ds.df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [4, 5, 6, 7]})
    canvas.update_single_axis(0, [ds], {}, rows=1, cols=1)

    line = canvas.all_axes[0].lines[0]
    assert len(line.get_xdata()) == 4


def test_update_single_axis_no_op_for_out_of_range_index(canvas):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.update_single_axis(5, [ds], {}, rows=1, cols=1)  # 例外が出なければOK


def test_update_single_axis_rebuilds_twinx_without_duplicating_it(canvas):
    ds_primary = Dataset(name="p", df=pd.DataFrame({"x": [1, 2], "y": [1, 2]}), x_col_name="x", y_col_name="y")
    ds_secondary = Dataset(name="s", df=pd.DataFrame({"x": [1, 2], "y": [10, 20]}), x_col_name="x", y_col_name="y",
                           use_secondary_y=True)
    canvas.redraw_all([ds_primary, ds_secondary], 1, 1, [{}])
    assert canvas.all_secondary_axes[0] is not None
    secondary_before = canvas.all_secondary_axes[0]

    canvas.update_single_axis(0, [ds_primary, ds_secondary], {}, rows=1, cols=1)

    assert canvas.all_secondary_axes[0] is not None
    assert canvas.all_secondary_axes[0] is not secondary_before  # 作り直された
    assert len(canvas.fig.axes) == 2  # 副軸が積み重なっていない


def test_update_single_axis_removes_secondary_axis_when_no_longer_needed(canvas):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [1, 2]}), x_col_name="x", y_col_name="y",
                 use_secondary_y=True)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas.all_secondary_axes[0] is not None

    ds.use_secondary_y = False
    canvas.update_single_axis(0, [ds], {}, rows=1, cols=1)

    assert canvas.all_secondary_axes[0] is None
    assert len(canvas.fig.axes) == 1


def test_update_single_axis_preserves_shared_axis_inner_label_hiding(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 2, 1, [{}, {}], share_x_axis=True)
    assert canvas.all_axes[0].xaxis.get_tick_params()['labelbottom'] is False

    # ax.cla()がtick_paramsをリセットするため、update_single_axis側で
    # 再適用されないとラベルが復活してしまう(share_x_axis=Trueを渡し忘れた
    # 場合の回帰を検知する)。
    canvas.update_single_axis(0, [ds0, ds1], {}, rows=2, cols=1, share_x_axis=True)
    assert canvas.all_axes[0].xaxis.get_tick_params()['labelbottom'] is False


def test_update_single_axis_free_layout_cols_zero_does_not_crash(canvas):
    """自由配置レイアウトではcols=0が渡されうる(行/列の概念が無いため)。
    _apply_shared_axis_tick_visibility内のdivmod(axis_index, cols)が
    ZeroDivisionErrorを起こさないことを確認する。"""
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 0, 0, [{'free_rect': (0.1, 0.1, 0.8, 0.8)}], layout_mode='free')
    canvas.update_single_axis(0, [ds], {}, rows=0, cols=0)  # 例外が出なければOK


# --- 項目C-003フェーズ2: update_all_axes_appearance_and_data
#     (パネルラベル/ダークモード切替のような、全Axesを均一に触るが軸の
#     所属自体は変えないトリガー専用の軽量な全体更新) ---

def test_update_all_axes_appearance_and_data_does_not_recreate_axes(canvas):
    """redraw_all()と異なりfig.clf()を経由しないため、Axesオブジェクト自体の
    アイデンティティは呼び出し前後で変わらない。"""
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}])
    axes_before = list(canvas.all_axes)

    canvas.update_all_axes_appearance_and_data([ds0, ds1], 1, 2, [{}, {}])

    assert canvas.all_axes[0] is axes_before[0]
    assert canvas.all_axes[1] is axes_before[1]


def test_update_all_axes_appearance_and_data_redraws_every_axis(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}])

    ds0.df = pd.DataFrame({"x": [1, 2, 3], "y": [3, 4, 5]})
    ds1.df = pd.DataFrame({"x": [1, 2, 3], "y": [5, 6, 7]})
    canvas.update_all_axes_appearance_and_data([ds0, ds1], 1, 2, [{}, {}])

    assert len(canvas.all_axes[0].lines[0].get_xdata()) == 3
    assert len(canvas.all_axes[1].lines[0].get_xdata()) == 3


def test_update_all_axes_appearance_and_data_returns_secondary_visible_global(canvas):
    ds_primary = Dataset(name="p", df=pd.DataFrame({"x": [1, 2], "y": [1, 2]}), x_col_name="x", y_col_name="y")
    ds_secondary = Dataset(name="s", df=pd.DataFrame({"x": [1, 2], "y": [10, 20]}), x_col_name="x", y_col_name="y",
                           use_secondary_y=True)
    canvas.redraw_all([ds_primary, ds_secondary], 1, 1, [{}])

    result = canvas.update_all_axes_appearance_and_data([ds_primary, ds_secondary], 1, 1, [{}])

    assert result is True
    assert canvas.all_secondary_axes[0] is not None


def test_update_all_axes_appearance_and_data_draws_panel_labels_when_enabled(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0, ds1], 1, 2, [{}, {}])

    canvas.update_all_axes_appearance_and_data([ds0, ds1], 1, 2, [{}, {}], panel_labels_enabled=True)

    texts0 = [t.get_text() for t in canvas.all_axes[0].texts]
    texts1 = [t.get_text() for t in canvas.all_axes[1].texts]
    assert "(a)" in texts0
    assert "(b)" in texts1


def test_update_all_axes_appearance_and_data_sets_facecolor_from_dark_mode(canvas):
    import matplotlib.colors as mcolors
    from gui.canvas import DARK_FIGURE_FACECOLOR
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 1, 1, [{}])

    canvas.dark_mode = True
    canvas.update_all_axes_appearance_and_data([ds], 1, 1, [{}])

    assert canvas.fig.get_facecolor() == pytest.approx(mcolors.to_rgba(DARK_FIGURE_FACECOLOR))


def test_update_all_axes_appearance_and_data_skips_tight_layout_for_free_layout(canvas, monkeypatch):
    """自由配置レイアウトではredraw_all()同様tight_layout()を呼ばない
    (呼ばれたら例外を投げるモックで検知する)。"""
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 0, 0, [{'free_rect': (0.1, 0.1, 0.8, 0.8)}], layout_mode='free')
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("tight_layout should not be called for free layout")),
    )
    canvas.update_all_axes_appearance_and_data([ds], 0, 0, [{'free_rect': (0.1, 0.1, 0.8, 0.8)}], layout_mode='free')


def test_update_all_axes_appearance_and_data_swallows_tight_layout_value_error(canvas, monkeypatch):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 1, 1, [{}])
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")),
    )
    canvas.update_all_axes_appearance_and_data([ds], 1, 1, [{}])  # 例外が伝播しなければOK


def test_update_all_axes_appearance_and_data_skips_axes_without_matching_settings(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 2, [{}])
    assert len(canvas.all_axes) == 2

    canvas.update_all_axes_appearance_and_data([ds], 1, 2, [{}])

    assert len(canvas.all_axes) == 2  # 引き続き2枚のまま(作り直されていない)


# --- 項目C-003フェーズ3b: add_free_axis/remove_last_free_axis
#     (自由配置レイアウトのサブプロット追加/削除専用の軽量パス) ---

def test_add_free_axis_appends_new_axis_without_touching_existing_ones(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    canvas.redraw_all([ds0], 0, 0, [{'free_rect': (0.1, 0.1, 0.4, 0.4)}], layout_mode='free')
    axis0_before = canvas.all_axes[0]

    canvas.add_free_axis([ds0], {'free_rect': (0.55, 0.55, 0.4, 0.4)})

    assert len(canvas.all_axes) == 2
    assert canvas.all_axes[0] is axis0_before
    assert canvas.all_secondary_axes[1] is None
    assert len(canvas.axis_is_date_x) == 2
    assert len(canvas.axis_is_category_x) == 2


def test_add_free_axis_draws_data_for_datasets_targeting_new_index(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all([ds0], 0, 0, [{'free_rect': (0.1, 0.1, 0.4, 0.4)}], layout_mode='free')

    canvas.add_free_axis([ds0, ds1], {'free_rect': (0.55, 0.55, 0.4, 0.4)})

    assert len(canvas.all_axes[1].lines) == 1


def test_add_free_axis_draws_panel_label_when_enabled(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    canvas.redraw_all([ds0], 0, 0, [{'free_rect': (0.1, 0.1, 0.4, 0.4)}], layout_mode='free')

    canvas.add_free_axis([ds0], {'free_rect': (0.55, 0.55, 0.4, 0.4)}, panel_labels_enabled=True)

    texts = [t.get_text() for t in canvas.all_axes[1].texts]
    assert "(b)" in texts


def test_remove_last_free_axis_removes_only_the_last_axis(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [5, 6]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    canvas.redraw_all(
        [ds0, ds1], 0, 0,
        [{'free_rect': (0.1, 0.1, 0.4, 0.4)}, {'free_rect': (0.55, 0.55, 0.4, 0.4)}],
        layout_mode='free',
    )
    axis0_before = canvas.all_axes[0]

    canvas.remove_last_free_axis([ds0, ds1])

    assert len(canvas.all_axes) == 1
    assert canvas.all_axes[0] is axis0_before
    assert len(canvas.fig.axes) == 1


def test_remove_last_free_axis_removes_secondary_axis_too(canvas):
    ds_primary = Dataset(name="p", df=pd.DataFrame({"x": [1, 2], "y": [1, 2]}), x_col_name="x", y_col_name="y",
                         subplot_target=0)
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=1)
    ds_secondary = Dataset(name="s", df=pd.DataFrame({"x": [1, 2], "y": [10, 20]}), x_col_name="x", y_col_name="y",
                           subplot_target=1, use_secondary_y=True)
    canvas.redraw_all(
        [ds_primary, ds0, ds_secondary], 0, 0,
        [{'free_rect': (0.1, 0.1, 0.4, 0.4)}, {'free_rect': (0.55, 0.55, 0.4, 0.4)}],
        layout_mode='free',
    )
    assert canvas.all_secondary_axes[1] is not None

    canvas.remove_last_free_axis([ds_primary, ds0, ds_secondary])

    assert len(canvas.all_axes) == 1
    assert len(canvas.fig.axes) == 1  # 副軸も一緒に取り除かれている


def test_remove_last_free_axis_cleans_up_annotation_state_for_removed_index(canvas):
    ds0 = Dataset(name="d0", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y",
                  subplot_target=0)
    settings1 = {
        'free_rect': (0.55, 0.55, 0.4, 0.4),
        'annotations': [{'type': 'text', 'xy': (1, 1), 'text': 'hi'}],
    }
    canvas.redraw_all([ds0], 0, 0, [{'free_rect': (0.1, 0.1, 0.4, 0.4)}, settings1], layout_mode='free')
    assert 1 in canvas._annotation_artists

    canvas.remove_last_free_axis([ds0])

    assert 1 not in canvas._annotation_artists


def test_remove_last_free_axis_noop_when_no_axes(canvas):
    canvas.remove_last_free_axis([])  # 例外が出なければOK
    assert canvas.all_axes == []


# --- 項目H-3: matplotlib(Figure)側の配色をgui/theme.pyのトークンと連動させる
#     (以前はcanvas.py独自のハードコード値を持ち、theme.pyのトークンとは
#     完全に無関係だった、H-0調査で判明した既知の不整合) ---

def test_figure_and_axes_facecolor_constants_match_theme_surface_token():
    from gui.canvas import (
        LIGHT_FIGURE_FACECOLOR, LIGHT_AXES_FACECOLOR,
        DARK_FIGURE_FACECOLOR, DARK_AXES_FACECOLOR,
    )
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS

    assert LIGHT_FIGURE_FACECOLOR == LIGHT_TOKENS['surface']
    assert LIGHT_AXES_FACECOLOR == LIGHT_TOKENS['surface']
    assert DARK_FIGURE_FACECOLOR == DARK_TOKENS['surface']
    assert DARK_AXES_FACECOLOR == DARK_TOKENS['surface']


def test_text_color_constants_match_theme_text_primary_token():
    from gui.canvas import LIGHT_TEXT_COLOR, DARK_TEXT_COLOR
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS

    assert LIGHT_TEXT_COLOR == LIGHT_TOKENS['text_primary']
    assert DARK_TEXT_COLOR == DARK_TOKENS['text_primary']


def test_legend_color_constants_match_theme_surface2_and_border_strong_tokens():
    from gui.canvas import (
        LIGHT_LEGEND_FACECOLOR, LIGHT_LEGEND_EDGECOLOR,
        DARK_LEGEND_FACECOLOR, DARK_LEGEND_EDGECOLOR,
    )
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS

    assert LIGHT_LEGEND_FACECOLOR == LIGHT_TOKENS['surface_2']
    assert LIGHT_LEGEND_EDGECOLOR == LIGHT_TOKENS['border_strong']
    assert DARK_LEGEND_FACECOLOR == DARK_TOKENS['surface_2']
    assert DARK_LEGEND_EDGECOLOR == DARK_TOKENS['border_strong']


def test_axes_facecolor_follows_dark_mode_flag(canvas):
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS
    import matplotlib.colors as mcolors

    ds = _make_dataset(3, show_point_labels=False)

    canvas.dark_mode = False
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas.all_axes[0].get_facecolor() == pytest.approx(
        mcolors.to_rgba(LIGHT_TOKENS['surface'])
    )

    canvas.dark_mode = True
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas.all_axes[0].get_facecolor() == pytest.approx(
        mcolors.to_rgba(DARK_TOKENS['surface'])
    )


def test_grid_lines_use_theme_border_strong_color(canvas):
    """
    以前グリッド線の色はmatplotlibの既定値(rcParams、テーマと無関係な固定の
    薄灰色)任せだった。border_strongトークンを明示的に使うことを確認する。
    """
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS
    import matplotlib.colors as mcolors

    ds = _make_dataset(3, show_point_labels=False)

    canvas.dark_mode = False
    canvas.redraw_all([ds], 1, 1, [{'grid_visible': True}])
    gridline = canvas.all_axes[0].xaxis.get_gridlines()[0]
    assert mcolors.to_rgba(gridline.get_color()) == pytest.approx(
        mcolors.to_rgba(LIGHT_TOKENS['border_strong'])
    )

    canvas.dark_mode = True
    canvas.redraw_all([ds], 1, 1, [{'grid_visible': True}])
    gridline = canvas.all_axes[0].xaxis.get_gridlines()[0]
    assert mcolors.to_rgba(gridline.get_color()) == pytest.approx(
        mcolors.to_rgba(DARK_TOKENS['border_strong'])
    )


# ============================================================================
# 以下、カバレッジギャップ埋め (missing lines) のための追加テスト。
# ============================================================================

def _make_secondary_dataset(name="sec", use_secondary_y=True):
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y",
                    use_secondary_y=use_secondary_y, plot_type='Line')


# --- redraw_all(): 早期returnとsettings不足時のスキップ ---

def test_redraw_all_returns_false_and_does_nothing_when_subplot_count_zero(canvas):
    result = canvas.redraw_all([], 0, 0, [])
    assert result is False
    assert canvas.all_axes == []


def test_redraw_all_skips_axes_without_matching_settings(canvas):
    """all_plot_settingsがサブプロット数より少ない場合、余った軸には
    データ描画・外観適用のどちらも行われずスキップされる(continue分岐)。"""
    import matplotlib.colors as mcolors
    from gui.theme import DARK_TOKENS
    canvas.dark_mode = True
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 2, [{}])
    assert len(canvas.all_axes) == 2
    assert canvas.all_axes[0].get_facecolor() == pytest.approx(mcolors.to_rgba(DARK_TOKENS['surface']))
    # 2つ目の軸は_apply_appearanceが呼ばれないため、ダークトークンの背景色になっていない
    assert canvas.all_axes[1].get_facecolor() != pytest.approx(mcolors.to_rgba(DARK_TOKENS['surface']))
    assert len(canvas.all_axes[1].lines) == 0


def test_redraw_all_returns_true_and_creates_secondary_axis_when_dataset_uses_secondary_y(canvas):
    ds = _make_secondary_dataset()
    result = canvas.redraw_all([ds], 1, 1, [{}])
    assert result is True
    assert canvas.all_secondary_axes[0] is not None


# --- redraw_all(): データセットの表示/非表示トグル (項目C-907) ---

def test_redraw_all_excludes_hidden_dataset_from_axes(canvas):
    """visible=Falseのデータセットは描画対象から除外され、Axesにも
    line/artistが残らない(データそのものは削除されず保持されたまま)。"""
    ds_visible = _make_dataset(3, show_point_labels=False)
    ds_visible.name = "visible_ds"
    ds_hidden = _make_dataset(3, show_point_labels=False)
    ds_hidden.name = "hidden_ds"
    ds_hidden.visible = False

    canvas.redraw_all([ds_visible, ds_hidden], 1, 1, [{}])

    assert ds_visible.artist is not None
    # 非表示のデータセットは描画自体が行われないため、artistは更新されずNoneのまま
    assert ds_hidden.artist is None
    assert len(canvas.all_axes[0].lines) == 1


def test_redraw_all_all_datasets_hidden_draws_nothing(canvas):
    """全データセットが非表示の場合でも、subplot_count>0であればAxes自体は
    作られる(空のグラフになるだけでクラッシュしない)。"""
    ds = _make_dataset(3, show_point_labels=False)
    ds.visible = False

    result = canvas.redraw_all([ds], 1, 1, [{}])

    assert len(canvas.all_axes) == 1
    assert len(canvas.all_axes[0].lines) == 0
    assert result is False


def test_redraw_all_missing_visible_attr_defaults_to_shown(canvas):
    """visible属性がインスタンスの__dict__に無い(この機能追加前のpickleを模倣)
    Datasetでも、redraw_all側のgetattr(ds, 'visible', True)フォールバックにより
    通常通り描画される(後方互換の保険。実際にはDataset.__setstate__/from_dict
    側でも既に補われるが、canvas.py単体としての安全網も確認する)。"""
    ds = _make_dataset(3, show_point_labels=False)
    del ds.__dict__['visible']

    canvas.redraw_all([ds], 1, 1, [{}])

    assert len(canvas.all_axes[0].lines) == 1


def test_redraw_all_swallows_tight_layout_value_error(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")),
    )
    # 例外が伝播せず正常に完了することを確認する
    canvas.redraw_all([ds], 1, 1, [{}])


def test_update_appearance_only_swallows_tight_layout_value_error(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")),
    )
    # 例外が伝播せず正常に完了することを確認する
    canvas.update_appearance_only([{}])


# --- tight_layout()のFileNotFoundError(実機フィードバック: 環境依存の
#     フォント欠落によるクラッシュ)を3箇所とも吸収することの回帰テスト ---

def test_redraw_all_swallows_tight_layout_file_not_found_error(canvas, monkeypatch):
    """
    実機フィードバック(ログで確認): 一部環境ではmatplotlib自体のインストールが
    不完全でフォールバック用フォント(LastResortHE-Regular.ttf)が欠落しており、
    tight_layout()がFileNotFoundErrorで失敗してアプリ全体がクラッシュしていた。
    """
    ds = _make_dataset(3, show_point_labels=False)
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("LastResortHE-Regular.ttf")),
    )
    canvas.redraw_all([ds], 1, 1, [{}])


def test_update_appearance_only_swallows_tight_layout_file_not_found_error(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("LastResortHE-Regular.ttf")),
    )
    canvas.update_appearance_only([{}])


def test_update_all_axes_appearance_and_data_swallows_tight_layout_file_not_found_error(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    monkeypatch.setattr(
        canvas.fig, "tight_layout",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("LastResortHE-Regular.ttf")),
    )
    canvas.update_all_axes_appearance_and_data([ds], 1, 1, [{}])


# --- _safe_draw(): self.draw()の例外を握りつぶさず必ずログに残す(実機調査) ---

def test_safe_draw_swallows_exception_and_does_not_propagate(canvas, monkeypatch):
    """
    実機調査(macOSの一部環境で、X/Y軸のmin/max変更が反映されないバグ):
    matplotlibのdraw_idle()経由の描画は、matplotlib自身の内部で例外を
    traceback.print_exc()だけで握りつぶしており(コンソールを持たない
    windowedビルドでは行き場がなくログにも残らない)、直接呼んでいる
    self.draw()にはそれすら無かった。_safe_draw()に統一し、例外が
    起きても最低限アプリを止めず、こちらのloggerには必ず記録されることを
    確認する。
    """
    monkeypatch.setattr(canvas, "draw", lambda: (_ for _ in ()).throw(FileNotFoundError("boom")))
    canvas._safe_draw()  # 例外が伝播しなければOK


def test_safe_draw_logs_the_exception(canvas, monkeypatch, caplog):
    monkeypatch.setattr(canvas, "draw", lambda: (_ for _ in ()).throw(FileNotFoundError("boom")))
    with caplog.at_level("ERROR"):
        canvas._safe_draw()
    assert any("boom" in record.message or "描画" in record.message for record in caplog.records)


def test_safe_draw_calls_draw_normally_when_no_exception(canvas):
    calls = []
    canvas.draw = lambda: calls.append(1)
    canvas._safe_draw()
    assert calls == [1]


def test_redraw_all_uses_safe_draw_and_does_not_crash_when_draw_fails(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    monkeypatch.setattr(canvas, "draw", lambda: (_ for _ in ()).throw(FileNotFoundError("boom")))
    canvas.redraw_all([ds], 1, 1, [{}])  # 例外が伝播しなければOK


def test_update_appearance_only_uses_safe_draw_and_does_not_crash_when_draw_fails(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    monkeypatch.setattr(canvas, "draw", lambda: (_ for _ in ()).throw(FileNotFoundError("boom")))
    canvas.update_appearance_only([{}])  # 例外が伝播しなければOK


def test_update_all_axes_appearance_and_data_uses_safe_draw_and_does_not_crash_when_draw_fails(canvas, monkeypatch):
    ds = _make_dataset(3, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    monkeypatch.setattr(canvas, "draw", lambda: (_ for _ in ()).throw(FileNotFoundError("boom")))
    canvas.update_all_axes_appearance_and_data([ds], 1, 1, [{}])  # 例外が伝播しなければOK


# --- _draw_annotations(): 削除失敗/描画失敗が例外を伝播させない ---

def test_draw_annotations_remove_failure_is_swallowed(canvas):
    ds = _make_dataset(2, show_point_labels=False)
    settings = {'annotations': [{'type': 'text', 'text': 'hello', 'xy': (0, 0), 'color': '#000000'}]}
    canvas.redraw_all([ds], 1, 1, [settings])
    artist = canvas._annotation_artists[0][0]
    artist.remove = lambda: (_ for _ in ()).throw(ValueError("cannot remove"))
    # 前回分の削除に失敗しても、例外を伝播させず描き直しが続行される
    canvas._draw_annotations(canvas.all_axes[0], 0, settings)


def test_draw_annotations_exception_during_draw_is_logged_and_skipped(canvas, caplog):
    ds = _make_dataset(2, show_point_labels=False)
    # 'xy'キーの無いarrow注釈はann['xy']でKeyErrorになるが、except Exceptionで
    # 捕捉されログに残るだけで、例外は伝播せず他の描画に影響しない。
    settings = {'annotations': [{'type': 'arrow', 'text': 'bad'}]}
    with caplog.at_level("ERROR"):
        canvas.redraw_all([ds], 1, 1, [settings])
    assert canvas._annotation_artists[0] == []


# --- _enable_element_picking(): BarContainerのpatches個別ピッカー設定 ---

def test_bar_plot_type_enables_picking_on_each_patch(canvas):
    from matplotlib.container import BarContainer
    df = pd.DataFrame({"x": ["a", "b", "c"], "y": [1, 2, 3]})
    ds = Dataset(name="bar_ds", df=df, x_col_name="x", y_col_name="y", plot_type='Bar', color='#112233')
    canvas.redraw_all([ds], 1, 1, [{}])
    assert isinstance(ds.artist, BarContainer)
    for patch in ds.artist.patches:
        assert patch.get_picker() == 5


# --- _add_gradient_fill(): X/Y範囲が潰れるケースの補正 ---

def test_add_gradient_fill_handles_all_x_equal(canvas):
    ax = canvas.fig.add_subplot(1, 1, 1)
    im = canvas._add_gradient_fill(ax, [2.0, 2.0, 2.0], [1.0, 2.0, 3.0], '#112233', '#ffffff', 0.5, baseline=0.0)
    assert im is not None


def test_add_gradient_fill_handles_all_y_equal_to_baseline(canvas):
    ax = canvas.fig.add_subplot(1, 1, 1)
    im = canvas._add_gradient_fill(ax, [0.0, 1.0, 2.0], [0.0, 0.0, 0.0], '#112233', '#ffffff', 0.5, baseline=0.0)
    assert im is not None


# --- ウォーターフォールのベースライン計算: 空データセットはスキップされる ---

def test_waterfall_baseline_calculation_skips_dataset_with_empty_data(canvas):
    df_empty = pd.DataFrame({"x": pd.Series([], dtype=float), "y": pd.Series([], dtype=float)})
    ds_empty = Dataset(name="empty_wf", df=df_empty, x_col_name="x", y_col_name="y",
                        plot_type='Line', waterfall_enabled=True, waterfall_offset_y=1.0)
    df_data = pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 2.0]})
    ds_data = Dataset(name="data_wf", df=df_data, x_col_name="x", y_col_name="y",
                       plot_type='Line', waterfall_enabled=True, waterfall_offset_y=1.0)
    # 空のデータセットが混ざっていてもベースライン計算がクラッシュしない
    canvas.redraw_all([ds_empty, ds_data], 1, 1, [{}])
    assert len(ds_data.artist.get_xdata()) == 2


# --- _apply_appearance()を通じたX軸/Y軸独立の小数点以下桁数(実機フィードバック) ---

def test_apply_appearance_x_and_y_tick_decimals_are_independent(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{'x_tick_decimals': 1, 'y_tick_decimals': 3}])
    ax = canvas.all_axes[0]
    assert ax.xaxis.get_major_formatter()(3.14159) == "3.1"
    assert ax.yaxis.get_major_formatter()(3.14159) == "3.142"


def test_apply_appearance_tick_decimals_default_leaves_formatter_unchanged(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    from matplotlib.ticker import FormatStrFormatter
    assert not isinstance(ax.xaxis.get_major_formatter(), FormatStrFormatter)
    assert not isinstance(ax.yaxis.get_major_formatter(), FormatStrFormatter)


# --- ウォーターフォールのzorderが軸の枠線/目盛を隠さないこと(実機フィードバック) ---

def test_waterfall_zorder_stays_below_default_spine_and_tick_zorder(canvas):
    """
    実機フィードバック(バグ報告): 「ウォーターフォール適用すると枠とかメモリが
    隠れる」。以前は積み重ね数に比例して際限なく大きくなるzorderを使っていた
    ため、トレースが数件あるだけでオクルージョン用fill_betweenのzorderが
    matplotlib既定のスパインzorder(2.5)・目盛zorder(約2.01)を超え、背景色の
    塗りつぶしがそれらを覆い隠していた。トレース本体・オクルージョン用
    fill_betweenの両方のzorderが、トレース数によらず常にそれらを下回ることを
    確認する。
    """
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    datasets = [_make_waterfall_dataset(f"wf{i}", x, y, offset_x=0.5, offset_y=1.0) for i in range(6)]

    canvas.redraw_all(datasets, 1, 1, [{}])

    ax = canvas.all_axes[0]
    spine_zorder = ax.spines['bottom'].get_zorder()
    tick_zorder = ax.xaxis.get_major_ticks()[0].tick1line.get_zorder()
    safe_ceiling = min(spine_zorder, tick_zorder)

    for ds in datasets:
        assert ds.artist.get_zorder() < safe_ceiling
    for collection in ax.collections:  # fill_between()が積むPolyCollection群
        assert collection.get_zorder() < safe_ceiling


def test_waterfall_zorder_preserves_relative_stacking_order(canvas):
    """積み重ねインデックスが小さい(手前の)トレースほど高いzorderを持ち、
    その相対順序がzorderの正規化後も保たれることを確認する。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    datasets = [_make_waterfall_dataset(f"wf{i}", x, y, offset_x=0.5, offset_y=1.0) for i in range(4)]

    canvas.redraw_all(datasets, 1, 1, [{}])

    zorders = [ds.artist.get_zorder() for ds in datasets]
    assert zorders == sorted(zorders, reverse=True)  # 先頭(手前)ほど高い


# --- ウォーターフォールのオクルージョンON/OFF切り替え(実機フィードバック) ---

def test_waterfall_occlusion_enabled_draws_background_fill(canvas):
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds0 = _make_waterfall_dataset("wf0", x, y, waterfall_occlusion_enabled=True)
    ds1 = _make_waterfall_dataset("wf1", x, y, waterfall_occlusion_enabled=True)

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    ax = canvas.all_axes[0]
    assert len(ax.collections) > 0  # fill_between()によるPolyCollectionが存在する


def test_waterfall_occlusion_disabled_skips_background_fill(canvas):
    """実機フィードバック: 「手前が奥を隠す(オクルージョン)はon/off切り替え
    可能にして」。waterfall_occlusion_enabled=Falseならfill_betweenを描かない。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds0 = _make_waterfall_dataset("wf0", x, y, waterfall_occlusion_enabled=False)
    ds1 = _make_waterfall_dataset("wf1", x, y, waterfall_occlusion_enabled=False)

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    ax = canvas.all_axes[0]
    assert len(ax.collections) == 0


def test_waterfall_occlusion_toggle_is_per_dataset(canvas):
    """オクルージョンのON/OFFは他の設定と同じくデータセット単位のため、
    同じ軸内で混在させた場合も個別に反映される。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds0 = _make_waterfall_dataset("wf0", x, y, waterfall_occlusion_enabled=True)
    ds1 = _make_waterfall_dataset("wf1", x, y, waterfall_occlusion_enabled=False)

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    ax = canvas.all_axes[0]
    assert len(ax.collections) == 1  # ds0の分だけfill_betweenが描かれる


# --- 平滑化 (CubicSpline): 成功時/失敗時のフォールバック経路 ---

def _make_smoothing_dataset(x, y, smoothing=True, gradient_enabled=False,
                             gradient_target='line', plot_type='Line'):
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(name="smooth_ds", df=df, x_col_name="x", y_col_name="y", plot_type=plot_type,
                    color='#112233', gradient_color2='#ffffff', smoothing=smoothing,
                    gradient_enabled=gradient_enabled, gradient_target=gradient_target)


def test_smoothing_success_draws_cubicspline_curve_without_gradient(canvas):
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert isinstance(ds.artist, Line2D)
    # 平滑化された曲線は元の4点より多い点数(200点)で構成される
    assert len(ds.artist.get_xdata()) == 200


def test_smoothing_not_applied_for_scatter_plot_type(canvas):
    """平滑化は「線で結んだ曲線」を滑らかにする機能のためScatterには適用しない
    (過去はplot_typeを問わず適用し、Scatterのマーカーが平滑化した線に丸ごと
    置き換わってしまう実害があったため修正)。"""
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], plot_type='Scatter')
    canvas.redraw_all([ds], 1, 1, [{}])
    assert hasattr(ds.artist, 'get_offsets')  # PathCollection(通常のScatter)のまま
    assert len(ds.artist.get_offsets()) == 4  # 元のデータ点数のまま(平滑化されていない)


def test_smoothing_not_applied_for_bar_plot_type(canvas):
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], plot_type='Bar')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.patches) == 4  # 通常のBarのまま(4本の棒)


def test_smoothing_not_applied_for_area_plot_type(canvas):
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], plot_type='Area')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert _poly_collections(ax) != []  # fill_between(Areaの塗りつぶし)が描画されている


def test_smoothing_disables_picking_on_smoothed_artist(canvas):
    """平滑化曲線(元データと1:1対応しない200点のCubicSpline補間点)は、
    データカーソルのクリック選択が誤った/無関係な行を指してしまうため、
    ピッカー自体を有効化しない(cursor_mixin._on_pickに到達させない)。"""
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist.get_picker() is None


def test_non_smoothed_line_keeps_picking_enabled(canvas):
    """平滑化していない通常のLineは、これまで通りクリック選択が有効。"""
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], smoothing=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist.get_picker() == 5


def test_smoothed_dataset_registered_in_non_pickable_dataset_ids(canvas):
    """平滑化曲線のdataset_idは_non_pickable_dataset_idsに登録される
    (cursor_mixin.pyの「データカーソルモード」ON操作が、この集合を見て
    一括set_picker(5)の対象から除外するために参照する)。"""
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id in canvas._non_pickable_dataset_ids


def test_non_pickable_dataset_ids_cleared_when_smoothing_disabled_on_redraw(canvas):
    """平滑化をOFFに戻して再描画すると、_non_pickable_dataset_idsから
    そのdataset_idが取り除かれる(古い状態が残ってピッカーが永久に無効化
    されたままにならないこと)。"""
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id in canvas._non_pickable_dataset_ids

    ds.smoothing = False
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas._non_pickable_dataset_ids
    assert ds.artist.get_picker() == 5


def test_non_pickable_dataset_ids_cleared_on_full_redraw(canvas):
    """redraw_all()の冒頭で_non_pickable_dataset_idsが全クリアされる
    (downsample_index_map等の他の再描画状態と同じ扱い)。"""
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert canvas._non_pickable_dataset_ids  # 空でないことを確認

    canvas.redraw_all([], 1, 1, [{}])  # 全データセット削除後の再描画
    assert canvas._non_pickable_dataset_ids == set()


def test_smoothing_cubicspline_failure_keeps_picking_enabled(canvas):
    """CubicSpline失敗時のフォールバック(元データ点のまま描画)は、平滑化された
    わけではないので通常通りクリック選択を有効にしてよい。"""
    ds = _make_smoothing_dataset([0.0, 0.0, 1.0, 2.0], [0.0, 1.0, 2.0, 3.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist.get_picker() == 5


def test_smoothing_success_with_gradient_uses_linecollection(canvas):
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0],
                                  gradient_enabled=True, gradient_target='line')
    canvas.redraw_all([ds], 1, 1, [{}])
    assert isinstance(ds.artist, LineCollection)


def test_smoothing_success_with_line_plus_scatter_overlays_markers(canvas):
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], plot_type='Line+Scatter')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert isinstance(ds.artist, Line2D)  # 平滑化した線
    assert len(ax.collections) >= 1  # 元データ点のscatterマーカーも重ねて描画される


def test_smoothing_cubicspline_failure_falls_back_to_plain_line(canvas):
    """xに重複値があるとCubicSplineがValueErrorを送出し、平滑化なしのプロットにフォールバックする"""
    ds = _make_smoothing_dataset([0.0, 0.0, 1.0, 2.0], [0.0, 1.0, 2.0, 3.0])
    canvas.redraw_all([ds], 1, 1, [{}])
    assert isinstance(ds.artist, Line2D)
    assert len(ds.artist.get_xdata()) == 4  # 元のデータ点数のまま(平滑化されていない)


def test_smoothing_cubicspline_failure_with_gradient_falls_back_to_gradient_line(canvas):
    ds = _make_smoothing_dataset([0.0, 0.0, 1.0, 2.0], [0.0, 1.0, 2.0, 3.0],
                                  gradient_enabled=True, gradient_target='line')
    canvas.redraw_all([ds], 1, 1, [{}])
    assert isinstance(ds.artist, LineCollection)
    assert len(ds.artist.get_array()) == 3  # 元の4点、3セグメント分(平滑化前のまま)


def test_line_plus_scatter_gradient_non_smoothed_overlays_scatter_on_gradient_line(canvas):
    ds = _make_smoothing_dataset([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], smoothing=False,
                                  gradient_enabled=True, gradient_target='both', plot_type='Line+Scatter')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert isinstance(ds.artist, LineCollection)
    assert len(ax.lines) == 0  # 通常のLine2Dは使わない
    from matplotlib.collections import PathCollection
    assert any(isinstance(c, PathCollection) for c in ax.collections)  # マーカーのscatter


def test_area_gradient_target_line_only_uses_plain_fill_between_not_gradient_fill(canvas):
    ds = _make_area_dataset(gradient_enabled=True, gradient_target='line')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.images) == 0  # 塗りはグラデーション化されない(通常のfill_between)
    assert any(isinstance(c, LineCollection) for c in ax.collections)  # 輪郭線はグラデーション化される
    from matplotlib.collections import PolyCollection
    assert any(isinstance(c, PolyCollection) for c in ax.collections)  # fill_betweenの塗り


# --- set_highlighted_points(): データ⇔グラフの双方向ハイライト ---

def test_set_highlighted_points_removes_previous_artist_on_second_call(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.set_highlighted_points(ds, [0, 1])
    first_artist = canvas._highlight_artists[ds.dataset_id]
    canvas.set_highlighted_points(ds, [2, 3])
    second_artist = canvas._highlight_artists[ds.dataset_id]
    assert first_artist is not second_artist


def test_set_highlighted_points_remove_failure_is_swallowed(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.set_highlighted_points(ds, [0, 1])
    old_artist = canvas._highlight_artists[ds.dataset_id]
    old_artist.remove = lambda: (_ for _ in ()).throw(ValueError("boom"))
    # 削除に失敗しても例外を伝播させず、新しいハイライトに切り替えられる
    canvas.set_highlighted_points(ds, [2])
    assert ds.dataset_id in canvas._highlight_artists


def test_set_highlighted_points_empty_indices_clears_highlight_without_error(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.set_highlighted_points(ds, [0, 1])
    canvas.set_highlighted_points(ds, [])
    assert ds.dataset_id not in canvas._highlight_artists


def test_set_highlighted_points_axis_index_out_of_range_is_noop(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    ds.subplot_target = 5  # all_axesの範囲外
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.set_highlighted_points(ds, [0])
    assert ds.dataset_id not in canvas._highlight_artists


def test_set_highlighted_points_on_secondary_axis(canvas):
    ds = _make_secondary_dataset(name="sec")
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.set_highlighted_points(ds, [0])
    assert ds.dataset_id in canvas._highlight_artists
    secondary_ax = canvas.all_secondary_axes[0]
    assert canvas._highlight_artists[ds.dataset_id] in secondary_ax.collections


def test_set_highlighted_points_index_conversion_exception_is_swallowed(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    # ハッシュ不可な要素(リスト)を渡すと `idx in visible_index` でTypeErrorになるが、
    # 例外を伝播させず単に何もハイライトしない扱いになる。
    canvas.set_highlighted_points(ds, [[1, 2]])
    assert ds.dataset_id not in canvas._highlight_artists


def test_set_highlighted_points_draws_scatter_with_expected_positions(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    canvas.set_highlighted_points(ds, [1, 3])
    artist = canvas._highlight_artists[ds.dataset_id]
    offsets = artist.get_offsets()
    assert list(offsets[:, 0]) == pytest.approx([1.0, 3.0])
    assert list(offsets[:, 1]) == pytest.approx([1.0, 3.0])


# --- _draw_point_labels(): 引数省略時のデフォルト、カスタム列、NaNスキップ ---

def test_draw_point_labels_defaults_to_dataset_xy_when_args_omitted(canvas):
    ds = _make_dataset(3, show_point_labels=True)
    ax = canvas.fig.add_subplot(1, 1, 1)
    canvas._draw_point_labels(ax, ds)  # x_data/y_dataを省略 → ds.x_data/ds.y_dataを使う
    assert len(ax.texts) == 3


def test_draw_point_labels_uses_custom_column_and_skips_empty_text(canvas):
    df = pd.DataFrame({
        "x": [0.0, 1.0, 2.0],
        "y": [0.0, 1.0, 2.0],
        "label": ["foo", None, "baz"],
    })
    ds = Dataset(name="d", df=df, x_col_name="x", y_col_name="y",
                 show_point_labels=True, point_label_col_name="label")
    ax = canvas.fig.add_subplot(1, 1, 1)
    canvas._draw_point_labels(ax, ds, x_data=ds.x_data, y_data=ds.y_data)
    texts = [t.get_text() for t in ax.texts]
    # NaN(None)のラベル値は空文字列になり描画がスキップされる(2番目の点)
    assert texts == ["foo", "baz"]


def test_draw_point_labels_skips_nan_coordinates(canvas):
    df = pd.DataFrame({"x": [0.0, float('nan'), 2.0], "y": [0.0, 1.0, 2.0]})
    ds = Dataset(name="d", df=df, x_col_name="x", y_col_name="y", show_point_labels=True)
    ax = canvas.fig.add_subplot(1, 1, 1)
    canvas._draw_point_labels(ax, ds, x_data=ds.x_data, y_data=ds.y_data)
    assert len(ax.texts) == 2  # X座標がNaNの点はスキップされる


# --- _apply_appearance(): 手動軸範囲・日付軸・カテゴリ軸・目盛り間隔 ---

def test_apply_appearance_manual_xlim_when_x_autoscale_false(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    settings = {'x_autoscale': False, 'x_min': -5, 'x_max': 15}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    assert ax.get_xlim() == pytest.approx((-5, 15))


def test_apply_appearance_manual_ylim_when_y_autoscale_false(canvas):
    ds = _make_dataset(3, show_point_labels=False)
    settings = {'y_autoscale': False, 'y_min': -5, 'y_max': 15}
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    assert ax.get_ylim() == pytest.approx((-5, 15))


def test_apply_appearance_date_x_axis_uses_autodate_locator_and_concise_formatter(canvas):
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    df = pd.DataFrame({"x": dates, "y": [1, 2, 3, 4, 5]})
    ds = Dataset(name="d", df=df, x_col_name="x", y_col_name="y")
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert isinstance(ax.xaxis.get_major_locator(), mdates.AutoDateLocator)
    assert isinstance(ax.xaxis.get_major_formatter(), mdates.ConciseDateFormatter)
    assert isinstance(ax.xaxis.get_minor_locator(), ticker.NullLocator)


def test_apply_appearance_category_x_axis_preserves_matplotlib_auto_locator(canvas):
    df = pd.DataFrame({"x": ["a", "b", "c"], "y": [1, 2, 3]})
    ds = Dataset(name="d", df=df, x_col_name="x", y_col_name="y", plot_type='Bar')
    canvas.redraw_all([ds], 1, 1, [{'x_major_tick_mode': 1, 'x_major_tick_interval': 2}])
    ax = canvas.all_axes[0]
    # 数値専用のx_major_tick_mode=1を指定していても、カテゴリ軸ではmatplotlibが
    # 自動設定したLocator/Formatterがそのまま使われ、MultipleLocatorには上書きされない
    assert not isinstance(ax.xaxis.get_major_locator(), ticker.MultipleLocator)
    assert isinstance(ax.xaxis.get_minor_locator(), ticker.NullLocator)


def test_apply_appearance_manual_major_tick_interval_for_x_and_y(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    settings = {
        'x_major_tick_mode': 1, 'x_major_tick_interval': 2,
        'y_major_tick_mode': 1, 'y_major_tick_interval': 3,
    }
    canvas.redraw_all([ds], 1, 1, [settings])
    ax = canvas.all_axes[0]
    x_locator = ax.xaxis.get_major_locator()
    y_locator = ax.yaxis.get_major_locator()
    assert isinstance(x_locator, ticker.MultipleLocator)
    assert x_locator._edge.step == pytest.approx(2)
    assert isinstance(y_locator, ticker.MultipleLocator)
    assert y_locator._edge.step == pytest.approx(3)


# --- _apply_appearance(): 目盛(目盛線本体)・目盛数値の表示/非表示切り替え ---

def test_apply_appearance_ticks_visible_default_shows_ticks_and_labels(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert ax.xaxis._major_tick_kw.get('tick1On', True) is True
    assert ax.xaxis._major_tick_kw.get('label1On', True) is True


def test_apply_appearance_ticks_visible_false_hides_tick_marks_but_not_labels(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{'ticks_visible': False}])
    ax = canvas.all_axes[0]
    assert ax.xaxis._major_tick_kw.get('tick1On') is False
    assert ax.yaxis._major_tick_kw.get('tick1On') is False
    assert ax.xaxis._major_tick_kw.get('label1On', True) is True


def test_apply_appearance_tick_labels_visible_false_hides_numbers_but_not_marks(canvas):
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{'tick_labels_visible': False}])
    ax = canvas.all_axes[0]
    assert ax.xaxis._major_tick_kw.get('label1On') is False
    assert ax.yaxis._major_tick_kw.get('label1On') is False
    assert ax.xaxis._major_tick_kw.get('tick1On', True) is True


def test_apply_appearance_ticks_visible_true_does_not_override_shared_axis_label_hiding(canvas):
    """
    tick_labels_visible=True(既定)であっても、軸共有(share_x_axis)が
    内側のサブプロットの目盛数値を隠した結果を上書きしないことを確認する
    回帰テスト。_apply_shared_axis_tick_visibility()は_apply_appearance()の
    「後」に適用される(redraw_all()側の呼び出し順)ことで、この優先順位を
    保証している。
    """
    ds = _make_dataset(5, show_point_labels=False)
    settings = [{'tick_labels_visible': True}, {'tick_labels_visible': True}]
    canvas.redraw_all([ds], 2, 1, settings, share_x_axis=True)
    # 2行1列レイアウトでshare_x_axis=Trueの場合、_apply_shared_axis_tick_visibilityは
    # 最下行以外(=1行目、axis_index 0)のX軸目盛数値を隠す仕様のため、
    # 「軸共有の対象になる側で実際に隠れていること」を確認する。
    first_ax = canvas.all_axes[0]
    assert first_ax.xaxis._major_tick_kw.get('label1On') is False


def test_apply_appearance_re_enabling_tick_visibility_after_disabling_actually_restores_it(canvas):
    """
    実機フィードバック(バグ報告): 「目盛と数字の表示非表示がちゃんと
    切り替わらない」。ax.tick_params()が設定した値はax.cla()を挟んでも
    保持され続けるため、「Falseの時だけ明示的に隠す」実装では、一度
    非表示にしてから再度表示に戻しても反映されなかった。同じAxesを
    使い回すupdate_appearance_only()(項目C-003の軽量再描画パス、実際に
    このバグが起きたのはこの経路)で、非表示→表示の順に設定し直すと
    正しく復元されることを確認する。
    """
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{'x_ticks_visible': False, 'x_tick_labels_visible': False}])
    ax = canvas.all_axes[0]
    assert ax.xaxis._major_tick_kw.get('tick1On') is False
    assert ax.xaxis._major_tick_kw.get('label1On') is False

    # 同じAxesを使い回す軽量パスで、今度は表示に戻す
    canvas.update_appearance_only([{'x_ticks_visible': True, 'x_tick_labels_visible': True}])

    assert ax.xaxis._major_tick_kw.get('tick1On') is True
    assert ax.xaxis._major_tick_kw.get('label1On') is True


def test_update_appearance_only_reapplies_shared_axis_tick_suppression(canvas):
    """
    update_appearance_only()もredraw_all()と同様、_apply_appearance()の後に
    軸共有による目盛数値抑制を再適用することを確認する(以前はこの経路に
    軸共有の再適用が無く、軽量再描画のたびに内側の目盛数値が復活して
    しまう可能性があった)。
    """
    ds = _make_dataset(5, show_point_labels=False)
    settings = [{}, {}]
    canvas.redraw_all([ds], 2, 1, settings, share_x_axis=True)
    first_ax = canvas.all_axes[0]
    assert first_ax.xaxis._major_tick_kw.get('label1On') is False

    canvas.update_appearance_only(settings, rows=2, cols=1, share_x_axis=True)

    assert first_ax.xaxis._major_tick_kw.get('label1On') is False


def test_apply_appearance_x_and_y_tick_visibility_are_independent(canvas):
    """実機フィードバック: 「X軸Y軸一括じゃなくてそれぞれで設定できるように」。"""
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{
        'x_ticks_visible': False, 'x_tick_labels_visible': True,
        'y_ticks_visible': True, 'y_tick_labels_visible': False,
    }])
    ax = canvas.all_axes[0]
    assert ax.xaxis._major_tick_kw.get('tick1On') is False
    assert ax.xaxis._major_tick_kw.get('label1On') is True
    assert ax.yaxis._major_tick_kw.get('tick1On') is True
    assert ax.yaxis._major_tick_kw.get('label1On') is False


def test_apply_appearance_falls_back_to_legacy_combined_tick_visibility_keys(canvas):
    """
    後方互換: v1.3.2で保存されたプロジェクト(軸共通のticks_visible/
    tick_labels_visibleキーのみ)を読み込んだ場合、その値がX/Y両方に
    適用されること。
    """
    ds = _make_dataset(5, show_point_labels=False)
    canvas.redraw_all([ds], 1, 1, [{'ticks_visible': False, 'tick_labels_visible': False}])
    ax = canvas.all_axes[0]
    assert ax.xaxis._major_tick_kw.get('tick1On') is False
    assert ax.xaxis._major_tick_kw.get('label1On') is False
    assert ax.yaxis._major_tick_kw.get('tick1On') is False
    assert ax.yaxis._major_tick_kw.get('label1On') is False


# --- _apply_appearance(): 凡例(第2Y軸のみ/主+第2Y軸結合/非表示時の削除) ---

def test_apply_appearance_legend_shows_secondary_only_when_no_primary_data(canvas):
    ds = _make_secondary_dataset(name="sec")
    canvas.redraw_all([ds], 1, 1, [{'legend_visible': True}])
    secondary_ax = canvas.all_secondary_axes[0]
    legend = secondary_ax.get_legend()
    assert legend is not None
    assert [t.get_text() for t in legend.get_texts()] == ['sec']


def test_apply_appearance_legend_combines_primary_and_secondary_when_both_present(canvas):
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]})
    ds_primary = Dataset(name="prim", df=df, x_col_name="x", y_col_name="y", plot_type='Line')
    ds_secondary = _make_secondary_dataset(name="sec")
    canvas.redraw_all([ds_primary, ds_secondary], 1, 1, [{'legend_visible': True}])
    ax = canvas.all_axes[0]
    legend = ax.get_legend()
    assert legend is not None
    labels = {t.get_text() for t in legend.get_texts()}
    assert labels == {"prim", "sec"}


def test_apply_appearance_legend_removed_from_secondary_axis_when_visible_false(canvas):
    ds = _make_secondary_dataset(name="sec")
    canvas.redraw_all([ds], 1, 1, [{}])  # legend_visibleは既定でTrue
    secondary_ax = canvas.all_secondary_axes[0]
    assert secondary_ax.get_legend() is not None
    canvas.update_appearance_only([{'legend_visible': False}])
    assert secondary_ax.get_legend() is None


# --- 表示用ダウンサンプリング(LTTB、項目C-1001) ---

def _make_large_dataset(n, plot_type="Line", **kwargs):
    x = np.arange(n, dtype=float)
    y = np.sin(x / 100.0)
    return Dataset(name="big", df=pd.DataFrame({"x": x, "y": y}),
                    x_col_name="x", y_col_name="y", plot_type=plot_type, **kwargs)


def test_downsampling_applied_above_threshold_for_line(canvas):
    ds = _make_large_dataset(LTTB_DOWNSAMPLE_THRESHOLD + 1)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id in canvas.downsample_index_map
    assert len(ds.artist.get_xdata()) == LTTB_DOWNSAMPLE_TARGET_POINTS


def test_downsampling_not_applied_below_threshold(canvas):
    ds = _make_large_dataset(LTTB_DOWNSAMPLE_THRESHOLD - 1)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas.downsample_index_map
    assert len(ds.artist.get_xdata()) == LTTB_DOWNSAMPLE_THRESHOLD - 1


def test_downsampling_not_applied_for_scatter(canvas):
    """LTTBは「線で結んだ形状」を保つアルゴリズムであり、点の疎密自体が情報
    であるScatterに適用すると実際のデータ密度分布が失われるため、Scatterは
    間引き対象から除外する(過去はScatterも対象に含めていたが設計上の
    見落としだったため修正)。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    ds = _make_large_dataset(n, plot_type="Scatter")
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas.downsample_index_map
    assert len(ds.artist.get_offsets()) == n


def test_downsampling_not_applied_for_line_plus_scatter(canvas):
    """Line+Scatterもマーカーの疎密が情報のため、Scatterと同様に間引き対象外。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    ds = _make_large_dataset(n, plot_type="Line+Scatter")
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas.downsample_index_map
    assert len(ds.artist.get_xdata()) == n


def test_full_resolution_bypasses_line_downsampling(canvas):
    """full_resolution=Trueが指定された場合、Lineでも点数によらず全点描画する
    (エクスポート時の「フル解像度」オプション用)。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    ds = _make_large_dataset(n)
    canvas.redraw_all([ds], 1, 1, [{}], full_resolution=True)
    assert ds.dataset_id not in canvas.downsample_index_map
    assert len(ds.artist.get_xdata()) == n


def test_point_labels_aligned_with_lttb_downsampled_points(canvas):
    """point_label_max_pointsがLTTB_DOWNSAMPLE_THRESHOLDより大きい値に設定
    されている場合(環境設定で変更可能)、LTTB間引きとポイントラベルが同時に
    適用されうる。間引き後の点数(x_data/y_data)とラベル値(元々visible_df
    基準のフルサイズ)の長さが揃っていないと、zip()が短い方で打ち切られ
    「間引き後のi番目の点」に「元データi番目の行の値」という無関係なラベルが
    付いてしまう実害があった。既知の平面 y = 2x のデータで、各点のラベルが
    間引き後もその点自身のY値(=2倍の関係)のまま保たれることを確認する。"""
    canvas.point_label_max_points = LTTB_DOWNSAMPLE_THRESHOLD + 10000
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = x * 2.0
    ds = Dataset(name="labeled_big", df=pd.DataFrame({"x": x, "y": y}),
                 x_col_name="x", y_col_name="y", plot_type="Line", show_point_labels=True)
    canvas.redraw_all([ds], 1, 1, [{}])

    assert ds.dataset_id in canvas.downsample_index_map  # 実際に間引きが発生した前提の確認
    ax = canvas.all_axes[0]
    labels = [t for t in ax.texts]
    assert len(labels) == LTTB_DOWNSAMPLE_TARGET_POINTS
    for t in labels:
        px, py = t.xy
        # ラベル文字列は".4g"(有効数字4桁)で丸められるため、相対誤差を広めに取る
        assert float(t.get_text()) == pytest.approx(py, rel=1e-3)  # ラベル値は自分自身の位置のY値と一致


def test_downsampling_not_applied_to_bar_plot_type(canvas):
    """Bar/Areaは1本1本・塗り形状の意味が変わるため、点数が多くても間引かない。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = np.abs(np.sin(x / 100.0))
    ds = Dataset(name="bars", df=pd.DataFrame({"x": x, "y": y}),
                 x_col_name="x", y_col_name="y", plot_type="Bar")
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas.downsample_index_map


def test_downsampling_skipped_for_non_monotonic_x(canvas):
    """Xが昇順でない(LTTBの前提を満たさない)場合は、形状を誤って変えないよう
    安全側に倒して間引かない。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 100, size=n)  # 昇順ではないランダムなX
    y = np.sin(x)
    ds = Dataset(name="scrambled", df=pd.DataFrame({"x": x, "y": y}),
                 x_col_name="x", y_col_name="y", plot_type="Line")
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas.downsample_index_map
    assert len(ds.artist.get_xdata()) == n


def test_downsampling_index_map_cleared_between_redraws(canvas):
    """前回の描画でダウンサンプリングされていたデータセットが削除された後、
    downsample_index_mapに古いエントリが残り続けない(fig.clf()と同様に
    redraw_all冒頭でクリアされる)ことを確認する。"""
    ds = _make_large_dataset(LTTB_DOWNSAMPLE_THRESHOLD + 1)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.dataset_id in canvas.downsample_index_map

    small_ds = _make_dataset(10)
    canvas.redraw_all([small_ds], 1, 1, [{}])
    assert ds.dataset_id not in canvas.downsample_index_map
    assert small_ds.dataset_id not in canvas.downsample_index_map


def test_downsampled_dataset_with_error_bars_does_not_crash_on_length_mismatch(canvas):
    """項目C-1001のerrorbar描画箇所の回帰テスト: plot_x_data/plot_y_dataが
    間引かれる一方でds.y_err_data(常にフルサイズ)をそのまま渡すと、
    matplotlib.errorbarが長さ不一致で例外を投げる。同じインデックスで
    誤差列も間引かれ、クラッシュせず描画できることを確認する。"""
    n = LTTB_DOWNSAMPLE_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = np.sin(x / 100.0)
    yerr = np.full(n, 0.1)
    ds = Dataset(
        name="big_with_err", df=pd.DataFrame({"x": x, "y": y, "yerr": yerr}),
        x_col_name="x", y_col_name="y", y_err_col_name="yerr",
        plot_type="Line", error_display="both",
    )
    canvas.redraw_all([ds], 1, 1, [{}])  # 例外が出なければOK
    assert ds.dataset_id in canvas.downsample_index_map


# --- _HeadlessRenderCanvas (項目C-004フェーズ5a: Qt非依存のバッチエクスポート用キャンバス) ---

def test_headless_render_canvas_redraw_and_savefig_on_gui_thread(tmp_path):
    """GUIスレッド上でも、MplCanvasと同じdescribe/appearanceロジック
    (_CanvasDrawingMixin経由)がQtに依存せず動作すること。"""
    ds = _make_dataset(5, show_point_labels=False)
    c = _HeadlessRenderCanvas()
    is_secondary_visible = c.redraw_all([ds], 1, 1, [{}])
    assert is_secondary_visible is False
    assert len(c.all_axes) == 1

    out_path = tmp_path / "headless.png"
    c.fig.savefig(str(out_path))
    assert out_path.exists()
    assert out_path.stat().st_size > 0
    plt.close(c.fig)


def test_headless_render_canvas_works_off_gui_thread(tmp_path):
    """バッチエクスポートの実スレッド化(項目C-004フェーズ5b)の前提条件:
    _HeadlessRenderCanvasはQWidgetのサブクラスではないため、GUIスレッド外の
    素のthreading.Thread上で構築・redraw_all・savefig()しても安全であること。"""
    import threading

    ds = _make_dataset(5, show_point_labels=False)
    out_path = tmp_path / "headless_thread.png"
    errors = []

    def _worker():
        try:
            c = _HeadlessRenderCanvas()
            c.redraw_all([ds], 1, 1, [{}])
            c.fig.savefig(str(out_path))
            plt.close(c.fig)
        except Exception as e:
            errors.append(e)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert errors == []
    assert out_path.exists()
    assert out_path.stat().st_size > 0


# =============================================================================
# 2Dマップ(ヒートマップ、項目C-508)
# =============================================================================

def _make_2d_dataset(name="heatmap", nx=4, ny=3, **overrides):
    xs = np.linspace(0.0, 3.0, nx)
    ys = np.linspace(0.0, 2.0, ny)
    x, y, z = [], [], []
    for yi in ys:
        for xi in xs:
            x.append(xi)
            y.append(yi)
            z.append(xi + yi)
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    kwargs = dict(name=name, df=df, x_col_name='x', y_col_name='y',
                  data_kind='2d_grid', z_col_name='z')
    kwargs.update(overrides)
    return Dataset(**kwargs)


def test_redraw_all_draws_heatmap_as_quadmesh():
    from matplotlib.collections import QuadMesh
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    ax = c.all_axes[0]

    meshes = [coll for coll in ax.collections if isinstance(coll, QuadMesh)]
    assert len(meshes) == 1
    assert ds.artist is meshes[0]
    plt.close(c.fig)


def test_heatmap_mesh_uses_dataset_colormap_and_alpha():
    ds = _make_2d_dataset(colormap='plasma', alpha=0.6)
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.get_cmap().name == 'plasma'
    assert ds.artist.get_alpha() == pytest.approx(0.6)
    plt.close(c.fig)


def test_heatmap_respects_explicit_vmin_vmax():
    ds = _make_2d_dataset(vmin=-10.0, vmax=10.0)
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.norm.vmin == pytest.approx(-10.0)
    assert ds.artist.norm.vmax == pytest.approx(10.0)
    plt.close(c.fig)


def test_heatmap_auto_vmin_vmax_from_data_when_unset():
    ds = _make_2d_dataset()  # z = x + y, x in [0,3], y in [0,2] -> z in [0,5]
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.norm.vmin == pytest.approx(0.0)
    assert ds.artist.norm.vmax == pytest.approx(5.0)
    plt.close(c.fig)


def test_heatmap_registers_mappable_for_colorbar():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert 0 in c._axis_2d_mappables
    assert c._axis_2d_mappables[0] is ds.artist
    plt.close(c.fig)


def test_heatmap_mappable_cleared_when_dataset_removed():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    assert 0 in c._axis_2d_mappables

    c.redraw_all([], 1, 1, [{}])
    assert 0 not in c._axis_2d_mappables
    plt.close(c.fig)


def test_heatmap_coexists_with_1d_line_dataset_on_same_axis():
    """将来のC-511(1Dスライス抽出)がヒートマップに重ねて線を描く想定の土台確認:
    2Dデータセットと1Dデータセットを同じサブプロットに置いても両方描画される。"""
    ds_2d = _make_2d_dataset(subplot_target=0)
    ds_1d = Dataset(
        name="slice", df=pd.DataFrame({'x': [0.0, 1.0, 2.0], 'y': [1.0, 2.0, 3.0]}),
        x_col_name='x', y_col_name='y', subplot_target=0,
    )
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds_2d, ds_1d], 1, 1, [{}])
    ax = c.all_axes[0]

    from matplotlib.collections import QuadMesh
    assert any(isinstance(coll, QuadMesh) for coll in ax.collections)
    assert len(ax.get_lines()) == 1
    plt.close(c.fig)


def test_2d_dataset_does_not_go_through_1d_downsampling_or_smoothing():
    """2DデータセットのZ列は長形式のためx_data/y_dataをそのまま1D描画すると
    無意味になる。_draw_dataが2Dデータセットを1D経路(Line描画)から
    確実に除外していることを、通常のLineとして描かれていないことで確認する。"""
    ds = _make_2d_dataset(nx=5, ny=5)
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    ax = c.all_axes[0]

    assert len(ax.get_lines()) == 0
    plt.close(c.fig)


def test_heatmap_large_grid_is_decimated_for_display():
    n = GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS + 200
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, 5)
    x, y, z = [], [], []
    for yi in ys:
        for xi in xs:
            x.append(xi)
            y.append(yi)
            z.append(xi + yi)
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    ds = Dataset(name="big", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.get_array().shape[1] <= GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS
    plt.close(c.fig)


def test_heatmap_full_resolution_bypasses_grid_decimation():
    """full_resolution=Trueが指定された場合、Line用LTTBと同様に2Dグリッドの
    間引き(GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS)も無視して全解像度で描画する
    (エクスポート時の「フル解像度」オプションが2Dマップにも一貫して効くように
    するための修正、以前は_draw_2d_dataにfull_resolutionが渡っておらず
    このオプションが2Dマップには効かなかった)。"""
    n = GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS + 200
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, 5)
    x, y, z = [], [], []
    for yi in ys:
        for xi in xs:
            x.append(xi)
            y.append(yi)
            z.append(xi + yi)
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    ds = Dataset(name="big", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}], full_resolution=True)

    assert ds.artist.get_array().shape[1] == n
    plt.close(c.fig)


def test_heatmap_with_no_valid_z_grid_draws_nothing_and_does_not_crash():
    df = pd.DataFrame({'x': [np.nan, np.nan], 'y': [1.0, 2.0], 'z': [1.0, 2.0]})
    ds = Dataset(name="bad", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])  # 例外を投げないこと

    assert 0 not in c._axis_2d_mappables
    plt.close(c.fig)


def test_heatmap_invalid_colormap_skips_dataset_without_crashing():
    ds = _make_2d_dataset(colormap='not_a_real_colormap')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])  # 例外を投げないこと

    assert ds.artist is None
    assert 0 not in c._axis_2d_mappables
    plt.close(c.fig)


def test_update_single_axis_also_draws_heatmap():
    """項目C-003(軽量再描画)経由でも2Dマップが描画されること。"""
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    c.update_single_axis(0, [ds], {}, rows=1, cols=1)

    from matplotlib.collections import QuadMesh
    ax = c.all_axes[0]
    assert any(isinstance(coll, QuadMesh) for coll in ax.collections)
    plt.close(c.fig)


def _colorbar_axes(fig):
    return [a for a in fig.axes if a.get_label() == '<colorbar>']


# --- カラーバー(項目C-501) ---

def test_colorbar_shown_by_default_when_heatmap_present():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert len(_colorbar_axes(c.fig)) == 1
    plt.close(c.fig)


def test_colorbar_absent_when_no_heatmap():
    ds = Dataset(name="line", df=pd.DataFrame({'x': [0.0, 1.0], 'y': [1.0, 2.0]}),
                 x_col_name='x', y_col_name='y')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert len(_colorbar_axes(c.fig)) == 0
    plt.close(c.fig)


def test_colorbar_can_be_disabled_via_settings():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{'colorbar_enabled': False}])

    assert len(_colorbar_axes(c.fig)) == 0
    plt.close(c.fig)


def test_colorbar_label_applied():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{'colorbar_label': '強度 (a.u.)'}])

    cbar_axes = _colorbar_axes(c.fig)
    assert len(cbar_axes) == 1
    assert cbar_axes[0].get_ylabel() == '強度 (a.u.)' or cbar_axes[0].get_xlabel() == '強度 (a.u.)'
    plt.close(c.fig)


def test_colorbar_position_bottom_uses_horizontal_orientation():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{'colorbar_position': 'bottom'}])

    cbar_axes = _colorbar_axes(c.fig)
    assert len(cbar_axes) == 1
    # 水平配置のカラーバーは横に長い(幅>高さ)
    bbox = cbar_axes[0].get_position()
    assert bbox.width > bbox.height
    plt.close(c.fig)


def test_colorbar_invalid_position_falls_back_to_right():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{'colorbar_position': 'not_a_real_position'}])

    assert len(_colorbar_axes(c.fig)) == 1  # 例外を投げず、既定(right)にフォールバック
    plt.close(c.fig)


def test_colorbar_invalid_width_fraction_falls_back_to_default():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{'colorbar_width_fraction': 'not_a_number'}])

    assert len(_colorbar_axes(c.fig)) == 1
    plt.close(c.fig)


def test_colorbar_removed_when_heatmap_dataset_removed():
    ds = _make_2d_dataset()
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    assert len(_colorbar_axes(c.fig)) == 1

    c.redraw_all([], 1, 1, [{}])
    assert len(_colorbar_axes(c.fig)) == 0
    plt.close(c.fig)


def test_colorbar_one_per_subplot_with_multiple_heatmaps():
    ds0 = _make_2d_dataset(name="a", subplot_target=0)
    ds1 = _make_2d_dataset(name="b", subplot_target=1)
    c = MplCanvas(width=6, height=3, dpi=80)
    c.redraw_all([ds0, ds1], 1, 2, [{}, {}])

    assert len(_colorbar_axes(c.fig)) == 2
    plt.close(c.fig)


def test_heatmap_scattered_data_falls_back_to_interpolated_grid():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, size=50)
    y = rng.uniform(0, 10, size=50)
    z = x + y
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    ds = Dataset(name="scattered", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z', grid_resolution=[20, 20])
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    from matplotlib.collections import QuadMesh
    ax = c.all_axes[0]
    assert any(isinstance(coll, QuadMesh) for coll in ax.collections)
    plt.close(c.fig)


# --- 等高線図(項目C-509) ---

def test_contour_mode_draws_lines_not_quadmesh():
    from matplotlib.collections import QuadMesh
    from matplotlib.contour import QuadContourSet
    ds = _make_2d_dataset(map_display_mode='contour', color='#ff0000')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    ax = c.all_axes[0]

    assert not any(isinstance(coll, QuadMesh) for coll in ax.collections)
    assert isinstance(ds.artist, QuadContourSet)
    plt.close(c.fig)


def test_contour_mode_does_not_register_colorbar_mappable():
    ds = _make_2d_dataset(map_display_mode='contour')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert 0 not in c._axis_2d_mappables
    assert len(_colorbar_axes(c.fig)) == 0
    plt.close(c.fig)


def test_contour_filled_mode_uses_colormap_and_registers_colorbar():
    ds = _make_2d_dataset(map_display_mode='contour_filled', colormap='plasma')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])

    assert 0 in c._axis_2d_mappables
    assert len(_colorbar_axes(c.fig)) == 1
    assert ds.artist.get_cmap().name == 'plasma'
    plt.close(c.fig)


def test_heatmap_contour_mode_draws_both_mesh_and_lines():
    from matplotlib.collections import QuadMesh
    ds = _make_2d_dataset(map_display_mode='heatmap_contour')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    ax = c.all_axes[0]

    assert any(isinstance(coll, QuadMesh) for coll in ax.collections)
    assert 0 in c._axis_2d_mappables  # カラーバー用のmappableはpcolormesh側
    plt.close(c.fig)


def test_contour_levels_setting_is_respected():
    """例外を投げずにcontour_levelsの値を使って描画できること
    (具体的な等高線本数の厳密検証はmatplotlib内部実装に依存するため行わない)。"""
    ds = _make_2d_dataset(map_display_mode='contour', contour_levels=3)
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])  # 例外を投げないこと
    plt.close(c.fig)


def test_invalid_map_display_mode_falls_back_to_heatmap():
    from matplotlib.collections import QuadMesh
    ds = _make_2d_dataset(map_display_mode='not_a_real_mode')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])
    ax = c.all_axes[0]

    assert any(isinstance(coll, QuadMesh) for coll in ax.collections)
    plt.close(c.fig)


def test_contour_mode_with_invalid_grid_does_not_crash():
    df = pd.DataFrame({'x': [np.nan, np.nan], 'y': [1.0, 2.0], 'z': [1.0, 2.0]})
    ds = Dataset(name="bad", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z', map_display_mode='contour')
    c = MplCanvas(width=4, height=3, dpi=80)
    c.redraw_all([ds], 1, 1, [{}])  # 例外を投げないこと

    assert ds.artist is None
    plt.close(c.fig)
