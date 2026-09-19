"""軸の設定のキーと既定値(graphica/core/axis_settings.py)が、画面・描画・保存の全経路で揃っていること。"""
import ast
import pathlib

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica
import graphica.gui.main_window as main_window_module
from graphica.core.axis_settings import AXIS_SETTING_DEFAULTS, axis_setting
from graphica.gui.main_window import PlotterApp

PACKAGE_DIR = pathlib.Path(graphica.__file__).parent
# 画面の欄から集めた値が、欄の既定のフォントなどで埋まるキー(既定値の {} は「欄の既定のまま」の意味)
FILLED_BY_WIDGETS = {'tick_font', 'axis_label_font', 'legend_font'}


def _make_window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.processEvents()
    return window


def test_the_panel_saves_exactly_the_defined_keys(tmp_path, monkeypatch):
    window = _make_window(tmp_path, monkeypatch)

    assert set(window._gather_settings_from_ui()) == set(AXIS_SETTING_DEFAULTS)


def test_an_old_project_without_any_key_opens_with_the_defaults(tmp_path, monkeypatch):
    """キーを1つも持たない設定を画面に戻して集め直すと、既定値そのものになる。"""
    window = _make_window(tmp_path, monkeypatch)
    window._apply_settings_to_ui_controls({})

    gathered = window._gather_settings_from_ui()

    mismatched = {
        key: (gathered[key], default) for key, default in AXIS_SETTING_DEFAULTS.items()
        if key not in FILLED_BY_WIDGETS and gathered[key] != default
    }
    assert mismatched == {}


def _get_calls_with_axis_keys(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'get' and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value in AXIS_SETTING_DEFAULTS):
            yield f"{path.relative_to(PACKAGE_DIR).as_posix()}:{node.lineno}"


def test_axis_settings_are_read_only_through_axis_setting():
    """settings.get('キー', 既定値) を書くと既定値がまた散らばるので、axis_setting() を使う。"""
    offenders = [
        hit for path in sorted(PACKAGE_DIR.rglob("*.py"))
        if path.name != "axis_settings.py"
        for hit in _get_calls_with_axis_keys(path)
    ]
    assert offenders == []


def test_missing_key_gives_the_default():
    assert axis_setting({}, 'legend_loc') == 'best'
    assert axis_setting({'legend_loc': 'upper left'}, 'legend_loc') == 'upper left'


def test_a_stored_none_is_kept():
    assert axis_setting({'legend_position': None}, 'legend_position') is None


def test_default_lists_are_not_shared():
    axis_setting({}, 'annotations').append({'type': 'text'})

    assert AXIS_SETTING_DEFAULTS['annotations'] == []


@pytest.mark.parametrize("key, legacy_key", [
    ('x_ticks_visible', 'ticks_visible'),
    ('y_ticks_visible', 'ticks_visible'),
    ('x_tick_labels_visible', 'tick_labels_visible'),
    ('y_tick_labels_visible', 'tick_labels_visible'),
])
def test_projects_with_the_shared_tick_key_still_hide_ticks(key, legacy_key):
    assert axis_setting({legacy_key: False}, key) is False
    assert axis_setting({legacy_key: False, key: True}, key) is True
