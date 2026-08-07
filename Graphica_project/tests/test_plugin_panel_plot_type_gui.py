# tests/test_plugin_panel_plot_type_gui.py
"""
gui/main_window.py (PlotterApp) 側の、register_panel() (項目D-1) の
ドック生成配線・register_plot_type() (項目D-2) のプロット種別コンボボックス
配線に対する統合テスト。PlotterAppのインスタンス化パターンは
tests/test_main_window.py の _make_isolated_plotter_app に倣う。
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import core.plugin_api as plugin_api_module
import gui.main_window as main_window_module
from core.plugin_api import GraphicaPluginAPI
from gui.main_window import PlotterApp


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _set_singleton_plugin_api(monkeypatch, api):
    monkeypatch.setattr(plugin_api_module, "_singleton_api", api)


# --- register_panel() (項目D-1) ---

def test_plugin_panel_dock_created_and_hidden_by_default(tmp_path, monkeypatch):
    received = []

    def widget_factory(project, undo_stack):
        received.append((project, undo_stack))
        return QLabel("hello")

    api = GraphicaPluginAPI()
    api.register_panel("My Panel", widget_factory)
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert "My Panel" in window._plugin_panel_docks
    dock = window._plugin_panel_docks["My Panel"]
    assert isinstance(dock.widget(), QLabel)
    assert dock.isVisible() is False
    assert len(received) == 1
    assert received[0] == (window.project, window.undo_stack)


def test_plugin_panel_area_maps_to_dock_widget_area(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt

    api = GraphicaPluginAPI()
    api.register_panel("Left Panel", lambda project, undo_stack: QLabel("x"), area="left")
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    dock = window._plugin_panel_docks["Left Panel"]
    assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea


def test_plugin_panel_construction_failure_is_isolated(tmp_path, monkeypatch):
    def broken_factory(project, undo_stack):
        raise RuntimeError("boom")

    api = GraphicaPluginAPI()
    api.register_panel("Broken Panel", broken_factory)
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)  # クラッシュしない

    assert "Broken Panel" not in window._plugin_panel_docks


def test_plugin_panel_wrong_return_type_is_isolated(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    api.register_panel("Bad Return", lambda project, undo_stack: "not a widget")
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert "Bad Return" not in window._plugin_panel_docks


def test_plugin_menu_has_panel_toggle_action(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    api.register_panel("My Panel", lambda project, undo_stack: QLabel("x"))
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    panel_menu = None
    for action in window._plugin_menu.actions():
        if action.menu() is not None and action.menu().title().replace('&', '') == "パネル":
            panel_menu = action.menu()
    assert panel_menu is not None
    action_texts = [a.text() for a in panel_menu.actions()]
    assert "My Panel" in action_texts


def test_no_panels_registered_leaves_docks_dict_empty(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert window._plugin_panel_docks == {}


# --- register_plot_type() (項目D-2) ---

def test_plot_type_combo_includes_plugin_registered_type(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    api.register_plot_type("Heatmap", lambda ds, ax, x, y: None)
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    items = [window.ui.plot_type_combo.itemText(i) for i in range(window.ui.plot_type_combo.count())]
    assert "Heatmap" in items


def test_plot_type_combo_unaffected_when_no_plot_types_registered(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    items = [window.ui.plot_type_combo.itemText(i) for i in range(window.ui.plot_type_combo.count())]
    assert items == ["Line", "Scatter", "Line+Scatter", "Area", "Bar"]
