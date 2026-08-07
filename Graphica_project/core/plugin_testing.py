# core/plugin_testing.py
"""
プラグイン開発者向けの疑似API(テストダブル、トラック1 フェーズA-3)。

本体(GUI/QApplication)を一切起動せずに、プラグインの register(api) 呼び出しが
期待通りのフックを登録しているかを単体テストできるようにするためのもの。

実際の GraphicaPluginAPI (core/plugin_api.py) と同じpublicメソッドシグネチャを
維持すること。tests/test_plugin_api_contract.py がこれを機械的に検証する。
各フックのメソッドは、そのフックを実装するフェーズ(B/C/D)で同時に追加する
(現時点では既存の register_fit_function / register_menu_action のみ)。
"""


class FakeGraphicaPluginAPI:
    """
    本体を起動せずにプラグインのregister呼び出しを検証するためのテストダブル。

    使い方の例(プラグイン側のテストコード):
        api = FakeGraphicaPluginAPI()
        my_plugin.register(api)
        assert "my_fit" in api.fit_functions
        assert api.menu_actions[0][0] == "My Action"
    """

    def __init__(self):
        self.fit_functions = {}  # name -> {"func":..., "param_names":..., "p0":...}
        self.menu_actions = []   # (text, callback, shortcut) のリスト。実物と同じ形。
        self.importers = {}      # 拡張子(".jdx"等) -> {"loader":..., "name":..., "priority":...}
        self.exporters = {}      # format_name.lower() -> {"extension":..., "writer":..., "name":...}
        self.processors = {}     # name -> {"fn":..., "category":..., "param_schema":...}
        self.analyzers = {}      # name -> {"fn":..., "output_kind":..., "param_schema":...}
        self.panels = {}         # name -> {"widget_factory":..., "area":...}
        self.plot_types = {}     # type_name -> {"drawer":..., "requires_2d":...}

    def register_fit_function(self, name, func, param_names, p0=None):
        self.fit_functions[name] = {"func": func, "param_names": param_names, "p0": p0}

    def register_menu_action(self, text, callback, shortcut=None):
        self.menu_actions.append((text, callback, shortcut))

    def register_importer(self, extensions, loader, *, name=None, priority=0):
        for ext in extensions:
            ext = ext.lower()
            if not ext.startswith('.'):
                ext = '.' + ext
            self.importers[ext] = {"loader": loader, "name": name, "priority": priority}

    def register_exporter(self, format_name, extension, writer, *, name=None):
        self.exporters[format_name.lower()] = {"extension": extension, "writer": writer, "name": name}

    def register_processor(self, name, fn, *, category="general", param_schema=None):
        self.processors[name] = {"fn": fn, "category": category, "param_schema": list(param_schema or [])}

    def register_analyzer(self, name, fn, *, output_kind="table", param_schema=None):
        self.analyzers[name] = {"fn": fn, "output_kind": output_kind, "param_schema": list(param_schema or [])}

    def register_panel(self, name, widget_factory, *, area="right"):
        self.panels[name] = {"widget_factory": widget_factory, "area": area}

    def register_plot_type(self, type_name, drawer, *, requires_2d=False):
        self.plot_types[type_name] = {"drawer": drawer, "requires_2d": requires_2d}
