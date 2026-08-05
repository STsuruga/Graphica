# core/plugin_api.py
"""
Graphicaのプラグイン機構。

設計方針:
- プラグインは `plugins/` ディレクトリ(resource_path("plugins")、実行ファイルの
  隣。無ければ起動時に自動作成する)配下の、各サブフォルダとして配置する。
  各サブフォルダは `__init__.py` を持つ通常のPythonパッケージで、以下の2つを
  トップレベルに定義する:

    PLUGIN_INFO = {"name": "...", "version": "...", "author": "...",
                    "description": "..."}

    def register(api: GraphicaPluginAPI) -> None:
        ...  # api.register_fit_function(...) 等を呼ぶ

- プラグインはアプリと同じPythonプロセス内で実行される、サンドボックスなしの
  通常のPythonコードである。信頼できる配布元のプラグインのみ導入すること
  (models/project.py の pickle 復元における _RestrictedUnpickler の
  ドキュメントコメントと同様の注意が必要)。
- 1つのプラグインの読み込み/登録に失敗しても、他のプラグインの読み込みや
  アプリ本体の起動を止めない(例外はログに記録し、そのプラグインだけを
  スキップする)。
- 拡張ポイントは現時点では「カーブフィット関数の追加」「メニューへの
  アクション追加」「データインポーターの追加」「エクスポート形式の追加」の4つ。
  今後も同様のパターン(register_xxx メソッドを追加する)で拡張できる。
"""
import importlib
import importlib.util
import logging
import os
import sys

from core.analysis import register_fit_function
from core.plugin_types import PluginExporter, PluginHookKind, PluginImporter, PluginRegistrationError

logger = logging.getLogger(__name__)

PLUGIN_MANIFEST_ATTR = "PLUGIN_INFO"
PLUGIN_REGISTER_FUNC = "register"


def _normalize_extension(extension):
    """拡張子を先頭ピリオド付き・小文字の形に揃える(例: "JDX" -> ".jdx")。"""
    ext = extension.lower()
    return ext if ext.startswith('.') else '.' + ext


class PluginLoadError(Exception):
    """プラグインの読み込み/登録に失敗したことを表す(呼び出し側でキャッチして続行する用途)"""


