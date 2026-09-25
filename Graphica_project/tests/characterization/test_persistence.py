"""保存と読み込み・アプリの設定を固定する: データファイルの取り込み、プロジェクトの読み込みと保存、
オートセーブと世代、起動時の復元、設定の書き出しと取り込み、QSettings に書かれる内容。"""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QDialog, QMessageBox

import recorder
from scenario import pump

TESTS_DIR = Path(__file__).resolve().parents[1]
LEGACY_DIR = TESTS_DIR / "fixtures" / "legacy_projects"
LEGACY_PROJECTS = sorted(p.name for p in LEGACY_DIR.iterdir() if p.suffix in (".graphica", ".pkl"))
ACCEPT = QDialog.DialogCode.Accepted


@pytest.fixture
def norm(normalizer):
    from graphica.gui.main_window import resource_path

    normalizer.add_path(LEGACY_DIR, "<LEGACY>")
    normalizer.add_path(TESTS_DIR / "fixtures", "<FIXTURES>")
    normalizer.add_path(resource_path(""), "<PKG>")
    return normalizer


def wait_until(condition, timeout_s=15.0):
    import time

    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("待っている状態にならなかった")
        pump(2)
        time.sleep(0.01)


def tree_items(tree_widget):
    def walk(item):
        node = {"text": item.text(0), "checked": item.checkState(0).name}
        children = [walk(item.child(i)) for i in range(item.childCount())]
        if children:
            node["children"] = children
        return node

    root = tree_widget.invisibleRootItem()
    return [walk(root.child(i)) for i in range(root.childCount())]


def group_tree(node):
    if "dataset" in node:
        return {"dataset": node["dataset"].name}
    return {"name": node.get("name", ""), "children": [group_tree(c) for c in node.get("children", [])]}


def tab_state(tab):
    project = tab.project
    return {
        "status": tab.statusBar().currentMessage(),
        "title": tab.document_title(),
        "unsaved": tab.has_unsaved_changes(),
        "datasets": [recorder.dataset_summary(ds) for ds in project.datasets],
        "group_tree": group_tree(project.dataset_group_tree),
        "tree_widget": tree_items(tab.ui.dataset_list_widget),
        "all_plot_settings": project.all_plot_settings,
        "layout": [project.layout_rows, project.layout_cols, project.layout_mode, project.panel_labels_enabled,
                   project.share_x_axis, project.share_y_axis, project.active_axis_index],
        "undo_count": tab.undo_stack.count(),
    }


def settings_dump(path):
    """設定ファイルに書かれたキーと値(バイナリはハッシュ)。"""
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    dumped = {}
    for key in sorted(settings.allKeys()):
        value = settings.value(key)
        if isinstance(value, (QByteArray, bytes)):
            data = bytes(value)
            value = {"bytes_sha256": hashlib.sha256(data).hexdigest()[:16], "len": len(data)}
        dumped[key] = value
    return dumped


def saved_json(path):
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "content": json.loads(raw.decode("utf-8"))}


# --- データファイルの取り込み ---

def _write_inputs(folder):
    csv = folder / "data.csv"
    csv.write_text("time,signal,noise\n0,1.5,0.1\n1,2.5,0.2\n2,2.0,0.1\n3,3.5,0.3\n", encoding="utf-8")
    tsv = folder / "data.txt"
    tsv.write_text("x\ty\n1\t10\n2\t20\n3\t15\n", encoding="utf-8")
    xlsx = folder / "book.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 7.0]}).to_excel(writer, sheet_name="one", index=False)
        pd.DataFrame({"p": [1.0, 2.0], "q": [9.0, 8.0]}).to_excel(writer, sheet_name="two", index=False)
    xls = folder / "legacy_two_sheets.xls"
    shutil.copy(TESTS_DIR / "fixtures" / "legacy_two_sheets.xls", xls)
    return {"csv": csv, "txt": tsv, "xlsx": xlsx, "xls": xls}


@pytest.mark.parametrize("kind", ["sample", "csv", "txt", "xlsx", "xls"])
def test_import_data_file(app_env, modal_log, norm, tmp_path, kind):
    tab = app_env.tab()
    if kind == "sample":
        modal_log.respond(ACCEPT)
        tab._load_sample_data()
    else:
        path = _write_inputs(tmp_path)[kind]
        if kind in ("xlsx", "xls"):
            # シートを選ぶダイアログ(既定の選択のまま OK)→ シートごとの列の選択(OK)
            modal_log.respond(ACCEPT, ACCEPT, ACCEPT)
        else:
            modal_log.respond(ACCEPT)
        tab.load_data(str(path))
    wait_until(lambda: tab._data_load_task_runner is None)
    pump()
    state = tab_state(tab)
    state["modals"] = modal_log.take()
    state["recent_files"] = tab._get_recent_files()
    recorder.check(f"persistence/import_{kind}", state, norm)


def test_import_cancelled_at_column_preview(app_env, modal_log, norm, tmp_path):
    tab = app_env.tab()
    tab.load_data(str(_write_inputs(tmp_path)["csv"]))
    wait_until(lambda: tab._data_load_task_runner is None)
    state = tab_state(tab)
    state["modals"] = modal_log.take()
    recorder.check("persistence/import_cancelled", state, norm)


