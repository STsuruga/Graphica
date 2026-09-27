"""配置を収める(gui/canvas.py fit_tight_layout)。描いた回数で軸の位置が変わらないこと。"""
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from graphica.gui.canvas import fit_tight_layout


def _figure_with_label_outside():
    fig = Figure(figsize=(6, 4))
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    # 軸の外にはみ出す注釈があると、tight_layout は 1 回では収まらない
    ax.annotate("はみ出すラベル", xy=(0.5, 0.5), xytext=(0.9, 1.15), textcoords="axes fraction",
                arrowprops={"arrowstyle": "->"})
    return fig, ax


def test_the_layout_settles_however_many_times_it_was_laid_out_before():
    fresh, fresh_ax = _figure_with_label_outside()
    fit_tight_layout(fresh)

    worn, worn_ax = _figure_with_label_outside()
    for _ in range(3):
        worn.tight_layout()
    fit_tight_layout(worn)

    for a, b in zip(fresh_ax.get_position().bounds, worn_ax.get_position().bounds):
        assert abs(a - b) < 1e-6
    settled = fresh_ax.get_position().bounds
    fit_tight_layout(fresh)
    assert all(abs(a - b) < 1e-7 for a, b in zip(fresh_ax.get_position().bounds, settled))


def test_a_single_pass_does_not_settle_this_figure():
    """前提の確認: 1 回だけでは位置がまだ動く(動かないならこの関数は要らない)。"""
    fig, ax = _figure_with_label_outside()
    fig.tight_layout()
    first = ax.get_position().bounds
    fig.tight_layout()
    assert max(abs(a - b) for a, b in zip(first, ax.get_position().bounds)) > 1e-7
