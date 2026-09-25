"""操作ごとの結果とメッセージを固定する。

どの操作も「利用者がダイアログを既定値のまま OK / はい で閉じた」ものとして流し、出たモーダル、ステータス表示、
操作のあとに開いた窓、できたデータセット、並び(描画順・ツリー・保存用の構造)、Undo の履歴を記録する。
続けて Undo をすべて戻したとき、Redo をすべてやり直したときの並びも記録する。
今の不具合(K-18 の並びの食い違い、K-21 の想定外の例外)も今の挙動として記録する。
"""
import time

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

import recorder
from scenario import pump

ACCEPT = QDialog.DialogCode.Accepted


# --- データ ---

def _peaky(n=41, start=0.0, stop=10.0, center=4.0, height=3.0, width=0.8, base=0.5, ripple=0.2):
    x = np.linspace(start, stop, n)
    y = height * np.exp(-((x - center) ** 2) / (2 * width ** 2)) + ripple * np.sin(3 * x) + base
    return pd.DataFrame({"x": x, "y": y, "yerr": 0.05 + 0.01 * x, "grp": ["a", "b"] * (n // 2) + ["a"] * (n % 2)})


def ds_a():
    from graphica.core.dataset import Dataset

    return Dataset(df=_peaky(), name="A", x_col_name="x", y_col_name="y", y_err_col_name="yerr")


def ds_b():
    from graphica.core.dataset import Dataset

    return Dataset(df=_peaky(start=0.5, stop=10.5, center=6.0, height=2.0, width=1.0, base=0.3, ripple=0.1),
                   name="B", x_col_name="x", y_col_name="y", color="#ff7f0e")


def ds_dup():
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"x": [0.0, 1.0, 1.0, 2.0, 3.0, 3.0, 3.0, 4.0], "y": [1.0, 2.0, 4.0, 3.0, 5.0, 6.0, 7.0, 2.0]})
    return Dataset(df=df, name="重複", x_col_name="x", y_col_name="y")


def ds_text_x():
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"name": ["a", "b", "c", "d"], "value": [1.0, 2.0, 3.0, 4.0]})
    return Dataset(df=df, name="文字のX", x_col_name="name", y_col_name="value")


# --- 記録 ---

def select(tab, *datasets):
    tree = tab.ui.dataset_list_widget
    tree.clearSelection()
    items = [tab._get_dataset_tree_item(ds) for ds in datasets]
    tree.setCurrentItem(items[0])
    for item in items:
        item.setSelected(True)
    pump(2)


def wait_idle(tab, timeout_s=30.0):
    runners = ("fit_runner", "batch_fit_runner", "multi_peak_fit_runner")
    deadline = time.monotonic() + timeout_s
    while any(getattr(tab.fitting, name, None) is not None for name in runners) \
            or tab._data_load_task_runner is not None:
        if time.monotonic() > deadline:
            raise AssertionError("処理が終わらなかった")
        pump(2)
        time.sleep(0.01)
    pump()


def tree_items(tree_widget):
    def walk(item):
        node = {"text": item.text(0), "checked": item.checkState(0).name, "hidden": item.isHidden(),
                "selected": item.isSelected()}
        children = [walk(item.child(i)) for i in range(item.childCount())]
        if children:
            node["children"] = children
        return node

    root = tree_widget.invisibleRootItem()
    return [walk(root.child(i)) for i in range(root.childCount())]


def order_state(tab):
    tab._sync_project_from_ui()

    def group(node):
        if "dataset" in node:
            return node["dataset"].name
        return {node.get("name", ""): [group(c) for c in node.get("children", [])]}

    stack = tab.undo_stack
    return {
        "draw_order": [ds.name for ds in tab.project.datasets],
        "tree": tree_items(tab.ui.dataset_list_widget),
        "group_tree": group(tab.project.dataset_group_tree),
        "current": (tab._get_current_dataset().name if tab._get_current_dataset() is not None else None),
        "undo": {"texts": [stack.text(i) for i in range(stack.count())], "index": stack.index()},
    }


def full_state(tab, windows_before):
    state = order_state(tab)
    state["status"] = tab.statusBar().currentMessage()
    state["datasets"] = [recorder.dataset_summary(ds) for ds in tab.project.datasets]
    state["annotations"] = [s.get("annotations", []) for s in tab.project.all_plot_settings]
    state["windows"] = [recorder.window_contents(w) for w in QApplication.topLevelWidgets()
                        if w.isVisible() and w not in windows_before and w is not tab and w is not tab.window()]
    return state


