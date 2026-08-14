# tests/test_element_constants_plugin.py
"""plugins/element_constants/ (項目P-805) のテスト。

データ検索ロジック(data.py)はGUI/plugin機構いずれにも依存しないため直接テストし、
register()の配線はcore/plugin_testing.pyのFakeGraphicaPluginAPI経由で検証、
実際の plugins/ ディレクトリからの読み込み自体はPluginManagerで検証する
(いずれもtests/test_plugin_manager.pyの既存パターンを踏襲)。
"""
import os

import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import PluginManager, GraphicaPluginAPI
from core.plugin_testing import FakeGraphicaPluginAPI
from plugins.element_constants.data import find_element, find_constant, ELEMENTS_BY_NUMBER


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


# --- data.py: find_element ---

def test_find_element_by_symbol_case_insensitive():
    assert find_element("Fe") == [(26, "Fe", "Iron", 55.845)]
    assert find_element("fe") == [(26, "Fe", "Iron", 55.845)]
    assert find_element("FE") == [(26, "Fe", "Iron", 55.845)]


def test_find_element_by_atomic_number():
    assert find_element("1") == [(1, "H", "Hydrogen", 1.008)]
    assert find_element("118") == [(118, "Og", "Oganesson", 294)]


def test_find_element_by_name_exact():
    assert find_element("Iron") == [(26, "Fe", "Iron", 55.845)]
    assert find_element("iron") == [(26, "Fe", "Iron", 55.845)]


def test_find_element_by_name_partial_match_returns_multiple():
    results = find_element("hy")
    symbols = [row[1] for row in results]
    assert "H" in symbols  # Hydrogen


def test_find_element_no_match_returns_empty_list():
    assert find_element("xx") == []
    assert find_element("999") == []


def test_find_element_empty_query_returns_empty_list():
    assert find_element("") == []
    assert find_element("   ") == []


def test_all_118_elements_present_and_unique():
    assert len(ELEMENTS_BY_NUMBER) == 118
    assert set(ELEMENTS_BY_NUMBER.keys()) == set(range(1, 119))


# --- data.py: find_constant ---

def test_find_constant_common_keyword_speed_of_light():
    results = find_constant("光速")
    assert len(results) == 1
    name, value, unit, uncertainty = results[0]
    assert value == pytest.approx(299792458.0)
    assert unit == "m s^-1"


def test_find_constant_common_keyword_planck():
    results = find_constant("プランク定数")
    assert len(results) == 1
    name, value, unit, uncertainty = results[0]
    assert value == pytest.approx(6.62607015e-34, rel=1e-6)


def test_find_constant_generic_substring_search():
    results = find_constant("electron mass")
    names = [r[0] for r in results]
    assert "electron mass" in names


def test_find_constant_no_match_returns_empty_list():
    assert find_constant("this-does-not-exist-anywhere") == []


def test_find_constant_empty_query_returns_empty_list():
    assert find_constant("") == []


# --- register()の配線 (FakeGraphicaPluginAPI経由) ---

def test_register_adds_exactly_one_panel():
    import plugins.element_constants as element_constants_plugin

    api = FakeGraphicaPluginAPI()
    element_constants_plugin.register(api)

    assert len(api.panels) == 1
    assert "元素・物理定数テーブル" in api.panels
    assert api.panels["元素・物理定数テーブル"]["area"] == "right"


def test_registered_widget_factory_returns_a_qwidget(qapp):
    import plugins.element_constants as element_constants_plugin
    from PySide6.QtWidgets import QWidget

    api = FakeGraphicaPluginAPI()
    element_constants_plugin.register(api)

    widget_factory = api.panels["元素・物理定数テーブル"]["widget_factory"]
    widget = widget_factory(None, None)  # (project, undo_stack) — このパネルはどちらも使わない
    assert isinstance(widget, QWidget)


# --- 実際のplugins/ディレクトリからの読み込み(スモークテスト) ---

def test_element_constants_plugin_loads_from_real_plugins_directory(qapp):
    """
    tmp_pathへの書き出しではなく、実際にリポジトリに同梱されているplugins/を
    そのままPluginManagerに渡して読み込む。plugin.jsonのapi_versionの誤り、
    __init__.py内の相対import(from .data import ...)の解決失敗など、
    tmp_pathベースのテストでは検出できない「本番と同じ読み込み経路」の
    不具合を検出するためのスモークテスト。
    """
    plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
    manager = PluginManager(plugins_dir)
    api = GraphicaPluginAPI()

    records = manager.load_all(api)

    element_constants_records = [r for r in records if r["name"] == "element_constants"]
    assert len(element_constants_records) == 1
    assert element_constants_records[0]["error"] is None
    assert any(panel.name == "元素・物理定数テーブル" for panel in api.get_panels())
