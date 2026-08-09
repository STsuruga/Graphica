# tests/test_plugin_importer_exporter_api.py
"""
GraphicaPluginAPI.register_importer() (項目B-1) / register_exporter() (項目B-2)
の登録メカニズム自体に対するテスト。read_data_file()側の実際の読み込み配線は
tests/test_workers.py、書き出し配線は本ファイル下部のexport_mixin関連テストで
それぞれ検証する。
"""
import pandas as pd
import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import (
    GraphicaPluginAPI, get_plugin_api, get_registered_exporters, get_registered_importer_extensions,
)


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


def _dummy_loader(file_path):
    return pd.DataFrame({'a': [1]})


def _dummy_writer(fig, out_path):
    pass


# --- register_importer ---

def test_register_importer_normalizes_extension_variants():
    api = GraphicaPluginAPI()
    api.register_importer(["jdx", ".DX", "Dat"], _dummy_loader, name="X")
    assert api.get_importer_extensions() == ['.dat', '.dx', '.jdx']


def test_get_importer_for_extension_accepts_any_case_or_dot_form():
    api = GraphicaPluginAPI()
    api.register_importer([".jdx"], _dummy_loader, name="X")
    assert api.get_importer_for_extension(".jdx") is not None
    assert api.get_importer_for_extension("JDX") is not None
    assert api.get_importer_for_extension("jdx") is not None


def test_get_importer_for_extension_returns_none_when_unregistered():
    api = GraphicaPluginAPI()
    assert api.get_importer_for_extension(".jdx") is None


def test_multiple_importers_same_extension_ordered_by_priority_descending():
    api = GraphicaPluginAPI()
    api.register_importer([".jdx"], _dummy_loader, name="Low", priority=0)
    api.register_importer([".jdx"], _dummy_loader, name="High", priority=5)
    api.register_importer([".jdx"], _dummy_loader, name="Mid", priority=2)

    importer = api.get_importer_for_extension(".jdx")
    assert importer.name == "High"


def test_importers_with_equal_priority_keep_registration_order():
    api = GraphicaPluginAPI()
    api.register_importer([".jdx"], _dummy_loader, name="First", priority=1)
    api.register_importer([".jdx"], _dummy_loader, name="Second", priority=1)

    importer = api.get_importer_for_extension(".jdx")
    assert importer.name == "First"


def test_register_importer_defaults_name_to_current_plugin_name():
    api = GraphicaPluginAPI()
    api._current_plugin_name = "auto_named_plugin"
    api.register_importer([".jdx"], _dummy_loader)
    assert api.get_importer_for_extension(".jdx").name == "auto_named_plugin"


def test_register_importer_bad_extensions_arg_is_isolated_not_raised():
    """extensionsがイテラブルでない等、登録処理自体が例外を出しても
    _safe_register経由でregistration_errorsに記録され、呼び出し元には伝播しない
    (フェーズA-2の隔離が新しいフックにも効いていることの確認)。"""
    api = GraphicaPluginAPI()
    result = api.register_importer(None, _dummy_loader, name="Broken")
    assert result is False
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "importer"


# --- register_exporter ---

def test_register_exporter_and_lookup_by_format_name():
    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", ".myf", _dummy_writer, name="X")
    exporter = api.get_exporter("myformat")
    assert exporter is not None
    assert exporter.format_name == "MyFormat"
    assert exporter.extension == ".myf"


def test_get_exporter_is_case_insensitive():
    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", ".myf", _dummy_writer, name="X")
    assert api.get_exporter("MYFORMAT") is not None
    assert api.get_exporter("myformat") is not None


def test_get_exporter_for_extension():
    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", "myf", _dummy_writer, name="X")  # ピリオド省略
    exporter = api.get_exporter_for_extension(".myf")
    assert exporter is not None
    assert exporter.format_name == "MyFormat"


def test_get_exporters_lists_all_registered():
    api = GraphicaPluginAPI()
    api.register_exporter("FormatA", ".a", _dummy_writer, name="X")
    api.register_exporter("FormatB", ".b", _dummy_writer, name="X")
    names = {exp.format_name for exp in api.get_exporters()}
    assert names == {"FormatA", "FormatB"}


def test_register_exporter_failure_is_isolated():
    api = GraphicaPluginAPI()
    result = api.register_exporter(None, ".x", _dummy_writer, name="Broken")  # format_nameがNone->.lower()で失敗
    assert result is False
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "exporter"


# --- モジュールレベルのアクセサ ---

def test_get_plugin_api_returns_none_when_unloaded():
    assert get_plugin_api() is None


def test_get_registered_importer_extensions_returns_empty_when_unloaded():
    assert get_registered_importer_extensions() == []


def test_get_registered_exporters_returns_empty_when_unloaded():
    assert get_registered_exporters() == []


def test_module_accessors_reflect_loaded_singleton():
    api = GraphicaPluginAPI()
    api.register_importer([".jdx"], _dummy_loader, name="X")
    api.register_exporter("MyFormat", ".myf", _dummy_writer, name="X")
    plugin_api_module._singleton_api = api

    assert get_plugin_api() is api
    assert get_registered_importer_extensions() == ['.jdx']
    assert [e.format_name for e in get_registered_exporters()] == ["MyFormat"]
