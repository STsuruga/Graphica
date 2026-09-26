"""アプリの設定の表(gui/app_settings.py)。"""
import re
from pathlib import Path

from PySide6.QtCore import QSettings

from graphica.gui import app_settings

PACKAGE = Path(app_settings.__file__).resolve().parents[1]


def _all_settings():
    return [v for v in vars(app_settings).values() if isinstance(v, app_settings.Setting)]


def test_keys_are_unique():
    keys = [s.key for s in _all_settings()]
    assert len(keys) == len(set(keys))


def test_export_list_keeps_the_saved_json_layout():
    # 書き出した JSON のキーの並び・型・既定値。変えると、書き出したファイルの中身が変わる
    spec = [(s.key, s.export_as, s.default if s.export_default is app_settings._TABLE_DEFAULT else s.export_default)
            for s in app_settings.EXPORTED_SETTINGS]
    assert spec == [
        ("language", str, ""),
        ("dark_mode", bool, False),
        ("autosave_interval_min", int, 5),
        ("point_label_max_points", int, 1000),
        ("snap_to_grid_enabled", bool, False),
        ("snap_grid_interval_px", int, 10),
        ("custom_color_palettes_json", str, ""),
        ("active_color_palette", str, ""),
        ("quick_access_pinned_actions", list, []),
        ("disabled_plugins", list, []),
    ]


def test_settings_are_opened_only_in_app_settings():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.name == "app_settings.py":
            continue
        if re.search(r"\bQSettings\(", path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_untyped_reads_return_what_qsettings_returns(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue("minimap_visible", False)
    settings.setValue("dataset_property_collapsed_sections", "[]")
    settings.sync()
    reread = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert app_settings.MINIMAP_VISIBLE.read(reread) is False
    assert app_settings.DATASET_PROPERTY_COLLAPSED_SECTIONS.read(reread) == "[]"
    assert app_settings.LANGUAGE.read(reread) == "ja"
    assert app_settings.LANGUAGE.read(reread, default="en") == "en"


def test_list_fixes_differ_by_reader_as_before():
    # 最近使ったファイル・クイックアクセスは "" を [""] にし、書き出しは [] にする(今の挙動)
    assert app_settings.as_list_keeping_empty_string("") == [""]
    assert app_settings.as_list_keeping_empty_string("a") == ["a"]
    assert app_settings.as_list_keeping_empty_string(None) == []
