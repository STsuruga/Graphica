"""データが無くなった軸の範囲は、1つの軸の描き直しでも全部の描き直しでも同じ(前のデータの範囲を残さない)。"""
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from graphica.core.dataset import Dataset
from graphica.gui.canvas import MplCanvas


def _dataset(**overrides):
    df = pd.DataFrame({"x": np.arange(100.0, 110.0), "y": np.arange(50.0, 60.0)})
    return Dataset(name="d", df=df, x_col_name="x", y_col_name="y", **overrides)


def _limits(canvas, axis_index):
    ax = canvas.all_axes[axis_index]
    return ax.get_xlim(), ax.get_ylim()


def _full_redraw_limits(datasets, rows, cols, axis_index):
    canvas = MplCanvas(width=4, height=3, dpi=60)
    canvas.redraw_all(datasets, rows, cols, [{}] * (rows * cols))
    return _limits(canvas, axis_index)


def test_hiding_every_dataset_gives_the_same_range_on_both_paths():
    ds = _dataset()
    canvas = MplCanvas(width=4, height=3, dpi=60)
    canvas.redraw_all([ds], 1, 1, [{}])

    ds.visible = False
    canvas.update_single_axis(0, [ds], {})

    assert _limits(canvas, 0) == _full_redraw_limits([ds], 1, 1, 0)
    assert canvas.all_axes[0].get_xlim()[1] < 1


def test_moving_the_last_dataset_to_another_subplot_empties_the_old_one():
    ds = _dataset()
    canvas = MplCanvas(width=4, height=3, dpi=60)
    canvas.redraw_all([ds], 1, 2, [{}, {}])

    ds.subplot_target = 1
    canvas.update_single_axis(0, [ds], {}, rows=1, cols=2)
    canvas.update_single_axis(1, [ds], {}, rows=1, cols=2)

    assert _limits(canvas, 0) == _full_redraw_limits([ds], 1, 2, 0)
    assert _limits(canvas, 1) == _full_redraw_limits([ds], 1, 2, 1)
