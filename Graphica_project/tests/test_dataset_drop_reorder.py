"""一覧のドラッグ&ドロップで並べ替えたら、描画順(ウォーターフォールの段)も変わる。

QTreeWidget のドロップは項目を取り出して入れ直すので rowsMoved が出ず、描画順が一覧の並びに追いついていなかった。
オフスクリーンでは本物のドラッグを起こせないので、Qt のドロップと同じく取り出して入れ直す処理に置き換えて流す。
"""
import pandas as pd
import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem

from graphica.core.dataset import Dataset
from graphica.gui.builders.dataset_panel import DatasetTreeWidget
from graphica.gui.main_window import PlotterApp


def _ds(name):
    return Dataset(name=name, df=pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 2.0]}),
                   x_col_name="x", y_col_name="y", waterfall_enabled=True, waterfall_offset_y=1.0)


@pytest.fixture
def window():
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    for name in ("a", "b", "c"):
        w._add_dataset(_ds(name), None, select=False)
    QApplication.instance().processEvents()
    yield w
    w.close()


def _drop(tree, monkeypatch, move):
    """move(tree) で項目を動かすドロップを、ツリーに届いたものとして流す。"""
    monkeypatch.setattr(QTreeWidget, "dropEvent", lambda self, event: move(self))
    mime = QMimeData()
    event = QDropEvent(QPointF(0, 0), Qt.DropAction.MoveAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(event)
    for _ in range(3):
        QApplication.instance().processEvents()


def _move_last_to_top(tree):
    tree.insertTopLevelItem(0, tree.takeTopLevelItem(tree.topLevelItemCount() - 1))


def _names(window):
    return [ds.name for ds in window.project.datasets]


def _steps(window):
    window._update_plot()
    return {ds.name: window.canvas.get_waterfall_transform(ds)['index'] for ds in window.project.datasets}


def test_the_tree_is_the_dropping_kind(window):
    assert isinstance(window.ui.dataset_list_widget, DatasetTreeWidget)


def test_dropping_reorders_the_waterfall_steps(window, monkeypatch):
    _drop(window.ui.dataset_list_widget, monkeypatch, _move_last_to_top)

    assert _names(window) == ["c", "a", "b"]
    assert _steps(window) == {"c": 0, "a": 1, "b": 2}


def test_a_reorder_in_the_same_folder_can_be_undone(window, monkeypatch):
    before = window.undo_stack.count()
    _drop(window.ui.dataset_list_widget, monkeypatch, _move_last_to_top)
    assert window.undo_stack.count() == before + 1

    window.undo_stack.undo()
    for _ in range(3):
        QApplication.instance().processEvents()

    assert _names(window) == ["a", "b", "c"]
    tree = window.ui.dataset_list_widget
    assert [tree.topLevelItem(i).text(0) for i in range(3)] == ["a", "b", "c"]


def test_moving_into_a_folder_follows_without_undo(window, monkeypatch):
    tree = window.ui.dataset_list_widget
    folder = window.dataset_order.add_folder("F")

    def move_first_into_folder(tree):
        folder.addChild(tree.takeTopLevelItem(0))

    before = window.undo_stack.count()
    _drop(tree, monkeypatch, move_first_into_folder)

    assert _names(window) == ["b", "c", "a"]
    assert window.undo_stack.count() == before


def test_a_drop_that_changes_nothing_adds_no_step(window, monkeypatch):
    before = window.undo_stack.count()
    _drop(window.ui.dataset_list_widget, monkeypatch, lambda tree: None)

    assert _names(window) == ["a", "b", "c"]
    assert window.undo_stack.count() == before


def test_items_dropped_tells_whether_every_item_kept_its_folder(qapp, monkeypatch):
    tree = DatasetTreeWidget()
    folder = QTreeWidgetItem(["F"])
    tree.addTopLevelItem(folder)
    for name in ("x", "y"):
        tree.addTopLevelItem(QTreeWidgetItem([name]))
    received = []
    tree.items_dropped.connect(received.append)

    _drop(tree, monkeypatch, _move_last_to_top)
    _drop(tree, monkeypatch, lambda t: folder.addChild(t.takeTopLevelItem(t.topLevelItemCount() - 1)))

    assert received == [True, False]
