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
  アクション追加」の2つ。今後、列計算・エクスポート形式なども同様の
  パターン(register_xxx メソッドを追加する)で拡張できる。
"""
import importlib
import importlib.util
import logging
import os
import sys

from core.analysis import register_fit_function

logger = logging.getLogger(__name__)

PLUGIN_MANIFEST_ATTR = "PLUGIN_INFO"
PLUGIN_REGISTER_FUNC = "register"


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
        register_fit_function(name, func, param_names, p0=p0)

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
        self._menu_actions.append((text, callback, shortcut))

    @property
    def menu_actions(self):
        return list(self._menu_actions)


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
