"""アプリの設定の読み書きを固定する(R-4 の前の基準)。

A: 設定ファイルに書いてある値(型付き・文字列・要素 1 つのリスト・壊れた値)を起動時にどう読んだか。
B: 設定を書く操作ごとに、設定ファイルに何が書かれたか。
"""
import json

import pytest
from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog

import recorder
from scenario import dispose, pump

ACCEPT = QDialog.DialogCode.Accepted


@pytest.fixture(autouse=True)
def _reset_custom_colors():
    # 「最近使った色」はプロセス全体のカスタムカラー欄に入るので、シナリオごとに白に戻す
    for i in range(16):
        QColorDialog.setCustomColor(i, QColor("#ffffff"))
    yield


def settings_dump(path):
    import hashlib

    settings = QSettings(str(path), QSettings.Format.IniFormat)
    dumped = {}
    for key in sorted(settings.allKeys()):
        value = settings.value(key)
        if isinstance(value, (QByteArray, bytes)):
            data = bytes(value)
            value = {"bytes_sha256": hashlib.sha256(data).hexdigest()[:16], "len": len(data)}
        dumped[key] = value
    return dumped


def _what_the_tab_read(tab):
    from graphica.core.i18n import get_language
    from graphica.core.named_colors import load_named_colors
    from graphica.gui.main_window import disabled_plugin_names

    return {
        "dark_mode": tab.canvas.dark_mode,
        "language": get_language(),
        "autosave": [tab.autosave_timer.isActive(), tab.autosave_timer.interval()],
        "autosave_file": tab._autosave_filename,
        "point_label_max_points": tab.canvas.point_label_max_points,
        "snap": [tab.snap_to_grid_enabled, tab.snap_grid_interval_px],
        "minimap_visible": tab.minimap_visible,
        "recent_files": tab._get_recent_files(),
        "recent_menu": [a.text() for a in tab.recent_files_menu.actions()],
        "quick_access_ids": tab._get_pinned_quick_access_ids(),
        "quick_access_toolbar": list(getattr(tab, "_quick_access_actions", {}).keys()),
        "disabled_plugins": sorted(disabled_plugin_names(tab.settings)),
        "collapsed_sections": sorted(tab._load_collapsed_property_sections()),
        "dock_presets": sorted(tab._load_dock_layout_presets()),
        "palettes": tab.colors.load_palettes(),
        "active_color_cycle": tab.colors.active_color_cycle(),
        "named_colors": load_named_colors(tab.settings),
        "custom_colors": [QColorDialog.customColor(i).name() for i in range(16)],
        "had_clean_exit": tab._had_clean_exit,
        "canvas_detached": tab.canvas_detached,
    }


def _write_ini(path, lines):
    path.write_text("[General]\n" + "\n".join(lines) + "\n", encoding="utf-8")


def _seed_typed(env, ini, case):
    env.settings(
        dark_mode=True, language="en", autosave_interval_min=12, point_label_max_points=300,
        snap_to_grid_enabled=True, snap_grid_interval_px=24, minimap_visible=False,
        recent_files=[str(case / "a.graphica"), str(case / "b.graphica")],
        quick_access_pinned_actions=["ファイル/上書き保存(P)"], disabled_plugins=["Example Plugin"],
        dataset_property_collapsed_sections=json.dumps(["waterfall", "map"]),
        custom_color_palettes_json=json.dumps({"研究室": ["#112233", "#445566"]}), active_color_palette="研究室",
        named_colors_json=json.dumps([{"name": "水", "color": "#1f77b4"}]),
        recent_colors=["#ff0000", "#00ff00"], clean_exit=True,
    )


def _seed_raw_strings(env, ini, case):
    # INI に文字列のまま書いたもの。要素が 1 つのリストは文字列で返る
    _write_ini(ini, [
        "dark_mode=true", "language=en", "autosave_interval_min=7", "point_label_max_points=50",
        "snap_to_grid_enabled=false", "snap_grid_interval_px=16", "minimap_visible=false",
        f"recent_files={(case / 'only.graphica').as_posix()}",
        "quick_access_pinned_actions=ファイル/上書き保存(P)", "disabled_plugins=Example Plugin",
        "recent_colors=#abcdef", "clean_exit=true",
    ])


def _seed_broken(env, ini, case):
    _write_ini(ini, [
        "dark_mode=maybe", "autosave_interval_min=abc", "point_label_max_points=-5", "snap_grid_interval_px=x",
        "dataset_property_collapsed_sections=not json", "custom_color_palettes_json={broken",
        "active_color_palette=存在しない", "named_colors_json=[{\"name\": 1}]", "dock_layout_presets=[1,2",
        "clean_exit=false",
    ])


SEEDS = {"empty": lambda env, ini, case: None, "typed": _seed_typed, "raw_strings": _seed_raw_strings,
         "broken": _seed_broken}


