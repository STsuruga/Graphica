"""データセットの並びの規則(gui/datasets/order.py の DatasetOrder)。画面を組み立てずに、ツリーとリストだけで確かめる。"""
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from graphica.core.dataset import Dataset
from graphica.gui.datasets.order import DatasetOrder, item_dataset


class _Project:
    def __init__(self):
        self.datasets = []
        self.dataset_group_tree = {'name': '', 'children': []}


def _order():
    tree = QTreeWidget()
    project = _Project()

    def make_item(dataset, parent):
        item = QTreeWidgetItem([dataset.name])
        item.setData(0, Qt.ItemDataRole.UserRole, dataset)
        if parent is not None:
            parent.addChild(item)
        else:
            tree.addTopLevelItem(item)
        return item

    return DatasetOrder(project, lambda: tree, make_item), project, tree


def _ds(name):
    return Dataset(df=pd.DataFrame({"x": [0.0], "y": [1.0]}), name=name, x_col_name="x", y_col_name="y")


def _names(datasets):
    return [ds.name for ds in datasets]


def test_adding_into_a_folder_follows_the_tree_in_the_draw_order():
    """K-18 の再現手順: フォルダ F を先に作り、最上位に A・B、F の中に C。描画順も一覧と同じ C, A, B になる。"""
    order, project, _tree = _order()
    folder = order.add_folder("F")
    order.append(_ds("A"))
    order.append(_ds("B"))
    order.append(_ds("C"), folder)
    assert _names(order.tree_order()) == ["C", "A", "B"]
    assert _names(project.datasets) == ["C", "A", "B"]
    order.append(_ds("D"), folder)
    order.append(_ds("E"))
    assert _names(project.datasets) == _names(order.tree_order()) == ["C", "D", "A", "B", "E"]


def test_adding_at_the_top_level_still_goes_to_the_end_of_the_draw_order():
    """最上位への追加は一覧でも末尾なので、描画順も末尾(保存済みの食い違いがあっても前には割り込まない)。"""
    order, project, _tree = _order()
    a, b = _ds("A"), _ds("B")
    order.append(a)
    order.append(b)
    project.datasets[:] = [b, a]
    order.append(_ds("C"))
    assert _names(project.datasets) == ["B", "A", "C"]


def test_removal_restores_the_draw_order_and_the_tree_positions():
    order, project, tree = _order()
    a, b, c = _ds("A"), _ds("B"), _ds("C")
    order.append(a)
    folder = order.add_folder("F")
    order.append(b, folder)
    order.append(c)
    remove, restore, removed = order.removal([folder, order.item_for(c)])
    assert _names(removed) == ["B", "C"]
    remove()
    assert _names(project.datasets) == ["A"] and tree.topLevelItemCount() == 1
    restore()
    assert _names(project.datasets) == ["A", "B", "C"]
    assert [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())] == ["A", "F", "C"]
    assert order.removal([]) is None


def test_group_tree_and_rebuild_round_trip():
    order, project, tree = _order()
    order.append(_ds("A"))
    outer = order.add_folder("外")
    inner = order.add_folder("内", outer)
    order.append(_ds("B"), inner)
    project.dataset_group_tree = order.group_tree()
    tree.clear()
    order.rebuild_tree()
    rebuilt = order.group_tree()
    assert [child.get('name') or child['dataset'].name for child in rebuilt['children']] == ["A", "外"]
    assert rebuilt['children'][1]['children'][0]['children'][0]['dataset'].name == "B"


def test_sorting_the_tree_to_the_draw_order_keeps_folders_in_place():
    order, project, tree = _order()
    a, b, c = _ds("A"), _ds("B"), _ds("C")
    for ds in (a, b):
        order.append(ds)
    order.add_folder("F")
    order.append(c)
    project.datasets[:] = [c, b, a]
    order.sort_tree_to_draw_order()
    assert [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())] == ["C", "B", "F", "A"]


def test_top_level_items_drop_children_of_selected_folders():
    order, _project, _tree = _order()
    folder = order.add_folder("F")
    child = order.append(_ds("A"), folder)
    other = order.append(_ds("B"))
    assert DatasetOrder.top_level_items([folder, child, other]) == [folder, other]
    assert item_dataset(folder) is None
