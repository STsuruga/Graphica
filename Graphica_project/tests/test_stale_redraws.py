"""操作のあとに描き直しと表示の更新が抜けていたところ。

どれも、全部を描き直したときと同じ状態になっていることで確かめる。
- 行のマスクの Undo/Redo で描き直さず、統計値も古いまま(マスクしたときも統計値は古いまま)
- データエディタで編集しても、一覧で何も選んでいないと描き直さない
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from graphica.core.commands import EditCellCommand
from graphica.core.dataset import Dataset
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


def _first_line_y(window):
    return list(window.canvas.all_axes[0].get_lines()[0].get_ydata())


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
