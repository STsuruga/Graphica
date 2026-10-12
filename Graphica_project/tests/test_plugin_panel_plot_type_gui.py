# tests/test_plugin_panel_plot_type_gui.py
"""
gui/main_window.py (PlotterApp) 側の、register_panel() (項目D-1) の
ドック生成配線・register_plot_type() (項目D-2) のプロット種別コンボボックス
配線に対する統合テスト。PlotterAppのインスタンス化パターンは
tests/test_main_window.py の _make_isolated_plotter_app に倣う。
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

import graphica.gui.app_settings as app_settings_module
import graphica.core.plugin_api as plugin_api_module
from graphica.core.plugin_api import GraphicaPluginAPI
from graphica.gui.main_window import PlotterApp


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
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

    def widget_factory(ctx):
        received.append(ctx)
        return QLabel("hello")

    api = GraphicaPluginAPI()
    api.register_panel("My Panel", widget_factory)
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    # GUI 刷新で、パネルは左端の帯の「プラグイン」のページに入る(以前はドック)
    assert "My Panel" in window._plugin_panels
    panel = window._plugin_panels["My Panel"]
    assert isinstance(panel, QLabel)
    assert window.plugin_page.panels["My Panel"] is panel
    assert window.left_panel.currentWidget() is not window.plugin_page  # 開くまでは見せない
    assert len(received) == 1
    assert received[0] is window.plugin_context(api.get_panels()[0].plugin_name)


def test_plugin_panel_area_is_only_a_hint_and_every_panel_goes_to_the_plugin_page(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    api.register_panel("Left Panel", lambda ctx: QLabel("x"), area="left")
    api.register_panel("Bottom Panel", lambda ctx: QLabel("y"), area="bottom")
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert set(window.plugin_page.panels) == {"Left Panel", "Bottom Panel"}
    # 2つ以上なら上の欄で選ぶ
    assert not window.plugin_page.selector.isHidden()
    window.show_plugin_panel("Bottom Panel")
    assert window.left_panel.currentWidget() is window.plugin_page
    assert window.plugin_page.stack.currentWidget() is window._plugin_panels["Bottom Panel"]
    assert window.activity_rail.current_page() == "plugins"


def test_plugin_panel_construction_failure_is_isolated(tmp_path, monkeypatch):
    def broken_factory(ctx):
        raise RuntimeError("boom")

    api = GraphicaPluginAPI()
    api.register_panel("Broken Panel", broken_factory)
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)  # クラッシュしない

    assert "Broken Panel" not in window._plugin_panels


def test_plugin_panel_wrong_return_type_is_isolated(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    api.register_panel("Bad Return", lambda ctx: "not a widget")
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert "Bad Return" not in window._plugin_panels


def test_plugin_menu_has_panel_toggle_action(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    api.register_panel("My Panel", lambda ctx: QLabel("x"))
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    panel_menu = None
    for action in window._plugin_menu.actions():
        if action.menu() is not None and action.menu().title().replace('&', '') == "パネル":
            panel_menu = action.menu()
    assert panel_menu is not None
    actions = {a.text(): a for a in panel_menu.actions()}
    assert "My Panel" in actions
    actions["My Panel"].trigger()
    assert window.left_panel.currentWidget() is window.plugin_page


def test_no_panels_registered_leaves_docks_dict_empty(tmp_path, monkeypatch):
    api = GraphicaPluginAPI()
    _set_singleton_plugin_api(monkeypatch, api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert window._plugin_panels == {}
    # パネルが無いときは、案内を出す
    assert window.plugin_page.stack.currentWidget() is window.plugin_page.empty


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
    assert items == ["Line", "Scatter", "Line+Scatter", "Area", "Bar", "Step",
                     "Density Scatter", "Z-Color Scatter"]
