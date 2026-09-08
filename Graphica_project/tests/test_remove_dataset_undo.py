# tests/test_remove_dataset_undo.py
"""
データセット/フォルダの削除がUndo/Redoできることのテスト(改善ボード A-3)。

以前は右クリック「削除」が `del self.project.datasets[row]` でモデルを直接
書き換えており、誤削除するとデータ・スタイル・フィット結果・マスク・注釈が
まとめて復旧不能になっていた(オートセーブからの復元しか手段がなかった)。

復元では次の3つが元に戻ることを確認する:

- `project.datasets` の内容と**順序**(=プロットの描画順/重なり順)
- ツリー上の**親フォルダ**と、その中での**インデックス**
- Datasetオブジェクトそのもの(同一インスタンス。スタイル・マスク・
  フィット結果などの付随情報がまとめて戻る)
"""
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.dataset import Dataset


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _add(window, name, parent_folder=None, **kwargs):
    ds = Dataset(
        name=name, df=pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 4.0]}),
        x_col_name="x", y_col_name="y", **kwargs,
    )
    window._add_dataset(ds, parent_folder=parent_folder, select=False)
    return ds


def _select(window, *datasets):
    tree = window.ui.dataset_list_widget
    tree.clearSelection()
    for ds in datasets:
        item = window._get_dataset_tree_item(ds)
        assert item is not None
        item.setSelected(True)
    return tree.selectedItems()


def _names(window):
    return [ds.name for ds in window.project.datasets]


def _tree_names(window):
    """ツリーを先行順に辿った「フォルダ名/データセット名」の一覧。"""
    tree = window.ui.dataset_list_widget

    def walk(parent, prefix):
        out = []
        source = tree.invisibleRootItem() if parent is None else parent
        for i in range(source.childCount()):
            child = source.child(i)
            label = prefix + child.text(0)
            out.append(label)
            if child.data(0, Qt.ItemDataRole.UserRole) is None:
                out.extend(walk(child, label + "/"))
        return out

    return walk(None, "")


# --- 単一データセットの削除 ---

def test_removing_one_dataset_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    a, b, c = _add(window, "a"), _add(window, "b"), _add(window, "c")

    _select(window, b)
    window._on_remove_dataset()
    assert _names(window) == ["a", "c"]

    window.undo_stack.undo()

    assert _names(window) == ["a", "b", "c"]
    # 復元されるのは同じインスタンス(スタイル・マスク等がまとめて戻る)
    assert window.project.datasets[1] is b
    assert window._get_dataset_tree_item(b) is not None


def test_undo_restores_the_dataset_with_its_mask_and_style(tmp_path, monkeypatch):
    """誤削除で失われて困るのはデータ本体だけではない。マスク(非破壊の
    外れ値除外)やスタイルもまとめて戻ること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add(window, "styled", color="#ff0000", linewidth=3.5)
    ds.masked_row_indices = [1]

    _select(window, ds)
    window._on_remove_dataset()
    window.undo_stack.undo()

    restored = window.project.datasets[0]
    assert restored is ds
    assert restored.color == "#ff0000"
    assert restored.linewidth == 3.5
    assert list(restored.masked_row_indices) == [1]


def test_redo_removes_it_again(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    a, b = _add(window, "a"), _add(window, "b")

    _select(window, a)
    window._on_remove_dataset()
    window.undo_stack.undo()
    assert _names(window) == ["a", "b"]

    window.undo_stack.redo()

    assert _names(window) == ["b"]
    assert window._get_dataset_tree_item(a) is None


def test_undo_restores_the_original_draw_order(tmp_path, monkeypatch):
    """描画順(=重なり順)まで戻ること。末尾に付け足すだけでは元に戻らない。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    for name in ("a", "b", "c", "d"):
        _add(window, name)
    b = window.project.datasets[1]

    _select(window, b)
    window._on_remove_dataset()
    assert _names(window) == ["a", "c", "d"]

    window.undo_stack.undo()

    assert _names(window) == ["a", "b", "c", "d"]


# --- 複数選択 ---

