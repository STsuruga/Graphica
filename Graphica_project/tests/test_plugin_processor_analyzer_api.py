# tests/test_plugin_processor_analyzer_api.py
"""
GraphicaPluginAPI.register_processor() (項目C-1) / register_analyzer() (項目C-2)
の登録メカニズム自体に対するテスト。実際のメニュー配線・実行(ダイアログ→fn呼び出し→
AddDatasetCommand)は tests/test_dataset_mixin.py 側で検証する。
"""
import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import GraphicaPluginAPI, get_registered_analyzers, get_registered_processors


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


def _dummy_processor_fn(dataset, params):
    return dataset


def _dummy_analyzer_fn(dataset, params):
    return None


# --- register_processor ---

def test_register_processor_and_list():
    api = GraphicaPluginAPI()
    api.register_processor("Smooth", _dummy_processor_fn, category="denoise")
    procs = api.get_processors()
    assert len(procs) == 1
    assert procs[0].name == "Smooth"
    assert procs[0].category == "denoise"


def test_register_processor_defaults_category_to_general():
    api = GraphicaPluginAPI()
    api.register_processor("Smooth", _dummy_processor_fn)
    assert api.get_processors()[0].category == "general"


def test_register_processor_stores_param_schema():
    schema = [{"name": "window", "type": "int", "default": 5}]
    api = GraphicaPluginAPI()
    api.register_processor("Smooth", _dummy_processor_fn, param_schema=schema)
    assert api.get_processors()[0].param_schema == schema


def test_register_processor_defaults_plugin_name_to_current_plugin():
    api = GraphicaPluginAPI()
    api._current_plugin_name = "my_plugin"
    api.register_processor("Smooth", _dummy_processor_fn)
    assert api.get_processors()[0].plugin_name == "my_plugin"


def test_get_processor_categories_deduped_and_sorted():
    api = GraphicaPluginAPI()
    api.register_processor("A", _dummy_processor_fn, category="z-cat")
    api.register_processor("B", _dummy_processor_fn, category="a-cat")
    api.register_processor("C", _dummy_processor_fn, category="a-cat")
    assert api.get_processor_categories() == ["a-cat", "z-cat"]


def test_register_processor_duplicate_name_is_isolated_not_raised():
    api = GraphicaPluginAPI()
    result1 = api.register_processor("Smooth", _dummy_processor_fn)
    result2 = api.register_processor("Smooth", _dummy_processor_fn)
    assert result1 is True
    assert result2 is False
    assert len(api.get_processors()) == 1
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "processor"


# --- register_analyzer ---

def test_register_analyzer_and_list():
    api = GraphicaPluginAPI()
    api.register_analyzer("Peaks", _dummy_analyzer_fn, output_kind="table")
    analyzers = api.get_analyzers()
    assert len(analyzers) == 1
    assert analyzers[0].name == "Peaks"
    assert analyzers[0].output_kind == "table"


def test_register_analyzer_defaults_output_kind_to_table():
    api = GraphicaPluginAPI()
    api.register_analyzer("Peaks", _dummy_analyzer_fn)
    assert api.get_analyzers()[0].output_kind == "table"


def test_register_analyzer_stores_param_schema():
    schema = [{"name": "threshold", "type": "float", "default": 0.5}]
    api = GraphicaPluginAPI()
    api.register_analyzer("Peaks", _dummy_analyzer_fn, param_schema=schema)
    assert api.get_analyzers()[0].param_schema == schema


def test_register_analyzer_duplicate_name_is_isolated_not_raised():
    api = GraphicaPluginAPI()
    result1 = api.register_analyzer("Peaks", _dummy_analyzer_fn)
    result2 = api.register_analyzer("Peaks", _dummy_analyzer_fn)
    assert result1 is True
    assert result2 is False
    assert len(api.get_analyzers()) == 1
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "analyzer"


# --- モジュールレベルのアクセサ ---

def test_get_registered_processors_returns_empty_when_unloaded():
    assert get_registered_processors() == []


def test_get_registered_analyzers_returns_empty_when_unloaded():
    assert get_registered_analyzers() == []


def test_module_accessors_reflect_loaded_singleton():
    api = GraphicaPluginAPI()
    api.register_processor("Smooth", _dummy_processor_fn)
    api.register_analyzer("Peaks", _dummy_analyzer_fn)
    plugin_api_module._singleton_api = api

    assert [p.name for p in get_registered_processors()] == ["Smooth"]
    assert [a.name for a in get_registered_analyzers()] == ["Peaks"]
