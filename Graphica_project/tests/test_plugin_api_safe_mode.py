# tests/test_plugin_api_safe_mode.py
"""core/plugin_api.py のセーフモード起動(項目F-4)に対するテスト。"""
import json
import os
import sys

import pytest

import core.analysis as analysis_module
import core.plugin_api as plugin_api_module
from core.plugin_api import (
    is_safe_mode_enabled, load_plugins_once, set_safe_mode,
)
from core.plugin_manifest import PLUGIN_API_VERSION


@pytest.fixture(autouse=True)
def _isolate_plugin_state():
    """
    各テストの前後で、プラグイン関連のグローバル状態(セーフモードフラグ、
    フィット関数レジストリ、load_plugins_once()のキャッシュ、importされた
    ダミーモジュール)をリセットする。test_plugin_manager.pyの
    _isolate_plugin_state と同じパターン(同じプロセス内グローバルを共有する
    テストファイルが複数あるため、片方だけリセットしても意味が無い)。
    """
    yield
    plugin_api_module._safe_mode_enabled = False
    analysis_module._PLUGIN_FIT_FUNCTIONS.clear()
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None
    for mod_name in [k for k in sys.modules if k.startswith("graphica_plugin_")]:
        del sys.modules[mod_name]


def _write_plugin(tmp_path, folder_name, content, manifest=None):
    """tests/test_plugin_manager.py の_write_plugin と同じ(__init__.py + plugin.json)。"""
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


def test_is_safe_mode_enabled_round_trips_with_set_safe_mode():
    assert is_safe_mode_enabled() is False
    set_safe_mode(True)
    assert is_safe_mode_enabled() is True
    set_safe_mode(False)
    assert is_safe_mode_enabled() is False


def test_load_plugins_once_in_safe_mode_returns_empty_api_without_touching_disk(tmp_path):
    """
    セーフモードが有効な状態でload_plugins_once()を呼ぶと、何も登録されていない
    空のAPIが返り、かつ指定したplugins_dirはディスク上に作成すらされない
    (=ファイルシステムに一切触れていないことの証拠)。
    """
    plugins_dir = tmp_path / "plugins_should_not_be_created"
    set_safe_mode(True)

    api = load_plugins_once(str(plugins_dir))

    assert api.get_panels() == []
    assert api.get_processors() == []
    assert api.get_analyzers() == []
    assert api.get_exporters() == []
    assert api.get_importer_extensions() == []
    assert api.get_plot_types() == []
    assert api.menu_actions == []
    assert not os.path.exists(plugins_dir)


def test_load_plugins_once_normal_mode_still_loads_real_plugin(tmp_path):
    """セーフモードの既定値(False)では、これまで通りプラグインが読み込まれる。"""
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)
    assert is_safe_mode_enabled() is False  # 既定でOFFであることの前提確認

    api = load_plugins_once(str(tmp_path))

    assert "valid_plugin_fit" in analysis_module.get_plugin_fit_type_names()
    assert len(api.menu_actions) == 1
    assert api.menu_actions[0][0] == "Do something"


def test_safe_mode_set_after_first_load_does_not_retroactively_empty_the_cache(tmp_path):
    """
    load_plugins_once()の1回目の呼び出しより後にset_safe_mode(True)しても、
    既にキャッシュされた(通常ロード済みの)GraphicaPluginAPIには影響しない。
    これは既存のシングルトンキャッシュの仕組み(_singleton_apiがNoneでなければ
    即座にそれを返す)と同じ挙動であり、main.pyがMainAppWindow()を構築する
    「前」にset_safe_mode()を呼ばなければならない理由そのものでもある。
    """
    _write_plugin(tmp_path, "valid_plugin", VALID_PLUGIN_SOURCE)

    api1 = load_plugins_once(str(tmp_path))
    set_safe_mode(True)
    api2 = load_plugins_once(str(tmp_path))

    assert api1 is api2
    assert len(api2.menu_actions) == 1  # 空にはならない(通常ロード時のまま)
