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
        self.render_backends = {}  # name -> {"backend":...}(項目G、骨組みのみ)

    def register_fit_function(self, name, func, param_names, p0=None):
        # ★ バグ修正: 実物(core/analysis.pyのregister_fit_function)は同名の
        # 重複登録をValueErrorで拒否するが、このFakeは黙って上書きしていた。
        # プラグイン開発者がこのFakeに対して単体テストを書き、重複登録の
        # ミスに気づけないまま「テストは通る」状態になり、実際にGraphica本体で
        # 読み込むと初めて失敗する(=このテストダブルの本来の目的を果たせて
        # いない)不整合があった。他のregister_xxxも同様の理由で実物と揃える。
        if name in self.fit_functions:
            raise ValueError(f"フィット関数 '{name}' は既に登録されています。")
        self.fit_functions[name] = {"func": func, "param_names": param_names, "p0": p0}

    def register_menu_action(self, text, callback, shortcut=None):
        self.menu_actions.append((text, callback, shortcut))

    def register_importer(self, extensions, loader, *, name=None, priority=0):
        # ★ 実物は拡張子ごとに優先度付きリストで複数プラグインの登録を許容する
        # (register_importerのdocstring参照)。単一値の上書きはこのFakeが
        # 単純化していた挙動だが、拡張子の対応表としては実物と一致するため
        # (=どの拡張子が使えるかの検証には支障が無いため)ここは変更しない。
        for ext in extensions:
            ext = ext.lower()
            if not ext.startswith('.'):
                ext = '.' + ext
            self.importers[ext] = {"loader": loader, "name": name, "priority": priority}

    def register_exporter(self, format_name, extension, writer, *, name=None):
        # 実物(_do_register_exporter)も同名上書きを許容する(重複拒否なし)
        # ため、Fakeもそれに合わせて上書きのままでよい。
        self.exporters[format_name.lower()] = {"extension": extension, "writer": writer, "name": name}

    def register_processor(self, name, fn, *, category="general", param_schema=None):
        if name in self.processors:
            raise ValueError(f"データ処理 '{name}' は既に登録されています。")
        self.processors[name] = {"fn": fn, "category": category, "param_schema": list(param_schema or [])}

    def register_analyzer(self, name, fn, *, output_kind="table", param_schema=None):
        if name in self.analyzers:
            raise ValueError(f"解析 '{name}' は既に登録されています。")
        self.analyzers[name] = {"fn": fn, "output_kind": output_kind, "param_schema": list(param_schema or [])}

    def register_panel(self, name, widget_factory, *, area="right"):
        if name in self.panels:
            raise ValueError(f"パネル '{name}' は既に登録されています。")
        self.panels[name] = {"widget_factory": widget_factory, "area": area}

    def register_plot_type(self, type_name, drawer, *, requires_2d=False):
        if type_name in self.plot_types:
            raise ValueError(f"プロット種別 '{type_name}' は既に登録されています。")
        self.plot_types[type_name] = {"drawer": drawer, "requires_2d": requires_2d}

    def register_render_backend(self, name, backend):
        if name in self.render_backends:
            raise ValueError(f"描画バックエンド '{name}' は既に登録されています。")
        self.render_backends[name] = {"backend": backend}
