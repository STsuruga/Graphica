"""PluginContext の本体側の実装。1つのタブ(PlotterApp)と1つのプラグインの組ごとに作る。"""
import logging
import weakref
from contextlib import contextmanager
from dataclasses import fields


from graphica.gui import notify
from graphica.core.app_paths import get_plugin_data_dir
from graphica.core.color_palettes import normalize_palettes
from graphica.core.commands import SetDatasetPropertiesCommand
from graphica.core.dataset import Dataset
from graphica.core.named_colors import add_named_color, load_named_colors, save_named_colors
from graphica.core.plugin_context import PluginContext

logger = logging.getLogger(__name__)

_DATASET_FIELDS = frozenset(f.name for f in fields(Dataset))


class TabPluginContext(PluginContext):

    def __init__(self, app, plugin_name):
        # タブを閉じたあとも窓口をプラグインが握っていることがあるので、タブは弱参照で持つ。
        self._app_ref = weakref.ref(app)
        self._plugin_name = plugin_name
        self._datasets_changed_callbacks = []
        self._selection_changed_callbacks = []
        # undo_group の中なら {"description", "started"}。マクロは最初の変更で始める(空のマクロも Undo 1回分になる)
        self._undo_group = None

    @property
    def _app(self):
        app = self._app_ref()
        if app is None:
            raise RuntimeError("このタブはすでに閉じられています。")
        return app

    def datasets(self):
        return list(self._app.project.datasets)

    def current_dataset(self):
        return self._app.current_dataset()

    def selected_datasets(self):
        return self._app.selected_datasets()

    def add_dataset(self, dataset, description=None):
        self._start_pending_undo_group()
        self._app.add_dataset_with_undo(
            dataset, description=description or f"[{self._plugin_name}] データセットの追加"
        )

    def set_dataset_properties(self, dataset, values, description=None):
        unknown = sorted(set(values) - _DATASET_FIELDS)
        if unknown:
            raise AttributeError(f"Dataset に無い属性です: {', '.join(unknown)}")
        app = self._app
        new_values = dict(values)
        old_values = {key: getattr(dataset, key) for key in new_values}
        self._start_pending_undo_group()
        app.undo_stack.push(SetDatasetPropertiesCommand(
            dataset, old_values, new_values,
            on_applied=lambda: app.refresh_after_dataset_property_change(
                dataset, changed_keys=new_values.keys(), old_values=old_values, new_values=new_values
            ),
            description=description or f"[{self._plugin_name}] プロパティの変更",
        ))

    @contextmanager
    def undo_group(self, description):
        outermost = self._undo_group is None
        if outermost:
            self._undo_group = {"description": description, "started": False}
        try:
            yield
        finally:
            if outermost:
                group, self._undo_group = self._undo_group, None
                if group["started"]:
                    self._app.undo_stack.endMacro()

    def _start_pending_undo_group(self):
        group = self._undo_group
        if group is not None and not group["started"]:
            self._app.undo_stack.beginMacro(group["description"])
            group["started"] = True

    def redraw(self):
        self._app.redraw()

    def on_datasets_changed(self, callback):
        self._datasets_changed_callbacks.append(callback)

    def on_selection_changed(self, callback):
        self._selection_changed_callbacks.append(callback)

    def _notify_datasets_changed(self):
        for callback in list(self._datasets_changed_callbacks):
            self._call_isolated(callback)

    def _notify_selection_changed(self, dataset):
        for callback in list(self._selection_changed_callbacks):
            self._call_isolated(callback, dataset)

    def _call_isolated(self, callback, *args):
        # 通知先のプラグインが失敗しても、描画や選択の処理を止めない。
        try:
            callback(*args)
        except Exception:
            logger.exception("[plugin:%s] 通知の処理に失敗しました", self._plugin_name)

    @property
    def parent_widget(self):
        return self._app_ref()

    def show_message(self, text, title=None):
        notify.information(self.parent_widget, title or self._plugin_name, text)

    def show_error(self, text, title=None):
        notify.warning(self.parent_widget, title or self._plugin_name, text)

    @property
    def data_dir(self):
        return get_plugin_data_dir(self._plugin_name)

    def named_colors(self):
        return load_named_colors(self._app.settings)

    def set_named_colors(self, entries):
        validated = []
        for entry in entries:
            validated = add_named_color(validated, entry.get("name"), entry.get("color"))
        save_named_colors(self._app.settings, validated)

    def color_palettes(self):
        return {name: list(colors) for name, colors in self._app.colors.load_palettes().items()}

    def set_color_palettes(self, palettes):
        self._app.colors.save_palettes(normalize_palettes(palettes))

    def active_color_cycle(self):
        return list(self._app.colors.active_color_cycle())

    def set_active_color_palette(self, name):
        self._app.colors.set_active_palette(name)
