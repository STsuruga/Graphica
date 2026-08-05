# tests/test_plugin_testing.py
"""core/plugin_testing.py (FakeGraphicaPluginAPI、トラック1 フェーズA-3) のテスト。"""
from core.plugin_testing import FakeGraphicaPluginAPI


def test_register_fit_function_stores_call():
    api = FakeGraphicaPluginAPI()
    func = lambda x, a: a * x
    api.register_fit_function("myfit", func, ["a"], p0=[1.0])
    assert api.fit_functions["myfit"] == {"func": func, "param_names": ["a"], "p0": [1.0]}


def test_register_menu_action_stores_call():
    api = FakeGraphicaPluginAPI()
    callback = lambda main_window: None
    api.register_menu_action("Do it", callback, shortcut="Ctrl+D")
    assert api.menu_actions == [("Do it", callback, "Ctrl+D")]


def test_register_importer_normalizes_extension():
    api = FakeGraphicaPluginAPI()
    loader = lambda fp: None
    api.register_importer(["JDX", ".dx"], loader, priority=5)
    assert set(api.importers.keys()) == {".jdx", ".dx"}
    assert api.importers[".jdx"]["loader"] is loader
    assert api.importers[".jdx"]["priority"] == 5


def test_register_exporter_stores_call_lowercased():
    api = FakeGraphicaPluginAPI()
    writer = lambda fig, path: None
    api.register_exporter("MyFormat", ".myf", writer, name="X")
    assert api.exporters["myformat"] == {"extension": ".myf", "writer": writer, "name": "X"}


def test_plugin_register_function_can_be_verified_via_fake_api():
    """プラグイン開発者が想定する典型的な使い方: register(api)を直接呼んで検証する。"""
    def register(api):
        api.register_fit_function("custom", lambda x, a: a * x, ["a"])
        api.register_menu_action("My Action", lambda mw: None)
        api.register_importer([".custom"], lambda fp: None)
        api.register_exporter("Custom", ".cst", lambda fig, path: None)

    api = FakeGraphicaPluginAPI()
    register(api)

    assert "custom" in api.fit_functions
    assert api.menu_actions[0][0] == "My Action"
    assert ".custom" in api.importers
    assert "custom" in api.exporters