class GraphicaPluginAPI:
    """
    プラグインの `register(api)` に渡されるオブジェクト。
    プラグインが触れて良い範囲を明示的なメソッド越しに限定するための窓口
    (Datasetやウィジェットの内部実装へ直接アクセスさせない)。
    """

    def __init__(self, main_window=None):
        self._main_window = main_window
        self._menu_actions = []  # (text, callback, shortcut) のリスト。メニュー構築側が読む。
        self._importers = {}  # 拡張子(".jdx"等) -> list[PluginImporter](priority降順)
        self._exporters = {}  # format_name.lower() -> PluginExporter

        # フック登録の失敗をプラグイン単位ではなくフック単位で隔離するための
        # 記録先(フェーズA-2)。1プラグインが複数のフックを登録する場合、
        # そのうち1つが失敗しても他のフックの登録は継続する。
        # F-2(プラグイン管理UI)から読み出される想定。
        self._registration_errors = []  # list[PluginRegistrationError]
        # 現在register(api)を実行中のプラグイン名。PluginManager.load_all()が
        # 各プラグインのregister()を呼ぶ直前に差し替える。register_xxx呼び出し
        # 自体はどのプラグインが呼んでいるか知らないため、この経由で伝える。
        self._current_plugin_name = "(不明なプラグイン)"

    def _safe_register(self, hook_kind, fn, *args, **kwargs):
        """
        フック登録処理(fn)を実行し、例外が起きてもプラグイン全体を巻き込まず
        このフック1件の失敗として隔離する(フェーズA-2)。

        Returns:
            bool: 登録に成功したかどうか。
        """
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

    def register_fit_function(self, name, func, param_names, p0=None):
        """
        カーブフィットの選択肢に、プラグイン提供の関数を追加する。

        Args:
            name (str): フィットタイプのコンボボックスに表示される名前
                (組み込みのフィットタイプ名や他のプラグイン名と重複不可)。
            func (callable): scipy.optimize.curve_fit に渡せる f(x, *params) 形式の関数。
            param_names (list[str]): パラメータ名のリスト(結果表示に使われる)。
            p0 (list[float] | callable | None): 初期値のリスト、または
                (x_data, y_data) -> list[float] を返す関数。省略時は全て1.0。
        """
        return self._safe_register(
            PluginHookKind.FIT_FUNCTION, register_fit_function, name, func, param_names, p0=p0
        )

    def register_menu_action(self, text, callback, shortcut=None):
        """
        「プラグイン」メニューにアクションを追加する。

        Args:
            text (str): メニューに表示するテキスト。
            callback (callable): クリック時に呼ばれる関数。呼び出し時に
                現在アクティブな PlotterApp インスタンスを1引数として渡す
                (データセット一覧やキャンバスへは、そこから通常のpublicな
                属性経由でアクセスする)。
            shortcut (str | None): キーボードショートカット(例: "Ctrl+Shift+P")。
        """
        return self._safe_register(
            PluginHookKind.MENU_ACTION, self._menu_actions.append, (text, callback, shortcut)
        )

    def register_importer(self, extensions, loader, *, name=None, priority=0):
        """
        データファイルの読み込みに、プラグイン提供のローダーを追加する(項目B-1)。
        登録した拡張子は、データ追加のファイルダイアログ・ドラッグ&ドロップ一括取込
        (項目77)の両方で自動的に受け付けられるようになる(gui/workers.pyの
        read_data_file()がファイル読み込みの入口で優先的に参照する)。

        現時点では単一の pandas.DataFrame を返すローダーのみサポートする
        (複数シート/複数データセットを一度に返す形式は未対応。将来的な拡張点)。

        Args:
            extensions (list[str]): 対応する拡張子のリスト(例: [".jdx", ".dx"]、
                先頭のピリオドは省略可)。
            loader (callable): ファイルパス(str)を受け取り、pandas.DataFrame を
                返す関数。
            name (str | None): エラーメッセージ等に表示する名前
                (省略時は登録元のプラグイン名)。
            priority (int): 同じ拡張子に複数のプラグインが登録した場合の優先順位
                (値が大きいほど優先。同点の場合は登録順)。
        """
        return self._safe_register(
            PluginHookKind.IMPORTER, self._do_register_importer, extensions, loader,
            name=name or self._current_plugin_name, priority=priority,
        )

    def _do_register_importer(self, extensions, loader, *, name, priority):
        for ext in extensions:
            ext = _normalize_extension(ext)
            importer = PluginImporter(extension=ext, loader=loader, name=name, priority=priority)
            bucket = self._importers.setdefault(ext, [])
            bucket.append(importer)
            # 優先度の高い順に並べ替える(同点は登録順を保つ安定ソート)
            bucket.sort(key=lambda imp: -imp.priority)

    def get_importer_for_extension(self, extension):
        """
        指定した拡張子に対して最も優先度の高い登録済みインポーターを返す
        (登録が無ければNone)。

        Args:
            extension (str): 先頭ピリオドの有無・大文字小文字を問わない。
        """
        bucket = self._importers.get(_normalize_extension(extension))
        return bucket[0] if bucket else None

    def get_importer_extensions(self):
        """登録済みインポーターが対応する拡張子の一覧(重複無し、ソート済み)。"""
        return sorted(self._importers.keys())

    def register_exporter(self, format_name, extension, writer, *, name=None):
        """
        プロットのエクスポート形式に、プラグイン提供の書き出し処理を追加する
        (項目B-2)。バッチエクスポートの「形式」コンボボックス・単発エクスポートの
        保存ダイアログの両方から選べるようになる。

        Args:
            format_name (str): エクスポート形式の選択肢に表示される名前
                (例: "MyFormat")。BatchExportDialogの形式コンボの選択値として
                そのまま使われる。
            extension (str): 出力ファイルの拡張子(先頭ピリオドは省略可)。
            writer (callable): (matplotlib.figure.Figure, 出力パス:str) を受け取り、
                ファイルへの書き出しを行う関数。戻り値は使われない。
            name (str | None): エラーメッセージ等に表示する名前
                (省略時は登録元のプラグイン名)。
        """
        return self._safe_register(
            PluginHookKind.EXPORTER, self._do_register_exporter, format_name, extension, writer,
            name=name or self._current_plugin_name,
        )

    def _do_register_exporter(self, format_name, extension, writer, *, name):
        self._exporters[format_name.lower()] = PluginExporter(
            format_name=format_name, extension=_normalize_extension(extension), writer=writer, name=name
        )

    def get_exporter(self, format_name):
        """指定した形式名(大文字小文字を問わない)に対応する登録済みエクスポーターを返す。"""
        return self._exporters.get(format_name.lower())

    def get_exporter_for_extension(self, extension):
        """指定した拡張子に対応する登録済みエクスポーターを返す(無ければNone)。"""
        ext = _normalize_extension(extension)
        for exporter in self._exporters.values():
            if exporter.extension == ext:
                return exporter
        return None

    def get_exporters(self):
        """登録済みエクスポーターの一覧。"""
        return list(self._exporters.values())

    @property
    def menu_actions(self):
        return list(self._menu_actions)

    @property
    def registration_errors(self):
        """このプロセスで発生した、フック単位の登録失敗の一覧。"""
        return list(self._registration_errors)


