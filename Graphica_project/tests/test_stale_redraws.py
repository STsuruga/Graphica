"""操作のあとに描き直しと表示の更新が抜けていたところ。

どれも、全部を描き直したときと同じ状態になっていることで確かめる。
- 行のマスクの Undo/Redo で描き直さず、統計値も古いまま(マスクしたときも統計値は古いまま)
- データエディタで編集しても、一覧で何も選んでいないと描き直さない
- 1つの軸だけ描き直す変更(第2Y軸など)と、キャンバスの大きさの変更で余白を合わせ直さない
"""
import pandas as pd
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from graphica.core.commands import EditCellCommand
from graphica.core.dataset import Dataset
from graphica.gui.canvas import MplCanvas
from graphica.gui.main_window import PlotterApp


def _ds(name):
    return Dataset(name=name, df=pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [1.0, 4.0, 9.0]}),
                   x_col_name="x", y_col_name="y")


@pytest.fixture
def window():
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.show()
    for name in ("a", "b"):
        w._add_dataset(_ds(name), None, select=True)
    w.ui.dataset_list_widget.setCurrentItem(w.ui.dataset_list_widget.topLevelItem(0))
    _settle()
    yield w
    w.close()


def _settle():
    QApplication.instance().processEvents()
    QTest.qWait(MplCanvas.RELAYOUT_DELAY_MS * 3)
    QApplication.instance().processEvents()


def _first_line_y(window):
    return list(window.canvas.all_axes[0].get_lines()[0].get_ydata())


def _positions(window):
    return [bound for ax in window.canvas.fig.axes for bound in ax.get_position().bounds]


def _assert_layout_matches_a_full_redraw(window):
    shown = _positions(window)
    window._update_plot()
    assert shown == pytest.approx(_positions(window), abs=1e-6)


# --- 行のマスク ---

def test_masking_updates_the_plot_and_the_stats_and_undo_redo_follow(window):
    dataset = window.project.datasets[0]

    window.dataset_host.push_masked_rows(dataset, [], [2], "マスク")
    assert _first_line_y(window) == [1.0, 4.0]
    assert "件数: 2" in window.stats_summary_label.text()

    window.undo_stack.undo()
    assert _first_line_y(window) == [1.0, 4.0, 9.0]
    assert "件数: 3" in window.stats_summary_label.text()

    window.undo_stack.redo()
    assert _first_line_y(window) == [1.0, 4.0]
    assert "件数: 2" in window.stats_summary_label.text()


def test_undoing_a_range_selection_mask_redraws(window):
    window.mouse_tools['range_select']._apply_range_mask(window.canvas.all_axes[0], 2.5, 3.5)
    assert _first_line_y(window) == [1.0, 4.0]

    window.undo_stack.undo()

    assert _first_line_y(window) == [1.0, 4.0, 9.0]


# --- データエディタ ---

def test_editing_in_the_data_editor_redraws_with_nothing_selected(window):
    window._on_show_data_editor()
    editor = window.data_editor_dialog
    tree = window.ui.dataset_list_widget
    tree.clearSelection()
    tree.setCurrentItem(None)

    dataset = editor.dataset
    editor.undo_stack.push(EditCellCommand(dataset, dataset.df.index[1], "y", 4.0, 50.0))

    assert _first_line_y(window) == [1.0, 50.0, 9.0]
    editor.close()


# --- 余白 ---

def test_turning_on_the_secondary_y_axis_refits_the_margins(window):
    dataset = window.project.datasets[0]
    window.push_dataset_property_command(dataset, {'use_secondary_y': False}, {'use_secondary_y': True}, "第2Y軸")
    _settle()
    _assert_layout_matches_a_full_redraw(window)


@pytest.mark.parametrize("dw, dh", [(300, 200), (-300, -200)])
def test_resizing_the_window_refits_the_margins(window, dw, dh):
    window.resize(window.width() + dw, window.height() + dh)
    _settle()
    _assert_layout_matches_a_full_redraw(window)
