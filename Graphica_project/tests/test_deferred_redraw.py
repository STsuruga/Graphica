"""データセットをまとめて足すとき、グラフ全体の描き直しを最後の1回にまとめる(Issue #90)。

PlotterApp.deferred_redraw() / batched_undo_group() と、それを使う操作(列の値で分割、プラグインの解析結果、
プラグインの undo_group)。Undo の単位と名前は変えずに、追加・Undo・Redo の描き直しがそれぞれ1回になること。
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QInputDialog

from graphica.core.dataset import Dataset
from graphica.core.plugin_types import AnalysisResult, PluginAnalyzer
from tests.test_main_window import _make_isolated_plotter_app


def _dataset(name="D", df=None):
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}) if df is None else df
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y")


@pytest.fixture
def window(tmp_path, monkeypatch):
    w = _make_isolated_plotter_app(tmp_path, monkeypatch)
    yield w
    w.close()


@pytest.fixture
def redraws(window, monkeypatch):
    """canvas.redraw_all(全体の描き直し)の回数。"""
    calls = []
    original = window.canvas.redraw_all

    def counting(*args, **kwargs):
        calls.append(kwargs.get("full_resolution", False))
        return original(*args, **kwargs)

    monkeypatch.setattr(window.canvas, "redraw_all", counting)
    return calls


def _names(window):
    return [ds.name for ds in window.project.datasets]


# --- deferred_redraw ---

def test_redraws_requested_inside_are_done_once_on_exit(window, redraws):
    with window.deferred_redraw():
        window.redraw()
        window.redraw()
        assert redraws == []
    assert len(redraws) == 1


def test_nested_deferral_redraws_only_when_the_outermost_exits(window, redraws):
    with window.deferred_redraw():
        with window.deferred_redraw():
            window.redraw()
        assert redraws == []
    assert len(redraws) == 1


def test_nothing_is_redrawn_when_nothing_asked_for_it(window, redraws):
    with window.deferred_redraw():
        pass
    assert redraws == []


def test_a_full_redraw_wins_over_light_ones(window, redraws, monkeypatch):
    light_calls = []
    monkeypatch.setattr(window.canvas, "update_all_axes_appearance_and_data",
                        lambda *a, **k: light_calls.append(k) or False)
    with window.deferred_redraw():
        window._update_plot(light=True)
        window._update_plot(full_resolution=True)
        window._update_plot(light=True)
    assert light_calls == []
    assert redraws == [True]


def test_only_light_requests_stay_light(window, redraws, monkeypatch):
    light_calls = []
    monkeypatch.setattr(window.canvas, "update_all_axes_appearance_and_data",
                        lambda *a, **k: light_calls.append(k) or False)
    with window.deferred_redraw():
        window._update_plot(light=True)
        window._update_plot(light=True)
    assert len(light_calls) == 1
    assert redraws == []


def test_the_deferred_redraw_still_happens_when_the_body_raises(window, redraws):
    with pytest.raises(RuntimeError):
        with window.deferred_redraw():
            window.redraw()
            raise RuntimeError("boom")
    assert len(redraws) == 1
    window.redraw()
    assert len(redraws) == 2  # 遅らせたままにならない


# --- batched_undo_group ---

def test_batched_group_is_one_undo_step_and_one_redraw_each_way(window, redraws):
    count_before = window.undo_stack.count()

    with window.batched_undo_group("まとめて追加"):
        for name in ("A", "B", "C"):
            window._add_dataset_with_undo(_dataset(name))

    assert len(redraws) == 1
    assert window.undo_stack.count() == count_before + 1
    assert window.undo_stack.undoText() == "まとめて追加"
    assert _names(window) == ["A", "B", "C"]

    window.undo_stack.undo()
    assert len(redraws) == 2
    assert _names(window) == []

    window.undo_stack.redo()
    assert len(redraws) == 3
    assert _names(window) == ["A", "B", "C"]


# --- それを使う操作 ---

def test_split_by_column_redraws_once_and_keeps_one_undo_step(window, redraws, monkeypatch):
    source = _dataset("src", pd.DataFrame({"x": range(12), "y": range(12), "grp": [f"g{i % 4}" for i in range(12)]}))
    window._add_dataset(source)
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("grp", True)))
    redraws.clear()

    window.processing.split_by_column()

    assert len(window.project.datasets) == 5
    assert len(redraws) == 1
    assert window.undo_stack.undoText() == "列「grp」で系列に分割 (4件)"
    window.undo_stack.undo()
    assert _names(window) == ["src"]
    assert len(redraws) == 2
    window.undo_stack.redo()
    assert len(window.project.datasets) == 5
    assert len(redraws) == 3


def test_plugin_analyzer_with_several_new_datasets_redraws_once(window, redraws):
    window._add_dataset(_dataset("orig"))
    count_before = window.undo_stack.count()
    redraws.clear()
    analyzer = PluginAnalyzer(
        name="多数", fn=lambda ds, params: AnalysisResult(new_datasets=[_dataset(f"n{i}") for i in range(4)]),
        output_kind="datasets", param_schema=[], plugin_name="p",
    )

    window.plugin_runs.run_analyzer(analyzer)

    assert _names(window) == ["orig", "n0", "n1", "n2", "n3"]
    assert len(redraws) == 1
    # Undo の単位は今までどおり1件ずつ
    assert window.undo_stack.count() == count_before + 4


def test_plugin_undo_group_redraws_once(window, redraws):
    ctx = window.plugin_context("p")

    with ctx.undo_group("プラグインの追加"):
        for name in ("A", "B", "C"):
            ctx.add_dataset(_dataset(name))

    assert len(redraws) == 1
    assert window.undo_stack.undoText() == "プラグインの追加"
    window.undo_stack.undo()
    assert _names(window) == []
    assert len(redraws) == 2
