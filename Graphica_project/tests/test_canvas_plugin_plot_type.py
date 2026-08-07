# tests/test_canvas_plugin_plot_type.py
"""
gui/canvas.py の _draw_data が、register_plot_type() (項目D-2) で登録された
未知のplot_typeをフォールバック経路で描画することに対するテスト。
既存5種類(Line/Scatter/Line+Scatter/Area/Bar)の分岐自体は変更していないため、
ここでは新設のelse分岐(プラグイン描画呼び出し・未登録時のLineフォールバック・
プラグイン描画が例外を投げた場合の隔離)のみを対象とする。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import GraphicaPluginAPI
from gui.canvas import MplCanvas
from core.dataset import Dataset


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def _make_dataset(plot_type):
    df = pd.DataFrame({'x': [0.0, 1.0, 2.0], 'y': [1.0, 2.0, 3.0]})
    return Dataset(name="d", df=df, x_col_name='x', y_col_name='y', plot_type=plot_type)


def test_unregistered_plot_type_falls_back_to_line(canvas):
    ds = _make_dataset('TotallyUnknownPlotType')
    canvas.redraw_all([ds], 1, 1, [{}])
    ax = canvas.all_axes[0]
    assert len(ax.lines) == 1
    assert ds.artist is not None


def test_registered_plugin_plot_type_calls_drawer(canvas):
    calls = []

    def drawer(dataset, ax, x_data, y_data):
        calls.append((dataset, list(x_data), list(y_data)))
        (artist,) = ax.plot(x_data, y_data)
        return artist

    api = GraphicaPluginAPI()
    api.register_plot_type("MyPlotType", drawer)
    plugin_api_module._singleton_api = api

    ds = _make_dataset('MyPlotType')
    canvas.redraw_all([ds], 1, 1, [{}])

    assert len(calls) == 1
    assert calls[0][1] == [0.0, 1.0, 2.0]
    assert calls[0][2] == [1.0, 2.0, 3.0]
    assert ds.artist is not None


def test_registered_plugin_plot_type_drawer_returning_none_leaves_artist_unset(canvas):
    def drawer(dataset, ax, x_data, y_data):
        ax.plot(x_data, y_data)
        return None

    api = GraphicaPluginAPI()
    api.register_plot_type("MyPlotType", drawer)
    plugin_api_module._singleton_api = api

    ds = _make_dataset('MyPlotType')
    assert ds.artist is None
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist is None


def test_plugin_plot_type_drawer_exception_is_isolated(canvas):
    def drawer(dataset, ax, x_data, y_data):
        raise RuntimeError("boom")

    api = GraphicaPluginAPI()
    api.register_plot_type("MyPlotType", drawer)
    plugin_api_module._singleton_api = api

    ds = _make_dataset('MyPlotType')
    # 例外を投げても、redraw_all全体はクラッシュせず完了する
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist is None