@pytest.mark.parametrize("seed", list(SEEDS))
def test_startup_reads(app_env, modal_log, normalizer, isolated_settings_file, tmp_path, monkeypatch, seed):
    from pathlib import Path

    from graphica.core.app_paths import get_app_data_dir

    # オートセーブの保存先を決めていないときは利用者のフォルダになる。本物を見ると、そこに残っている
    # オートセーブの有無で復元の確認が出るかどうかが機械ごとに変わるので、空の一時フォルダに向ける
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    normalizer.add_path(get_app_data_dir(), "<APPDATA>")
    ini = Path(isolated_settings_file)
    SEEDS[seed](app_env, ini, tmp_path)
    app_env.use_plugins(example_plugin=True)
    from graphica.gui.main_window import PlotterApp

    tab = PlotterApp(run_startup_checks=True, tab_id=None)
    pump()
    read = _what_the_tab_read(tab)
    read["modals"] = modal_log.take()
    read["settings_after_start"] = settings_dump(ini)
    dispose(tab)
    recorder.check(f"app_settings/startup_{seed}", read, normalizer)


# --- 設定を書く操作 ---

def _fill_preferences(tmp_path):
    def fill(dialog):
        dialog.dark_mode_checkbox.setChecked(True)
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        dialog.autosave_spinbox.setValue(9)
        dialog.autosave_dir_edit.setText(str(tmp_path / "elsewhere"))
        dialog.point_label_max_spinbox.setValue(250)
        dialog.snap_to_grid_checkbox.setChecked(True)
        dialog.snap_grid_interval_spinbox.setValue(30)
        return ACCEPT
    return fill


def _op_preferences(tab, modal_log, tmp_path):
    modal_log.respond_to("exec", _fill_preferences(tmp_path))
    tab._on_show_preferences()


def _op_preferences_unchanged(tab, modal_log, tmp_path):
    modal_log.respond_to("exec", ACCEPT)
    tab._on_show_preferences()


def _op_autosave_interval(tab, modal_log, tmp_path):
    modal_log.respond_to("getInt", (0, True))
    tab._on_configure_autosave_interval()
    modal_log.respond_to("getInt", (15, True))
    tab._on_configure_autosave_interval()


def _op_dark_mode(tab, modal_log, tmp_path):
    tab.dark_mode_action.setChecked(True)
    pump()


def _op_minimap(tab, modal_log, tmp_path):
    tab._on_toggle_minimap(False)


def _op_recent_files(tab, modal_log, tmp_path):
    for name in ("a", "b", "a"):
        tab._add_recent_file(str(tmp_path / f"{name}.graphica"))
    tab._last_recent_snapshot = tab._get_recent_files()
    tab._on_clear_recent_files()


def _op_quick_access(tab, modal_log, tmp_path):
    actions = tab._collect_menu_actions()
    for path, action in actions[:2]:
        tab.pin_quick_access_action("/".join(path), action)
    tab.unpin_quick_access_action("/".join(actions[0][0]))


def _op_palettes(tab, modal_log, tmp_path):
    tab.colors.save_palettes({"寒色": ["#0000ff", "#00ffff"]})
    modal_log.respond_to("exec", ACCEPT)
    tab.colors.manage_palettes()


def _op_dock_preset(tab, modal_log, tmp_path):
    modal_log.respond_to("getText", ("自分の配置", True))
    tab._on_save_dock_layout_preset()


def _op_collapse_section(tab, modal_log, tmp_path):
    tab._prop_sections["waterfall"]["toggle"].setChecked(False)
    tab._prop_sections["map"]["toggle"].setChecked(False)
    tab._prop_sections["map"]["toggle"].setChecked(True)


def _op_detach_canvas(tab, modal_log, tmp_path):
    tab._detach_canvas()
    pump()
    tab._reattach_canvas()
    pump()


def _op_named_colors(tab, modal_log, tmp_path):
    from graphica.core.named_colors import add_named_color, load_named_colors, save_named_colors

    save_named_colors(tab.settings, add_named_color(load_named_colors(tab.settings), "塩", "#aa0000"))


def _op_recent_colors(tab, modal_log, tmp_path):
    from graphica.gui.color_history import get_color_with_history

    for color in ("#123456", "#abcdef", "#123456"):
        modal_log.respond_to("getColor", QColor(color))
        get_color_with_history(tab.settings, tab)


OPERATIONS = {
    "preferences": _op_preferences, "preferences_unchanged": _op_preferences_unchanged,
    "autosave_interval": _op_autosave_interval, "dark_mode": _op_dark_mode, "minimap": _op_minimap,
    "recent_files": _op_recent_files, "quick_access": _op_quick_access, "palettes": _op_palettes,
    "dock_preset": _op_dock_preset, "collapse_section": _op_collapse_section, "detach_canvas": _op_detach_canvas,
    "named_colors": _op_named_colors, "recent_colors": _op_recent_colors,
}


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_settings_written_by(app_env, modal_log, normalizer, isolated_settings_file, tmp_path, monkeypatch, name):
    if name == "recent_colors":
        def get_color(*args, **kwargs):
            modal_log.record({"kind": "QColorDialog.getColor"})
            return modal_log._next("getColor", QColor())
        monkeypatch.setattr(QColorDialog, "getColor", get_color)
    tab = app_env.tab(example_plugin=True)
    before = settings_dump(isolated_settings_file)
    modal_log.take()
    OPERATIONS[name](tab, modal_log, tmp_path)
    pump()
    record = {
        "before": before,
        "after": settings_dump(isolated_settings_file),
        "modals": modal_log.take(),
        "status": tab.statusBar().currentMessage(),
        "read_back": _what_the_tab_read(tab),
    }
    if hasattr(tab, "_last_recent_snapshot"):
        record["recent_before_clear"] = tab._last_recent_snapshot
    recorder.check(f"app_settings/written_by_{name}", record, normalizer)
