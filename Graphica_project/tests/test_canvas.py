# tests/test_canvas.py
"""gui/canvas.py の純粋なヘルパー関数(凡例順序・目盛りロケータ/フォーマッタ)に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.collections import LineCollection
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
import pandas as pd
import pytest

from gui.canvas import (
    _apply_legend_order, _safe_multiple_locator,
    _sci_each_formatter, _apply_tick_format_mode,
    MplCanvas, DEFAULT_POINT_LABEL_MAX_POINTS,
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


# --- ウォーターフォールプロット(項目80) ---
# 同一サブプロット上で plot_type=='Waterfall' のデータセットだけを対象に、
# リスト順で0始まりの積み重ねインデックスを振り、X/Yをそれぞれ
# (index * waterfall_offset_x, index * waterfall_offset_y) だけずらして描画する。
# 実装は通常の2D Axesの範囲内(mpl_toolkits.mplot3dは使わない疑似3D)。

def _make_waterfall_dataset(name, x, y, offset_x=0.0, offset_y=1.0):
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(
        name=name, df=df, x_col_name="x", y_col_name="y",
        plot_type='Waterfall', color='#112233',
        waterfall_offset_x=offset_x, waterfall_offset_y=offset_y,
    )


def test_waterfall_zero_offset_matches_plain_line_position(canvas):
    """offset=(0,0)の単独'Waterfall'データセットは、積み重ねインデックス0番目
    として何もずらされないため、通常の'Line'と同じ位置に描画される
    (回帰防止のためのベースライン確認)。"""
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
    """2件の'Waterfall'データセットは、リスト順で0,1のインデックスを振られ、
    2件目はX方向に1*offset_x、Y方向に1*offset_yだけずれた位置に描画される。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds0 = _make_waterfall_dataset("wf0", x, y, offset_x=1.0, offset_y=2.0)
    ds1 = _make_waterfall_dataset("wf1", x, y, offset_x=1.0, offset_y=2.0)

    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    assert list(ds0.artist.get_xdata()) == pytest.approx(x)
    assert list(ds0.artist.get_ydata()) == pytest.approx(y)
    assert list(ds1.artist.get_xdata()) == pytest.approx([v + 1.0 for v in x])
    assert list(ds1.artist.get_ydata()) == pytest.approx([v + 2.0 for v in y])


def test_waterfall_non_waterfall_datasets_unaffected_and_excluded_from_index(canvas):
    """同じサブプロットに非Waterfallのデータセットが混在していても、積み重ね
    インデックスの計算には参加せず、位置も一切ずらされない。'Waterfall'側の
    インデックス付番も、非Waterfallのデータセットを無視してWaterfall同士だけの
    順序で振られる。"""
    x, y = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    ds_line = Dataset(name="line", df=pd.DataFrame({"x": x, "y": y}),
                       x_col_name="x", y_col_name="y", plot_type='Line', color='#445566')
    ds_wf0 = _make_waterfall_dataset("wf0", x, y, offset_x=1.0, offset_y=2.0)
    ds_wf1 = _make_waterfall_dataset("wf1", x, y, offset_x=1.0, offset_y=2.0)

    # 非Waterfallのデータセットをリストの先頭・間に挟んでも結果が変わらないこと
    canvas.redraw_all([ds_line, ds_wf0, ds_wf1], 1, 1, [{}])

    assert list(ds_line.artist.get_xdata()) == pytest.approx(x)
    assert list(ds_line.artist.get_ydata()) == pytest.approx(y)
    # wf0 はWaterfallの中で0番目のまま(lineに割り込まれてもインデックスは変わらない)
    assert list(ds_wf0.artist.get_xdata()) == pytest.approx(x)
    assert list(ds_wf0.artist.get_ydata()) == pytest.approx(y)
    # wf1 はWaterfallの中で1番目
    assert list(ds_wf1.artist.get_xdata()) == pytest.approx([v + 1.0 for v in x])
    assert list(ds_wf1.artist.get_ydata()) == pytest.approx([v + 2.0 for v in y])


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
