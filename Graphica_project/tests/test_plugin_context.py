"""gui/plugin_context.py(本体側の PluginContext)のテスト。"""
import pandas as pd
import pytest

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.core.named_colors import NamedColorError
from graphica.core.plugin_types import PluginMenuAction
from tests.test_main_window import _make_isolated_plotter_app


def _dataset(name="D"):
    return Dataset(name=name, df=pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]}),
                   x_col_name="x", y_col_name="y")


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    return _make_isolated_plotter_app(tmp_path, monkeypatch)


def test_context_is_one_per_plugin_and_tab(window, tmp_path, monkeypatch):
    other_tab = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.plugin_context("a") is window.plugin_context("a")
    assert window.plugin_context("a") is not window.plugin_context("b")
    assert window.plugin_context("a") is not other_tab.plugin_context("a")


def test_context_reads_the_tabs_datasets_and_selection(window):
    ds = _dataset()
    window._add_dataset(ds, None, select=True)
    ctx = window.plugin_context("p")
    assert ctx.datasets() == [ds]
    assert ctx.current_dataset() is ds
    assert ctx.selected_datasets() == [ds]
    ctx.datasets().clear()
    assert window.project.datasets == [ds]  # 返したリストを変えても本体は変わらない


def test_add_dataset_can_be_undone(window):
    ctx = window.plugin_context("p")
    ds = _dataset()
    ctx.add_dataset(ds)
    assert window.project.datasets == [ds]
    assert window.undo_stack.undoText() == "[p] データセットの追加"
    window.undo_stack.undo()
    assert window.project.datasets == []


def test_set_dataset_properties_can_be_undone(window):
    ds = _dataset()
    window._add_dataset(ds, None, select=True)
    ctx = window.plugin_context("p")
    old_color = ds.color
    ctx.set_dataset_properties(ds, {"color": "#123456", "linewidth": 3.0}, description="色と太さ")
    assert (ds.color, ds.linewidth) == ("#123456", 3.0)
    assert window.undo_stack.undoText() == "色と太さ"
    window.undo_stack.undo()
    assert ds.color == old_color


def test_set_dataset_properties_rejects_unknown_attributes(window):
    ds = _dataset()
    window._add_dataset(ds, None, select=True)
    with pytest.raises(AttributeError, match="no_such_field"):
        window.plugin_context("p").set_dataset_properties(ds, {"no_such_field": 1})
    assert window.undo_stack.count() == 0


def test_datasets_changed_fires_after_redraws_and_property_changes(window):
    ds = _dataset()
    window._add_dataset(ds, None, select=True)
    ctx = window.plugin_context("p")
    calls = []
    ctx.on_datasets_changed(lambda: calls.append("x"))
    ctx.redraw()
    ctx.set_dataset_properties(ds, {"color": "#000000"})
    assert len(calls) >= 2


def test_selection_changed_passes_the_current_dataset(window):
    a, b = _dataset("A"), _dataset("B")
    window._add_dataset(a, None, select=True)
    window._add_dataset(b, None, select=False)
    seen = []
    window.plugin_context("p").on_selection_changed(seen.append)
    window.ui.dataset_list_widget.setCurrentItem(window._get_dataset_tree_item(b))
    assert seen[-1] is b


def test_a_failing_listener_does_not_stop_drawing(window):
    ctx = window.plugin_context("p")
    after = []

    def broken():
        raise RuntimeError("plugin bug")

    ctx.on_datasets_changed(broken)
    ctx.on_datasets_changed(lambda: after.append(1))
    window._update_plot()
    assert after  # 後ろの通知先にも届く


def test_menu_action_gets_the_context_and_failures_are_shown_not_raised(window, monkeypatch):
    received = []
    window._run_plugin_menu_action(PluginMenuAction("ok", received.append, None, "p"))
    assert received == [window.plugin_context("p")]

    shown = []
    monkeypatch.setattr(main_window_module.QMessageBox, "critical", staticmethod(lambda *a, **k: shown.append(a)))

    def broken(ctx):
        raise ValueError("boom")

    window._run_plugin_menu_action(PluginMenuAction("壊れた項目", broken, None, "p"))
    assert len(shown) == 1 and "[p]" in shown[0][2] and "boom" in shown[0][2]


def test_data_dir_is_per_plugin_under_the_app_data_dir(window, tmp_path):
    path = window.plugin_context("My Plugin/1").data_dir
    assert path.startswith(str(tmp_path / "appdata"))
    assert path.endswith("My_Plugin_1")


def test_named_colors_round_trip_and_are_validated(window):
    ctx = window.plugin_context("p")
    ctx.set_named_colors([{"name": "水", "color": "#ABC"}])
    assert ctx.named_colors() == [{"name": "水", "color": "#aabbcc"}]
    with pytest.raises(NamedColorError):
        ctx.set_named_colors([{"name": "水", "color": "#000"}, {"name": "水", "color": "#111"}])
    assert ctx.named_colors() == [{"name": "水", "color": "#aabbcc"}]  # 失敗したら何も書かない


def test_color_palettes_round_trip_and_are_validated(window):
    ctx = window.plugin_context("p")
    ctx.set_color_palettes({"Mine": ["#FF0000", "#00f"]})
    assert ctx.color_palettes() == {"Mine": ["#ff0000", "#0000ff"]}
    with pytest.raises(ValueError):
        ctx.set_color_palettes({"Mine": ["red"]})
    assert ctx.active_color_cycle()  # 既定のパレットでも色が返る