def run_case(tab, modal_log, action):
    """操作を流し、結果・Undo をすべて戻した状態・Redo をすべてやり直した状態を返す。"""
    pump()
    modal_log.take()
    windows_before = set(QApplication.topLevelWidgets())
    result = {}
    try:
        action(tab)
    except Exception as error:  # 今の挙動として、例外が外に出ること自体を記録する
        result["exception"] = f"{type(error).__name__}: {error}"
    wait_idle(tab)
    result["modals"] = modal_log.take()
    result["after"] = full_state(tab, windows_before)
    result["clipboard"] = QApplication.clipboard().text()

    stack = tab.undo_stack
    if stack.count():
        while stack.canUndo():
            stack.undo()
        pump()
        result["after_undo_all"] = order_state(tab)
        while stack.canRedo():
            stack.redo()
        pump()
        result["after_redo_all"] = order_state(tab)
        result["undo_modals"] = modal_log.take()
    return result


def _new_tab(app_env, *datasets, example_plugin=False):
    tab = app_env.tab(example_plugin=example_plugin)
    for ds in datasets:
        tab._add_dataset(ds)
    tab.undo_stack.clear()
    QApplication.clipboard().clear()
    pump()
    return tab


# --- 処理・フィット・ピーク・色・重ね描き ---

def _two(action):
    def build(app_env):
        a, b = ds_a(), ds_b()
        tab = _new_tab(app_env, a, b)
        select(tab, a, b)
        return tab, action
    return build


def _one(action, make=ds_a, others=(ds_b,)):
    def build(app_env):
        target = make()
        tab = _new_tab(app_env, target, *[m() for m in others])
        select(tab, target)
        return tab, action
    return build


def _with_text_x(action):
    def build(app_env):
        text, a = ds_text_x(), ds_a()
        tab = _new_tab(app_env, text, a)
        select(tab, text, a)
        return tab, action
    return build


def _fill_formula(dialog):
    dialog.output_col_combo.setCurrentText("y2")
    dialog.formula_edit.setText("y * 2 + 1")
    return ACCEPT


def _fit_then_show_and_burn(tab):
    tab.fitting.fit_current_dataset()
    wait_idle(tab)
    select(tab, tab.project.datasets[-1])
    tab.fitting.show_fit_result()


def _fill_row_filter(dialog):
    dialog.formula_edit.setText("y > 1.5")
    return ACCEPT


def _auto_place_peaks(dialog):
    dialog.auto_detect_button.click()
    return ACCEPT


def _copy_methods_after_normalize(tab):
    tab.processing.normalize()
    tab.transfer.copy_methods_text()


def _copy_and_paste_style(tab):
    a, b = tab.project.datasets[0], tab.project.datasets[1]
    select(tab, a)
    tab.transfer.copy_style()
    select(tab, b)
    tab.transfer.paste_style()


OPERATIONS = {
    "arithmetic": _two(lambda t: t.processing.arithmetic()),
    "arithmetic_needs_two": _one(lambda t: t.processing.arithmetic()),
    "align": _two(lambda t: t.processing.align_selected()),
    "mean_sd": _two(lambda t: t.processing.mean_and_sd_of_selected()),
    "normalize": _one(lambda t: t.processing.normalize()),
    "savgol": _one(lambda t: t.processing.savgol_smooth()),
    "baseline": _one(lambda t: t.processing.baseline_correction()),
    "interval_integral": _one(lambda t: t.processing.interval_integral()),
    "cumulative_integral": _one(lambda t: t.processing.cumulative_integral()),
    "split_by_column": _one(lambda t: t.processing.split_by_column()),
    "resample": _one(lambda t: t.processing.resample()),
    "histogram_kde": _one(lambda t: t.processing.histogram_or_kde()),
    "duplicate_x": _one(lambda t: t.processing.detect_duplicate_x(), make=ds_dup),
    "duplicate_x_none": _one(lambda t: t.processing.detect_duplicate_x()),
    "filter_rows": _one(lambda t: t.processing.filter_rows()),
    "filter_rows_empty": _one(lambda t: t.processing.filter_rows()),
    "outliers": _one(lambda t: t.processing.detect_outliers()),
    "batch_column_calculate": _two(lambda t: t.processing.batch_column_calculate()),
    "normalize_text_x": _one(lambda t: t.processing.normalize(), make=ds_text_x),
    "arithmetic_text_x": _with_text_x(lambda t: t.processing.arithmetic()),
    "align_text_x": _with_text_x(lambda t: t.processing.align_selected()),
    "fit": _one(_fit_then_show_and_burn),
    "batch_fit": _two(lambda t: t.fitting.batch_fit_selected()),
    "multi_peak_fit": _one(lambda t: t.fitting.multi_peak_fit_current_dataset()),
    "multi_peak_fit_without_guesses": _one(lambda t: t.fitting.multi_peak_fit_current_dataset()),
    "find_peaks": _one(lambda t: t.peaks.find_peaks()),
    "peak_labels": _one(lambda t: t.peaks.add_peak_labels()),
    "auto_colors": _two(lambda t: t.colors.auto_assign_colors()),
    "colors_from_colormap": _two(lambda t: t.colors.auto_assign_colors_from_colormap()),
    "manage_palettes": _one(lambda t: t.colors.manage_palettes()),
    "copy_paste_style": _two(_copy_and_paste_style),
    "copy_methods_text": _one(_copy_methods_after_normalize),
    "stat_label": _one(lambda t: t.overlays.add_stat_label()),
    "inset": _one(lambda t: t.overlays.add_inset()),
}


