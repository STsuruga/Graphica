"""
Graphica のプラグイン機構。

プラグインは探索フォルダ(gui/main_window.py の plugin_search_paths())の下の、
`__init__.py` と `plugin.json` を持つ Python パッケージ。`__init__.py` に
`register(api: GraphicaPluginAPI)` を定義し、その中で api.register_xxx() を呼ぶ。

- plugin.json が無い・壊れている・api_version が合わないプラグインは import しない。
- プラグインはサンドボックスなしで同じプロセス内で動く。信頼できる配布元のものだけ入れること。
- 1つのプラグインの失敗で他のプラグインやアプリの起動を止めない(ログに残してスキップ)。
- 登録はプロセス全体で1回(タブごとではない)。タブに関わる操作は、呼び出し時に渡る
  PluginContext(core/plugin_context.py)を通す。
- プラグインが渡す表示名(メニュー項目名など)は翻訳しない。tr() の辞書に載せると、
  プラグイン作者が本体の翻訳辞書を意識しなければならなくなる。
"""
import importlib
import importlib.util
import logging
import os
import sys

from graphica.core.analysis import register_fit_function
# 外部プラグインが core.plugin_api から import している可能性があるため再公開する。
from graphica.core.plugin_manifest import PLUGIN_API_VERSION, PluginManifestError, load_plugin_manifest  # noqa: F401
from graphica.core.plugin_types import (
    PluginAnalyzer, PluginExporter, PluginHookKind, PluginImporter, PluginMenuAction,
    PluginPanel, PluginPlotType, PluginProcessor, PluginRegistrationError,
    PluginRenderBackend, RenderBackend,
)
from typing import Any, Callable

logger = logging.getLogger(__name__)

PLUGIN_REGISTER_FUNC = "register"


def _normalize_extension(extension: str) -> str:
    """".JDX" / "jdx" を ".jdx" にそろえる。"""
    ext = extension.lower()
    return ext if ext.startswith('.') else '.' + ext


def _check_plugin_dependencies(info: dict[str, Any]) -> list[str]:
    """plugin.json の requires のうち、import できないモジュール名を返す。"""
    missing = []
    for module_name in info.get("requires", []) or []:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing


class PluginLoadError(Exception):
    """プラグインの読み込みに失敗した(呼び出し側で捕まえて次のプラグインへ進む)。"""


