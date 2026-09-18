"""core/plugin_testing.py(プラグイン作者向けの偽物)のテスト。"""
import pandas as pd
import pytest

from core.dataset import Dataset
from core.named_colors import NamedColorError
from core.plugin_testing import FakeGraphicaPluginAPI, FakePluginContext
from core.plugin_types import PluginMenuAction


def test_register_fit_function_stores_call():
    api = FakeGraphicaPluginAPI()
    func = lambda x, a: a * x
    api.register_fit_function("myfit", func, ["a"], p0=[1.0])
    assert api.fit_functions["myfit"] == {"func": func, "param_names": ["a"], "p0": [1.0]}


def test_register_menu_action_stores_call():
    api = FakeGraphicaPluginAPI()
    def callback(ctx):
        return None

    api.register_menu_action("Do it", callback, shortcut="Ctrl+D")
    assert api.menu_actions == [PluginMenuAction("Do it", callback, "Ctrl+D", "test_plugin")]


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
        api.register_menu_action("My Action", lambda ctx: None)
        api.register_importer([".custom"], lambda fp: None)
        api.register_exporter("Custom", ".cst", lambda fig, path: None)

    api = FakeGraphicaPluginAPI()
    register(api)

    assert "custom" in api.fit_functions
    assert api.menu_actions[0].text == "My Action"
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
    api.register_panel("mypanel", lambda ctx: None)
    with pytest.raises(ValueError):
        api.register_panel("mypanel", lambda ctx: None)


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


# --- FakePluginContext ---

def _dataset(name="D"):
    return Dataset(name=name, df=pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 2.0]}), x_col_name="x", y_col_name="y")


def test_fake_context_runs_a_menu_callback_end_to_end():
    api = FakeGraphicaPluginAPI(plugin_name="counter")

    def show_count(ctx):
        ctx.show_message(f"{len(ctx.current_dataset().visible_df)} 点")

    api.register_menu_action("点数", show_count)
    ds = _dataset()
    ctx = FakePluginContext(datasets=[ds], current=ds, plugin_name="counter")

    api.menu_actions[0].callback(ctx)

    assert ctx.messages == [("info", "counter", "2 点")]


def test_fake_context_records_undoable_changes_and_notifies():
    ds = _dataset()
    ctx = FakePluginContext(datasets=[ds], current=ds)
    changes = []
    ctx.on_datasets_changed(lambda: changes.append(len(ctx.datasets())))

    ctx.set_dataset_properties(ds, {"color": "#ff0000"}, description="色")
    ctx.add_dataset(_dataset("E"))

    assert ds.color == "#ff0000"
    assert ctx.undo_descriptions == ["色", "[test_plugin] データセットの追加"]
    assert changes == [1, 2]


def test_fake_context_rejects_unknown_dataset_attributes_like_the_real_one():
    ds = _dataset()
    ctx = FakePluginContext(datasets=[ds])
    with pytest.raises(AttributeError, match="no_such_field"):
        ctx.set_dataset_properties(ds, {"no_such_field": 1})


def test_fake_context_validates_colors_like_the_real_one():
    ctx = FakePluginContext()
    ctx.set_named_colors([{"name": "水", "color": "#ABC"}])
    assert ctx.named_colors() == [{"name": "水", "color": "#aabbcc"}]
    with pytest.raises(NamedColorError):
        ctx.set_named_colors([{"name": "水", "color": "#000"}, {"name": "水", "color": "#111"}])
    with pytest.raises(ValueError):
        ctx.set_color_palettes({"P": ["blue"]})


def test_fake_context_select_notifies_selection_listeners():
    ds = _dataset()
    ctx = FakePluginContext(datasets=[ds])
    seen = []
    ctx.on_selection_changed(seen.append)
    ctx.select(ds)
    assert seen == [ds] and ctx.current_dataset() is ds and ctx.selected_datasets() == [ds]


def test_fake_context_data_dir_is_writable(tmp_path):
    ctx = FakePluginContext(data_dir=str(tmp_path))
    assert ctx.data_dir == str(tmp_path)
    assert FakePluginContext().data_dir  # 省略時は一時フォルダ