# 既定値のままでは何も起きない操作に、先に積んでおく答え
SCRIPTED_ANSWERS = {
    "batch_column_calculate": [("exec", _fill_formula)],
    "split_by_column": [("getItem", ("grp", True))],
    "filter_rows": [("exec", _fill_row_filter)],
    "multi_peak_fit": [("exec", _auto_place_peaks)],
}


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_operation(app_env, modal_log, normalizer, name):
    tab, action = OPERATIONS[name](app_env)
    modal_log.accept_defaults()
    for kind, answer in SCRIPTED_ANSWERS.get(name, ()):
        modal_log.respond_to(kind, answer)
    recorder.check(f"operations/{name}", run_case(tab, modal_log, action), normalizer)


# --- 転送 ---

def test_export_selected_datasets(app_env, modal_log, normalizer, tmp_path):
    a, b = ds_a(), ds_b()
    tab = _new_tab(app_env, a, b)
    modal_log.accept_defaults()
    files = {}

    select(tab, a)
    modal_log.respond_to("getSaveFileName", (str(tmp_path / "one"), "CSV Files (*.csv)"))
    one = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    files["one.csv"] = (tmp_path / "one.csv").read_text(encoding="utf-8-sig")

    select(tab, a, b)
    modal_log.respond_to("getItem", ("Excel (1ブックにシート分け)", True))
    modal_log.respond_to("getSaveFileName", (str(tmp_path / "book.xlsx"), "Excel Files (*.xlsx)"))
    to_excel = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    book = pd.read_excel(tmp_path / "book.xlsx", sheet_name=None)
    files["book.xlsx"] = {sheet: {"columns": list(df.columns), "values": recorder.array_summary(df.to_numpy())}
                          for sheet, df in book.items()}

    folder = tmp_path / "csv_folder"
    folder.mkdir()
    modal_log.respond_to("getExistingDirectory", str(folder))
    to_folder = run_case(tab, modal_log, lambda t: t.transfer.export_data())
    files["csv_folder"] = {p.name: p.read_text(encoding="utf-8-sig") for p in sorted(folder.iterdir())}
    recorder.check("operations/export_data", {"one": one, "to_excel": to_excel, "to_folder": to_folder,
                                              "files": files}, normalizer)


def test_reload_from_source(app_env, modal_log, normalizer, tmp_path):
    from graphica.core.dataset import Dataset

    source = tmp_path / "source.csv"
    source.write_text("x,y\n0,1\n1,2\n2,3\n", encoding="utf-8")
    ds = Dataset(df=pd.read_csv(source), name="元", x_col_name="x", y_col_name="y", source_file=str(source),
                 masked_row_indices=[1])
    tab = _new_tab(app_env, ds)
    select(tab, ds)
    modal_log.accept_defaults()
    source.write_text("x,y\n0,10\n1,20\n2,30\n3,40\n", encoding="utf-8")
    reloaded = run_case(tab, modal_log, lambda t: t.transfer.reload_from_source())
    source.write_text("a,b\n0,1\n", encoding="utf-8")
    missing_column = run_case(tab, modal_log, lambda t: t.transfer.reload_from_source())
    source.unlink()
    missing_file = run_case(tab, modal_log, lambda t: t.transfer.reload_from_source())
    recorder.check("operations/reload_from_source",
                   {"reloaded": reloaded, "missing_column": missing_column, "missing_file": missing_file}, normalizer)