class GraphicaPluginAPI:
    """
    プラグインの register(api) に渡される登録窓口。

    特定のタブへの参照は持たない。タブを操作する callback には、呼び出し時にそのタブの
    PluginContext が渡る(最初に開いたタブを握り続けると、複数タブで取り違える)。
    """

    def __init__(self) -> None:
        self._menu_actions: list[PluginMenuAction] = []
        self._importers: dict[str, list[PluginImporter]] = {}  # 拡張子 -> priority の高い順
        self._exporters: dict[str, PluginExporter] = {}  # format_name.lower() -> PluginExporter
        self._processors: dict[str, PluginProcessor] = {}
        self._analyzers: dict[str, PluginAnalyzer] = {}
        self._panels: dict[str, PluginPanel] = {}
        self._plot_types: dict[str, PluginPlotType] = {}
        self._render_backends: dict[str, PluginRenderBackend] = {}

        # 1プラグインの中でもフック単位で失敗を隔離し、プラグイン管理画面に出す。
        self._registration_errors: list[PluginRegistrationError] = []
        # register_xxx は呼び出し元のプラグインを知らないので、PluginManager が差し替える。
        self._current_plugin_name = "(不明なプラグイン)"

    def _safe_register(self, hook_kind: PluginHookKind, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """登録に失敗してもこのフック1件だけの失敗として記録し、False を返す。"""
        try:
            fn(*args, **kwargs)
            return True
        except Exception as e:
            self._registration_errors.append(
                PluginRegistrationError(self._current_plugin_name, hook_kind, str(e), e)
            )
            logger.warning(
                "[plugin:%s] %s の登録に失敗しました: %s",
                self._current_plugin_name, hook_kind.value, e,
            )
            return False

    def register_fit_function(self, name: str, func: Callable[..., Any], param_names: list[str],
                              p0: list[float] | Callable[..., Any] | None = None) -> bool:
        """
        曲線フィットの選択肢に関数を追加する。

        Args:
            name (str): フィットの種類の選択肢に出す名前(組み込みや他のプラグインと重複不可)。
            func (callable): scipy.optimize.curve_fit に渡せる f(x, *params)。
            param_names (list[str]): パラメータ名(結果の表示に使う)。
            p0 (list[float] | callable | None): 初期値、または (x_data, y_data) -> list[float]。
                省略時はすべて 1.0。
        """
        return self._safe_register(
            PluginHookKind.FIT_FUNCTION, register_fit_function, name, func, param_names, p0=p0
        )

    def register_menu_action(self, text: str, callback: Callable[..., Any], shortcut: str | None = None) -> bool:
        """
        「プラグイン」メニューに項目を追加する。

        Args:
            text (str): メニューに出す文字列。
            callback (callable): (PluginContext) -> None。選んだときのタブの窓口が渡る。
                例外はプラグイン名付きでエラー表示され、アプリは止まらない。
            shortcut (str | None): キーボードショートカット(例: "Ctrl+Shift+P")。
        """
        return self._safe_register(
            PluginHookKind.MENU_ACTION, self._menu_actions.append,
            PluginMenuAction(text=text, callback=callback, shortcut=shortcut,
                             plugin_name=self._current_plugin_name),
        )

    def register_importer(self, extensions: list[str], loader: Callable[[str], Any], *, name: str | None = None,
                          priority: int = 0) -> bool:
        """
        データファイルの読み込み形式を追加する。ファイルを開くダイアログ、ドラッグ&ドロップ、
        フォルダからの一括インポートのすべてで使われる。

        Args:
            extensions (list[str]): 対応する拡張子(例: [".jdx", ".dx"]、ピリオドは省略可)。
            loader (callable): (ファイルパス: str) -> pandas.DataFrame。
            name (str | None): エラー表示に使う名前。省略時はプラグイン名。
            priority (int): 同じ拡張子に複数登録されたときの優先度(大きいほど優先、同点は登録順)。
        """
        return self._safe_register(
            PluginHookKind.IMPORTER, self._do_register_importer, extensions, loader,
            name=name or self._current_plugin_name, priority=priority,
        )

    def _do_register_importer(self, extensions: list[str], loader: Callable[[str], Any], *, name: str,
                              priority: int) -> None:
        for ext in extensions:
            ext = _normalize_extension(ext)
            importer = PluginImporter(extension=ext, loader=loader, name=name, priority=priority)
            bucket = self._importers.setdefault(ext, [])
            bucket.append(importer)
            bucket.sort(key=lambda imp: -imp.priority)  # 安定ソートなので同点は登録順のまま

    def get_importer_for_extension(self, extension: str) -> PluginImporter | None:
        """最も優先度の高いインポーター。無ければ None。"""
        bucket = self._importers.get(_normalize_extension(extension))
        return bucket[0] if bucket else None

    def get_importer_extensions(self) -> list[str]:
        return sorted(self._importers.keys())

    def register_exporter(self, format_name: str, extension: str, writer: Callable[[Any, str], Any], *,
                          name: str | None = None) -> bool:
        """
        グラフの書き出し形式を追加する。エクスポートと一括エクスポートの両方で選べる。

        Args:
            format_name (str): 形式の選択肢に出す名前。
            extension (str): 出力ファイルの拡張子(ピリオドは省略可)。
            writer (callable): (matplotlib.figure.Figure, 出力パス: str) -> None。
            name (str | None): エラー表示に使う名前。省略時はプラグイン名。
        """
        return self._safe_register(
            PluginHookKind.EXPORTER, self._do_register_exporter, format_name, extension, writer,
            name=name or self._current_plugin_name,
        )

    def _do_register_exporter(self, format_name: str, extension: str, writer: Callable[[Any, str], Any], *,
                              name: str) -> None:
        self._exporters[format_name.lower()] = PluginExporter(
            format_name=format_name, extension=_normalize_extension(extension), writer=writer, name=name
        )

    def get_exporter(self, format_name: str) -> PluginExporter | None:
        return self._exporters.get(format_name.lower())

    def get_exporter_for_extension(self, extension: str) -> PluginExporter | None:
        ext = _normalize_extension(extension)
        for exporter in self._exporters.values():
            if exporter.extension == ext:
                return exporter
        return None

    def get_exporters(self) -> list[PluginExporter]:
        return list(self._exporters.values())

    def register_processor(self, name: str, fn: Callable[[Any, dict[str, Any]], Any], *, category: str = "general",
                           param_schema: list[dict[str, Any]] | None = None) -> bool:
        """
        現在のデータセットから新しいデータセットを作る処理を、「プラグイン ▸ データ処理」に追加する。
        結果は Undo できる形で追加されるので、プラグイン側で Undo を扱う必要はない。

        Args:
            name (str): メニューに出す名前(他のプラグインと重複不可)。
            fn (callable): (Dataset, dict) -> Dataset。元の Dataset は変更しないこと。
                第2引数は param_schema から作った入力フォームの値(無ければ空の辞書)。
            category (str): メニューでのまとまり。
            param_schema (list[dict] | None): 入力フォームの定義。各要素は "name" と
                "type"("int"/"float"/"str"/"bool"/"choice")を持つ。
                例: [{"name": "window", "label": "窓幅", "type": "int", "default": 5, "min": 1, "max": 999}]
                省略時は入力なしで実行する。
        """
        return self._safe_register(
            PluginHookKind.PROCESSOR, self._do_register_processor, name, fn,
            category=category, param_schema=param_schema, plugin_name=self._current_plugin_name,
        )

    def _do_register_processor(self, name: str, fn: Callable[[Any, dict[str, Any]], Any], *, category: str,
                               param_schema: list[dict[str, Any]] | None, plugin_name: str) -> None:
        if name in self._processors:
            raise ValueError(f"データ処理 '{name}' は既に登録されています。")
        self._processors[name] = PluginProcessor(
            name=name, fn=fn, category=category, param_schema=list(param_schema or []),
            plugin_name=plugin_name,
        )

    def get_processors(self) -> list[PluginProcessor]:
        return list(self._processors.values())

    def get_processor_categories(self) -> list[str]:
        return sorted({p.category for p in self._processors.values()})

    def register_analyzer(self, name: str, fn: Callable[[Any, dict[str, Any]], Any], *, output_kind: str = "table",
                          param_schema: list[dict[str, Any]] | None = None) -> bool:
        """
        現在のデータセットを解析し、表・注釈・新しいデータセットを返す処理を、
        「プラグイン ▸ 解析」に追加する。

        Args:
            name (str): メニューに出す名前(他のプラグインと重複不可)。
            fn (callable): (Dataset, dict) -> AnalysisResult。第2引数は register_processor と同じ。
            output_kind (str): 結果の分類(表示上の区別だけで、動作は変わらない)。
            param_schema (list[dict] | None): register_processor と同じ形式。
        """
        return self._safe_register(
            PluginHookKind.ANALYZER, self._do_register_analyzer, name, fn,
            output_kind=output_kind, param_schema=param_schema, plugin_name=self._current_plugin_name,
        )

    def _do_register_analyzer(self, name: str, fn: Callable[[Any, dict[str, Any]], Any], *, output_kind: str,
                              param_schema: list[dict[str, Any]] | None, plugin_name: str) -> None:
        if name in self._analyzers:
            raise ValueError(f"解析 '{name}' は既に登録されています。")
        self._analyzers[name] = PluginAnalyzer(
            name=name, fn=fn, output_kind=output_kind, param_schema=list(param_schema or []),
            plugin_name=plugin_name,
        )

    def get_analyzers(self) -> list[PluginAnalyzer]:
        return list(self._analyzers.values())

    def register_panel(self, name: str, widget_factory: Callable[..., Any], *, area: str = "right") -> bool:
        """
        ドックパネルを追加する。「プラグイン ▸ パネル」から表示を切り替えられる。

        Args:
            name (str): パネルのタイトル(他のプラグインと重複不可)。
            widget_factory (callable): (PluginContext) -> QWidget。タブごとに、そのタブを
                作るときに1回呼ばれ、そのタブの窓口が渡る。例外を出すとそのタブにはパネルを作らない。
            area (str): "right" / "left" / "top" / "bottom"。
        """
        return self._safe_register(
            PluginHookKind.PANEL, self._do_register_panel, name, widget_factory,
            area=area, plugin_name=self._current_plugin_name,
        )

    def _do_register_panel(self, name: str, widget_factory: Callable[..., Any], *, area: str, plugin_name: str) -> None:
        if name in self._panels:
            raise ValueError(f"パネル '{name}' は既に登録されています。")
        self._panels[name] = PluginPanel(
            name=name, widget_factory=widget_factory, area=area, plugin_name=plugin_name,
        )

    def get_panels(self) -> list[PluginPanel]:
        return list(self._panels.values())

    def register_plot_type(self, type_name: str, drawer: Callable[..., Any], *, requires_2d: bool = False) -> bool:
        """
        データセットのプロット種別を追加する。

        Args:
            type_name (str): Dataset.plot_type に入る値で、種別の選択肢にも出る
                (組み込みや他のプラグインと重複不可)。
            drawer (callable): (Dataset, Axes, x_data, y_data) -> Artist | None。
                x_data / y_data はウォーターフォールのずらしなどを適用済みの描画用の配列。
                返した Artist は凡例に使う(不要なら None)。グラデーションなどの重ね描きは
                組み込みの種別だけの機能で、プラグインの種別には付かない。
            requires_2d (bool): 分類用の予約フラグ(いまは動作に影響しない)。
        """
        return self._safe_register(
            PluginHookKind.PLOT_TYPE, self._do_register_plot_type, type_name, drawer,
            requires_2d=requires_2d, plugin_name=self._current_plugin_name,
        )

    def _do_register_plot_type(self, type_name: str, drawer: Callable[..., Any], *, requires_2d: bool,
                               plugin_name: str) -> None:
        if type_name in self._plot_types:
            raise ValueError(f"プロット種別 '{type_name}' は既に登録されています。")
        self._plot_types[type_name] = PluginPlotType(
            type_name=type_name, drawer=drawer, requires_2d=requires_2d, plugin_name=plugin_name,
        )

    def get_plot_types(self) -> list[PluginPlotType]:
        return list(self._plot_types.values())

    def get_plot_type(self, type_name: str) -> PluginPlotType | None:
        return self._plot_types.get(type_name)

    def register_render_backend(self, name: str, backend: RenderBackend) -> bool:
        """
        描画バックエンドの登録枠(予約)。描画にはまだ接続しておらず、登録しても何も起きない。

        Args:
            name (str): 識別名(他のプラグインと重複不可)。
            backend (RenderBackend): 中身の仕様は未定。
        """
        return self._safe_register(
            PluginHookKind.RENDER_BACKEND, self._do_register_render_backend, name, backend,
            plugin_name=self._current_plugin_name,
        )

    def _do_register_render_backend(self, name: str, backend: RenderBackend, *, plugin_name: str) -> None:
        if name in self._render_backends:
            raise ValueError(f"描画バックエンド '{name}' は既に登録されています。")
        self._render_backends[name] = PluginRenderBackend(
            name=name, backend=backend, plugin_name=plugin_name,
        )

    def get_render_backends(self) -> list[PluginRenderBackend]:
        return list(self._render_backends.values())

    @property
    def menu_actions(self) -> list[PluginMenuAction]:
        return list(self._menu_actions)

    @property
    def registration_errors(self) -> list[PluginRegistrationError]:
        return list(self._registration_errors)


class PluginManager:
    """探索フォルダのプラグインを見つけて読み込み、register(api) を呼ぶ。"""

    def __init__(self, plugins_dir: str | list[str]) -> None:
        """plugins_dir は1つのパス、または優先順のパスのリスト。"""
        self.plugins_dirs = [plugins_dir] if isinstance(plugins_dir, str) else list(plugins_dir)
        self.loaded_plugins: list[dict[str, Any]] = []  # {"name", "info", "error", "disabled"}
        self._plugin_locations: dict[str, str] = {}  # プラグイン名 -> 見つかった探索フォルダ

    def discover_plugin_dirs(self) -> list[str]:
        """__init__.py を持つサブフォルダ名を返す。同名は先に見つかった探索フォルダのものを使う。"""
        self._plugin_locations = {}
        names = []
        for plugins_dir in self.plugins_dirs:
            if not os.path.isdir(plugins_dir):
                continue
            for entry in sorted(os.listdir(plugins_dir)):
                entry_path = os.path.join(plugins_dir, entry)
                if not (os.path.isdir(entry_path) and os.path.exists(os.path.join(entry_path, "__init__.py"))):
                    continue
                if entry in self._plugin_locations:
                    logger.warning(
                        "プラグイン '%s' は複数の探索パスに存在するため、'%s' のものを使用します"
                        "('%s' は無視されます)。",
                        entry, self._plugin_locations[entry], plugins_dir,
                    )
                    continue
                self._plugin_locations[entry] = plugins_dir
                names.append(entry)
        return names

    def _load_module(self, plugin_name: str) -> Any:
        base_dir = self._plugin_locations[plugin_name]
        init_path = os.path.join(base_dir, plugin_name, "__init__.py")
        module_name = f"graphica_plugin_{plugin_name}"
        spec = importlib.util.spec_from_file_location(
            module_name, init_path,
            submodule_search_locations=[os.path.join(base_dir, plugin_name)],
        )
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"プラグイン '{plugin_name}' のモジュール仕様を作成できませんでした。")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            sys.modules.pop(module_name, None)
            raise PluginLoadError(f"プラグイン '{plugin_name}' の読み込み中にエラー: {e}") from e
        return module

    def load_all(self, api: GraphicaPluginAPI, disabled_names: set[str] | None = None) -> list[dict[str, Any]]:
        """
        すべてのプラグインを読み込み register(api) を呼ぶ。1つが失敗しても続ける。

        disabled_names に含まれるプラグインは、表示用に manifest だけ読み、import しない。
        """
        disabled_names = disabled_names or set()
        self.loaded_plugins = []
        for plugin_name in self.discover_plugin_dirs():
            record: dict[str, Any] = {"name": plugin_name, "info": None, "error": None, "disabled": False}
            plugin_dir = os.path.join(self._plugin_locations[plugin_name], plugin_name)

            if plugin_name in disabled_names:
                record["disabled"] = True
                try:
                    record["info"] = load_plugin_manifest(plugin_dir)
                except PluginManifestError:
                    logger.debug("無効化中のプラグイン '%s' の manifest を読めません", plugin_name, exc_info=True)
                self.loaded_plugins.append(record)
                continue

            try:
                # manifest は import より前に検証する。弾いたプラグインのコードは一切実行しない。
                info = load_plugin_manifest(plugin_dir)
                record["info"] = info

                missing = _check_plugin_dependencies(info)
                if missing:
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' の依存パッケージが不足しています: "
                        f"{', '.join(missing)}。プラグインは本体に同梱済みの依存"
                        "(numpy/pandas/scipy/matplotlib/PySide6等)のみ使用できます。"
                        "pip版のGraphicaであれば追加の依存パッケージを導入して動作させられます。"
                    )

                module = self._load_module(plugin_name)
                register_func = getattr(module, PLUGIN_REGISTER_FUNC, None)
                if not callable(register_func):
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' に {PLUGIN_REGISTER_FUNC}(api) 関数がありません。"
                    )
                api._current_plugin_name = plugin_name
                register_func(api)

            except Exception as e:
                # 本体側のコード(manifest の解析など)の不具合もここに来るので、traceback を残す。
                record["error"] = str(e)
                logger.exception("プラグイン '%s' の読み込みに失敗しました: %s", plugin_name, e)

            self.loaded_plugins.append(record)

        return self.loaded_plugins


