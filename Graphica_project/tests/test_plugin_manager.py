# tests/test_plugin_manager.py
"""core/plugin_api.py (プラグイン機構) に対するテスト。"""
import sys

import pytest

import core.analysis as analysis_module
from core.plugin_api import GraphicaPluginAPI, PluginManager, load_plugins_once
import core.plugin_api as plugin_api_module


@pytest.fixture(autouse=True)
def _isolate_plugin_state():
    """
    各テストの前後で、プラグイン関連のグローバル状態(フィット関数レジストリ、
    load_plugins_once()のキャッシュ、importされたダミーモジュール)を
    リセットする。テスト間で汚染が伝播しないようにするため。
    """
    yield
    analysis_module._PLUGIN_FIT_FUNCTIONS.clear()
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None
    for mod_name in [k for k in sys.modules if k.startswith("graphica_plugin_")]:
        del sys.modules[mod_name]


def _write_plugin(tmp_path, folder_name, content):
    plugin_dir = tmp_path / folder_name
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(content, encoding="utf-8")
    return plugin_dir


VALID_PLUGIN_SOURCE = '''
PLUGIN_INFO = {"name": "Valid Plugin", "version": "1.0", "author": "test", "description": "d"}

def register(api):
    def dummy_func(x, a):
        return a * x
    api.register_fit_function("valid_plugin_fit", dummy_func, ["a"])
    api.register_menu_action("Do something", lambda main_window: None)
'''

MISSING_INFO_PLUGIN_SOURCE = '''
def register(api):
    pass
'''

MISSING_REGISTER_PLUGIN_SOURCE = '''
PLUGIN_INFO = {"name": "No Register", "version": "1.0", "author": "test", "description": "d"}
'''

RAISES_ON_REGISTER_PLUGIN_SOURCE = '''
PLUGIN_INFO = {"name": "Raises", "version": "1.0", "author": "test", "description": "d"}

def register(api):
    raise RuntimeError("something went wrong during registration")
'''

SYNTAX_ERROR_PLUGIN_SOURCE = '''
this is not valid python (((
'''


def test_discover_plugin_dirs_only_finds_packages(tmp_path):
    _write_plugin(tmp_path, "real_plugin", VALID_PLUGIN_SOURCE)
    (tmp_path / "not_a_plugin").mkdir()  # __init__.py が無いのでプラグインではない
    (tmp_path / "stray_file.py").write_text("x = 1", encoding="utf-8")

    manager = PluginManager(str(tmp_path))
    assert manager.discover_plugin_dirs() == ["real_plugin"]


def test_load_all_registers_valid_plugin(tmp_path):
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert len(records) == 1
    assert records[0]["name"] == "valid_plugin"
    assert records[0]["error"] is None
    assert records[0]["info"]["name"] == "Valid Plugin"

    assert "valid_plugin_fit" in analysis_module.get_plugin_fit_type_names()
    assert len(api.menu_actions) == 1
    assert api.menu_actions[0][0] == "Do something"


def test_load_all_isolates_broken_plugin_missing_info(tmp_path):
    _write_plugin(tmp_path, "broken_plugin", MISSING_INFO_PLUGIN_SOURCE)
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    by_name = {r["name"]: r for r in records}
    assert by_name["broken_plugin"]["error"] is not None
    # 壊れたプラグインがあっても、他の正常なプラグインは読み込まれる
    assert by_name["valid_plugin"]["error"] is None
    assert "valid_plugin_fit" in analysis_module.get_plugin_fit_type_names()


def test_load_all_isolates_plugin_missing_register_func(tmp_path):
    _write_plugin(tmp_path, "no_register", MISSING_REGISTER_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is not None
    assert "register" in records[0]["error"]


def test_load_all_isolates_plugin_that_raises_in_register(tmp_path):
    _write_plugin(tmp_path, "raises_plugin", RAISES_ON_REGISTER_PLUGIN_SOURCE)
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    by_name = {r["name"]: r for r in records}
    assert "something went wrong" in by_name["raises_plugin"]["error"]
    assert by_name["valid_plugin"]["error"] is None


def test_load_all_isolates_plugin_with_syntax_error(tmp_path):
    _write_plugin(tmp_path, "syntax_error_plugin", SYNTAX_ERROR_PLUGIN_SOURCE)
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    by_name = {r["name"]: r for r in records}
    assert by_name["syntax_error_plugin"]["error"] is not None
    assert by_name["valid_plugin"]["error"] is None


def test_discover_plugin_dirs_on_missing_directory_returns_empty(tmp_path):
    manager = PluginManager(str(tmp_path / "does_not_exist"))
    assert manager.discover_plugin_dirs() == []


def test_load_plugins_once_caches_across_calls(tmp_path):
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api1 = load_plugins_once(str(tmp_path))
    api2 = load_plugins_once(str(tmp_path))

    assert api1 is api2
    # 2回呼んでも登録は1回だけ (2回目呼び出しで重複登録エラーが起きない)
    assert analysis_module.get_plugin_fit_type_names().count("valid_plugin_fit") == 1


def test_load_plugins_once_creates_missing_directory(tmp_path):
    plugins_dir = tmp_path / "plugins_not_created_yet"
    assert not plugins_dir.exists()

    load_plugins_once(str(plugins_dir))

    assert plugins_dir.exists()


def test_register_menu_action_stores_shortcut():
    api = GraphicaPluginAPI()
    api.register_menu_action("Test Action", lambda mw: None, shortcut="Ctrl+Shift+T")
    assert api.menu_actions[0] == ("Test Action", api.menu_actions[0][1], "Ctrl+Shift+T")
