# tests/test_plugin_panel_plot_type_api.py
"""
GraphicaPluginAPI.register_panel() (項目D-1) / register_plot_type() (項目D-2)
の登録メカニズム自体に対するテスト。実際のドック生成配線はgui/main_window.py側、
plot_type描画のフォールバック配線はgui/canvas.py側でそれぞれ検証する(Qt/matplotlib
を必要としないため、ここではAPIの登録・参照ロジックのみを対象とする)。
"""
import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import GraphicaPluginAPI, get_registered_panels, get_registered_plot_types


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


def _dummy_widget_factory(project, undo_stack):
    return object()


def _dummy_drawer(dataset, ax, x_data, y_data):
    return None


# --- register_panel ---

def test_register_panel_and_list():
    api = GraphicaPluginAPI()
    api.register_panel("My Panel", _dummy_widget_factory, area="left")
    panels = api.get_panels()
    assert len(panels) == 1
    assert panels[0].name == "My Panel"
    assert panels[0].area == "left"
    assert panels[0].widget_factory is _dummy_widget_factory


def test_register_panel_defaults_area_to_right():
    api = GraphicaPluginAPI()
    api.register_panel("My Panel", _dummy_widget_factory)
    assert api.get_panels()[0].area == "right"


def test_register_panel_defaults_plugin_name_to_current_plugin():
    api = GraphicaPluginAPI()
    api._current_plugin_name = "my_plugin"
    api.register_panel("My Panel", _dummy_widget_factory)
    assert api.get_panels()[0].plugin_name == "my_plugin"


def test_register_panel_duplicate_name_is_isolated_not_raised():
    api = GraphicaPluginAPI()
    result1 = api.register_panel("My Panel", _dummy_widget_factory)
    result2 = api.register_panel("My Panel", _dummy_widget_factory)
    assert result1 is True
    assert result2 is False
    assert len(api.get_panels()) == 1
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "panel"


# --- register_plot_type ---

def test_register_plot_type_and_list():
    api = GraphicaPluginAPI()
    api.register_plot_type("Heatmap", _dummy_drawer, requires_2d=True)
    plot_types = api.get_plot_types()
    assert len(plot_types) == 1
    assert plot_types[0].type_name == "Heatmap"
    assert plot_types[0].requires_2d is True
    assert plot_types[0].drawer is _dummy_drawer


def test_register_plot_type_defaults_requires_2d_to_false():
    api = GraphicaPluginAPI()
    api.register_plot_type("Heatmap", _dummy_drawer)
    assert api.get_plot_types()[0].requires_2d is False


def test_get_plot_type_looks_up_by_name():
    api = GraphicaPluginAPI()
    api.register_plot_type("Heatmap", _dummy_drawer)
    found = api.get_plot_type("Heatmap")
    assert found is not None
    assert found.type_name == "Heatmap"


def test_get_plot_type_returns_none_when_unregistered():
    api = GraphicaPluginAPI()
    assert api.get_plot_type("Heatmap") is None


def test_register_plot_type_duplicate_name_is_isolated_not_raised():
    api = GraphicaPluginAPI()
    result1 = api.register_plot_type("Heatmap", _dummy_drawer)
    result2 = api.register_plot_type("Heatmap", _dummy_drawer)
    assert result1 is True
    assert result2 is False
    assert len(api.get_plot_types()) == 1
    assert len(api.registration_errors) == 1
    assert api.registration_errors[0].hook_kind.value == "plot_type"


# --- モジュールレベルのアクセサ ---

def test_get_registered_panels_returns_empty_when_unloaded():
    assert get_registered_panels() == []


def test_get_registered_plot_types_returns_empty_when_unloaded():
    assert get_registered_plot_types() == []


def test_module_accessors_reflect_loaded_singleton():
    api = GraphicaPluginAPI()
    api.register_panel("My Panel", _dummy_widget_factory)
    api.register_plot_type("Heatmap", _dummy_drawer)
    plugin_api_module._singleton_api = api

    assert [p.name for p in get_registered_panels()] == ["My Panel"]
    assert [p.type_name for p in get_registered_plot_types()] == ["Heatmap"]
