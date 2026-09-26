"""データセットの並び(描画順・一覧のツリー・保存用のフォルダ構造)を、R-6 の前に固定する。

test_operations.py の tree_* が見ていない操作を足す: フォルダごとの削除、フォルダをまたぐ削除、フォルダの中への
移動とその中での並べ替え、フォルダをフォルダの中へ、フォルダの中への Undo できる追加、フォルダの中での複製、
入れ子のフォルダの保存と読み込み。どれも操作の後、Undo をすべて戻した後、Redo をすべてやり直した後の並びを残す。
"""
import pandas as pd
import pytest

import recorder
from scenario import pump
from test_operations import ds_a, ds_b, order_state, run_case, select, _new_tab


def _small(name, y=1.0):
    from graphica.core.dataset import Dataset

    return Dataset(df=pd.DataFrame({"x": [0.0, 1.0], "y": [y, y + 1.0]}), name=name, x_col_name="x", y_col_name="y")


def _folder(tab, name, parent=None):
    return tab._add_dataset_folder_item(name, parent)


def _move_into(tab, dataset, folder, row=None):
    """ドラッグ&ドロップと同じく、項目を移してから rowsMoved の処理を呼ぶ。"""
    tree = tab.ui.dataset_list_widget
    item = tab._get_dataset_tree_item(dataset)
    source_parent = item.parent()
    if source_parent is None:
        item = tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
    else:
        source_parent.removeChild(item)
    folder.insertChild(folder.childCount() if row is None else row, item)
    tab._on_dataset_rows_moved(source_parent, 0, 0, folder, 0)
    pump()


def _nested(tab):
    """A, [F1: B, [F2: C]], D の形にする(Undo の履歴は消す)。"""
    a, b, c, d = tab.project.datasets
    f1 = _folder(tab, "F1")
    _move_into(tab, b, f1)
    f2 = _folder(tab, "F2", f1)
    _move_into(tab, c, f2)
    tree = tab.ui.dataset_list_widget
    moved_d = tree.takeTopLevelItem(tree.indexOfTopLevelItem(tab._get_dataset_tree_item(d)))
    tree.addTopLevelItem(moved_d)
    tab._on_dataset_rows_moved(None, 0, 0, None, 0)
    pump()
    tab.undo_stack.clear()
    return f1, f2


def _select_items(tab, *items):
    tree = tab.ui.dataset_list_widget
    tree.clearSelection()
    tree.setCurrentItem(items[0])
    for item in items:
        item.setSelected(True)
    pump()


CASES = {}


def case(name):
    def decorator(fn):
        CASES[name] = fn
        return fn
    return decorator


@case("remove_folder_with_contents")
def _remove_folder(tab, modal_log):
    f1, _f2 = _nested(tab)
    _select_items(tab, f1)
    return run_case(tab, modal_log, lambda t: t._on_remove_dataset())


@case("remove_across_folders")
def _remove_across(tab, modal_log):
    _f1, f2 = _nested(tab)
    a = tab.project.datasets[0]
    _select_items(tab, tab._get_dataset_tree_item(a), f2.child(0))
    return run_case(tab, modal_log, lambda t: t._on_remove_dataset())


@case("remove_folder_and_its_child_selected")
def _remove_folder_and_child(tab, modal_log):
    f1, _f2 = _nested(tab)
    _select_items(tab, f1, f1.child(0))
    return run_case(tab, modal_log, lambda t: t._on_remove_dataset())


@case("reorder_inside_folder")
def _reorder_inside(tab, modal_log):
    f1, _f2 = _nested(tab)
    e = _small("E", 5.0)
    tab._add_dataset(e, f1)
    tab.undo_stack.clear()

    def action(t):
        moved = f1.takeChild(f1.indexOfChild(t._get_dataset_tree_item(e)))
        f1.insertChild(0, moved)
        t._on_dataset_rows_moved(f1, 2, 2, f1, 0)
        pump()
    return run_case(tab, modal_log, action)


@case("folder_into_folder")
def _folder_into_folder(tab, modal_log):
    f1, _f2 = _nested(tab)
    f3 = _folder(tab, "F3")

    def action(t):
        tree = t.ui.dataset_list_widget
        moved = tree.takeTopLevelItem(tree.indexOfTopLevelItem(f1))
        f3.addChild(moved)
        t._on_dataset_rows_moved(None, 1, 1, f3, 0)
        pump()
    return run_case(tab, modal_log, action)


@case("add_with_undo_into_folder")
def _add_with_undo(tab, modal_log):
    _f1, f2 = _nested(tab)
    return run_case(tab, modal_log, lambda t: t._add_dataset_with_undo(_small("新規"), f2, description="追加の確認"))


@case("duplicate_inside_folder")
def _duplicate_inside(tab, modal_log):
    _f1, f2 = _nested(tab)
    _select_items(tab, f2.child(0))
    return run_case(tab, modal_log, lambda t: t._on_duplicate_dataset())


@case("new_folder_inside_selected_folder")
def _new_folder_inside(tab, modal_log):
    f1, _f2 = _nested(tab)
    _select_items(tab, f1)
    modal_log.respond_to("getText", ("中のフォルダ", True))
    return run_case(tab, modal_log, lambda t: t._on_new_folder())


@case("search_inside_folders")
def _search_inside(tab, modal_log):
    _nested(tab)

    def action(t):
        t._on_dataset_search_changed("c")
        from test_operations import tree_items
        t._search_snapshot = tree_items(t.ui.dataset_list_widget)
        t._on_dataset_search_changed("")
    result = run_case(tab, modal_log, action)
    result["while_searching"] = tab._search_snapshot
    return result


@pytest.mark.parametrize("name", list(CASES))
def test_dataset_order(app_env, modal_log, normalizer, name):
    tab = _new_tab(app_env, ds_a(), ds_b(), _small("c", 3.0), _small("D", 4.0))
    modal_log.accept_defaults()
    recorder.check(f"dataset_order/{name}", CASES[name](tab, modal_log), normalizer)


def test_nested_folders_survive_save_and_load(app_env, modal_log, normalizer, tmp_path):
    tab = _new_tab(app_env, ds_a(), ds_b(), _small("c", 3.0), _small("D", 4.0))
    modal_log.accept_defaults()
    _nested(tab)
    select(tab, tab.project.datasets[0])
    before = order_state(tab)
    path = tmp_path / "order.graphica"
    tab._sync_project_from_ui()
    tab.project.save_project(str(path))

    fresh = _new_tab(app_env)
    fresh._load_project_from_path(str(path))
    pump()
    recorder.check("dataset_order/save_and_load",
                   {"before": before, "after_load": order_state(fresh), "modals": modal_log.take()}, normalizer)
