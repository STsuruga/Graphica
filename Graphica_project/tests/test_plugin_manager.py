# tests/test_plugin_manager.py
"""core/plugin_api.py (プラグイン機構) に対するテスト。"""
import json
import sys

import pytest

import core.analysis as analysis_module
from core.plugin_api import GraphicaPluginAPI, PluginManager, load_plugins_once
from core.plugin_manifest import PLUGIN_API_VERSION
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


def _write_plugin(tmp_path, folder_name, content, manifest=None):
    """
    プラグインディレクトリを作る(__init__.py + plugin.json、項目F-1)。

    manifest(dict)を渡すとそれをplugin.jsonとして書き込む。省略時は
    api_versionが一致する最小限の有効なmanifestを自動生成する
    (name=folder_name)。manifest=False を渡すとplugin.json自体を書かない
    (マニフェスト欠落時の挙動をテストするため)。
    """
    plugin_dir = tmp_path / folder_name
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(content, encoding="utf-8")
    if manifest is not False:
        if manifest is None:
            manifest = {"name": folder_name, "version": "1.0", "author": "test",
                        "api_version": PLUGIN_API_VERSION}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin_dir


VALID_PLUGIN_SOURCE = '''
def register(api):
    def dummy_func(x, a):
        return a * x
    api.register_fit_function("valid_plugin_fit", dummy_func, ["a"])
    api.register_menu_action("Do something", lambda main_window: None)
'''

MISSING_REGISTER_PLUGIN_SOURCE = '''
x = 1  # register関数が定義されていない
'''

RAISES_ON_REGISTER_PLUGIN_SOURCE = '''
def register(api):
    raise RuntimeError("something went wrong during registration")
'''

# フック単位の隔離(フェーズA-2)を検証するためのプラグイン。
# register_fit_function が(意図的に、既存名との衝突で)失敗しても、
# その後の register_menu_action は実行され続けることを確認する。
PARTIAL_FAILURE_PLUGIN_SOURCE = '''
def register(api):
    def dummy_func(x, a):
        return a * x
    api.register_fit_function("線形", dummy_func, ["a"])  # 組み込み名と衝突して必ず失敗する
    api.register_menu_action("After the failure", lambda main_window: None)
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
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "Valid Plugin", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION, "description": "d"})

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


# --- フック単位の登録失敗の隔離(フェーズA-2) ---

def test_hook_failure_does_not_abort_other_hooks_in_the_same_plugin(tmp_path):
    """
    1つのプラグインが複数のフックを登録する場合、そのうち1つ
    (ここではregister_fit_functionが組み込み名と衝突して失敗)が失敗しても、
    同じregister()内の後続のフック呼び出し(register_menu_action)は
    実行され続けること。
    """
    _write_plugin(tmp_path, "partial_failure_plugin", PARTIAL_FAILURE_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    # register()自体は例外を投げずに最後まで実行されるため、プラグイン全体としては成功扱い
    assert records[0]["error"] is None
    # だが後続のフックは登録されている
    assert len(api.menu_actions) == 1
    assert api.menu_actions[0][0] == "After the failure"


def test_hook_failure_is_recorded_in_registration_errors(tmp_path):
    _write_plugin(tmp_path, "partial_failure_plugin", PARTIAL_FAILURE_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    manager.load_all(api)

    assert len(api.registration_errors) == 1
    error = api.registration_errors[0]
    assert error.plugin_name == "partial_failure_plugin"
    assert error.hook_kind.value == "fit_function"
    assert "衝突" in error.message
    assert isinstance(error.exception, ValueError)


def test_registration_errors_empty_for_fully_successful_plugin(tmp_path):
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    manager.load_all(api)

    assert api.registration_errors == []


# --- 複数探索パス(項目E-1) ---

def test_plugin_manager_accepts_list_of_dirs_and_finds_plugin_in_second_path(tmp_path):
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()
    _write_plugin(dir2, "only_in_dir2", VALID_PLUGIN_SOURCE)

    manager = PluginManager([str(dir1), str(dir2)])
    assert manager.discover_plugin_dirs() == ["only_in_dir2"]

    api = GraphicaPluginAPI()
    records = manager.load_all(api)
    assert len(records) == 1
    assert records[0]["name"] == "only_in_dir2"
    assert records[0]["error"] is None


def test_plugin_manager_same_name_in_both_paths_first_path_wins(tmp_path):
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()
    _write_plugin(dir1, "dup_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "From Dir1", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION})
    _write_plugin(dir2, "dup_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "From Dir2", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION})

    manager = PluginManager([str(dir1), str(dir2)])
    # discover_plugin_dirs()は重複を1回だけ返す
    assert manager.discover_plugin_dirs() == ["dup_plugin"]

    api = GraphicaPluginAPI()
    records = manager.load_all(api)
    assert len(records) == 1
    assert records[0]["info"]["name"] == "From Dir1"


def test_load_plugins_once_accepts_list_of_dirs(tmp_path):
    dir1 = tmp_path / "dir1_not_created_yet"
    dir2 = tmp_path / "dir2_not_created_yet"
    assert not dir1.exists()
    assert not dir2.exists()

    load_plugins_once([str(dir1), str(dir2)])

    assert dir1.exists()
    assert dir2.exists()


# --- 依存パッケージチェック(項目E-3) ---

MISSING_DEPENDENCY_PLUGIN_SOURCE = '''
def register(api):
    api.register_menu_action("Should not be registered", lambda main_window: None)
'''

EXISTING_DEPENDENCY_PLUGIN_SOURCE = '''
def register(api):
    api.register_menu_action("Registered fine", lambda main_window: None)