@pytest.mark.parametrize("move", [False, True], ids=["copy", "move"])
def test_copy_or_move_to_other_tab(app_env, modal_log, normalizer, move):
    modal_log.accept_defaults()
    main = app_env.main_window(has_shown_welcome=True)
    first = main.tab_widget.widget(0)
    second = main.add_new_project_tab()
    main.tab_widget.setCurrentIndex(0)
    a, b = ds_a(), ds_b()
    for ds in (a, b):
        first._add_dataset(ds)
    first.undo_stack.clear()
    select(first, a, b)
    result = run_case(first, modal_log, lambda t: t.transfer.copy_or_move_to_tab(move))
    result["other_tab"] = order_state(second)
    result["other_tab_datasets"] = [recorder.dataset_summary(ds) for ds in second.project.datasets]
    recorder.check(f"operations/{'move' if move else 'copy'}_to_other_tab", result, normalizer)


# --- プラグイン ---

PLUGIN_SOURCE = '''
import pandas as pd

from graphica.plugin import AnalysisResult, Dataset


def _scale(dataset, params):
    df = dataset.df.copy()
    df[dataset.y_col_name] = df[dataset.y_col_name] * params.get("factor", 1.0)
    return Dataset(df=df, name=f"{dataset.name} x{params.get('factor')}", x_col_name=dataset.x_col_name,
                   y_col_name=dataset.y_col_name)


def _summary(dataset, params):
    y = dataset.df[dataset.y_col_name]
    return AnalysisResult(
        table=pd.DataFrame({"stat": ["mean", "max"], "value": [float(y.mean()), float(y.max())]}),
        annotations=[{"type": "text", "text": "max", "xy": (1.0, float(y.max())), "xytext": (1.0, float(y.max())),
                      "color": "#000000"}],
        new_datasets=[Dataset(df=dataset.df.head(3).copy(), name="head", x_col_name=dataset.x_col_name,
                              y_col_name=dataset.y_col_name)],
    )


def _broken(dataset, params):
    raise RuntimeError("わざと失敗")


def register(api):
    api.register_processor("倍にする", _scale, category="テスト",
                           param_schema=[{"name": "factor", "type": "float", "default": 2.0, "label": "倍率"}])
    api.register_processor("失敗する処理", _broken)
    api.register_analyzer("要約", _summary)
'''


