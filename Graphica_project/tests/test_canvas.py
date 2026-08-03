# tests/test_canvas.py
"""gui/canvas.py の純粋なヘルパー関数(凡例順序・目盛りロケータ/フォーマッタ)に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pytest

from gui.canvas import (
    _apply_legend_order, _safe_multiple_locator,
    _sci_each_formatter, _apply_tick_format_mode,
)


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
