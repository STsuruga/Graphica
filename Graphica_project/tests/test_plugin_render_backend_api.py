# tests/test_plugin_render_backend_api.py
"""
GraphicaPluginAPI.register_render_backend() (項目G、描画バックエンド差し替えの
骨組みのみ) に対するテスト。

このロードマップではフックの型定義・登録メカニズムのみを実装し、
gui/canvas.py のレンダリング経路への実際の組み込みはスコープ外(将来の
別ロードマップに切り出す)。そのため、ここでは「登録できる」「重複登録は
隔離される」「未読み込み時は空を返す」という登録メカニズム自体のみを検証し、
実際に何かを描画する経路のテストは意図的に含めない。
"""
import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import GraphicaPluginAPI, get_registered_render_backends


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


class _DummyBackend:
    pass


def test_register_render_backend_and_list():
    api = GraphicaPluginAPI()
    backend = _DummyBackend()
    api.register_render_backend("MyBackend", backend)
    backends = api.get_render_backends()
    assert len(backends) == 1
    assert backends[0].name == "MyBackend"
    assert backends[0].backend is backend


def test_register_render_backend_defaults_plugin_name_to_current_plugin():
    api = GraphicaPluginAPI()
    api._current_plugin_name = "my_plugin"
    api.register_render_backend("MyBackend", _DummyBackend())
    assert api.get_render_backends()[0].plugin_name == "my_plugin"


def test_register_render_backend_duplicate_name_is_isolated_not_raised():
    api = GraphicaPluginAPI()
    result1 = api.register_render_backend("MyBackend", _DummyBackend())
    result2 = api.register_render_backend("MyBackend", _DummyBackend())
    assert result1 is True
    assert result2 is False
    assert len(api.get_render_backends()) == 1
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "render_backend"


def test_get_registered_render_backends_returns_empty_when_unloaded():
    assert get_registered_render_backends() == []


def test_module_accessor_reflects_loaded_singleton():
    api = GraphicaPluginAPI()
    api.register_render_backend("MyBackend", _DummyBackend())
    plugin_api_module._singleton_api = api

    assert [b.name for b in get_registered_render_backends()] == ["MyBackend"]