def test_removing_multiple_datasets_is_undone_in_one_step(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    for name in ("a", "b", "c", "d"):
        _add(window, name)
    b, d = window.project.datasets[1], window.project.datasets[3]

    _select(window, b, d)
    window._on_remove_dataset()
    assert _names(window) == ["a", "c"]

    window.undo_stack.undo()

    assert _names(window) == ["a", "b", "c", "d"]
    assert _tree_names(window) == ["a", "b", "c", "d"]


# --- フォルダごとの削除 ---

def test_removing_a_folder_restores_the_folder_and_its_contents(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    outside = _add(window, "outside")
    folder = window._add_dataset_folder_item("グループ1")
    inner1 = _add(window, "inner1", parent_folder=folder)
    inner2 = _add(window, "inner2", parent_folder=folder)
    assert _tree_names(window) == ["outside", "グループ1", "グループ1/inner1", "グループ1/inner2"]

    window.ui.dataset_list_widget.clearSelection()
    folder.setSelected(True)
    window._on_remove_dataset()

    assert _names(window) == ["outside"]
    assert _tree_names(window) == ["outside"]

    window.undo_stack.undo()

    assert _names(window) == ["outside", "inner1", "inner2"]
    assert _tree_names(window) == ["outside", "グループ1", "グループ1/inner1", "グループ1/inner2"]
    assert window.project.datasets[1] is inner1
    assert window.project.datasets[2] is inner2


def test_undo_restores_a_dataset_into_its_original_folder_position(tmp_path, monkeypatch):
    """フォルダの中の何番目だったか(親フォルダとインデックス)まで戻ること。
    末尾に戻すだけの実装だと、ここで並びが変わってしまう。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("グループ1")
    for name in ("i1", "i2", "i3"):
        _add(window, name, parent_folder=folder)
    i2 = window.project.datasets[1]

    _select(window, i2)
    window._on_remove_dataset()
    assert _tree_names(window) == ["グループ1", "グループ1/i1", "グループ1/i3"]

    window.undo_stack.undo()

    assert _tree_names(window) == ["グループ1", "グループ1/i1", "グループ1/i2", "グループ1/i3"]


def test_selecting_both_a_folder_and_its_child_does_not_double_remove(tmp_path, monkeypatch):
    """フォルダと、その中のデータセットを同時に選択して削除しても、
    Undoで正しく1回分だけ戻ること(最上位アイテムのみを対象にしている)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("グループ1")
    inner = _add(window, "inner", parent_folder=folder)

    window.ui.dataset_list_widget.clearSelection()
    folder.setSelected(True)
    window._get_dataset_tree_item(inner).setSelected(True)
    window._on_remove_dataset()
    assert _names(window) == []

    window.undo_stack.undo()

    assert _names(window) == ["inner"]
    assert _tree_names(window) == ["グループ1", "グループ1/inner"]


# --- Undoスタックへの載り方 ---

def test_removal_pushes_exactly_one_command(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add(window, "a")
    _add(window, "b")
    before = window.undo_stack.count()

    _select(window, *window.project.datasets)
    window._on_remove_dataset()

    assert window.undo_stack.count() == before + 1


def test_command_text_names_a_single_removed_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _add(window, "スペクトル1")

    _select(window, ds)
    window._on_remove_dataset()

    assert "スペクトル1" in window.undo_stack.command(window.undo_stack.count() - 1).text()


def test_removing_with_nothing_selected_pushes_no_command(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add(window, "a")
    window.ui.dataset_list_widget.clearSelection()
    before = window.undo_stack.count()

    window._on_remove_dataset()

    assert window.undo_stack.count() == before
    assert _names(window) == ["a"]


# --- 「別のタブへ移動」経路 ---

def test_remove_without_confirmation_is_also_undoable(tmp_path, monkeypatch):
    """項目C-905の「別のタブへ移動」が使う削除経路も、このタブ側の削除は
    Undoできること(移動先タブへの追加は別のundo_stackなので戻らない
    ―_remove_datasets_without_confirmationのdocstring参照)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    a, b = _add(window, "a"), _add(window, "b")

    window._remove_datasets_without_confirmation([a], description="別のタブへ移動(1件)")
    assert _names(window) == ["b"]

    assert window.undo_stack.command(window.undo_stack.count() - 1).text() == "別のタブへ移動(1件)"
    window.undo_stack.undo()

    assert _names(window) == ["a", "b"]
    assert window.project.datasets[0] is a


# --- プロジェクト読み込みとの関係 ---

def test_loading_a_project_clears_the_undo_stack(tmp_path, monkeypatch):
    """別のプロジェクトを読み込んだら、それ以前のUndo履歴は破棄されること。

    RemoveDatasetCommand も ReorderDatasetsCommand も project.datasets を
    リストごと差し戻すため、履歴が残ったままだと「読み込んだ直後にUndoすると
    読み込んだ内容が以前のデータセット群に置き換わる」という壊れ方をする
    (ProjectModelのインスタンスは load_project() で使い回されるため、
    コマンド側からは文書が入れ替わったことを検出できない)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    kept = _add(window, "kept")
    saved = tmp_path / "saved.graphica"
    window.project.save_project(str(saved))

    doomed = _add(window, "doomed")
    _select(window, doomed)
    window._on_remove_dataset()
    assert window.undo_stack.count() > 0

    window._load_project_from_path(str(saved), add_to_recent=False)

    assert window.undo_stack.count() == 0
    assert window.undo_stack.canUndo() is False
    assert _names(window) == ["kept"]
