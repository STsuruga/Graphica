"""
プラグイン作者向けのテスト用の偽物。本体(Qt・QApplication)を起動せずにテストできる。

    api = FakeGraphicaPluginAPI()
    my_plugin.register(api)
    ctx = FakePluginContext(datasets=[ds])
    api.menu_actions[0].callback(ctx)
    assert ctx.messages == [("info", "My Plugin", "3 点")]

FakeGraphicaPluginAPI は本物の GraphicaPluginAPI と同じ公開メソッドを持ち、本物が拒む
重複登録は同じく ValueError にする(偽物だけ通るとテストが通っても本体で失敗する)。
tests/test_plugin_api_contract.py が両者のシグネチャの一致を確かめている。
"""
import tempfile

from core.color_palettes import normalize_palettes
from core.named_colors import add_named_color
from core.plugin_context import PluginContext
from core.plugin_types import PluginMenuAction


class FakeGraphicaPluginAPI:
    """
    登録内容を記録するだけの GraphicaPluginAPI。

    Attributes:
        menu_actions (list[PluginMenuAction]): 本物と同じ形。callback に FakePluginContext を渡して試せる。
        panels (dict): 名前 -> {"widget_factory", "area"}。
        そのほか fit_functions / importers / exporters / processors / analyzers / plot_types /
        render_backends は、名前(または拡張子)をキーにした登録内容の辞書。
    """

    def __init__(self, plugin_name="test_plugin"):
        self.plugin_name = plugin_name
        self.fit_functions = {}
        self.menu_actions = []
        self.importers = {}
        self.exporters = {}
        self.processors = {}
        self.analyzers = {}
        self.panels = {}
        self.plot_types = {}
        self.render_backends = {}

    def register_fit_function(self, name, func, param_names, p0=None):
        if name in self.fit_functions:
            raise ValueError(f"フィット関数 '{name}' は既に登録されています。")
        self.fit_functions[name] = {"func": func, "param_names": param_names, "p0": p0}

    def register_menu_action(self, text, callback, shortcut=None):
        self.menu_actions.append(PluginMenuAction(
            text=text, callback=callback, shortcut=shortcut, plugin_name=self.plugin_name,
        ))

    def register_importer(self, extensions, loader, *, name=None, priority=0):
        # 本物は拡張子ごとに複数を優先度順で持つが、使える拡張子を確かめる用途にはこれで足りる。
        for ext in extensions:
            ext = ext.lower()
            if not ext.startswith('.'):
                ext = '.' + ext
            self.importers[ext] = {"loader": loader, "name": name, "priority": priority}

    def register_exporter(self, format_name, extension, writer, *, name=None):
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


class FakePluginContext(PluginContext):
    """
    メモリ上だけで動く PluginContext。本物と同じ検証をし、行った操作を記録する。

    Args:
        datasets (list[Dataset] | None): タブにあるデータセット。
        current (Dataset | None): 選ばれているデータセット。
        selected (list[Dataset] | None): 選択中のデータセット。省略時は current だけ。
        plugin_name (str): show_message の既定のタイトル。
        data_dir (str | None): 省略時は一時フォルダを作る。
        named_colors (list[dict] | None) / color_palettes (dict | None) / color_cycle (list[str] | None):
            色の初期値。

    Attributes:
        messages (list[tuple]): 表示したメッセージ ("info" または "error", タイトル, 本文)。
        undo_descriptions (list[str]): Undo 履歴に積まれた操作の説明。
        redraw_count (int): redraw() が呼ばれた回数。
    """

    def __init__(self, datasets=None, current=None, selected=None, plugin_name="test_plugin",
                 data_dir=None, named_colors=None, color_palettes=None, color_cycle=None):
        self._datasets = list(datasets or [])
        self._current = current
        self._selected = list(selected) if selected is not None else ([current] if current else [])
        self._plugin_name = plugin_name
        self._data_dir = data_dir
        self._named_colors = [dict(e) for e in (named_colors or [])]
        self._palettes = normalize_palettes(color_palettes or {})
        self._color_cycle = list(color_cycle or ["#1f77b4", "#ff7f0e", "#2ca02c"])
        self._datasets_changed_callbacks = []
        self._selection_changed_callbacks = []
        self.messages = []
        self.undo_descriptions = []
        self.redraw_count = 0

    def datasets(self):
        return list(self._datasets)

    def current_dataset(self):
        return self._current

    def selected_datasets(self):
        return list(self._selected)

    def add_dataset(self, dataset, description=None):
        self._datasets.append(dataset)
        self.undo_descriptions.append(description or f"[{self._plugin_name}] データセットの追加")
        self.fire_datasets_changed()

    def set_dataset_properties(self, dataset, values, description=None):
        unknown = sorted(k for k in values if not hasattr(dataset, k))
        if unknown:
            raise AttributeError(f"Dataset に無い属性です: {', '.join(unknown)}")
        for key, value in values.items():
            setattr(dataset, key, value)
        self.undo_descriptions.append(description or f"[{self._plugin_name}] プロパティの変更")
        self.fire_datasets_changed()

    def redraw(self):
        self.redraw_count += 1

    def on_datasets_changed(self, callback):
        self._datasets_changed_callbacks.append(callback)

    def on_selection_changed(self, callback):
        self._selection_changed_callbacks.append(callback)

    def fire_datasets_changed(self):
        """テスト用: データセットが変わったときの通知を送る。"""
        for callback in list(self._datasets_changed_callbacks):
            callback()

    def select(self, dataset):
        """テスト用: データセット一覧で dataset を選んだことにし、通知を送る。"""
        self._current = dataset
        self._selected = [dataset] if dataset is not None else []
        for callback in list(self._selection_changed_callbacks):
            callback(dataset)

    @property
    def parent_widget(self):
        return None

    def show_message(self, text, title=None):
        self.messages.append(("info", title or self._plugin_name, text))

    def show_error(self, text, title=None):
        self.messages.append(("error", title or self._plugin_name, text))

    @property
    def data_dir(self):
        if self._data_dir is None:
            self._data_dir = tempfile.mkdtemp(prefix=f"graphica_{self._plugin_name}_")
        return self._data_dir

    def named_colors(self):
        return [dict(e) for e in self._named_colors]

    def set_named_colors(self, entries):
        validated = []
        for entry in entries:
            validated = add_named_color(validated, entry.get("name"), entry.get("color"))
        self._named_colors = validated

    def color_palettes(self):
        return {name: list(colors) for name, colors in self._palettes.items()}

    def set_color_palettes(self, palettes):
        self._palettes = normalize_palettes(palettes)

    def active_color_cycle(self):
        return list(self._color_cycle)