'''


def test_plugin_with_missing_dependency_is_skipped_and_not_registered(tmp_path):
    _write_plugin(tmp_path, "missing_dep_plugin", MISSING_DEPENDENCY_PLUGIN_SOURCE,
                  manifest={"name": "Needs Missing Dep", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION,
                            "requires": ["some_module_that_does_not_exist_xyz123"]})

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is not None
    assert "some_module_that_does_not_exist_xyz123" in records[0]["error"]
    assert api.menu_actions == []


def test_plugin_with_existing_dependency_loads_normally(tmp_path):
    _write_plugin(tmp_path, "real_dep_plugin", EXISTING_DEPENDENCY_PLUGIN_SOURCE,
                  manifest={"name": "Needs Real Dep", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION, "requires": ["numpy"]})

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is None
    assert len(api.menu_actions) == 1
    assert api.menu_actions[0][0] == "Registered fine"


def test_plugin_without_requires_key_is_unaffected(tmp_path):
    """requiresキーを持たない(今までどおりの)プラグインは、依存チェックの影響を受けない。"""
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is None
    assert len(api.menu_actions) == 1


# --- プラグインマニフェスト plugin.json(項目F-1) ---

def test_plugin_missing_manifest_is_isolated_and_register_not_called(tmp_path):
    """plugin.json自体が無いプラグインは、__init__.pyが正しくてもロードされない
    (register()は一切呼ばれず、他のプラグインのロードは継続する)。"""
    _write_plugin(tmp_path, "no_manifest_plugin", VALID_PLUGIN_SOURCE, manifest=False)
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    by_name = {r["name"]: r for r in records}
    assert by_name["no_manifest_plugin"]["error"] is not None
    assert "plugin.json" in by_name["no_manifest_plugin"]["error"]
    assert by_name["valid_plugin"]["error"] is None
    # no_manifest_pluginのregister()は呼ばれていないので、menu_actionsには
    # valid_pluginの分(1件)しか無い
    assert len(api.menu_actions) == 1
    assert api.menu_actions[0][0] == "Do something"


def test_plugin_manifest_invalid_json_is_isolated(tmp_path):
    plugin_dir = _write_plugin(tmp_path, "broken_json_plugin", VALID_PLUGIN_SOURCE, manifest=False)
    (plugin_dir / "plugin.json").write_text("{not valid json", encoding="utf-8")

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is not None
    assert api.menu_actions == []


def test_plugin_manifest_missing_required_keys_is_isolated(tmp_path):
    _write_plugin(tmp_path, "incomplete_manifest_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "Incomplete"})  # version/api_versionが無い

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is not None
    assert "version" in records[0]["error"]
    assert "api_version" in records[0]["error"]
    assert api.menu_actions == []


def test_plugin_manifest_api_version_mismatch_is_isolated(tmp_path):
    _write_plugin(tmp_path, "old_api_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "Old API Plugin", "version": "1.0", "author": "test",
                            "api_version": "0.9"})

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is not None
    assert "api_version" in records[0]["error"]
    assert "0.9" in records[0]["error"]
    # api_versionが不一致の場合、__init__.py自体がimportされずregister()も呼ばれない
    assert api.menu_actions == []


def test_plugin_manifest_matching_api_version_loads_normally(tmp_path):
    _write_plugin(tmp_path, "current_api_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "Current API Plugin", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION})

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["error"] is None
    assert len(api.menu_actions) == 1


# --- プラグイン管理UIからの個別ON/OFF(項目F-2) ---

def test_disabled_plugin_is_skipped_but_still_listed(tmp_path):
    """無効化されたプラグインはregister()が呼ばれない(=フックが登録されない)が、
    管理UIに表示するため一覧には残る(disabled=Trueとして)。"""
    _write_plugin(tmp_path, "disabled_plugin", VALID_PLUGIN_SOURCE,
                  manifest={"name": "Disabled Plugin", "version": "1.0", "author": "test",
                            "api_version": PLUGIN_API_VERSION})

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api, disabled_names={"disabled_plugin"})

    assert len(records) == 1
    assert records[0]["disabled"] is True
    assert records[0]["error"] is None
    # manifestの表示用情報は読めているが、register()は呼ばれていない
    assert records[0]["info"]["name"] == "Disabled Plugin"
    assert api.menu_actions == []
    assert "valid_plugin_fit" not in analysis_module.get_plugin_fit_type_names()


def test_disabled_plugin_does_not_affect_other_plugins(tmp_path):
    _write_plugin(tmp_path, "disabled_plugin", VALID_PLUGIN_SOURCE)
    _write_plugin(tmp_path, "enabled_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api, disabled_names={"disabled_plugin"})

    by_name = {r["name"]: r for r in records}
    assert by_name["disabled_plugin"]["disabled"] is True
    assert by_name["enabled_plugin"]["disabled"] is False
    assert by_name["enabled_plugin"]["error"] is None
    assert len(api.menu_actions) == 1


def test_no_disabled_names_behaves_as_before(tmp_path):
    """disabled_namesを省略した場合(既存呼び出し元との後方互換)、
    全プラグインのdisabledはFalseで通常通りロードされる。"""
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api = GraphicaPluginAPI()
    manager = PluginManager(str(tmp_path))
    records = manager.load_all(api)

    assert records[0]["disabled"] is False
    assert records[0]["error"] is None


def test_load_plugins_once_threads_disabled_names_through(tmp_path):
    _write_plugin(tmp_path, "disabled_plugin", VALID_PLUGIN_SOURCE)

    api = load_plugins_once(str(tmp_path), disabled_names={"disabled_plugin"})

    assert api.menu_actions == []
    records = plugin_api_module.get_loaded_plugin_records()
    assert records[0]["disabled"] is True