class PluginManager:
    """
    plugins/ ディレクトリ配下のプラグインを検出・読み込み・登録するマネージャー。
    """

    def __init__(self, plugins_dir):
        self.plugins_dir = plugins_dir
        # 読み込み結果の記録: 各要素は
        # {"name": フォルダ名, "info": PLUGIN_INFO or None, "error": str or None}
        self.loaded_plugins = []

    def discover_plugin_dirs(self):
        """plugins_dir 配下の、__init__.py を持つサブディレクトリ名の一覧を返す"""
        if not os.path.isdir(self.plugins_dir):
            return []
        names = []
        for entry in sorted(os.listdir(self.plugins_dir)):
            entry_path = os.path.join(self.plugins_dir, entry)
            if os.path.isdir(entry_path) and os.path.exists(os.path.join(entry_path, "__init__.py")):
                names.append(entry)
        return names

    def _load_module(self, plugin_name):
        """1つのプラグインパッケージを importlib で読み込み、モジュールオブジェクトを返す"""
        init_path = os.path.join(self.plugins_dir, plugin_name, "__init__.py")
        module_name = f"graphica_plugin_{plugin_name}"
        spec = importlib.util.spec_from_file_location(
            module_name, init_path,
            submodule_search_locations=[os.path.join(self.plugins_dir, plugin_name)],
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

    def load_all(self, api):
        """
        plugins_dir 配下の全プラグインを読み込み、register(api) を呼び出す。
        1つのプラグインで例外が発生しても、他のプラグインの読み込みは継続する。
        """
        self.loaded_plugins = []
        for plugin_name in self.discover_plugin_dirs():
            record = {"name": plugin_name, "info": None, "error": None}
            try:
                module = self._load_module(plugin_name)

                info = getattr(module, PLUGIN_MANIFEST_ATTR, None)
                if not isinstance(info, dict):
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' に {PLUGIN_MANIFEST_ATTR} (dict) がありません。"
                    )
                record["info"] = info

                register_func = getattr(module, PLUGIN_REGISTER_FUNC, None)
                if not callable(register_func):
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' に {PLUGIN_REGISTER_FUNC}(api) 関数がありません。"
                    )
                # register_xxx呼び出し自身はどのプラグインが呼んでいるか知らないため、
                # ここで現在実行中のプラグイン名をapiに伝える(_safe_register参照)。
                api._current_plugin_name = plugin_name
                register_func(api)

            except Exception as e:
                record["error"] = str(e)
                logger.warning("プラグイン '%s' の読み込みに失敗しました: %s", plugin_name, e)

            self.loaded_plugins.append(record)

        return self.loaded_plugins


# ★ フィット関数のレジストリ (core/analysis.py の _PLUGIN_FIT_FUNCTIONS) は
# プロセス全体で1つのモジュールレベル辞書であり、複数プロジェクトタブ(項目40)
# では PlotterApp インスタンスがタブごとに作られるため、タブが増えるたびに
# 同じプラグインを読み込むと「既に登録されています」エラーになってしまう。
# そのためプラグインの読み込み・登録はプロセス全体で1度だけ行い、以降の呼び出しは
# 同じ GraphicaPluginAPI インスタンス(と、そのmenu_actions)を使い回す。
_singleton_api = None
_singleton_manager = None


def load_plugins_once(plugins_dir):
    """
    plugins_dir 配下のプラグインを、プロセス内で最初の呼び出し時にのみ読み込む。
    2回目以降の呼び出しは、キャッシュされた GraphicaPluginAPI をそのまま返す
    (新しいタブが開かれるたびに再読み込み・再登録が走らないようにするため)。
    """
    global _singleton_api, _singleton_manager
    if _singleton_api is not None:
        return _singleton_api

    os.makedirs(plugins_dir, exist_ok=True)
    _singleton_api = GraphicaPluginAPI()
    _singleton_manager = PluginManager(plugins_dir)
    _singleton_manager.load_all(_singleton_api)
    return _singleton_api


def get_loaded_plugin_records():
    """最後に load_plugins_once() で読み込まれたプラグインの一覧を返す(未読み込みならNone)"""
    return None if _singleton_manager is None else list(_singleton_manager.loaded_plugins)


def get_plugin_registration_errors():
    """
    フック単位の登録失敗の一覧を返す(未読み込みならNone、フェーズA-2)。
    プラグイン全体としては読み込みに成功していても、個別のregister_xxx呼び出しが
    失敗している場合はここに記録される(get_loaded_plugin_recordsのerrorには現れない)。
    """
    return None if _singleton_api is None else _singleton_api.registration_errors


def get_plugin_api():
    """
    現在ロード済みの GraphicaPluginAPI を返す(未読み込みなら None)。
    plugins_dir を知らない呼び出し元(gui/workers.py 等、UIから離れた場所)向けの
    アクセサ。load_plugins_once() と異なり、未読み込みでも新規ロードは行わない。
    """
    return _singleton_api


def get_registered_importer_extensions():
    """登録済みインポーターが対応する拡張子の一覧(未読み込みなら空リスト、項目B-1)。"""
    return _singleton_api.get_importer_extensions() if _singleton_api is not None else []


def get_registered_exporters():
    """登録済みエクスポーターの一覧(未読み込みなら空リスト、項目B-2)。"""
    return _singleton_api.get_exporters() if _singleton_api is not None else []