def _write_test_plugin(tmp_path):
    plugin_dir = tmp_path / "plugins" / "char_test_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        '{"name": "Char Test", "version": "1.0", "api_version": "2.0"}', encoding="utf-8")
    (plugin_dir / "__init__.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    return str(tmp_path / "plugins")


def test_plugin_processors_analyzers_and_menu_action(app_env, modal_log, normalizer, tmp_path, request):
    import sys

    plugin_dir = _write_test_plugin(tmp_path)
    request.addfinalizer(lambda: [sys.modules.pop(m) for m in list(sys.modules) if "char_test_plugin" in m])
    a = ds_a()
    tab = app_env.tab(example_plugin=True, plugin_dirs=(plugin_dir,))
    tab._add_dataset(a)
    tab.undo_stack.clear()
    select(tab, a)
    modal_log.accept_defaults()
    api = tab.plugin_api
    processors = {p.name: p for p in api.get_processors()}
    analyzers = {p.name: p for p in api.get_analyzers()}
    actions = {m.text: m for m in api.menu_actions}
    results = {
        "registered": {"processors": sorted(processors), "analyzers": sorted(analyzers), "menu_actions": sorted(actions),
                       "plugin_menu": [recorder.menu_tree(a.menu()) for a in tab.menuBar().actions()
                                       if a.menu() is not None and "プラグイン" in a.text()]},
        "processor": run_case(tab, modal_log, lambda t: t.plugin_runs.run_processor(processors["倍にする"])),
        "broken_processor": run_case(tab, modal_log, lambda t: t.plugin_runs.run_processor(processors["失敗する処理"])),
        "analyzer": run_case(tab, modal_log, lambda t: t.plugin_runs.run_analyzer(analyzers["要約"])),
        "example_menu_action": run_case(tab, modal_log,
                                        lambda t: t._run_plugin_menu_action(actions["選択中データセットの点数を表示"])),
    }
    recorder.check("operations/plugins", results, normalizer)


# --- 一覧ツリー ---

def _tree_case(name):
    def decorator(fn):
        TREE_CASES[name] = fn
        return fn
    return decorator


TREE_CASES = {}


@_tree_case("add_remove_undo")
def _add_remove(tab, modal_log):
    a, b = tab.project.datasets[:2]
    select(tab, a)
    return run_case(tab, modal_log, lambda t: t._on_remove_dataset())


@_tree_case("duplicate")
def _duplicate(tab, modal_log):
    a, b = tab.project.datasets[:2]
    select(tab, a, b)
    return run_case(tab, modal_log, lambda t: t._on_duplicate_dataset())


@_tree_case("folder_create_move_rename")
def _folders(tab, modal_log):
    def action(t):
        a, b, c = t.project.datasets[:3]
        t.ui.dataset_list_widget.clearSelection()
        t.ui.dataset_list_widget.setCurrentItem(None)
        t._on_new_folder()
        folder = t.ui.dataset_list_widget.topLevelItem(t.ui.dataset_list_widget.topLevelItemCount() - 1)
        tree = t.ui.dataset_list_widget
        item = tree.takeTopLevelItem(tree.indexOfTopLevelItem(t._get_dataset_tree_item(a)))
        folder.addChild(item)
        t._on_dataset_rows_moved(None, 0, 0, folder, 0)
        tree.setCurrentItem(folder)
        modal_log.respond_to("getText", ("改名したフォルダ", True))
        t._on_rename_dataset_folder()
    return run_case(tab, modal_log, action)


@_tree_case("reorder_same_level")
def _reorder(tab, modal_log):
    def action(t):
        tree = t.ui.dataset_list_widget
        moved = tree.takeTopLevelItem(2)
        tree.insertTopLevelItem(0, moved)
        t._on_dataset_rows_moved(None, 2, 2, None, 0)
        pump()
    return run_case(tab, modal_log, action)


@_tree_case("visibility_checkbox_and_all")
def _visibility(tab, modal_log):
    def action(t):
        a = t.project.datasets[0]
        t._get_dataset_tree_item(a).setCheckState(0, Qt.CheckState.Unchecked)
        pump()
        t._on_hide_all_datasets()
        t._on_show_all_datasets()
    return run_case(tab, modal_log, action)


@_tree_case("search")
def _search(tab, modal_log):
    def action(t):
        t._on_dataset_search_changed("b")
        snapshot = tree_items(t.ui.dataset_list_widget)
        t._on_dataset_search_changed("")
        t._search_snapshot = snapshot
    result = run_case(tab, modal_log, action)
    result["while_searching"] = tab._search_snapshot
    return result


@_tree_case("add_into_folder_order_mismatch")
def _k18(tab, modal_log):
    """K-18: フォルダの中に足すと、ツリーの順と描画順が食い違う。"""
    def action(t):
        t.ui.dataset_list_widget.clearSelection()
        t.ui.dataset_list_widget.setCurrentItem(None)
        t._on_new_folder()
        folder = t.ui.dataset_list_widget.topLevelItem(t.ui.dataset_list_widget.topLevelItemCount() - 1)
        from graphica.core.dataset import Dataset

        t._add_dataset(Dataset(df=pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 0.0]}), name="C", x_col_name="x",
                               y_col_name="y"), parent_folder=folder)
    return run_case(tab, modal_log, action)


@_tree_case("new_empty_dataset")
def _new_dataset(tab, modal_log):
    result = run_case(tab, modal_log, lambda t: t._on_create_new_dataset())
    return result


@_tree_case("undo_redo_property_changes")
def _property_undo(tab, modal_log):
    def action(t):
        a = t.project.datasets[0]
        select(t, a)
        t.ui.plot_type_combo.setCurrentText("Scatter")
        t.ui.linewidth_spinbox.setValue(3.0)
        t.ui.legend_name_edit.setText("名前を変えた")
        t.ui.legend_name_edit.editingFinished.emit()
        pump()
    return run_case(tab, modal_log, action)


@pytest.mark.parametrize("name", list(TREE_CASES))
def test_dataset_tree(app_env, modal_log, normalizer, name):
    from graphica.core.dataset import Dataset

    a, b = ds_a(), ds_b()
    c = Dataset(df=pd.DataFrame({"x": [0.0, 5.0], "y": [2.0, 2.5]}), name="bb", x_col_name="x", y_col_name="y")
    tab = _new_tab(app_env, a, b, c)
    modal_log.accept_defaults()
    recorder.check(f"operations/tree_{name}", TREE_CASES[name](tab, modal_log), normalizer)