# 登録先(フィット関数の辞書など)がプロセス全体で1つなので、読み込みもプロセスで1回だけ行う。
# タブごとに読み込むと「既に登録されています」で失敗する。
_singleton_api = None
_singleton_manager = None

# main.py が load_plugins_once() の最初の呼び出しより前に設定する。
_safe_mode_enabled = False


def set_safe_mode(enabled: bool) -> None:
    """load_plugins_once() が一度呼ばれたあとに変えても、読み込み済みの結果には影響しない。"""
    global _safe_mode_enabled
    _safe_mode_enabled = bool(enabled)


def is_safe_mode_enabled() -> bool:
    return _safe_mode_enabled


def load_plugins_once(plugins_dir: str | list[str], disabled_names: set[str] | None = None) -> "GraphicaPluginAPI":
    """
    最初の呼び出しでだけプラグインを読み込み、以後は同じ GraphicaPluginAPI を返す。
    セーフモードでは探索フォルダに一切触れず(作成もしない)、空の API を返す。
    """
    global _singleton_api, _singleton_manager
    if _singleton_api is not None:
        return _singleton_api

    if is_safe_mode_enabled():
        _singleton_api = GraphicaPluginAPI()
        _singleton_manager = None
        return _singleton_api

    dirs = [plugins_dir] if isinstance(plugins_dir, str) else list(plugins_dir)
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    _singleton_api = GraphicaPluginAPI()
    _singleton_manager = PluginManager(plugins_dir)
    _singleton_manager.load_all(_singleton_api, disabled_names=disabled_names)
    return _singleton_api


def get_loaded_plugin_records() -> list[dict[str, Any]] | None:
    """未読み込みなら None。"""
    return None if _singleton_manager is None else list(_singleton_manager.loaded_plugins)


def get_plugin_registration_errors() -> list[PluginRegistrationError] | None:
    """フック単位の登録失敗(プラグイン全体の読み込みは成功していても記録される)。未読み込みなら None。"""
    return None if _singleton_api is None else _singleton_api.registration_errors


def get_plugin_api() -> "GraphicaPluginAPI | None":
    """読み込み済みの API。未読み込みなら None(読み込みはしない)。"""
    return _singleton_api


def get_registered_importer_extensions() -> list[str]:
    return _singleton_api.get_importer_extensions() if _singleton_api is not None else []


def get_registered_exporters() -> list[PluginExporter]:
    return _singleton_api.get_exporters() if _singleton_api is not None else []