def test_import_broken_file(app_env, modal_log, norm, tmp_path):
    tab = app_env.tab()
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a real workbook")
    tab.load_data(str(broken))
    wait_until(lambda: tab._data_load_task_runner is None)
    state = tab_state(tab)
    state["modals"] = modal_log.take()
    recorder.check("persistence/import_broken", state, norm)


# --- プロジェクトの読み込みと保存 ---

@pytest.mark.parametrize("name", LEGACY_PROJECTS)
def test_load_legacy_project_and_save_again(app_env, modal_log, norm, tmp_path, name):
    tab = app_env.tab()
    source = tmp_path / name
    shutil.copy(LEGACY_DIR / name, source)
    tab._load_project_from_path(str(source))
    pump()
    loaded = tab_state(tab)
    loaded["modals"] = modal_log.take()

    saved_path = tmp_path / "resaved.graphica"
    tab._save_project_to_path(str(saved_path))
    after_save = {"status": tab.statusBar().currentMessage(), "title": tab.document_title(),
                  "unsaved": tab.has_unsaved_changes(), "file": saved_json(saved_path),
                  "modals": modal_log.take()}

    pickle_path = tmp_path / "resaved.pkl"
    tab._save_project_to_path(str(pickle_path))
    tab._load_project_from_path(str(pickle_path))
    pump()
    from_pickle = tab_state(tab)
    from_pickle["modals"] = modal_log.take()
    recorder.check(f"persistence/project_{Path(name).stem}",
                   {"loaded": loaded, "saved": after_save, "reloaded_from_pickle": from_pickle,
                    "recent_files": tab._get_recent_files()}, norm)


def _broken_projects(folder):
    newer = folder / "newer.graphica"
    newer.write_text(json.dumps({"format_version": 999, "datasets": []}), encoding="utf-8")
    not_json = folder / "not_json.graphica"
    not_json.write_text("{ this is not json", encoding="utf-8")
    evil = folder / "evil.pkl"
    evil.write_bytes(b"cos\nsystem\n(S'echo hi'\ntR.")
    wrong_ext = folder / "project.txt"
    wrong_ext.write_text("x", encoding="utf-8")
    return {"newer": newer, "not_json": not_json, "evil_pickle": evil, "wrong_extension": wrong_ext,
            "missing": folder / "missing.graphica"}


def test_load_broken_projects(app_env, modal_log, norm, tmp_path):
    tab = app_env.tab()
    results = {}
    for key, path in _broken_projects(tmp_path).items():
        tab._load_project_from_path(str(path))
        pump()
        results[key] = {"modals": modal_log.take(), "title": tab.document_title(),
                        "datasets": len(tab.project.datasets)}
    recorder.check("persistence/project_broken", results, norm)


@pytest.mark.pinned_os  # エラー文言は OS ごとに違う
def test_save_to_unwritable_path(app_env, modal_log, norm, tmp_path):
    tab = app_env.tab()
    folder = tmp_path / "is_a_folder.graphica"
    folder.mkdir()
    tab._save_project_to_path(str(folder))
    recorder.check("persistence/save_failed", {"modals": modal_log.take(), "title": tab.document_title()}, norm)


def test_save_as_and_open_through_dialogs(app_env, modal_log, norm, tmp_path):
    from graphica.core.dataset import Dataset

    tab = app_env.tab()
    tab._add_dataset(Dataset(df=pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}), name="d", x_col_name="x",
                             y_col_name="y"))
    target = tmp_path / "chosen"
    modal_log.respond((str(target), "Graphica Project (*.graphica)"))
    tab.manual_save_as()
    first = {"modals": modal_log.take(), "files": sorted(p.name for p in tmp_path.iterdir()),
             "title": tab.document_title()}
    modal_log.respond((str(tmp_path / "chosen.graphica"), ""))
    tab.manual_load()
    pump()
    second = tab_state(tab)
    second["modals"] = modal_log.take()
    recorder.check("persistence/save_as_and_open", {"save_as": first, "open": second}, norm)


# --- オートセーブ ---

def test_autosave_generations(app_env, modal_log, norm, tmp_path):
    from graphica.core.dataset import Dataset

    tab = app_env.tab()
    autosave_dir = tmp_path / "autosave"
    rounds = []
    for i in range(4):
        tab._add_dataset(Dataset(df=pd.DataFrame({"x": [0.0, 1.0], "y": [float(i), 2.0]}), name=f"d{i}",
                                 x_col_name="x", y_col_name="y"))
        tab.auto_save()
        files = {}
        for path in sorted(autosave_dir.iterdir()):
            content = json.loads(path.read_text(encoding="utf-8"))
            files[path.name] = [ds["name"] for ds in content["datasets"]]
        rounds.append({"status": tab.statusBar().currentMessage(), "files": files})
    modal_log.respond(QDialog.DialogCode.Rejected)
    tab._on_show_autosave_history()
    recorder.check("persistence/autosave_generations",
                   {"autosave_file": tab._autosave_filename, "rounds": rounds, "history_modals": modal_log.take()},
                   norm)


