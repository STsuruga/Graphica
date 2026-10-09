"""軸の手動の範囲: 最小に大きい方を入れても範囲として使い(向きは入れ替える)、ウォーターフォールで X をずらしたら
奥のトレースが切れないように広げる。

最小 > 最大だった範囲は黙って無視され、自動の範囲(余白つき)になっていた。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from graphica.core.axis_settings import axis_inverted, manual_axis_range
from graphica.core.dataset import Dataset
from graphica.gui.canvas import MplCanvas


# --- 判定 ---

@pytest.mark.parametrize("settings, expected", [
    ({'x_autoscale': True, 'x_min': 0, 'x_max': 10}, None),
    ({'x_autoscale': False, 'x_min': 0, 'x_max': 10}, (0, 10)),
    ({'x_autoscale': False, 'x_min': 25, 'x_max': -15}, (-15, 25)),
    ({'x_autoscale': False, 'x_min': 3, 'x_max': 3}, None),
])
def test_manual_axis_range(settings, expected):
    assert manual_axis_range(settings, 'x') == expected


@pytest.mark.parametrize("settings, expected", [
    ({'x_autoscale': False, 'x_min': 0, 'x_max': 10, 'x_invert': False}, False),
    ({'x_autoscale': False, 'x_min': 0, 'x_max': 10, 'x_invert': True}, True),
    ({'x_autoscale': False, 'x_min': 25, 'x_max': -15, 'x_invert': False}, True),
    ({'x_autoscale': False, 'x_min': 25, 'x_max': -15, 'x_invert': True}, False),
    # 自動スケールなら最小・最大は使わないので、反転のチェックだけ
    ({'x_autoscale': True, 'x_min': 25, 'x_max': -15, 'x_invert': False}, False),
])
def test_axis_inverted(settings, expected):
    assert axis_inverted(settings, 'x') is expected


# --- 描画 ---

@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def _ds(name="d", x=(-10, 0, 20), **kwargs):
    return Dataset(name=name, df=pd.DataFrame({"x": list(x), "y": [1.0, 2.0, 3.0]}),
                   x_col_name="x", y_col_name="y", **kwargs)


def _manual(x_min, x_max, **extra):
    return {'x_autoscale': False, 'x_min': x_min, 'x_max': x_max, **extra}


def test_min_greater_than_max_draws_that_range_reversed(canvas):
    canvas.redraw_all([_ds()], 1, 1, [_manual(25, -15)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((25, -15))


def test_same_look_as_min_max_with_invert(canvas):
    canvas.redraw_all([_ds()], 1, 1, [_manual(-15, 25, x_invert=True)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((25, -15))


def test_reversed_range_with_invert_turns_back(canvas):
    canvas.redraw_all([_ds()], 1, 1, [_manual(25, -15, x_invert=True)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((-15, 25))


def test_equal_min_and_max_is_still_ignored(canvas):
    canvas.redraw_all([_ds()], 1, 1, [_manual(5, 5)])
    x0, x1 = canvas.all_axes[0].get_xlim()
    assert x0 < -9 and x1 > 19  # データが見える範囲(自動)


def _waterfall(name, offset_x, **kwargs):
    return _ds(name, waterfall_enabled=True, waterfall_offset_x=offset_x, waterfall_offset_y=1.0, **kwargs)


def test_waterfall_x_shift_widens_the_manual_range_to_keep_back_traces(canvas):
    """段ごとに +2 ずつ右へずらす 3 本: 手前は 0〜10、奥は最大 +4 ずれるので右端を 14 まで広げる。"""
    datasets = [_waterfall("a", 2.0), _waterfall("b", 2.0), _waterfall("c", 2.0)]
    canvas.redraw_all(datasets, 1, 1, [_manual(0, 10)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((0, 14))


def test_negative_waterfall_shift_widens_to_the_left(canvas):
    datasets = [_waterfall("a", -1.5), _waterfall("b", -1.5)]
    canvas.redraw_all(datasets, 1, 1, [_manual(0, 10)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((-1.5, 10))


def test_widening_keeps_the_reversed_direction(canvas):
    """ユーザーの例: 25〜-15(右へ行くほど小さい)で、奥のトレースが +X へずれる。"""
    datasets = [_waterfall("a", 1.0), _waterfall("b", 1.0), _waterfall("c", 1.0)]
    canvas.redraw_all(datasets, 1, 1, [_manual(25, -15)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((27, -15))


def test_absolute_offsets_widen_by_each_traces_own_shift(canvas):
    datasets = [_waterfall("a", 3.0, waterfall_offset_mode='absolute'),
                _waterfall("b", -2.0, waterfall_offset_mode='absolute')]
    canvas.redraw_all(datasets, 1, 1, [_manual(0, 10)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((-2, 13))


def test_hidden_traces_do_not_widen(canvas):
    datasets = [_waterfall("a", 2.0), _waterfall("b", 2.0), _waterfall("c", 2.0, visible=False)]
    canvas.redraw_all(datasets, 1, 1, [_manual(0, 10)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((0, 12))


def test_without_waterfall_the_manual_range_is_exact(canvas):
    canvas.redraw_all([_ds("a"), _ds("b")], 1, 1, [_manual(0, 10)])
    assert canvas.all_axes[0].get_xlim() == pytest.approx((0, 10))


def test_y_range_is_not_widened(canvas):
    datasets = [_waterfall("a", 2.0), _waterfall("b", 2.0)]
    canvas.redraw_all(datasets, 1, 1, [{'y_autoscale': False, 'y_min': 0, 'y_max': 5}])
    assert canvas.all_axes[0].get_ylim() == pytest.approx((0, 5))


# --- スクリプトの書き出し ---

def test_script_export_uses_the_same_range_and_direction():
    from graphica.core.script_export import generate_python_script
    from graphica.models.project import ProjectModel
    project = ProjectModel()
    project.datasets = [_ds()]
    project.all_plot_settings = [{**_manual(25, -15), 'y_invert': True}]

    script = generate_python_script(project)

    assert "set_xlim(-15, 25)" in script
    assert "invert_xaxis()" in script
    assert "invert_yaxis()" in script  # 主の Y 軸の反転もこれまで書き出していなかった
