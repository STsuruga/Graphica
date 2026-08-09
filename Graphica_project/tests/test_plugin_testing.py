# tests/test_plugin_testing.py
"""core/plugin_testing.py (FakeGraphicaPluginAPI、トラック1 フェーズA-3) のテスト。"""
import pytest

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


# --- 重複登録の拒否(回帰テスト) ---
# 実物(core/plugin_api.py)はfit_function/processor/analyzer/panel/plot_type/
# render_backendの同名重複登録をValueErrorで拒否するが、以前はこのFakeが
# 黙って上書きしていた。プラグイン開発者がこのFakeでの単体テストだけを
# 頼りにすると、重複登録のミスに気づけないまま「テストは通る」状態になり、
# 実際にGraphica本体へ読み込んで初めて失敗する不整合があった。

def test_register_fit_function_rejects_duplicate_name():
    api = FakeGraphicaPluginAPI()
    api.register_fit_function("myfit", lambda x, a: a * x, ["a"])
    with pytest.raises(ValueError):
        api.register_fit_function("myfit", lambda x, a: a * x, ["a"])


def test_register_processor_rejects_duplicate_name():
    api = FakeGraphicaPluginAPI()
    api.register_processor("myproc", lambda ds, params: ds)
    with pytest.raises(ValueError):
        api.register_processor("myproc", lambda ds, params: ds)


def test_register_analyzer_rejects_duplicate_name():
    api = FakeGraphicaPluginAPI()
    api.register_analyzer("myanalysis", lambda ds, params: None)
    with pytest.raises(ValueError):
        api.register_analyzer("myanalysis", lambda ds, params: None)


def test_register_panel_rejects_duplicate_name():
    api = FakeGraphicaPluginAPI()
    api.register_panel("mypanel", lambda project, undo_stack: None)
    with pytest.raises(ValueError):
        api.register_panel("mypanel", lambda project, undo_stack: None)


def test_register_plot_type_rejects_duplicate_name():
    api = FakeGraphicaPluginAPI()
    api.register_plot_type("MyPlot", lambda ds, ax, x, y: None)
    with pytest.raises(ValueError):
        api.register_plot_type("MyPlot", lambda ds, ax, x, y: None)


def test_register_render_backend_rejects_duplicate_name():
    api = FakeGraphicaPluginAPI()
    api.register_render_backend("mybackend", object())
    with pytest.raises(ValueError):
        api.register_render_backend("mybackend", object())