@pytest.mark.parametrize("answer", ["Yes", "No"])
def test_recovery_from_autosave_at_startup(app_env, modal_log, norm, tmp_path, answer):
    from graphica.core.dataset import Dataset
    from graphica.models.project import ProjectModel

    autosave_dir = tmp_path / "autosave"
    autosave_dir.mkdir()
    project = ProjectModel()
    project.datasets = [Dataset(df=pd.DataFrame({"x": [1.0, 2.0], "y": [5.0, 6.0]}), name="残っていた",
                                x_col_name="x", y_col_name="y")]
    project.dataset_group_tree = {"name": "", "children": [{"dataset": project.datasets[0]}]}
    project.save_project(str(autosave_dir / "autosave.graphica"))

    modal_log.respond(getattr(QMessageBox.StandardButton, answer))
    main = app_env.main_window(clean_exit=False, has_shown_welcome=True)
    tab = main.tab_widget.widget(0)
    state = tab_state(tab)
    state["modals"] = modal_log.take()
    recorder.check(f"persistence/recovery_{answer.lower()}", state, norm)


# --- アプリの設定 ---

@pytest.mark.pinned_os  # ウィンドウの位置とドックの配置のバイト列は OS ごとに違う
def test_settings_written_by_startup_and_close(app_env, modal_log, norm, isolated_settings_file):
    main = app_env.main_window()
    after_start = settings_dump(isolated_settings_file)
    main.close()
    pump()
    recorder.check("persistence/settings_startup_and_close",
                   {"after_start": after_start, "after_close": settings_dump(isolated_settings_file),
                    "modals": modal_log.take()}, norm)


def test_settings_export_and_import(app_env, modal_log, norm, tmp_path, isolated_settings_file):
    app_env.settings(custom_color_palettes_json=json.dumps({"研究室": ["#112233", "#445566"]}),
                     active_color_palette="研究室", point_label_max_points=50,
                     quick_access_pinned_actions=["ファイル/上書き保存(&P)"], disabled_plugins=["example_plugin"])
    tab = app_env.tab()
    exported = tmp_path / "exported"
    modal_log.respond((str(exported), "JSON Files (*.json)"))
    tab._on_export_settings()
    export_modals = modal_log.take()
    exported_json = json.loads((tmp_path / "exported.json").read_text(encoding="utf-8"))

    incoming = tmp_path / "incoming.json"
    incoming.write_text(json.dumps({"format_version": 1, "settings": {
        "dark_mode": True, "language": "en", "autosave_interval_min": 12, "unknown_key": 1,
        "quick_access_pinned_actions": ["表示/ダークモード"]}}, ensure_ascii=False), encoding="utf-8")
    modal_log.respond((str(incoming), ""))
    tab._on_import_settings()
    import_modals = modal_log.take()

    broken = tmp_path / "broken.json"
    broken.write_text("[1, 2", encoding="utf-8")
    modal_log.respond((str(broken), ""))
    tab._on_import_settings()
    recorder.check("persistence/settings_export_import", {
        "exported": exported_json, "export_modals": export_modals, "import_modals": import_modals,
        "settings_after_import": settings_dump(isolated_settings_file), "broken_import_modals": modal_log.take(),
    }, norm)


def test_recent_files_list(app_env, modal_log, norm, tmp_path):
    tab = app_env.tab()
    for i in range(12):
        path = tmp_path / f"p{i}.graphica"
        path.write_text("{}", encoding="utf-8")
        tab._add_recent_file(str(path))
    (tmp_path / "p11.graphica").unlink()
    menu_texts = [a.text() for a in tab.recent_files_menu.actions()]
    recorder.check("persistence/recent_files", {"recent": tab._get_recent_files(), "menu": menu_texts,
                                                "modals": modal_log.take()}, norm)


def test_np_values_round_trip(app_env, modal_log, norm, tmp_path):
    """日時・文字列・NaN・マスク・来歴を含むデータセットの保存と読み込み。"""
    from graphica.core.dataset import Dataset
    from graphica.core.provenance import build_provenance

    tab = app_env.tab()
    df = pd.DataFrame({
        "when": pd.date_range("2025-03-01", periods=4, freq="h"),
        "value": [1.0, np.nan, 3.5, -2.0],
        "label": ["a", None, "c", "d"],
        "count": [1, 2, 3, 4],
    })
    ds = Dataset(df=df, name="mixed", x_col_name="when", y_col_name="value", masked_row_indices=[2],
                 point_label_col_name="label", show_point_labels=True)
    ds.provenance = build_provenance("normalize", {"mode": "max"}, [ds])
    tab._add_dataset(ds)
    path = tmp_path / "mixed.graphica"
    tab._save_project_to_path(str(path))
    tab._load_project_from_path(str(path))
    pump()
    state = tab_state(tab)
    state["file"] = saved_json(path)
    state["modals"] = modal_log.take()
    recorder.check("persistence/mixed_types_round_trip", state, norm)
