"""gui/panels/ の部品(軸の設定・データセットの一覧)と、PlotterApp に出す同じ名前の窓口。"""
import ast
import inspect

import graphica.gui.panels as panels_package
from graphica.gui.main_window import PlotterApp


def test_panels_never_pass_themselves_where_a_widget_is_expected():
    """部品は QWidget ではない。ダイアログや通知の親にはタブ(self._app)を渡す(self を渡すと実行時に落ちる)。"""
    offenders = []
    for panel_class in panels_package.PANEL_CLASSES.values():
        module = inspect.getmodule(panel_class)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("getattr", "setattr", "hasattr"):
                continue
            passed = list(node.args) + [keyword.value for keyword in node.keywords]
            if any(isinstance(arg, ast.Name) and arg.id == "self" for arg in passed):
                offenders.append(f"{module.__name__}:{node.lineno}")
    assert offenders == []


def test_every_exposed_name_reaches_its_panel(qapp):
    app = PlotterApp(run_startup_checks=False, tab_id=99)
    try:
        for key, panel_class in panels_package.PANEL_CLASSES.items():
            panel = app.panels[key]
            for name in panel_class.EXPOSED_NAMES:
                assert getattr(app, name) == getattr(panel, name), name
    finally:
        app.close()


def test_patching_a_name_on_the_tab_reaches_the_panel(qapp, monkeypatch):
    """テストが窓口の名前を差し替えると、部品の中からの呼び出しにも効く。"""
    app = PlotterApp(run_startup_checks=False, tab_id=99)
    try:
        calls = []
        monkeypatch.setattr(app, "_on_axis_setting_changed", lambda: calls.append("changed"))
        app._on_change_tick_color.__self__._on_axis_setting_changed()
        assert calls == ["changed"]
    finally:
        app.close()
