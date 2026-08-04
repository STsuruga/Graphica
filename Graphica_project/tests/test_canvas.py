# tests/test_canvas.py
"""gui/canvas.py の純粋なヘルパー関数(凡例順序・目盛りロケータ/フォーマッタ)に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
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
